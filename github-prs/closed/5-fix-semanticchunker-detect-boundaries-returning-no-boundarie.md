---
title: "Fix SemanticChunker.detect_boundaries returning no boundaries"
number: 5
state: merged
labels: []
repo: book-ingestion-python
url: https://github.com/tstephx/book-ingestion-python/pull/5
created: 2026-08-22
updated: 2026-08-22
merged: 2026-08-22
base: main
head: fix-detect-boundaries-4
additions: 14
deletions: 7
changed_files: 2
---

Fixes #4.

Two compounding bugs, both required to make `test_detect_boundaries_basic` pass:

1. `_split_into_sentences` merges sentences into `buffer_size`-word chunks (default 200, tuned for chapter-scale input). The test's ~70-word sample collapses into a single chunk, so `detect_boundaries` short-circuits via `len(sentences) < 2` and returns `[]`. Fixed by giving the test a smaller `buffer_size` so its three topic paragraphs become separate comparable chunks.

2. The percentile threshold computed `threshold_idx = int(len(sorted_sims) * (1 - percentile_threshold))` as a raw list index. For the default `percentile_threshold=0.9`, this truncates to index 0 — the bare minimum — whenever there are fewer than 10 similarity values, and nothing can ever be strictly less than the minimum. `is_significant` was therefore always `False` for any chapter producing under ~11 buffer chunks, not just this test's sample. Fixed with `numpy.percentile`'s linear interpolation — the issue's own "likely a threshold... issue" hunch pointed at this.

## Verification

`uv sync --locked` + `.venv/bin/python -m pytest -q` (this repo's own pre-merge command, `.config/wt.toml`): **241 passed**.

Note: the main checkout's pip-based `.venv` currently can't run this path at all due to unrelated dependency drift (stale `torch`, mismatched `numpy`/`transformers`) — filed as a separate issue, not part of this fix.

## Test plan
- [x] `test_detect_boundaries_basic` passes
- [x] Full suite (241 tests) passes via `uv sync --locked`
- [x] Diff scoped to the two bugs only — no incidental reformatting (confirmed via commit-reviewer)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01CLiiuuWYtqhbTrti7ibfeM
