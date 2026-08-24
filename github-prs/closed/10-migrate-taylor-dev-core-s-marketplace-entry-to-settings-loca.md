---
title: "Migrate taylor-dev-core's marketplace entry to settings.local.json"
number: 10
state: merged
labels: []
repo: book-ingestion-python
url: https://github.com/tstephx/book-ingestion-python/pull/10
created: 2026-08-23
updated: 2026-08-23
merged: 2026-08-23
base: main
head: migrate-settings-local-84
additions: 6
deletions: 20
changed_files: 2
---

Consumer-side cleanup for [workspace-control-plane#104](https://github.com/tstephx/workspace-control-plane/pull/104) (taylor-dev-core#84 fix): `enable-taylor-dev-core.rb`/`promote-harness-release.rb` now write the machine-local `extraKnownMarketplaces.taylor-dev` entry to untracked `settings.local.json` instead of tracked `settings.json`. This removes the entry from `settings.json` here and reverts #8's now-unnecessary portability-guard allowlist entry back to empty.

This machine's own `.claude/settings.local.json` was re-enabled and re-promoted as part of this migration (untracked, not part of this PR) — confirmed via `harness-release-status.rb`: `active_marketplace_state` reads `active`.

## Verification
- `bash scripts/check_portability.sh` passes with an empty allowlist.
- Full test suite: 241 passed.
- Reviewed by commit-reviewer: **APPROVE**, clean.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01CLiiuuWYtqhbTrti7ibfeM
