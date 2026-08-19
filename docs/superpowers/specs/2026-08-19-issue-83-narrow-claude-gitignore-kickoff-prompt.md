# Narrow the blanket `.claude/` gitignore rule

## Where things stand

Tracking issue: https://github.com/tstephx/taylor-dev-core/issues/83 (open,
filed in `taylor-dev-core` as the portfolio-wide tracker; this repo is one of
three affected — the fix itself happens here)

`.gitignore` line 38 currently has a blanket `.claude/` rule. That excludes
everything under `.claude/`, including legitimate content that should be
tracked: `.claude/settings.json` and, most concretely, the repo-local
`.claude/skills/db-schema/SKILL.md` skill — currently lost to the blanket
ignore, never committed.

Confirmed by inspection (2026-08-19): `.claude/` here currently contains
`settings.json`, `settings.local.json`, and `skills/db-schema/SKILL.md`.
Only `settings.local.json` is genuinely local/secret-shaped and should stay
ignored — `git ls-files .claude` currently returns nothing at all, meaning
none of it is tracked. The root-level `CLAUDE.md` (outside `.claude/`) is
already tracked and unaffected by this rule.

A sibling repo, `Claude-Innit`, hit and fixed this same pattern earlier
today (commit `2ec7d92`, "Track .claude/settings.json; enable and promote
taylor-dev-core"): narrowed its blanket `.claude/` rule down to ignoring only
`.claude/settings.local.json` and other genuinely local files, then tracked
the rest. Use that as the shape of the fix, not a file to go read in another
repo.

## What this session does

1. Confirm current state matches the above: `cat .gitignore | grep -n
   claude` and `find .claude -type f`.
2. Edit `.gitignore`: replace the blanket `.claude/` line with a narrower
   rule that ignores only `.claude/settings.local.json` (and any other file
   under `.claude/` you find that's genuinely local/secret-shaped — re-check
   with `find .claude -type f` first, don't assume the list above is
   complete by the time you run this).
3. `git add .gitignore .claude/settings.json .claude/skills/db-schema` (and
   any other legitimate content the re-check in step 2 surfaced). Before
   staging, scan every newly-tracked file for anything secret-shaped
   (tokens, keys, credentials) — this repo's own security rules require
   that check before any commit, not just a rule to follow in the abstract.
4. Commit with a message describing the fix (mention it's the
   `book-ingestion-python` slice of `taylor-dev-core#83`, but do **not** use
   a GitHub closing keyword — `closes`/`fixes #83` — since #83 covers two
   other repos too and isn't done until all of them land).
5. Push directly to `main` (this repo mixes direct pushes and PR-merges in
   its recent history — a PR isn't required here, but check `git log` for
   any indication otherwise before pushing).
6. Comment on `taylor-dev-core#83`
   (`gh issue comment 83 --repo tstephx/taylor-dev-core`) noting this repo's
   slice is done, with the commit SHA.

## Constraints carried over

Don't touch `Claude-Innit` or `behavioral-studio` — those are separate,
independently-running pieces of this same issue. Don't track
`.claude/settings.local.json` or anything else genuinely local. Don't close
issue #83 — only comment that this repo's slice is done.

## Caution

Re-derive current state (`git status`, `git log`, `cat .gitignore`, `find
.claude -type f`) before trusting anything above — verify the file contents
directly rather than assuming this description is still accurate. Run the
`concurrent-session-preflight` skill before starting and again immediately
before your final push, since another session may be working
`behavioral-studio`'s identical-shaped slice of the same tracking issue
concurrently.
