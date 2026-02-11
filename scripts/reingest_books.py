#!/usr/bin/env python3
"""
Re-ingest books with improved chapter detection.

Uses the EnhancedPipeline (with merge guards and degenerate detection fallback)
to re-process books that have broken or poor chapter splitting.

Usage:
    # Preview what would change (dry run)
    python scripts/reingest_books.py --book-id <uuid>

    # Preview all critical books (empty/broken)
    python scripts/reingest_books.py --critical

    # Apply changes
    python scripts/reingest_books.py --book-id <uuid> --apply

    # Apply all critical
    python scripts/reingest_books.py --critical --apply
"""

import argparse
import os
import sqlite3
import sys
import uuid
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from book_ingestion.converters.pdf_converter import PDFConverter
from book_ingestion.converters.epub_converter import EPUBConverter
from book_ingestion.processors.enhanced_pipeline import EnhancedPipeline, ProcessingMode
from book_ingestion.utils.config import Config

# Library DB path (shared with book-mcp-server)
DB_PATH = os.environ.get(
    "AGENTIC_PIPELINE_DB",
    os.path.expanduser("~/_Projects/book-ingestion-python/data/library.db"),
)

# Tier 1: Critically broken (empty or near-empty content)
CRITICAL_BOOK_IDS = [
    "0f35c133-0976-4e28-b2e8-ff699a9a5576",  # Designing Experiences (32 words)
    "327f0f91-a573-4d5a-bbb1-1a269100e90d",  # TAOCP Vol 4B (14 words)
    "4a8c598a-2d7d-4e32-9f43-46a2dff0caff",  # William Ellet (407 words)
]

# Tier 2: Would significantly improve (single giant chapter or few huge chapters)
SHOULD_REINGEST_IDS = [
    "9516b6ed-1c9f-47ac-b003-7caeb57ba07e",  # What Makes Love Last (3 ch → 13)
    "e20baf98-ac14-4463-b350-9d016bde9b24",  # Git Mastery (1 ch, 20K words)
    "a49a8ef9-c5d2-4870-a551-45526ffac221",  # How to Draw (1 ch, 33K words)
    "2ea0b4ad-3936-4510-9133-50c790f48224",  # TAOCP Vol 4A (1 ch, 24K words)
    "dbd8cbc6-7cb5-4786-b45a-bb518e369e6b",  # DevOps Handbook (2 ch, 15K avg)
]

# All IDs for --all flag
ALL_REINGEST_IDS = CRITICAL_BOOK_IDS + SHOULD_REINGEST_IDS


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_book_info(conn, book_id):
    """Get book info and current chapters."""
    book = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    if not book:
        return None, []

    chapters = conn.execute(
        "SELECT id, chapter_number, title, word_count FROM chapters "
        "WHERE book_id = ? ORDER BY chapter_number",
        (book_id,),
    ).fetchall()

    return dict(book), [dict(c) for c in chapters]


def convert_file(source_path):
    """Convert source file to text."""
    ext = Path(source_path).suffix.lower()
    if ext == ".pdf":
        converter = PDFConverter()
    elif ext == ".epub":
        converter = EPUBConverter()
    else:
        return None, None, f"Unsupported format: {ext}"

    result = converter.convert(source_path)
    if not result.get("success"):
        return None, None, result.get("error", "Conversion failed")

    return result["text"], result.get("toc_titles", []), None


def detect_chapters(text, book_id, toc_titles):
    """Run enhanced pipeline to detect chapters."""
    pipeline = EnhancedPipeline(mode=ProcessingMode.STANDARD)
    result = pipeline.process_book(
        text,
        book_id,
        external_toc_titles=toc_titles,
    )
    return result


def print_comparison(book, old_chapters, new_chapters, pipeline_result):
    """Print side-by-side comparison of old vs new chapters."""
    print(f"\n{'='*70}")
    print(f"  {book['title']}")
    print(f"  Source: {book['source_file']}")
    print(f"{'='*70}")

    old_total = sum(c["word_count"] for c in old_chapters)
    new_total = sum(c.get("word_count", 0) for c in new_chapters)

    print(f"\n  Detection method: {pipeline_result.detection_method}")
    print(f"  Detection confidence: {pipeline_result.detection_confidence:.0%}")
    print(f"  Quality score: {pipeline_result.quality_report.quality_score}/100")

    print(f"\n  {'CURRENT':^35} {'NEW':^35}")
    print(f"  {'-'*35} {'-'*35}")
    print(f"  {'Chapters:':<15} {len(old_chapters):>5}          {'Chapters:':<15} {len(new_chapters):>5}")
    print(f"  {'Total words:':<15} {old_total:>10,}     {'Total words:':<15} {new_total:>10,}")

    old_avg = old_total / len(old_chapters) if old_chapters else 0
    new_avg = new_total / len(new_chapters) if new_chapters else 0
    print(f"  {'Avg words:':<15} {old_avg:>10,.0f}     {'Avg words:':<15} {new_avg:>10,.0f}")

    # Determine if this is an improvement
    improvements = []
    regressions = []

    if old_total < 1000 and new_total > 1000:
        improvements.append(f"Content recovered: {old_total} → {new_total:,} words")
    elif new_total < old_total * 0.5:
        regressions.append(f"Content LOST: {old_total:,} → {new_total:,} words")

    if len(old_chapters) == 1 and len(new_chapters) > 1:
        improvements.append(f"Chapters split: 1 → {len(new_chapters)}")

    if old_avg > 15000 and new_avg < 10000:
        improvements.append(f"Avg size reduced: {old_avg:,.0f} → {new_avg:,.0f}")
    elif old_avg < 10000 and new_avg > 15000:
        regressions.append(f"Avg size increased: {old_avg:,.0f} → {new_avg:,.0f}")

    # Check if we lost real chapter titles (only counts as regression if
    # the old chapters actually had meaningful content AND multiple chapters)
    old_has_names = any(
        not c["title"].startswith("Section ") and not c["title"].startswith("Chapter ")
        for c in old_chapters
    )
    new_all_generic = all(
        c.get("title", "").startswith("Section ") for c in new_chapters
    )
    if old_has_names and new_all_generic and old_total <= 1000:
        improvements.append("Named chapters had no content; generic sections have full text")
    elif old_has_names and new_all_generic and len(old_chapters) == 1:
        # Single chapter with a name → splitting is still better for search
        pass  # don't count as regression
    elif old_has_names and new_all_generic and len(old_chapters) > 1 and old_total > 1000:
        regressions.append("Lost named chapters → generic 'Section N'")

    print()
    if improvements:
        for imp in improvements:
            print(f"  [+] {imp}")
    if regressions:
        for reg in regressions:
            print(f"  [-] {reg}")
    if not improvements and not regressions:
        print("  [=] No significant change")

    # Show new chapter list
    print(f"\n  New chapters:")
    for ch in new_chapters[:20]:
        title = ch.get("title", "Unknown")[:45]
        words = ch.get("word_count", 0)
        print(f"    {ch.get('chapter_number', '?'):>3}. {title:<45} {words:>8,} words")
    if len(new_chapters) > 20:
        print(f"    ... and {len(new_chapters) - 20} more")

    # Content recovery always wins — a book with content is better than
    # a book with nice names but no text
    has_content_recovery = any("Content recovered" in i for i in improvements)
    is_improvement = bool(improvements) and (not bool(regressions) or has_content_recovery)
    return is_improvement


def write_chapter_files(book_id, book_title, new_chapters):
    """Write chapter markdown files to disk for the MCP server."""
    config = Config()
    output_dir = Path(config.output_dir)
    book_dir = output_dir / book_id
    chapters_dir = book_dir / "chapters"

    # Clean up old chapter files if they exist
    if chapters_dir.exists():
        import shutil
        shutil.rmtree(chapters_dir)

    chapters_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "raw").mkdir(parents=True, exist_ok=True)

    for ch in new_chapters:
        title = ch.get("title", f"Section {ch['chapter_number']}")
        # Sanitize filename
        safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in title)
        safe_title = safe_title.strip()[:50] or f"section-{ch['chapter_number']}"
        filename = f"{ch['chapter_number']:02d}-{safe_title}.md"
        chapter_path = chapters_dir / filename

        with open(chapter_path, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n")
            f.write(f"**Chapter {ch['chapter_number']}**\n")
            f.write(f"*Word Count: {ch.get('word_count', 0)}*\n\n")
            f.write("---\n\n")
            f.write(ch.get("content", ""))

        ch["file_path"] = str(chapter_path)

    return str(chapters_dir)


def apply_reingest(conn, book_id, book_title, new_chapters):
    """Replace old chapters with new ones in the database and write files."""
    # Write chapter files first
    files_dir = write_chapter_files(book_id, book_title, new_chapters)

    cursor = conn.cursor()

    # Delete old chapters (embeddings will be regenerated by book-mcp-server)
    cursor.execute("DELETE FROM chapters WHERE book_id = ?", (book_id,))
    old_count = cursor.rowcount

    # Insert new chapters (now with file_path populated from write_chapter_files)
    for ch in new_chapters:
        ch_id = f"{book_id}-ch{ch['chapter_number']}"
        cursor.execute(
            "INSERT INTO chapters (id, book_id, chapter_number, title, file_path, word_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                ch_id,
                book_id,
                ch["chapter_number"],
                ch.get("title", f"Section {ch['chapter_number']}"),
                ch.get("file_path", ""),
                ch.get("word_count", 0),
            ),
        )

    # Update book word count
    total_words = sum(c.get("word_count", 0) for c in new_chapters)
    cursor.execute(
        "UPDATE books SET word_count = ? WHERE id = ?",
        (total_words, book_id),
    )

    conn.commit()
    return old_count


def main():
    parser = argparse.ArgumentParser(description="Re-ingest books with improved chapter detection")
    parser.add_argument("--book-id", help="Specific book UUID to re-ingest")
    parser.add_argument("--critical", action="store_true", help="Re-ingest all critically broken books")
    parser.add_argument("--should", action="store_true", help="Re-ingest books that would significantly improve")
    parser.add_argument("--all", action="store_true", help="Re-ingest all recommended books")
    parser.add_argument("--apply", action="store_true", help="Actually apply changes (default is dry run)")
    args = parser.parse_args()

    if not any([args.book_id, args.critical, args.should, args.all]):
        parser.print_help()
        sys.exit(1)

    # Build list of book IDs to process
    book_ids = []
    if args.book_id:
        book_ids = [args.book_id]
    elif args.all:
        book_ids = ALL_REINGEST_IDS
    elif args.critical:
        book_ids = CRITICAL_BOOK_IDS
    elif args.should:
        book_ids = SHOULD_REINGEST_IDS

    conn = get_db()
    results = {"improved": 0, "skipped": 0, "failed": 0, "applied": 0}

    for book_id in book_ids:
        book, old_chapters = get_book_info(conn, book_id)
        if not book:
            print(f"\nBook {book_id} not found in database")
            results["failed"] += 1
            continue

        source_file = book.get("source_file", "")
        if not source_file or not os.path.exists(source_file):
            print(f"\nSource file not found for: {book['title']}")
            print(f"  Path: {source_file}")
            results["skipped"] += 1
            continue

        # Convert source file
        print(f"\nConverting: {Path(source_file).name}...")
        text, toc_titles, error = convert_file(source_file)
        if error:
            print(f"  Conversion error: {error}")
            results["failed"] += 1
            continue

        # Run enhanced pipeline
        print(f"  Analyzing with EnhancedPipeline...")
        pipeline_result = detect_chapters(text, book_id, toc_titles)
        new_chapters = pipeline_result.chapters

        # Compare
        is_improvement = print_comparison(book, old_chapters, new_chapters, pipeline_result)

        if is_improvement and args.apply:
            old_count = apply_reingest(conn, book_id, book["title"], new_chapters)
            print(f"\n  APPLIED: Replaced {old_count} chapters with {len(new_chapters)}")
            results["applied"] += 1
        elif is_improvement:
            print(f"\n  DRY RUN: Would replace {len(old_chapters)} chapters with {len(new_chapters)}")
            print(f"  Use --apply to apply changes")
            results["improved"] += 1
        else:
            print(f"\n  SKIPPED: Re-ingestion would not improve this book")
            results["skipped"] += 1

    # Summary
    print(f"\n{'='*70}")
    print(f"  Summary: {len(book_ids)} books processed")
    print(f"  Improved: {results['improved']} (dry run)")
    print(f"  Applied: {results['applied']}")
    print(f"  Skipped: {results['skipped']}")
    print(f"  Failed: {results['failed']}")
    if results["improved"] > 0 and not args.apply:
        print(f"\n  Run with --apply to apply changes")
    if results["applied"] > 0:
        print(f"\n  NOTE: Embeddings need regeneration. Run:")
        print(f"  python -c \"from src.utils.embedding_sync import update_embeddings_incremental; update_embeddings_incremental()\"")
    print(f"{'='*70}")

    conn.close()


if __name__ == "__main__":
    main()
