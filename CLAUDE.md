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
Converts PDF/EPUB into chapter-segmented markdown + SQLite + embeddings. Powers book-mcp-server search. The shared/canonical DB is `~/Library/Application Support/book-library/library.db` (env `AGENTIC_PIPELINE_DB`); the local `data/library.db` is a small dev copy only.

## Bootstrap
```bash
uv sync --locked --python 3.12 --extra all --extra dev
source .venv/bin/activate
python -m book_ingestion.cli list   # smoke test
```
Python 3.12 required (3.13 not supported — PyTorch). Use `uv sync
--locked`, not a plain `pip install -e .` — a plain install never upgrades
an already-satisfying direct dependency (e.g. `torch`) while unpinned
transitive deps keep resolving to latest, so the two drift apart from
each other over time and can land on a broken combination (confirmed
2026-08-22, `#6`: a stale `pip install -e .` venv pulled in a `transformers`
requiring `torch>=2.4` alongside a frozen `torch==2.2.2`, breaking the
`sentence_transformers` import chain). `uv.lock` already pins a known-
working set together; `.config/wt.toml`'s worktree bootstrap uses this
same command for that reason — keep the main checkout's venv built the
same way instead of drifting from it.

Copy `.mcp.json.example` to `.mcp.json` and set `BOOK_LIBRARY_DB`/`BOOK_MCP_SERVER_HOME` to enable the `sqlite`/`agentic-pipeline` MCP servers (see Integration below).

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
- DB path resolution: see `.claude/skills/db-schema/SKILL.md` (canonical vs. dev-copy paths, and current known gaps)
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
Read `docs/triage.md` when a processing/embeddings/detection run fails or behaves unexpectedly.

## Integration
After processing + embeddings, restart the MCP host serving book-mcp-server (Claude Desktop, Claude Code, etc.).

`.mcp.json` here also defines an `agentic-pipeline` server that launches out of **book-mcp-server's own venv**, not a local one — deliberate shared-provider pattern (see `book-mcp-server/CLAUDE.md`'s "agentic-pipeline is a shared MCP provider" section), not a stray path to "fix."

---

*Last updated: 2026-08-21*
