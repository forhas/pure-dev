#!/usr/bin/env bash
# Historical contracts below cover opt-in legacy flows; verify-lean-workflow.sh covers the new default.
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

  if [ "$n" = notion-dev ]; then
    assert_has "$n: dispatch uses the runtime protocol" "$S" 'references/runtime.md'
    assert_has "$n: dispatch consumes a completed result" "$S" 'prepare/attach/wait/consume'
  else
    assert_present "$n: the dispatch is one \`general-purpose\` agent, synchronously" \
      "$S" 1 "$L" 'Dispatch \*\*one\*\* `general-purpose` agent, \*\*synchronously\*\*'
  fi

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
  [ "$n" != notion-dev ] || S=plugins/notion-dev/references/legacy/review-and-merge.md
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

  # The sweep's own reviewer-unavailable branch says an unreviewable batch merges anyway.
  # Read as covering a *prohibited* reviewer it would override the stop above, which is the
  # one outcome the rule exists to prevent — so the branch has to disclaim that reading.
  assert_present "$n: a prohibited reviewer is not the sweep-s unavailable reviewer" \
    "$S" 1 "$L" 'A local reviewer the user prohibited is not "unavailable" in that sense'
  assert_present "$n: the sweep branch does not override the stop before the merge" \
    "$S" 1 "$L" 'stops before the merge and this branch does not override it'

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
# The two seats take DIFFERENT no-agent paths, and a pointer that flattens them into one
# contradicts the subsection it cites. Pin both halves, not the sentence.
assert_present "develop: the reviewer seat stops the phase rather than self-reviewing" \
  "$DEV" 1 "$L" 'the reviewer seat stops this phase rather than turning it into a self-review'
assert_present "develop: the completeness checker takes the degraded path instead of stopping" \
  "$DEV" 1 "$L" 'the completeness checker takes the degraded path step 4 already mirrors'
assert_present "develop: the execution delegation is the one substitutable dispatch" \
  "$DEV" 1 "$L" 'is the one place in this flow that may substitute'
assert_present "develop: execution subagents buy throughput, not independence" \
  "$DEV" 1 "$L" 'buy context hygiene and throughput, not independence'
assert_present "develop: the review seats never substitute the same way" \
  "$DEV" 1 "$L" 'The review seats never substitute this way'
# The plan-review CALL SITE, not just the skill — the same gap #34 closed in notion-dev's
# ticket.md 4.2(b). `../plan-review/SKILL.md` Step 2 states that invoking it *is* the request
# for its agent, and only a run that invokes the skill can read that: a run that decides at
# step 3 not to invoke never sees it. Pinned here, or deleting the mandate leaves every
# harness green while a session carrying a standing no-subagents default skips the seat and
# self-reviews.
assert_present "develop: reaching step 3 is itself the request for plan-review's agent" \
  "$DEV" 1 "$L" 'Reaching this step is itself the request for that agent'
assert_present "develop: a standing no-subagents rule is satisfied by the user invoking the skill" \
  "$DEV" 1 "$L" 'already satisfied by the user invoking'
assert_present "develop: reviewing the plan yourself is never the substitute" \
  "$DEV" 1 "$L" '\*\*Never review the plan yourself instead\.\*\*'
assert_present "develop: a forbidden dispatch emits \`PLAN-REVIEW: degraded\` and reports the plan unreviewed" \
  "$DEV" 1 "$L" 'emits `PLAN-REVIEW: degraded`, and the final report must say plainly that the plan went unreviewed'
# Without the narrow reading, the step-5 exemption swallows the rule: a host- or session-level
# default reads as "explicitly disallowed" and the whole flow self-executes.
assert_present "develop: \"explicitly disallowed\" is an instruction aimed at this dispatch, not a general default" \
  "$DEV" 1 "$L" '\*\*"Explicitly disallowed" means an instruction aimed at this dispatch'

TK=plugins/notion-dev/references/legacy/ticket.md
L=$(total_lines "$TK")
# The call site, not just the skill. `plan-review/SKILL.md` Step 2 already states that
# invoking it *is* the request for its agent — and only a run that invokes the skill can
# read that. A run that decides at this step not to invoke never sees it, so the mandate
# has to be pinned here too, or deleting it leaves every harness green.
#
# Cited twice on purpose (`assert_count`, not a region-scoped `assert_present`): Phase
# 8's record-unit dispatch (Task 9) makes the identical mandate argument for its own,
# unrelated agent — reaching that step is that dispatch's request too, for the same
# reason (a standing no-subagents default must not silently skip it). Two genuine sites
# for one mechanism, re-checked in both directions: this goes red if either drops the
# sentence, or if a third copy appears unaccounted for.
assert_count "ticket: 'reaching this step is itself the request for that agent' is cited for both mandatory dispatches (plan-review, the record-unit)" \
  "$TK" 1 "$L" 'Reaching this step is itself the request for that agent' 2
assert_present "ticket: a standing no-subagents rule is already satisfied by reaching the step" \
  "$TK" 1 "$L" 'already satisfied by reaching here'
assert_present "ticket: reviewing the plan yourself is never the substitute" \
  "$TK" 1 "$L" '\*\*Never review the plan yourself instead\.\*\*'
assert_present "ticket: a self-review is the absence of the check, reported as the check" \
  "$TK" 1 "$L" 'the absence of the check, reported as the check'
assert_present "ticket: a forbidden dispatch emits \`PLAN-REVIEW: degraded\` and reports the plan unreviewed" \
  "$TK" 1 "$L" 'emits `PLAN-REVIEW: degraded`, and the final report must say plainly that the plan went unreviewed'

# Was "is the one place in this command that may substitute" — Task 9's Phase 8
# record-unit dispatch made that a false uniqueness claim (there are now two such
# places), so 4.2's sentence was rewritten to name the class and cross-reference
# Phase 8 instead of counting members. Retitled and repointed to match.
assert_present "ticket: this delegation may substitute, naming the record-unit dispatch as the same class rather than counting members" \
  "$TK" 1 "$L" 'this delegation may substitute — as may Phase 8.s record-unit dispatch, the same class for the same reason'
assert_present "ticket: the substitution carve-out reaches only a prohibition aimed at this dispatch" \
  "$TK" 1 "$L" 'means an instruction aimed at this dispatch'
assert_present "ticket: execution subagents buy throughput, not independence" \
  "$TK" 1 "$L" 'buy context hygiene and throughput, not independence'
assert_present "ticket: the review seats never substitute the same way" \
  "$TK" 1 "$L" 'The review seats never substitute this way'

# A DISPATCHED FLOW UNIT DISPATCHES NOTHING IT MUST WAIT ON.
# The proxy respondent exists to keep the agent that wrote a review finding out of the
# interview seat. A dispatched record unit never wrote it — it got the packet second-hand —
# so the proxy buys it nothing, and costs it the run: a dispatched agent has no *waiting*
# state, so it ends with no `RECORD:` block, the caller reads that as a dispatch failure and
# recovers inline, and the grandchildren deliver after the run is over. Measured twice on
# notion-dev 0.29.0 in a client (`unexpected:record-unit-not-dispatched`). The rule is one
# flag threaded through four files, so each hop is pinned separately: a hop that goes quiet
# silently restores the nested dispatch.
CT=plugins/notion-dev/commands/create-task.md; CTL=$(total_lines "$CT")
RC=plugins/notion-dev/references/legacy/record.md;     RCL=$(total_lines "$RC")
EU=plugins/notion-dev/skills/epic-update/references/with-followups.md; EUL=$(total_lines "$EU")
assert_present "create-task: the \`--no-proxy\` flag answers Phase 2.1 from the \`--context-file\` packet instead of dispatching a proxy respondent" \
  "$CT" 1 "$CTL" '`--no-proxy` \| Answer Phase 2\.1.s interview from `--context-file`.s packet directly, in this agent, instead of dispatching a proxy-respondent subagent'
assert_present "create-task: a dispatched agent has no waiting state, so a grandchild proxy leaves no \`RECORD:\` block" \
  "$CT" 1 "$CTL" 'A dispatched agent has no way to be \*waiting\*.*emitted no `RECORD:` block at all'
assert_present "create-task: only a dispatched flow unit passes \`--no-proxy\`; the inline paths keep the proxy respondent" \
  "$CT" 1 "$CTL" 'a dispatched flow unit passes `--no-proxy`.*inline paths.*do \*\*not\*\* pass it, and keep the proxy respondent'
# A carve-out stated once, beside three operational instructions that still say "dispatch",
# is the nested dispatch with a paragraph next to it. Caught as a P1 on this PR's round 2.
# Every site that tells the agent to dispatch the proxy is conditioned, and pinned separately.
assert_present "create-task: the phase table row conditions the proxy on \`--no-proxy\` being absent" \
  "$CT" 1 "$CTL" '\| 2\.1 interview \|.*proxy-respondent subagent.*unless `--no-proxy`'
assert_present "create-task: the dispatch instruction itself is conditioned on \`--no-proxy\`" \
  "$CT" 1 "$CTL" 'Unless `--no-proxy` was supplied.*dispatch the subagent with the context packet'
assert_present "create-task: Phase 2.1's non-interactive routing names the \`--no-proxy\` exception" \
  "$CT" 1 "$CTL" "In \*\*non-interactive mode\*\*, the interviewer.s questions go to the proxy-respondent subagent.*unless \`--no-proxy\` was supplied"
# The completeness gate caught the prose naming the wrong mechanism for the second inline path:
# finalize never reads record.md at all. The behaviour was right and the sentence was not, which
# is exactly the class that rots into a wrong fix later.
assert_has "create-task: lean inline callers share record without the dispatched-unit exemption" \
  "$CT" 'The lean ticket and finalize both run `references/record.md` inline.'
# The hint is the user-visible flag list; a table counting eight beside a hint listing seven is
# the kind of drift nobody reads until it is wrong in a client.
assert_present "create-task: the \`argument-hint\` frontmatter lists \`--no-proxy\` with the other flags" \
  "$CT" 1 "$CTL" '^argument-hint:.*\[--provenance=<marker>\] \[--no-proxy\]' 
assert_present "record: passes \`NO_PROXY: true\` exactly when the caller passed \`DISPATCHED: true\`" \
  "$RC" 1 "$RCL" 'pass `NO_PROXY: true` whenever the caller passed `DISPATCHED: true`'
assert_present "ticket: the record-unit dispatch carries \`DISPATCHED: true\` and the inline recovery omits it" \
  "$TK" 1 "$L" '`DISPATCHED: true`.*inline recovery path below omits it and keeps the proxy'
assert_present "epic-update: includes \`--no-proxy\` exactly when the caller passed \`NO_PROXY: true\`, never otherwise" \
  "$EU" 1 "$EUL" 'Include `--no-proxy` exactly when the caller passed `NO_PROXY: true`\*\*, and never otherwise'
# Position is the whole of this one: create-task parses flags off the FRONT of the argument
# string, so a flag trailing `prompt:` is prompt text and the mode never activates. Caught as a
# P1 on this PR's own round 1, against a template that read correctly everywhere else.
assert_present "epic-update: the template puts \`--no-proxy\` before the \`prompt:\` argument, where flags are parsed" \
  "$EU" 1 "$EUL" '\[--no-proxy\] prompt:<finding title>'

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
