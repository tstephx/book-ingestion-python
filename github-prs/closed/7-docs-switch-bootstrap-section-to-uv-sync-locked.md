---
title: "docs: switch Bootstrap section to uv sync --locked"
number: 7
state: merged
labels: []
repo: book-ingestion-python
url: https://github.com/tstephx/book-ingestion-python/pull/7
created: 2026-08-22
updated: 2026-08-22
merged: 2026-08-22
base: main
head: fix-stale-main-venv-6
additions: 12
deletions: 4
changed_files: 1
---

## Summary
- Replaces the plain `venv` + `pip install -e .` Bootstrap steps in `CLAUDE.md` with `uv sync --locked --python 3.12 --extra all --extra dev`, matching what `.config/wt.toml`'s worktree `pre-start` hook already uses.
- The old path drifts from `uv.lock` over time since nothing ties it back to the lockfile; confirmed 2026-08-22 as the root cause of a stale main-checkout venv where `torch` was frozen at an old version while unpinned transitive deps (`transformers`) kept resolving to latest, breaking the `sentence_transformers` import chain.

Fixes #6

## Test plan
- [x] `uv sync --locked --python 3.12 --extra all --extra dev` succeeds from a fresh worktree
- [x] `python -m book_ingestion.cli list` smoke test runs
- [x] Full suite: 241 passed
