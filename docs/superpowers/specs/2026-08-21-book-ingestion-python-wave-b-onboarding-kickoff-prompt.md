# Onboard book-ingestion-python to taylor-dev-core (Wave B, data-pipelines — sequential)

## Where things stand

`rss-news-server` closed as Wave B's `data-pipelines` representative
2026-08-21 (that repo's own
`docs/superpowers/specs/2026-08-21-rss-news-server-wave-b-onboarding-kickoff-prompt.md`,
now merged at commit `b952646`) — owner decision: retain. Per the migration
plan's Task 6 Step 3 ("Execute the canonical transaction for the remaining
repositories"), `book-ingestion-python` and `document-intelligence` (this
category's other two members) can now proceed sequentially — neither is
gated on the other the way the `applications`/`knowledge-systems` pairs are
on their own unproven representative.

**Note on population**: the migration plan's Task 6 lists Wave B's
population as **9** repositories, including `api-dashboard` and
`vault-rss-feeds` — neither appeared in the 7-repository scope the
rss-news-server kickoff prompt stated. This discrepancy hasn't been
reconciled with the owner.

**Registry**: `book-ingestion-python`, category `data-pipelines`, lifecycle
`active`, path `/Users/taylorstephens/Dev/_Projects/book-ingestion-python`
(`registry.yaml`). Same category as rss-news-server — `hint_map` has no
`data-pipelines` entry, so `registry_hint` will resolve to `none`, same
situation rss-news-server was in. `data-pipeline` (the purpose-built profile
added since Wave A) is the obvious candidate by category match, though it's
worth checking whether `python-service` fits the actual shape better —
present both, as rss-news-server's own transaction did for
`data-pipeline` vs. `external-automation`.

**This repo already completed a prerequisite `behavioral-studio` hasn't**:
`taylor-dev-core#83`'s `.claude/` gitignore-narrowing fix is already merged
to `main` here (`f705739 Narrow .claude/ gitignore, track settings.json and
db-schema skill`) — unlike `behavioral-studio`, where the equivalent fix is
still sitting in an unmerged worktree. No such prerequisite blocks this
transaction.

**Git state (live snapshot as of 2026-08-21)**: `main`, synced with
`origin/main`, clean except an untracked `github-prs/` directory (a local
artifact, not gitignored — worth a `.gitignore` decision separately, not
part of this onboarding). No onboarding-named branch or worktree exists.

**Existing `.claude/`**: `settings.json` exists —
`{"enabledPlugins": {"commands-database-operations@buildwithclaude": true}}`
— unrelated plugin, preserve unmodified; no `taylor-dev-core`/`taylor-dev`
reference. No `.claude/ai-adoption.yaml` — manifest should resolve
`missing`, confirm fresh.

**No canonical verify gate wired yet** — unlike rss-news-server, briefcase,
and morning-reader, this repo has no `.githooks/pre-push`, no CI workflow
(`.github/` doesn't exist), and no wrapper script. `CLAUDE.md` documents
`python -m pytest tests/ -v` (after activating `.venv`) as the manual
command a human runs, but that command takes arguments and there's no
repo-owned file wrapping it — `resolve-command.rb` requires a real,
non-symlinked, executable *file* with no arguments, so this can't be
`commands.verify` directly. No `templates/data-pipeline/` or
`templates/python-service/` starter exists either. **Propose
`--wrap-command pytest`** to `onboard-repo.sh` — a bare, single-token
command matching the flag's allowed character set, which scaffolds a
deterministic, venv-preferring, PATH-falling-back wrapper at the proposed
`verify_relative` path (per `repo-onboard`'s own SKILL.md). Confirm with the
owner before assuming this is the right shape versus asking for a
repo-owned wrapper script to be authored by hand first.

**venv**: `.venv/bin/python3` exists (symlink to `python3.12`, resolves and
is executable); `.venv/bin/pip`/`pip3`/`pip3.12` all present and
executable — not a pip-absent uv-only venv, no caveat to flag here.

**No prior AI-adoption GitHub activity** found via `gh issue list` / `gh pr
list` search against `tstephx/book-ingestion-python`.

## What this session does

Run the same canonical per-repository transaction
(`docs/plans/2026-07-28-portfolio-onboarding-migration-sequence.md`,
Task 6 Step 3), against `book-ingestion-python`
(`/Users/taylorstephens/Dev/_Projects/book-ingestion-python`):

1. **Read-only preflight.** Re-confirm the registry entry, canonical
   checkout state, and current `taylor-dev-core` release status
   (`harness-release-status.rb`) fresh.
2. **Release enablement and promotion**
   (`enable-taylor-dev-core.rb` then `promote-harness-release.rb`), if not
   already done.
3. **Propose a profile and `commands.verify`** via `/repo-onboard`
   detection — present `data-pipeline` and `python-service` as profile
   options, and `--wrap-command pytest` as the verify-command approach, to
   the owner for approval before applying.
4. **Apply transactionally** via `onboard-repo.sh` once approved.
5. **Verify, in order**: `/repo-status`, `/repo-verify`, `/repo-drift`,
   `/repo-context` (draft an owner-authored task contract for review, don't
   author it unilaterally — copy
   `templates/repo-context/task-contract-example.yaml`, per
   taylor-dev-core#93).
6. **Present the resulting decision point** — `retain` / `revise` /
   `rollback` / `defer` / `stop` — to the owner.

## Constraints carried over

- Touch only `book-ingestion-python`. Do not touch `registry.yaml`,
  `policy/ai-adoption-release.yaml`, or
  `docs/ai-engineering/portfolio-onboarding-ledger.yaml`.
- Do not push the onboarding commit without separate, explicit owner
  direction beyond the retain/revise decision itself.
- Do not start any other Wave B repository's onboarding from this session.

## Caution

Re-derive current state before trusting anything above: `git log --oneline
-5` and `git status` fresh in this repo, and re-check
`policy/ai-adoption-release.yaml`'s `approved_commit` (confirm it hasn't
moved — a peer session committed twice to rss-news-server's own main
mid-transaction there, unprompted, so treat the release record as capable of
moving between sessions). Run `concurrent-session-preflight`
(`ListAgents`, `gh pr list`, `git ls-remote --heads origin`) before
starting — no busy peer session was observed against this specific repo at
research time, but a large, unrelated fleet of concurrent sessions was
active across many other repositories simultaneously; don't assume that's
changed. Run the preflight again immediately before any push.
