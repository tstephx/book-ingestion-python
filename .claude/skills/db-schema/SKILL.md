---
name: db-schema
description: "Map of this project's SQLite schema and DB-path resolution. Use before answering any question about tables, columns, or 'which database does this write to' — the docs and the code disagree."
---

# Database Schema Map

Orientation only. This tells you where the schema lives and what will mislead
you. It is not a table reference — read the source for that.

## Canonical source

Table-creation code is `book_ingestion/storage/database.py`'s
`BookDatabase.initialize()` (~lines 15-58): three tables — `books`, `chapters`,
`processing_checkpoints`. That is ALL this repo's code ever creates.

The canonical, shared DB (read by book-mcp-server) is
`~/Library/Application Support/book-library/library.db` — 20 tables, including
`chunks`, FTS tables, `autonomy_*`, `pipeline_*`, none of which exist in
`database.py`. Those come from migrations outside this repo. Never trust
`database.py` for canonical schema shape — verify with:

    sqlite3 ~/"Library/Application Support/book-library/library.db" "PRAGMA table_info(books)"

## Known traps

- **CLAUDE.md's DB-path claim is currently false for the main CLI.**
  `CLAUDE.md:78` says code "must point at the canonical DB... never a
  repo-local `data/library.db`" — but `book_ingestion/cli.py` and
  `cli_enhanced.py` (12 call sites total) all do `Config()` with no override,
  which reads `config/config.json:3`'s `"database_path": "./data/library.db"`.
  `AGENTIC_PIPELINE_DB` is only honored by `scripts/reingest_books.py`
  (line 41-44) — nowhere else. Running any documented `python -m
  book_ingestion.cli ...` command writes to the LOCAL dev copy, silently.

- **The dev copy (`data/library.db`) is a schema subset, not a mirror.** It
  has 3 tables vs canonical's 20, and `books` is missing 6 columns
  (`book_type`, `classification_confidence`, `suggested_tags`,
  `classification_reasoning`, `classified_at`, `classified_by`) that exist
  only in canonical.

- **Commit `2930459` fixed docs + one script, not the config default.**
  `book_ingestion/utils/config.py:27` and `config/config.json:3` still
  hardcode the dev-copy path. Don't assume a "fix DB path" commit fixed all
  callers — check each entry point.

## What this file is not

Not a table reference. Do not paste table definitions here — read them from
`book_ingestion/storage/database.py` or query the live DB with `PRAGMA
table_info`. This file tells you where to look and what will mislead you.
