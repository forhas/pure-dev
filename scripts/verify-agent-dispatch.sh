#!/usr/bin/env bash
# Every review seat in these plugins is filled by a separate agent — unless the
# user forbade it.
#
# `plan-review`, the local review loop, and the completeness verifier all exist
# to get a reader who is not the party that believes the work is done. A session
# carrying a standing rule of the shape "do not dispatch subagents unless the
# user asks" reads that rule as forbidding the dispatch, fills the seat itself,
# and emits `clean` — a verdict no independent party ever produced. The failure
# is silent: the output block parses, the caller proceeds, and nothing
# downstream can tell a real review from a self-review.
#
# So every skill that dispatches a review agent must say three things, and this
# harness pins them: the dispatch is mandatory; invoking the skill *is* the
# request a generic no-subagents rule asks for; and the single carve-out — an
# explicit user prohibition — takes that seat's own no-agent path (degrade, or
# stop before the merge) rather than a self-review.
#
# The execution delegations are the deliberate exception, also pinned here: their
# subagents buy context hygiene, not independence, so they may be substituted.
#
# These are standing invariants of the skills, not change-scoped checks, so this
# harness carries no version floor to go stale.
#
# Run from anywhere: ./scripts/verify-agent-dispatch.sh
set -uo pipefail
cd "$(dirname "$0")/.."

fails=0

ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# Assertions come from the shared library, like every other harness here.
# (cd to the repo root already happened above, so this path is stable.)
. ./scripts/lib/assert.sh

plugin_of() { basename "$(dirname "$(dirname "$(dirname "$1")")")"; }

# ---------------------------------------------------------------------------
# plan-review — the pre-implementation seat
# ---------------------------------------------------------------------------
# Both plugins ship a fork of this skill. They are deliberate forks, not mirrors,
# but this invariant is the same in both — so each set below is walked, never
# listed, and a third plugin adding one of these skills is checked the day it
# lands.
plan_reviews=0
for S in plugins/*/skills/plan-review/SKILL.md; do
  [ -f "$S" ] || continue
  plan_reviews=$((plan_reviews + 1))
  n=$(plugin_of "$S")
  L=$(total_lines "$S")

  echo "== $n plan-review dispatch =="

  assert_present "$n: the dispatch is one \`general-purpose\` agent, synchronously" \
    "$S" 1 "$L" 'Dispatch \*\*one\*\* `general-purpose` agent, \*\*synchronously\*\*'

  assert_present "$n: invoking the skill is itself the request for that agent" \
    "$S" 1 "$L" '\*\*Invoking this skill \*is\* the request for that agent\.\*\*'

  assert_present "$n: a standing no-subagents rule does not skip the dispatch" \
    "$S" 1 "$L" 'do not dispatch subagents unless the user asks for one'

  assert_present "$n: reviewing the plan yourself is never the fallback" \
    "$S" 1 "$L" 'Reviewing it yourself is never the fallback'

  assert_present "$n: the only carve-out is a prohibition the user stated explicitly" \
    "$S" 1 "$L" '\*\*Unless the user explicitly disallowed it\.\*\*'

  assert_present "$n: a forbidden dispatch neither retries nor substitutes itself" \
    "$S" 1 "$L" 'Then do not retry, and do not substitute yourself'

  assert_present "$n: a forbidden dispatch emits the degraded block" \
    "$S" 1 "$L" '`PLAN-REVIEW: degraded` per \*\*Degradation\*\* below'

  assert_present "$n: the prohibition is named on the unresolved line of the block" \
    "$S" 1 "$L" 'name the prohibition on the `UNRESOLVED:` line'

  assert_present "$n: the report says plainly that the plan went unreviewed" \
    "$S" 1 "$L" 'say plainly in the report that the plan went unreviewed'

  assert_present "$n: a forbidden dispatch still lets the build proceed" \
    "$S" 1 "$L" 'The build still proceeds\.'

  assert_present "$n: the status row for \`degraded\` names the disallowed dispatch" \
    "$S" 1 "$L" '^\| `degraded` \| reviewer unavailable after one retry, or the dispatch explicitly disallowed by the user'

  # Order is the mechanism, not decoration: the carve-out has to read as an
  # exception to a mandate already stated, and it has to point at a degradation
  # rule that follows it. A carve-out hoisted above the mandate inverts the
  # default this whole file exists to hold.
  assert_order "$n plan-review: the mandate precedes its rationale precedes the carve-out precedes degradation" \
    "$S" 1 "$L" \
    "dispatch mandate"   'Dispatch \*\*one\*\* `general-purpose` agent' \
    "request rationale"  '\*\*Invoking this skill \*is\* the request' \
    "explicit carve-out" '\*\*Unless the user explicitly disallowed it\.\*\*' \
    "degradation rule"   '^\*\*Degradation\.\*\* If the agent fails'
done

# ---------------------------------------------------------------------------
# review-and-merge — the local reviewer and the completeness verifier
# ---------------------------------------------------------------------------
rms=0
for S in plugins/*/skills/review-and-merge/SKILL.md; do
  [ -f "$S" ] || continue
  rms=$((rms + 1))
  n=$(plugin_of "$S")
  L=$(total_lines "$S")

  echo "== $n review-and-merge dispatch =="

  assert_present "$n: the skill states the rule for the agents it dispatches" \
    "$S" 1 "$L" '^### Dispatching this skill.s agents$'

  assert_present "$n: both seats exist for independence from the party that believes the work is done" \
    "$S" 1 "$L" 'independence from the party that believes the work is done. Whoever runs this skill'

  assert_present "$n: filling a seat yourself is the absence of the check" \
    "$S" 1 "$L" 'it is the absence of the check, reported as the check'

  assert_present "$n: invoking the skill is itself the request for those agents" \
    "$S" 1 "$L" '\*\*Invoking this skill is the request for those agents\.\*\*'

  assert_present "$n: a standing no-subagents rule does not skip a dispatch" \
    "$S" 1 "$L" 'do not dispatch subagents unless the user asks for one'

  assert_present "$n: the only carve-out is a prohibition the user stated explicitly" \
    "$S" 1 "$L" '\*\*Unless the user explicitly disallowed it\*\* —'

  assert_present "$n: a forbidden reviewer dispatch stops before the merge" \
    "$S" 1 "$L" '\*\*stop before the merge\*\* and report the prohibition as the reason'

  assert_present "$n: the merge never rests on your own reading of the diff" \
    "$S" 1 "$L" 'Never merge on your own reading of the diff'

  assert_present "$n: a forbidden verifier dispatch takes the degradation path" \
    "$S" 1 "$L" 'every criterion counted in `CRITERIA-UNVERIFIED`, the prohibition as its reason'

  assert_present "$n: a degraded completeness result never resolves to \`clean\`" \
    "$S" 1 "$L" 'It never resolves to `clean`'

  assert_present "$n: the final report names the unfilled seat and the prohibition" \
    "$S" 1 "$L" 'name the unfilled seat and the prohibition in the final report'

  # The subsection governs the two loops below it, so it has to come first, and
  # the reviewer's stop has to precede the verifier's degradation — the two paths
  # are deliberately different and a reader who meets them out of order will take
  # the wrong one.
  assert_order "$n review-and-merge: the rule precedes both seats and precedes the loop it governs" \
    "$S" 1 "$L" \
    "dispatch rule heading" '^### Dispatching this skill.s agents$' \
    "request rationale"     '\*\*Invoking this skill is the request for those agents\.\*\*' \
    "explicit carve-out"    '\*\*Unless the user explicitly disallowed it\*\* —' \
    "reviewer stop"         '\*\*stop before the merge\*\* and report the prohibition as the reason' \
    "verifier degradation"  'every criterion counted in `CRITERIA-UNVERIFIED`, the prohibition as its reason' \
    "local review loop"     '^### Local review loop \(reviewer unavailable\)$'
done

# ---------------------------------------------------------------------------
# The callers — review seats point at the rule; execution delegations may substitute
# ---------------------------------------------------------------------------
echo "== callers =="

DEV=plugins/quick-dev/skills/develop/SKILL.md
L=$(total_lines "$DEV")
assert_present "develop: local mode points at the dispatch rule instead of restating it" \
  "$DEV" 1 "$L" '\*\*### Dispatching this skill.s agents\*\* governs'
assert_present "develop: a disallowed dispatch stops the phase rather than self-reviewing" \
  "$DEV" 1 "$L" 'stops this phase rather than turning it into a self-review'
assert_present "develop: the execution delegation is the one substitutable dispatch" \
  "$DEV" 1 "$L" 'is the one place in this flow that may substitute'
assert_present "develop: execution subagents buy throughput, not independence" \
  "$DEV" 1 "$L" 'buy context hygiene and throughput, not independence'
assert_present "develop: the review seats never substitute the same way" \
  "$DEV" 1 "$L" 'The review seats never substitute this way'

TK=plugins/notion-dev/commands/ticket.md
L=$(total_lines "$TK")
assert_present "ticket: the execution delegation is the one substitutable dispatch" \
  "$TK" 1 "$L" 'is the one place in this command that may substitute'
assert_present "ticket: execution subagents buy throughput, not independence" \
  "$TK" 1 "$L" 'buy context hygiene and throughput, not independence'
assert_present "ticket: the review seats never substitute the same way" \
  "$TK" 1 "$L" 'The review seats never substitute this way'

echo "== dispatch set =="
if [ "$plan_reviews" -gt 0 ]; then
  ok "$plan_reviews plan-review skill(s) checked (discovered by glob, never listed)"
else
  bad "no plugins/*/skills/plan-review/SKILL.md found — the set cannot be empty"
fi
if [ "$rms" -gt 0 ]; then
  ok "$rms review-and-merge skill(s) checked (discovered by glob, never listed)"
else
  bad "no plugins/*/skills/review-and-merge/SKILL.md found — the set cannot be empty"
fi

if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
fi
exit $(( fails > 0 ? 1 : 0 ))
