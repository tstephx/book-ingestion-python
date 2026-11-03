---
title: "fix: make merge-chapters analysis-only (rename to analyze-merges)"
number: 13
state: merged
labels: []
repo: book-ingestion-python
url: https://github.com/tstephx/book-ingestion-python/pull/13
created: 2026-11-03
updated: 2026-11-03
merged: 
base: main
head: fix/12-merge-chapters-analysis-only
additions: 68
deletions: 32
changed_files: 5
---

Takes the issue's second option. The command only ever analysed; it now says so.

- Renamed to `analyze-merges`; `merge-chapters` stays as a hidden, deprecated alias
- Removed the TODO/'not implemented' path; `--dry-run` is a hidden no-op
- Updated README, docs/ENHANCED-CHUNKING.md and the hint in scripts/validate_library.py
- Added tests/test_cli_enhanced_merges.py

A real merge would need repository update/delete methods, chapter file rewrite and renumbering, and embedding/FTS regeneration — worth a separate PRD if wanted.

248 tests pass.

Fixes #12

🤖 Generated with [Claude Code](https://claude.com/claude-code)
