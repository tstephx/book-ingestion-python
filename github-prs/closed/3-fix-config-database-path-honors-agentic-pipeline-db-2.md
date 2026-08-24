---
title: "fix: Config.database_path honors AGENTIC_PIPELINE_DB (#2)"
number: 3
state: merged
labels: []
repo: book-ingestion-python
url: https://github.com/tstephx/book-ingestion-python/pull/3
created: 2026-08-14
updated: 2026-08-14
merged: 2026-08-14
base: main
head: canonical-db-cli-default-2
additions: 104
deletions: 28
changed_files: 2
---

## Summary
- CLAUDE.md already claimed code always points at the canonical DB — true only for `scripts/reingest_books.py`, which reads `AGENTIC_PIPELINE_DB` directly. `cli.py`/`cli_enhanced.py` (12 call sites) construct `Config()` with no override, which reads `database_path` from the loaded `config.json` (present on disk, hardcoded to the local dev copy) — `_get_defaults()` was never actually the effective path despite being what the issue originally suggested fixing.
- Fix is at the actual read point: `Config.database_path` now checks `AGENTIC_PIPELINE_DB` first, falling back to `config.json`/defaults only when unset — matching the pattern `reingest_books.py` already established. With this, CLAUDE.md's claim is now true for the primary CLI too, not just the one script.
- Fixes #2.

## Test plan
- [x] 3 new tests in `tests/test_config.py`: env override wins over config.json, config.json still wins with no override (today's behavior preserved), no-config.json fallback also honors the override.
- [x] Confirmed red before the fix, green after.
- [x] Full suite: 240 passed, 1 pre-existing unrelated failure (`test_semantic_chunker.py::test_detect_boundaries_basic`) — confirmed via `git stash` that it fails identically with this change fully reverted, not introduced by this diff. Local `wt merge`'s test gate blocks on it regardless, hence a PR instead of a direct merge.

Note: `ruff format` reflowed the whole file on save (whitespace/quote-style only, no behavior change) — this repo isn't fully `ruff format`-clean yet, so any edited file gets normalized on touch. Unrelated to the actual fix, called out so it doesn't read as a bigger diff than it is.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
