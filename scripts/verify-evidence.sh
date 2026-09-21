#!/usr/bin/env bash
# Standing invariants for evidence reuse, bounded delta indexes, verification receipts,
# host publication probes, and the generic evaluation fixture.
#
# WHY A SEPARATE HARNESS
#
# verify-runtime.sh pins the lifecycle protocol: prepare, attach, consume, accept,
# merge. This one pins the things that decide how much WORK a second review round
# costs, and they fail in a different direction. A lifecycle defect blocks a merge and
# somebody notices. An evidence defect makes a "delta" quietly re-investigate
# everything and still pass every gate: the run is correct and three times the price,
# which no existing assertion can see.
#
# So the invariants here are about what is CARRIED FORWARD and what is REFERENCED
# rather than copied, plus the two directions every reuse mechanism has to keep:
# reuse happens when it is applicable, and never when it is not.
set -uo pipefail
cd "$(dirname "$0")/.."

fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# shellcheck source=lib/assert.sh
. ./scripts/lib/assert.sh

PYBIN=${KNOWLEDGE_PY:-python3}
ND=plugins/notion-dev
RT=$ND/scripts/runtime.py
TM=$ND/scripts/telemetry.py
PROTOCOL=$ND/references/runtime.md
CONVERGENCE=$ND/references/convergence.md
REVIEW=$ND/skills/review-and-merge/SKILL.md
EVAL=scripts/fixtures/evaluation

echo "== behavioural fixtures =="
if PYTHONDONTWRITEBYTECODE=1 $PYBIN scripts/tests/test_runtime_evidence.py; then
  ok "offline evidence, delta index, verification receipt and probe fixtures"
else
  bad "offline evidence, delta index, verification receipt and probe fixtures"
fi
if PYTHONDONTWRITEBYTECODE=1 $PYBIN scripts/tests/test_evaluation_fixture.py; then
  ok "the evaluation fixture's seeded defects are still defects"
else
  bad "the evaluation fixture's seeded defects are still defects"
fi

echo "== evidence is ingested per item, and completeness is still required =="
assert_has "runtime.py ingests one requirement at a time" \
  "$RT" 'resolve each requirement at most once per call'
assert_lacks "runtime.py no longer discards a partial resolution" \
  "$RT" 'resolve every requirement exactly once'
assert_has "runtime.py refuses a citation for an unknown requirement" \
  "$RT" 'citation resolves an unknown requirement'
# Partial INGESTION must not become a partial GATE: this is the line that keeps the
# two apart, and deleting it is the one change that would make the relaxation unsafe.
assert_has "the merge gate still requires every requirement resolved" \
  "$RT" 'parent citation resolution is incomplete'
assert_has "the merge gate blocks on a changed evidence dependency" \
  "$RT" 'evidence dependency changed'
assert_has "the merge gate blocks on a missing evidence dependency" \
  "$RT" 'evidence dependency is missing'
assert_has "a declared dependency must be a real file when it is recorded" \
  "$RT" 'evidence dependency must be an existing file'
assert_has "applicability has a blocked state for a verdict that was never met" \
  "$RT" "not 'met'"

echo "== the delta index references, and never inlines =="
assert_has "runtime.py bounds the index at INDEX_BYTES" "$RT" 'INDEX_BYTES = 2048'
assert_lacks "the index no longer carries the previous result inline" "$RT" 'previous_result'
assert_lacks "the index no longer carries the previous citations inline" "$RT" 'previous_citations'
assert_has "the previous report is a hash-bound reference" "$RT" '"previous-report.json"'
assert_has "shortening a list names it in sections.incomplete" "$RT" 'incomplete.append(name)'
# One page can still exceed the budget on its own, so the cut has to be able to go
# below a page. Without this the index silently ships over budget, which is how a
# "bounded" index stops being bounded on exactly the wide changes it exists for.
assert_has "an oversized list halves past one page rather than shipping over budget" \
  "$RT" 'index[name][:min(page, length // 2)]'
assert_has "the index reports whether it fit its budget" "$RT" '"within_budget"'
assert_has "paged retrieval refuses a page past the end" "$RT" 'section page is past the end'
assert_has "publication rehashes the delta sections file" "$RT" 'delta sections changed'
assert_has "publication rehashes the delta input index" "$RT" 'delta input index changed'
assert_has "publication rehashes the previous report" "$RT" 'previous report changed'
assert_has "publication rehashes the evidence index" "$RT" 'evidence index changed'

echo "== verification receipts are reused only while they apply =="
assert_has "runtime.py decides applicability in one place" "$RT" 'def receipt_applicable'
assert_has "a moved revision is not reusable" "$RT" 'revision changed since this receipt'
assert_has "an edited log is not reusable" "$RT" 'verification log changed after the run'
assert_has "a tree-modifying command is not reusable" "$RT" 'the command modified the tree it verified'
assert_has "a changed toolchain signature is not reusable" "$RT" 'toolchain signature changed or unrecorded'
# The signature is four named facts. Hashing the environment would put credentials in
# durable state AND invalidate every receipt on an unrelated variable.
assert_has "the environment signature is four named toolchain facts" "$RT" '"os_name": os.name'
assert_lacks "the environment itself is never hashed into state" "$RT" 'dict(os.environ)'
RTL=$(total_lines "$RT")
assert_present "reuse is refused for a nonzero exit as well as an inapplicable receipt" \
  "$RT" 1 "$RTL" 'receipt\["exit_code"\] != 0'

echo "== the publication probe can fail =="
assert_has "probe distinguishes a truncated delivery from a mangled one" "$RT" '"truncated" if expected.startswith(received)'
assert_has "probe reports a missing result rather than passing" "$RT" '"missing" if result is None'
assert_has "probe passes only on an exact byte match" "$RT" '"passed": finding == "delivered"'
assert_has "probe refuses a worker of another role" "$RT" 'publication probes use the probe role'

echo "== provider outcomes are recorded, never performed here =="
assert_has "the five record outcomes are a closed set" \
  "$RT" 'RECORD_OUTCOMES = ("planned", "attempted", "confirmed", "unknown-outcome", "failed")'
assert_has "an invalid outcome is refused" "$RT" 'invalid record operation outcome'
assert_has "summary surfaces every operation that is not confirmed" "$RT" 'unconfirmed_record_operations'

echo "== telemetry attributes children, and says what it could not attribute =="
assert_has "telemetry builds a worker roster from the runtime state" "$TM" 'def roster(state)'
assert_has "telemetry matches child logs to workers by host agent ID" "$TM" 'def correlate(workers, logs)'
assert_has "an ambiguous containment match is not evidence" "$TM" 'if len(candidates) == 1 else None'
assert_has "a worker with no log is unknown cost, never zero" "$TM" 'unknown cost, never zero'
assert_has "an unmatched log is reported rather than absorbed" "$TM" '"unmatched_logs"'
# Peaks are concurrent scopes. Summing them describes a window no request ever held.
assert_has "peaks are reported separately and never summed" "$TM" 'peaks are never summed'
assert_has "summary names its own scope instead of implying whole-run totals" "$RT" 'unknown, not zero'

echo "== the protocol documents each new command =="
assert_has "protocol documents per-item citation resolution" "$PROTOCOL" 'Ingestion is per item'
assert_has "protocol documents the \`depends_on\` obligation" "$PROTOCOL" '`depends_on` is how a receipt goes stale'
assert_has "protocol documents the \`evidence\` index command" "$PROTOCOL" 'evidence --worker <worker>'
assert_has "protocol documents paged \`section\` retrieval" "$PROTOCOL" 'section --worker <worker> --name changed_paths'
assert_has "protocol documents the \`verifications\` index" "$PROTOCOL" 'verifications --worktree <absolute-worktree>'
assert_has "protocol documents \`verify --reuse\`" "$PROTOCOL" '`verify --reuse` returns an applicable passing receipt'
assert_has "protocol documents the \`probe\` command" "$PROTOCOL" 'probe --worker <worker> --expect <payload-file>'
assert_has "protocol documents \`record-op\` outcomes" "$PROTOCOL" 'record-op --operation <stable-logical-id>'
assert_has "protocol documents the \`correction-needed\` reason" "$PROTOCOL" 'correction-needed --worktree <worktree> --reason'
assert_has "protocol says an unread page is not complete input" \
  "$PROTOCOL" '**No truncated section and no unread page is complete input.**'
assert_has "protocol says a reuse candidate is not a verdict" "$PROTOCOL" 'marks a **reuse candidate**, not a'
PL=$(total_lines "$PROTOCOL")
assert_present "protocol says reuse is a stated choice, never a silent cache" \
  "$PROTOCOL" 1 "$PL" 'never a silent cache'

echo "== the review skill resolves evidence at the boundary =="
assert_has "review resolves citations when the result is consumed" \
  "$REVIEW" 'resolve every citation it supports'
assert_has "review reads the returned unresolved list" "$REVIEW" '`unresolved` list'
assert_has "review pages a section the index marked incomplete" "$REVIEW" 'section --name <list> --page <n>'
assert_has "review keeps reuse-applicable a candidate set" "$REVIEW" 'is a candidate set, never a verdict'

echo "== the slice claims nothing it has not measured =="
assert_has "convergence records the live-host disposition as blocked" \
  "$CONVERGENCE" '**Disposition: `blocked`** — the host publication probe'
assert_has "convergence claims no token or time improvement yet" \
  "$CONVERGENCE" 'No token or time improvement is claimed here'
assert_has "convergence keeps partial ingestion out of the gate" \
  "$CONVERGENCE" 'never whether it is complete'

echo "== the evaluation fixture stays a fixture =="
assert_has "the candidate declares that its defects are deliberate" \
  "$EVAL/project/scheduler.py" 'THIS FILE CARRIES SEEDED DEFECTS ON PURPOSE'
assert_has "the candidate says not to fix it" "$EVAL/project/scheduler.py" 'Do not "fix" this file'
assert_has "the fixture carries no client source, only defect classes" \
  "$EVAL/project/scheduler.py" 'Nothing here is derived from any client'
assert_has "the README refuses an in-place candidate run" \
  "$EVAL/README.md" 'Never run a candidate workflow against this directory in place'
assert_has "the README refuses a git checkout to undo a run" "$EVAL/README.md" 'git checkout -- .'
assert_has "the README scores quality before cost" "$EVAL/README.md" 'A cheaper run that missed a defect is not'
for finding in concurrency-limit memoization-key config-validation \
               lookup-reduction-claim misleading-checkbox constraint-outside-acceptance; do
  assert_has "expected-findings.json declares $finding" "$EVAL/expected-findings.json" "\"id\": \"$finding\""
done
assert_has "the oracle is selected by EVAL_SCHEDULER, not by a hardcoded path" \
  "$EVAL/oracle/test_scheduler.py" 'os.environ["EVAL_SCHEDULER"]'

echo
if [ "$fails" -eq 0 ]; then
  echo "verify-evidence: all PASS"
else
  echo "verify-evidence: $fails FAIL"
fi
exit $((fails > 0))
