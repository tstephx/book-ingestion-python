#!/usr/bin/env python3
"""
Reprocess Problematic Books Script

Identifies and fixes books with quality issues:
- Merges over-fragmented chapters
- Regenerates chapter boundaries
- Updates database with fixed content

Usage:
    python scripts/reprocess_problematic.py --list       # List books needing fixes
    python scripts/reprocess_problematic.py --fix-all    # Fix all problematic books
    python scripts/reprocess_problematic.py --book-id <uuid>  # Fix single book
    python scripts/reprocess_problematic.py --dry-run    # Preview changes
"""

import argparse
import sqlite3
import sys
import statistics
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from copy import deepcopy

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm

from src.processors.chunk_merger import ChapterMerger, MergeResult
from src.processors.semantic_chunker import validate_chunking

console = Console()


class BookReprocessor:
    """Reprocesses books with quality issues"""
    
    # Quality thresholds
    MIN_AVG_WORDS = 2000
    MAX_CHAPTER_COUNT = 40
    MIN_QUALITY_SCORE = 60
    
    def __init__(self, db_path: str, output_dir: str = None):
        self.db_path = db_path
        self.output_dir = Path(output_dir) if output_dir else Path("./data/books")
        self.merger = ChapterMerger()
    
    def get_problematic_books(self) -> List[Dict]:
        """Get books that need reprocessing"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get all books with chapter stats
        cursor.execute("""
            SELECT 
                b.id,
                b.title,
                b.author,
                b.source_file,
                COUNT(c.id) as chapter_count,
                SUM(c.word_count) as total_words,
                AVG(c.word_count) as avg_words
            FROM books b
            LEFT JOIN chapters c ON b.id = c.book_id
            GROUP BY b.id
            HAVING chapter_count > 0
            ORDER BY avg_words ASC
        """)
        
        books = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        # Filter to problematic ones
        problematic = []
        for book in books:
            issues = self._check_book_issues(book)
            if issues:
                book['issues'] = issues
                problematic.append(book)
        
        return problematic
    
    def _check_book_issues(self, book: Dict) -> List[str]:
        """Check what issues a book has"""
        issues = []
        
        avg_words = book.get('avg_words', 0) or 0
        chapter_count = book.get('chapter_count', 0) or 0
        total_words = book.get('total_words', 0) or 0
        
        # Over-fragmentation
        if avg_words < self.MIN_AVG_WORDS:
            issues.append(f"Over-fragmented (avg {avg_words:.0f} words)")
        
        # Too many chapters
        if chapter_count > self.MAX_CHAPTER_COUNT and avg_words < 5000:
            issues.append(f"Too many chapters ({chapter_count})")
        
        # Expected vs actual chapter count
        if total_words > 0:
            expected = max(3, total_words // 10000)
            if chapter_count > expected * 3:
                issues.append(f"3x expected chapters ({chapter_count} vs ~{expected})")
        
        return issues
    
    def get_book_chapters(self, book_id: str) -> List[Dict]:
        """Get all chapters for a book"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, book_id, chapter_number, title, content, word_count, file_path
            FROM chapters
            WHERE book_id = ?
            ORDER BY chapter_number
        """, (book_id,))
        
        chapters = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return chapters
    
    def preview_merge(self, book_id: str) -> Optional[MergeResult]:
        """Preview what merges would be performed"""
        chapters = self.get_book_chapters(book_id)
        
        if not chapters:
            return None
        
        # Use auto-merge to determine optimal merges
        result = self.merger.auto_merge(chapters)
        
        return result
    
    def apply_merges(
        self,
        book_id: str,
        merge_result: MergeResult,
        backup: bool = True
    ) -> bool:
        """Apply merges to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            if backup:
                # Create backup of original chapters
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS chapters_backup (
                        id TEXT,
                        book_id TEXT,
                        chapter_number INTEGER,
                        title TEXT,
                        content TEXT,
                        word_count INTEGER,
                        file_path TEXT,
                        backup_date TEXT
                    )
                """)
                
                cursor.execute("""
                    INSERT INTO chapters_backup
                    SELECT id, book_id, chapter_number, title, content, word_count, 
                           file_path, ?
                    FROM chapters
                    WHERE book_id = ?
                """, (datetime.now().isoformat(), book_id))
            
            # Delete old chapters
            cursor.execute("DELETE FROM chapters WHERE book_id = ?", (book_id,))
            
            # Insert merged chapters
            for chapter in merge_result.chapters:
                cursor.execute("""
                    INSERT INTO chapters (id, book_id, chapter_number, title, 
                                         content, word_count, file_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    chapter['id'],
                    chapter['book_id'],
                    chapter['chapter_number'],
                    chapter['title'],
                    chapter['content'],
                    chapter['word_count'],
                    chapter.get('file_path', '')
                ))
            
            # Update book record
            cursor.execute("""
                UPDATE books 
                SET processing_status = 'reprocessed',
                    word_count = ?
                WHERE id = ?
            """, (
                sum(c['word_count'] for c in merge_result.chapters),
                book_id
            ))
            
            conn.commit()
            return True
            
        except Exception as e:
            conn.rollback()
            console.print(f"[red]Error applying merges: {e}[/red]")
            return False
        finally:
            conn.close()
    
    def update_chapter_files(
        self,
        book_id: str,
        chapters: List[Dict]
    ) -> bool:
        """Update chapter markdown files on disk"""
        book_dir = self.output_dir / book_id
        
        if not book_dir.exists():
            console.print(f"[yellow]Book directory not found: {book_dir}[/yellow]")
            return False
        
        try:
            # Remove old chapter files
            for f in book_dir.glob("*.md"):
                if f.name != "metadata.json":
                    f.unlink()
            
            # Write new chapter files
            for chapter in chapters:
                # Create filename
                num = chapter['chapter_number']
                title_slug = "".join(
                    c if c.isalnum() or c == ' ' else ''
                    for c in chapter.get('title', f'chapter-{num}')
                )[:50].strip().replace(' ', '-').lower()
                
                filename = f"{num:02d}-{title_slug}.md"
                filepath = book_dir / filename
                
                # Write content with frontmatter
                content = f"""---
title: "{chapter.get('title', '')}"
chapter: {num}
tokens: {int(chapter['word_count'] * 1.33)}
words: {chapter['word_count']}
---

# {chapter.get('title', f'Chapter {num}')}

**Chapter {num}** | *{chapter['word_count']:,} words*

---

{chapter['content']}
"""
                filepath.write_text(content, encoding='utf-8')
                
                # Update chapter record with new path
                chapter['file_path'] = str(filepath)
            
            return True
            
        except Exception as e:
            console.print(f"[red]Error updating files: {e}[/red]")
            return False
    
    def fix_book(
        self,
        book_id: str,
        dry_run: bool = False,
        update_files: bool = True
    ) -> Tuple[bool, MergeResult]:
        """Fix a single book's chapter fragmentation"""
        chapters = self.get_book_chapters(book_id)
        
        if not chapters:
            console.print(f"[red]No chapters found for book: {book_id}[/red]")
            return False, None
        
        # Calculate current stats
        word_counts = [c['word_count'] for c in chapters]
        current_avg = statistics.mean(word_counts)
        
        # Perform merge analysis
        result = self.merger.auto_merge(chapters)
        
        if result.merges_performed == 0:
            console.print("[yellow]No merges needed[/yellow]")
            return True, result
        
        # Show what would happen
        new_avg = statistics.mean([c['word_count'] for c in result.chapters])
        
        console.print(f"\n[bold]Merge Preview[/bold]")
        console.print(f"  Original: {len(chapters)} chapters, avg {current_avg:.0f} words")
        console.print(f"  After:    {len(result.chapters)} chapters, avg {new_avg:.0f} words")
        console.print(f"  Merges:   {result.merges_performed}")
        
        if dry_run:
            console.print("\n[yellow]Dry run - no changes made[/yellow]")
            return True, result
        
        # Apply changes
        success = self.apply_merges(book_id, result)
        
        if success and update_files:
            self.update_chapter_files(book_id, result.chapters)
        
        return success, result
    
    def fix_all(
        self,
        dry_run: bool = False,
        confirm: bool = True
    ) -> Dict:
        """Fix all problematic books"""
        problematic = self.get_problematic_books()
        
        if not problematic:
            console.print("[green]No problematic books found![/green]")
            return {"fixed": 0, "failed": 0, "skipped": 0}
        
        console.print(f"\n[bold]Found {len(problematic)} books needing fixes[/bold]\n")
        
        # Show summary
        table = Table(show_header=True, header_style="bold")
        table.add_column("Title", max_width=40)
        table.add_column("Chapters", justify="right")
        table.add_column("Avg Words", justify="right")
        table.add_column("Issues")
        
        for book in problematic[:10]:
            issues = ", ".join(book.get('issues', []))[:40]
            table.add_row(
                book['title'][:40],
                str(int(book['chapter_count'])),
                f"{book['avg_words']:.0f}",
                issues
            )
        
        if len(problematic) > 10:
            table.add_row("...", "...", "...", f"+ {len(problematic) - 10} more")
        
        console.print(table)
        
        if confirm and not dry_run:
            if not Confirm.ask("\nProceed with fixes?"):
                return {"fixed": 0, "failed": 0, "skipped": len(problematic)}
        
        # Process each book
        results = {"fixed": 0, "failed": 0, "skipped": 0}
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Fixing books...", total=len(problematic))
            
            for book in problematic:
                progress.update(task, description=f"Fixing: {book['title'][:30]}...")
                
                try:
                    success, _ = self.fix_book(
                        book['id'],
                        dry_run=dry_run,
                        update_files=True
                    )
                    
                    if success:
                        results["fixed"] += 1
                    else:
                        results["failed"] += 1
                        
                except Exception as e:
                    console.print(f"[red]Error fixing {book['title']}: {e}[/red]")
                    results["failed"] += 1
                
                progress.update(task, advance=1)
        
        return results


def main():
    parser = argparse.ArgumentParser(
        description="Reprocess books with quality issues"
    )
    parser.add_argument(
        "--db", "-d",
        default="./data/library.db",
        help="Path to library database"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="./data/books",
        help="Path to books output directory"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List problematic books without fixing"
    )
    parser.add_argument(
        "--fix-all", "-a",
        action="store_true",
        help="Fix all problematic books"
    )
    parser.add_argument(
        "--book-id", "-b",
        help="Fix single book by ID"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview changes without applying"
    )
    parser.add_argument(
        "--no-confirm",
        action="store_true",
        help="Skip confirmation prompts"
    )
    parser.add_argument(
        "--no-files",
        action="store_true",
        help="Don't update chapter files on disk"
    )
    
    args = parser.parse_args()
    
    # Check database exists
    db_path = Path(args.db)
    if not db_path.exists():
        console.print(f"[red]Error: Database not found: {db_path}[/red]")
        sys.exit(1)
    
    reprocessor = BookReprocessor(
        str(db_path),
        output_dir=args.output_dir
    )
    
    if args.list:
        # List mode
        problematic = reprocessor.get_problematic_books()
        
        if not problematic:
            console.print("[green]No problematic books found![/green]")
            sys.exit(0)
        
        console.print(f"\n[bold]Problematic Books ({len(problematic)})[/bold]\n")
        
        table = Table(show_header=True, header_style="bold")
        table.add_column("ID", max_width=10)
        table.add_column("Title", max_width=35)
        table.add_column("Chapters", justify="right")
        table.add_column("Avg Words", justify="right")
        table.add_column("Issues", max_width=40)
        
        for book in problematic:
            issues = ", ".join(book.get('issues', []))
            table.add_row(
                book['id'][:8] + "...",
                book['title'][:35],
                str(int(book['chapter_count'])),
                f"{book['avg_words']:.0f}",
                issues[:40]
            )
        
        console.print(table)
        
        console.print(f"\n[bold]Run with --fix-all to fix these books[/bold]")
        
    elif args.book_id:
        # Single book mode
        console.print(f"\n[bold]Fixing book: {args.book_id}[/bold]\n")
        
        success, result = reprocessor.fix_book(
            args.book_id,
            dry_run=args.dry_run,
            update_files=not args.no_files
        )
        
        if success:
            if args.dry_run:
                console.print("\n[yellow]Dry run complete - no changes made[/yellow]")
            else:
                console.print("\n[green]✅ Book fixed successfully[/green]")
        else:
            console.print("\n[red]❌ Failed to fix book[/red]")
            sys.exit(1)
            
    elif args.fix_all:
        # Fix all mode
        console.print("\n[bold]Fixing All Problematic Books[/bold]\n")
        
        results = reprocessor.fix_all(
            dry_run=args.dry_run,
            confirm=not args.no_confirm
        )
        
        console.print(f"\n[bold]Results:[/bold]")
        console.print(f"  ✅ Fixed: {results['fixed']}")
        console.print(f"  ❌ Failed: {results['failed']}")
        console.print(f"  ⏭️ Skipped: {results['skipped']}")
        
        if results['failed'] > 0:
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
