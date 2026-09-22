#!/usr/bin/env bash
# Historical contracts below cover opt-in legacy flows; verify-lean-workflow.sh covers the new default.
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
if PYTHONDONTWRITEBYTECODE=1 $PYBIN scripts/tests/test_runtime_convergence.py; then
  ok "offline context packets, independent deltas, and workflow ordering"
else
  bad "offline context packets, independent deltas, and workflow ordering"
fi
if PYTHONDONTWRITEBYTECODE=1 $PYBIN scripts/tests/test_runtime_corrections.py; then
  ok "terminal-sweep code verdicts without a prior completeness receipt"
else
  bad "terminal-sweep code verdicts without a prior completeness receipt"
fi
if PYTHONDONTWRITEBYTECODE=1 $PYBIN scripts/tests/test_dependencies.py; then
  ok "live dependency diagnostics and local disablement"
else
  bad "live dependency diagnostics and local disablement"
fi
ND=plugins/notion-dev
TICKET=$ND/references/legacy/ticket.md
REVIEW=$ND/references/legacy/review-and-merge.md
PROTOCOL=$ND/references/legacy/runtime.md
# The legacy entrypoints must load the LEGACY contract: `prepare` omits `result_contract`
# for schema 1/2, so pointing them at the lean one dispatches workers against a contract
# their packet does not carry. Pinning the legacy path is what this assertion now asserts.
assert_has "ticket establishes the legacy runtime lifecycle" "$TICKET" 'references/legacy/runtime.md'
assert_has "ticket gates readiness before implementation" "$TICKET" 'runtime.py --state "$RUNTIME_STATE" ready'
assert_has "finalize shares the legacy runtime lifecycle" "$ND/references/legacy/finalize.md" 'references/legacy/runtime.md'
assert_has "next-task does not advance while a worker is pending" "$ND/references/legacy/next-task.md" 'never increment `DONE`'
assert_has "record worker publishes before final reply" "$ND/references/legacy/record.md" 'publish the complete `RECORD:` block'
assert_has "protocol resolves citations before merge" "$PROTOCOL" 'resolve-citations --worker'
assert_has "protocol tracks the entire requirement" "$PROTOCOL" 'reviewed_whole_ticket'

# Consuming is not accepting. A contract-invalid report has to be consumed before it can
# be judged, so `consumed` alone must never unlock a same-role replacement -- that left a
# rejected worker unterminated and possibly still running beside its replacement, which
# for `record` is duplicate provider writes.
assert_has "protocol separates accepting a result from consuming it" "$PROTOCOL" '**Consuming a result is not accepting it, and the difference is enforced.**'
assert_has "protocol names \`accept\` as an exit from consumed" "$PROTOCOL" 'accept --worker'
assert_has "runtime.py gates replacement on acceptance or confirmed termination" "$ND/scripts/runtime.py" 'not w["terminated"] and not w.get("accepted")'
assert_has "runtime.py refuses to accept a result that was never consumed" "$ND/scripts/runtime.py" 'consume the result before accepting it'
assert_lacks "replacement no longer unlocks on \`consumed\` alone" "$ND/scripts/runtime.py" 'w["status"] != "consumed" and not w["terminated"]'
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
