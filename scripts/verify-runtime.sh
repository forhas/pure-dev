#!/usr/bin/env bash
# Offline runtime fixtures; shared assertions pin integration mechanisms below.
set -uo pipefail
cd "$(dirname "$0")/.."
fails=0
ok() { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }
. ./scripts/lib/assert.sh
PYBIN=${KNOWLEDGE_PY:-python3}
if PYTHONDONTWRITEBYTECODE=1 $PYBIN scripts/tests/test_runtime.py; then
  ok "offline runtime and telemetry fixtures"
else
  bad "offline runtime and telemetry fixtures"
fi
ND=plugins/notion-dev
TICKET=$ND/commands/ticket.md
REVIEW=$ND/skills/review-and-merge/SKILL.md
PROTOCOL=$ND/references/runtime.md
assert_has "ticket establishes the runtime lifecycle" "$TICKET" 'references/runtime.md'
assert_has "ticket gates readiness before implementation" "$TICKET" 'runtime.py --state "$RUNTIME_STATE" ready'
assert_has "finalize shares the runtime lifecycle" "$ND/commands/finalize.md" 'references/runtime.md'
assert_has "next-task does not advance while a worker is pending" "$ND/commands/next-task.md" 'never increment `DONE`'
assert_has "record worker publishes before final reply" "$ND/references/record.md" 'publish the complete `RECORD:` block'
assert_has "protocol resolves citations before merge" "$PROTOCOL" 'resolve-citations --worker'
assert_has "protocol tracks the entire requirement" "$PROTOCOL" 'reviewed_whole_ticket'
assert_has "second pass returns a full current-head verdict set" "$REVIEW" 'complete current-head verdict set for every inventory ID'
assert_has "verifier may honestly report ambiguity" "$REVIEW" '**The verifier writes `met`, `not-met`, or `unverified`**'
assert_lacks "mandatory incompleteness cannot pass by labeling" "$REVIEW" 'is exactly what this gate exists to produce rather than prevent'
assert_order "runtime receipt gate precedes the irreversible merge" \
  "$REVIEW" 1 "$(total_lines "$REVIEW")" \
  "runtime gate" '^\*\*Runtime receipt gate' \
  "merge command" '^gh pr merge <pr>'
for f in "$ND/skills/plan-review/SKILL.md" "$ND/skills/flow-triage/SKILL.md" "$REVIEW" "$TICKET"; do
  assert_lacks "$f has no restart inference from relative age" "$f" 'it is restarting from the beginning rather than making progress'
done
[ "$fails" -eq 0 ]
