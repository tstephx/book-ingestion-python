---
title: "Anchor check_portability.sh's ALLOWLIST to line shape, not substring"
number: 11
state: merged
labels: []
repo: book-ingestion-python
url: https://github.com/tstephx/book-ingestion-python/pull/11
created: 2026-08-26
updated: 2026-08-26
merged: 2026-08-26
base: main
head: anchor-portability-allowlist
additions: 132
deletions: 4
changed_files: 2
---

## Summary
- `ALLOWLIST` entries previously matched an allowed line by bare substring containment anywhere in the line — not anchored to the actual JSON key/value shape, so an unrelated line elsewhere in the same file containing the same substring could also be incorrectly allowlisted.
- Entries are now `"file:regex"` pairs matched via an anchored regex (`^...$`) against the full, whitespace-stripped line, mirroring the shape of `taylor-dev-core`'s canonical `scripts/check-claude-config-portability.rb` (ported the matching approach, not the Ruby itself).
- Scanned scope (`.claude/**`, `.mcp.json*`, `CLAUDE.md`, lines containing `/Users/`) is unchanged — this is a match-precision fix only, no scope expansion.
- Allowlist was already empty (its one prior entry moved to untracked `settings.local.json` per `#8`/`#10`), so this is a pure matching-logic change with no live entries to migrate.

## Test plan
- [x] Added `tests/test_check_portability.py` (no existing test file for this script): empty-allowlist pass/fail baseline cases, an allowlist entry permitting its exact anchored line shape, and the core regression test proving an unrelated line containing the same substring is no longer allowlisted.
- [x] `python -m pytest tests/` — 245 passed
- [x] `bash scripts/check_portability.sh` against this repo's own tracked config — passes
- [x] `bash -n scripts/check_portability.sh` — syntax OK

Closes #9

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01PEYrX4FefvMDYDEDbfppyk
