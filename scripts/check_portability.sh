#!/usr/bin/env bash
# Portability regression guard for tracked Claude Code config.
#
# Fails if a tracked .claude/**, .mcp.json*, or CLAUDE.md file contains a
# hardcoded /Users/ path. A fresh clone at a different filesystem location
# (or under a different user account) must not depend on such a path.
#
# Add an allowlist entry below ONLY for a path a fleet portability audit
# explicitly classified as an intentional remote-host or historical-example
# reference (retained on purpose, not a defect). Format: "file:substring".
# None currently apply to this repo -- the one entry this file used to
# carry (extraKnownMarketplaces.taylor-dev.source.path, taylor-dev-core#84)
# is obsolete: that entry now lives in untracked settings.local.json
# (workspace-control-plane#104), never in this scanned, tracked file.
set -euo pipefail

ALLOWLIST=(
  # "path/to/file:substring-of-the-allowed-line"
)

cd "$(git rev-parse --show-toplevel)"

mapfile -t FILES < <(git ls-files '.claude/**' '.mcp.json*' 'CLAUDE.md')

failed=0

for f in "${FILES[@]}"; do
  [ -f "$f" ] || continue
  while IFS=: read -r lineno content; do
    allowed=0
    for entry in "${ALLOWLIST[@]:-}"; do
      [ -z "$entry" ] && continue
      allow_file="${entry%%:*}"
      allow_sub="${entry#*:}"
      if [ "$f" = "$allow_file" ] && [[ "$content" == *"$allow_sub"* ]]; then
        allowed=1
        break
      fi
    done
    if [ "$allowed" -eq 0 ]; then
      echo "Portability check failed: $f:$lineno contains a hardcoded /Users/ path:" >&2
      echo "  $content" >&2
      failed=1
    fi
  done < <(grep -n '/Users/' "$f" || true)
done

if [ "$failed" -ne 0 ]; then
  echo "" >&2
  echo "If this path is intentional (remote-host or historical example), add an" >&2
  echo "allowlist entry in scripts/check_portability.sh instead of removing it." >&2
  exit 1
fi

echo "Portability check passed: no unallowlisted /Users/ paths in tracked .claude/**, .mcp.json*, CLAUDE.md"
