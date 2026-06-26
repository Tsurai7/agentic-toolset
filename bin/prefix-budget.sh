#!/usr/bin/env bash
# Guard the always-on Claude prefix size.
#
# The per-turn prefix (and thus the toolset's token overhead) is dominated by the
# files providers/claude/install.sh:install_claude_md concatenates into
# ~/.claude/agentic-cfg.generated.md. This check sums those source files and fails if
# they exceed a committed budget, so the always-on layer cannot silently grow (W2 of
# plans/06-overhead-and-uplift.md). It mirrors that render's file set: the stub,
# AGENTS.md, core/principles/*.md (minus README), and core/instructions/user-rules/*.md
# minus cursor-rules-pointer.md (Cursor-only meta, excluded from the Claude prefix).
#
# Override the budget for experiments with PREFIX_BUDGET_BYTES; raising the committed
# default is a deliberate decision, not an accident.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUDGET="${PREFIX_BUDGET_BYTES:-11300}"

total=0
add() { [[ -f "$1" ]] && total=$((total + $(wc -c < "$1"))); }

add "${ROOT}/providers/claude/CLAUDE.md.stub"
add "${ROOT}/core/instructions/AGENTS.md"
for f in "${ROOT}/core/principles"/*.md; do
  [[ "$(basename "$f")" == "README.md" ]] && continue
  add "$f"
done
for f in "${ROOT}/core/instructions/user-rules"/*.md; do
  [[ "$(basename "$f")" == "cursor-rules-pointer.md" ]] && continue
  add "$f"
done

echo "always-on Claude prefix source: ${total} bytes (budget ${BUDGET})"
if (( total > BUDGET )); then
  echo "FAIL: always-on prefix source ${total} > budget ${BUDGET} bytes." >&2
  echo "Trim the always-on layer (de-dup) or raise PREFIX_BUDGET_BYTES deliberately." >&2
  exit 1
fi
