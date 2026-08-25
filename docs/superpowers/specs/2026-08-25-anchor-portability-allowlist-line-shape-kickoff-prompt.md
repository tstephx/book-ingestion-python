# Anchor check_portability.sh's ALLOWLIST to line shape, not bare substring (closes #9)

## Where things stand

`book-ingestion-python#9` (confirmed still open, 2026-08-25). Non-blocking
nit from PR #8's review, merged as-is (`9a0f706`). Low priority per the
issue itself — pre-existing pattern (predates PR #8, commit `6df54a4`),
small practical risk given the script's narrow scanned scope.

Current implementation, `scripts/check_portability.sh` (re-read in full
before starting, it's short): the `ALLOWLIST` array is currently *empty*
— re-derive this fresh, don't assume the issue's original example entry
(`.claude/settings.json:.harness-releases/taylor-dev-core/`) still
exists; it was already noted obsolete in the script's own header comment
(taylor-dev-core#84 landing 2 moved that pin to untracked
`settings.local.json`). The matching logic itself is what needs fixing
regardless of current entry count:

```bash
if [ "$f" = "$allow_file" ] && [[ "$content" == *"$allow_sub"* ]]; then
```

This matches `$allow_sub` as a substring anywhere in the line — not
anchored to the actual JSON key/value shape, so an unrelated line
elsewhere in the same file containing the same substring would also be
allowlisted.

Canonical reference pattern already exists in `taylor-dev-core`'s
`scripts/check-claude-config-portability.rb` (re-verified current
2026-08-25): a `relative_path => [Regexp, ...]` hash (currently also
empty, same reason), matched via anchored regex against each line, not
substring containment. Port the *shape* of that approach to this repo's
bash script — don't just copy the Ruby.

## What this session does

1. Change `scripts/check_portability.sh`'s `ALLOWLIST` entries from
   `"file:substring"` pairs matched by substring containment to
   `"file:regex"` pairs (or an equivalent per-file array structure)
   matched by anchored regex against the full stripped line — e.g. a
   pattern shaped like `^"path": "/Users/.../\.harness-releases/...[^"]+"$`
   for a JSON `"path"` value, not a bare substring test.
2. Since the allowlist is currently empty, this is a pure matching-logic
   change with no live entries to migrate — write it so a future
   entry's format is obvious from the code and a comment, matching the
   canonical script's style.
3. Add or extend this repo's own test coverage for the script (check
   for an existing test file first — grep `tests/` for
   `check_portability` — extend it if found, don't create a parallel
   test file).

## Constraints carried over

- Keep the script's scanned scope unchanged (`.claude/**`, `.mcp.json*`,
  `CLAUDE.md` only, lines already containing `/Users/`) — this issue is
  about match precision, not scope.
- Low priority per the issue — don't expand this into a larger portage
  of the Ruby script's full structure; just fix the substring-vs-anchor
  gap.

## Caution

Re-derive current state before trusting anything above: `gh issue view 9
--repo tstephx/book-ingestion-python`, `git log --oneline -5`, and the
actual current content of `scripts/check_portability.sh` (its ALLOWLIST
may have changed since 2026-08-25). Run the `concurrent-session-preflight`
skill before starting and again immediately before the final push — this
repo's working tree may carry other sessions' local, unpushed commits at
times; check `git log origin/main..HEAD` before touching anything shared,
and don't sweep unrelated commits into your push without confirming
they're meant to go out.
