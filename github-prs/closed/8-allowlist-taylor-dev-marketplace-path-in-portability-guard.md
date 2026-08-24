---
title: "Allowlist taylor-dev marketplace path in portability guard"
number: 8
state: merged
labels: []
repo: book-ingestion-python
url: https://github.com/tstephx/book-ingestion-python/pull/8
created: 2026-08-22
updated: 2026-08-22
merged: 2026-08-22
base: main
head: allowlist-taylor-dev-path-84
additions: 10
deletions: 2
changed_files: 1
---

Fixes the CI redness on `main` since the taylor-dev-core onboarding commit (`712ec18`) — `check-hardcoded-paths` fails on `.claude/settings.json`'s `extraKnownMarketplaces.taylor-dev.source.path`, which `promote-harness-release.rb` (a separate `_Workspace`-owned tool) writes as an inherently machine-local path.

Root cause is tracked at [taylor-dev-core#84](https://github.com/tstephx/taylor-dev-core/issues/84) as a `_Workspace`-side architectural decision (a `directory`-source marketplace entry has no portable form as currently designed) — out of scope for this repo alone. This PR applies the same accepted interim mitigation already used in `rss-news-server#13` and `briefcase` (commit `787835c`): a documented allowlist entry in the portability guard, not a weakening of the check.

## Verification
- `bash scripts/check_portability.sh` now exits 0.
- Reviewed by commit-reviewer: CLEAN.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01CLiiuuWYtqhbTrti7ibfeM
