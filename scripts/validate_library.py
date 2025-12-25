#!/usr/bin/env python3
"""
Library Validation Script

Analyzes all books in the library for quality issues and generates
a comprehensive report with recommendations.

Usage:
    python scripts/validate_library.py
    python scripts/validate_library.py --output report.md
    python scripts/validate_library.py --fix-undersized
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple
import statistics

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.config import Config
from src.storage.database import BookDatabase
from src.processors.semantic_chunker import validate_chunking, ChapterBoundaryValidator
from src.processors.profiler import DataProfiler, BookProfile, QualityReport
from src.processors.chunk_merger import ChapterMerger


def load_library() -> Tuple[List[Dict], List[List[Dict]]]:
    """Load all books and their chapters from the database"""
    config = Config()
    db = BookDatabase(config.database_path)
    
    books = db.get_all_books()
    all_chapters = []
    
    for book in books:
        chapters = db.get_chapters_by_book(book['id'])
        all_chapters.append(chapters)
    
    return books, all_chapters


def analyze_book(book: Dict, chapters: List[Dict]) -> Dict:
    """Analyze a single book for quality issues"""
    profiler = DataProfiler()
    
    # Get profile and quality assessment
    profile = profiler.profile_book(book, chapters)
    quality = profiler.assess_quality(profile)
    
    # Quick validation check
    quick_check = validate_chunking(chapters)
    
    # Merge analysis
    merger = ChapterMerger()
    should_merge = merger.should_merge_chapters(chapters)
    
    merge_candidates = []
    if should_merge:
        merge_candidates = merger.find_merge_candidates(chapters)
    
    return {
        'book': book,
        'profile': profile,
        'quality': quality,
        'quick_check': quick_check,
        'should_merge': should_merge,
        'merge_candidates': merge_candidates[:5],  # Top 5 only
    }


def generate_report(analyses: List[Dict]) -> str:
    """Generate a markdown report from analyses"""
    lines = [
        "# Library Quality Validation Report",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Executive Summary",
        "",
    ]
    
    # Calculate summary stats
    total_books = len(analyses)
    total_chapters = sum(a['profile'].total_chapters for a in analyses)
    total_words = sum(a['profile'].total_words for a in analyses)
    
    good_books = sum(1 for a in analyses if a['quality'].quality_score >= 75)
    fair_books = sum(1 for a in analyses if 50 <= a['quality'].quality_score < 75)
    poor_books = sum(1 for a in analyses if a['quality'].quality_score < 50)
    
    needs_merge = sum(1 for a in analyses if a['should_merge'])
    has_issues = sum(1 for a in analyses if not a['quick_check']['valid'])
    
    avg_score = statistics.mean(a['quality'].quality_score for a in analyses)
    
    lines.extend([
        f"- **Total Books:** {total_books}",
        f"- **Total Chapters:** {total_chapters}",
        f"- **Total Words:** {total_words:,}",
        f"- **Average Quality Score:** {avg_score:.1f}/100",
        "",
        "### Quality Distribution",
        "",
        f"- 🟢 Good (≥75): {good_books} books ({good_books/total_books*100:.1f}%)",
        f"- 🟡 Fair (50-74): {fair_books} books ({fair_books/total_books*100:.1f}%)",
        f"- 🔴 Poor (<50): {poor_books} books ({poor_books/total_books*100:.1f}%)",
        "",
        "### Issues Summary",
        "",
        f"- Books needing merge: {needs_merge}",
        f"- Books with validation issues: {has_issues}",
        "",
    ])
    
    # Books needing attention
    problem_books = [a for a in analyses 
                    if not a['quick_check']['valid'] or a['quality'].quality_score < 75]
    
    if problem_books:
        lines.extend([
            "## ⚠️ Books Needing Attention",
            "",
        ])
        
        for analysis in sorted(problem_books, key=lambda x: x['quality'].quality_score):
            book = analysis['book']
            profile = analysis['profile']
            quality = analysis['quality']
            quick = analysis['quick_check']
            
            lines.extend([
                f"### {book.get('title', 'Unknown')[:60]}",
                "",
                f"- **ID:** `{book['id'][:8]}...`",
                f"- **Score:** {quality.quality_score}/100",
                f"- **Chapters:** {profile.total_chapters}",
                f"- **Avg Chapter:** {profile.avg_chapter_words:,.0f} words",
                "",
            ])
            
            if not quick['valid']:
                lines.append(f"- **Issue:** {quick['issue']} - {quick.get('message', '')}")
            
            if quality.warnings:
                lines.append("- **Warnings:**")
                for warning in quality.warnings[:3]:
                    lines.append(f"  - {warning}")
            
            if analysis['should_merge']:
                lines.append(f"- **Merge candidates:** {len(analysis['merge_candidates'])}")
            
            lines.append("")
    
    # All books table
    lines.extend([
        "## Complete Book List",
        "",
        "| Title | Chapters | Words | Avg Ch | Score | Status |",
        "|-------|----------|-------|--------|-------|--------|",
    ])
    
    for analysis in sorted(analyses, key=lambda x: x['quality'].quality_score, reverse=True):
        book = analysis['book']
        profile = analysis['profile']
        quality = analysis['quality']
        quick = analysis['quick_check']
        
        title = book.get('title', 'Unknown')[:35]
        if len(book.get('title', '')) > 35:
            title += "..."
        
        if quality.quality_score >= 75:
            status = "🟢"
        elif quality.quality_score >= 50:
            status = "🟡"
        else:
            status = "🔴"
        
        if not quick['valid']:
            status += f" {quick['issue']}"
        
        lines.append(
            f"| {title} | {profile.total_chapters} | {profile.total_words:,} | "
            f"{profile.avg_chapter_words:,.0f} | {quality.quality_score} | {status} |"
        )
    
    # Recommendations
    lines.extend([
        "",
        "## Recommendations",
        "",
    ])
    
    if needs_merge > 0:
        lines.extend([
            f"### 1. Merge Over-Fragmented Chapters ({needs_merge} books)",
            "",
            "Run merge on these books to improve chapter quality:",
            "```bash",
        ])
        for analysis in analyses:
            if analysis['should_merge']:
                lines.append(f"python -m src.cli merge-chapters {analysis['book']['id'][:8]}...")
        lines.extend([
            "```",
            "",
        ])
    
    if has_issues > 0:
        lines.extend([
            f"### 2. Review Validation Issues ({has_issues} books)",
            "",
            "These books have structural issues that may require reprocessing:",
            "",
        ])
        for analysis in analyses:
            if not analysis['quick_check']['valid']:
                book = analysis['book']
                issue = analysis['quick_check']['issue']
                lines.append(f"- `{book['id'][:8]}...`: {issue}")
        lines.append("")
    
    if poor_books > 0:
        lines.extend([
            f"### 3. Consider Reprocessing Poor Quality Books ({poor_books} books)",
            "",
            "Books with quality score below 50 may benefit from reprocessing with updated patterns.",
            "",
        ])
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Validate library quality and generate report"
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        help='Output file for report (default: stdout)'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output in JSON format'
    )
    parser.add_argument(
        '--fix-undersized',
        action='store_true',
        help='Automatically merge undersized chapters'
    )
    parser.add_argument(
        '--min-score',
        type=int,
        default=0,
        help='Only show books below this score'
    )
    
    args = parser.parse_args()
    
    print("Loading library...", file=sys.stderr)
    books, all_chapters = load_library()
    
    if not books:
        print("No books found in library.", file=sys.stderr)
        sys.exit(1)
    
    print(f"Analyzing {len(books)} books...", file=sys.stderr)
    
    analyses = []
    for i, (book, chapters) in enumerate(zip(books, all_chapters)):
        print(f"  [{i+1}/{len(books)}] {book.get('title', 'Unknown')[:40]}...", 
              file=sys.stderr, end='\r')
        analysis = analyze_book(book, chapters)
        analyses.append(analysis)
    
    print(f"\n✓ Analysis complete for {len(analyses)} books", file=sys.stderr)
    
    # Filter by min score if specified
    if args.min_score > 0:
        analyses = [a for a in analyses if a['quality'].quality_score < args.min_score]
        print(f"  Filtered to {len(analyses)} books below score {args.min_score}",
              file=sys.stderr)
    
    # Generate output
    if args.json:
        import json
        output = json.dumps([{
            'id': a['book']['id'],
            'title': a['book'].get('title'),
            'score': a['quality'].quality_score,
            'chapters': a['profile'].total_chapters,
            'avg_words': a['profile'].avg_chapter_words,
            'valid': a['quick_check']['valid'],
            'issue': a['quick_check'].get('issue'),
        } for a in analyses], indent=2)
    else:
        output = generate_report(analyses)
    
    if args.output:
        Path(args.output).write_text(output)
        print(f"Report saved to: {args.output}", file=sys.stderr)
    else:
        print(output)
    
    # Summary stats
    good = sum(1 for a in analyses if a['quality'].quality_score >= 75)
    print(f"\nSummary: {good}/{len(analyses)} books with good quality (≥75)", 
          file=sys.stderr)


if __name__ == '__main__':
    main()
