#!/usr/bin/env python3
"""
Backfill books.word_count from chapter sums.

Books ingested before the pipeline fix always stored word_count=0.
This migration sets word_count = SUM(chapters.word_count) for any
book where word_count is 0 but chapters exist.
"""

import sqlite3
import sys
from pathlib import Path


def backfill_word_counts(db_path):
    print(f"Migrating database: {db_path}")
    conn = sqlite3.connect(db_path)

    result = conn.execute("""
        UPDATE books
        SET word_count = (
            SELECT COALESCE(SUM(c.word_count), 0)
            FROM chapters c
            WHERE c.book_id = books.id
        )
        WHERE word_count = 0
        AND EXISTS (SELECT 1 FROM chapters WHERE book_id = books.id)
    """)
    conn.commit()

    count = result.rowcount
    if count:
        print(f"✓ Backfilled word_count for {count} books")
    else:
        print("✓ No books needed backfill (already up to date)")

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Default to shared library DB
        db_path = Path(__file__).resolve().parent.parent / "data" / "library.db"
    else:
        db_path = Path(sys.argv[1])

    if not db_path.exists():
        print(f"Error: database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    backfill_word_counts(str(db_path))
