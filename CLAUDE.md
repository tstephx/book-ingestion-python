---
status: active
tags: [project/book-ingestion-python, format/readme]
type: note
created: '2026-02-18'
modified: '2026-02-18'
related: ["[[Claude-Config/mcp-servers/agentic-pipeline]]"]
---

# CLAUDE.md — Book Ingestion Pipeline
<!-- project-name: book-ingestion-python -->

**DO NOT scan directories on startup.** Do not paste large verbatim book text into chat; summarize and reference output file paths.

## Purpose
Converts PDF/EPUB into chapter-segmented markdown + SQLite + embeddings. Powers book-mcp-server search. DB is shared (`data/library.db`).

## Bootstrap
```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
python -m book_ingestion.cli list   # smoke test
```
Python 3.12 required (3.13 not supported — PyTorch).

## Common Commands
```bash
source .venv/bin/activate

# Process
python -m book_ingestion.cli process book.pdf -t "Title" -a "Author"
python -m book_ingestion.cli batch /path/to/ebooks --dry-run

# Query
python -m book_ingestion.cli list
python -m book_ingestion.cli audit
python -m book_ingestion.cli analyze <book-id>

# Embeddings
python scripts/generate_embeddings.py

# Tests
python -m pytest tests/ -v
```

## Config
Defaults in `config/config.json` (auto-generated if missing):
- DB: `data/library.db` (shared with book-mcp-server)
- Output: `data/books/{book-id}/` (metadata.json, chapters/*.md)
- Embedding model: all-MiniLM-L6-v2

## Project Structure
```
book_ingestion/
├── cli.py                   # Primary CLI
├── cli_enhanced.py          # Analysis/diagnostics
├── converters/              # PDF/EPUB (PyMuPDF, ebooklib)
├── processors/
│   ├── pipeline.py          # Main orchestration
│   ├── chapter_detector.py  # Multi-strategy detection
│   ├── section_splitter.py  # Large chapter splitting (>15K tokens)
│   └── text_cleaner.py      # LLM-optimized cleaning
├── storage/                 # SQLite + markdown output
├── embeddings/              # Embedding generation
└── utils/config.py          # Config & DB path
```

## Triage

| Symptom | Check |
|---------|-------|
| Chapter boundaries wrong | `python -m book_ingestion.cli analyze <book-id>` — inspect detected TOC/anchors |
| Long chapters (>15K tokens) | Confirm section_splitter behavior; check if semantic boundaries exist |
| Embeddings fail | Verify Python 3.12 (not 3.13), torch installed, rerun `generate_embeddings.py` |
| MCP server doesn't see new books | Confirm embeddings generated, then restart/reload MCP host |
| DB mismatch | Both repos must point to same `data/library.db` |

## Integration
After processing + embeddings, restart the MCP host serving book-mcp-server (Claude Desktop, Claude Code, etc.).

---

*Last updated: 2026-02-18*
