#!/usr/bin/env bash
# The mechanisms the client issue logs forced into these plugins.
#
# `notion-dev:issue-log` writes a runtime deviation into every client repo at the
# moment it happens; `feedback-harvest` reads those logs and applies what is
# warranted. Each assertion below pins one mechanism that a *measured* client
# failure put there — not a phrasing someone liked, but the specific rule whose
# absence a real run demonstrated.
#
# WHY THESE NEED A HARNESS AT ALL
#
# Every one of them is a rule about a case that looks like a non-event. A
# contentless agent report reads as an agent with nothing to say; an empty
# `requested_reviewers` reads as a request that never landed; a `--body` of `@-`
# exits 0. Text that guards a silent failure is exactly the text a later edit
# trims as noise, because nothing visibly breaks when it goes. The client log
# that recorded each one is reset after its harvest, so once these lines are gone
# there is no artifact left that would notice.
#
# These are standing invariants of the skills, not change-scoped checks, so this
# harness carries no version floor to go stale. Both plugins are walked rather
# than listed: `notion-dev` vendors adapted forks of several `quick-dev` skills,
# and where a fix touched shared behaviour it landed in both, so a third plugin
# adding one of these skills is checked the day it lands.
#
# Run from anywhere: ./scripts/verify-runtime-feedback.sh
set -uo pipefail
cd "$(dirname "$0")/.."

fails=0

ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# Assertions come from the shared library, like every other harness here.
. ./scripts/lib/assert.sh

plugin_of() { basename "$(dirname "$(dirname "$(dirname "$1")")")"; }

# ---------------------------------------------------------------------------
# A zero-byte agent result is its own failure shape
# ---------------------------------------------------------------------------
# Measured across five occurrences in one client, up to the current plugin
# version: dispatched subagents signalled idle with no payload at all. Every
# dispatch site described its failure as output that "lacks the required
# sections", which does not cover an empty result — so a caller reading "agent
# went idle" as "agent finished" records a review that never happened.
#
# The nudge that recovers it is the subtle half. One run recovered six seats for
# six with a single follow-up message; another, same host and version, recovered
# neither of two. So the nudge is mandatory AND insufficient, and a rule that
# states only the first half is worse than none — it licenses "nudge once, then
# trust the result", which converts this condition into a false clean.
zero_byte_sites=0
for S in plugins/*/skills/plan-review/SKILL.md plugins/*/skills/flow-triage/SKILL.md; do
  [ -f "$S" ] || continue
  zero_byte_sites=$((zero_byte_sites + 1))
  n=$(plugin_of "$S")
  k=$(basename "$(dirname "$S")")
  L=$(total_lines "$S")

  echo "== $n $k — zero-byte agent result =="

  assert_present "$n $k: a zero-byte result is its own failure shape, not a malformed one" \
    "$S" 1 "$L" 'A zero-byte result is its own failure shape — not a malformed one'

  assert_present "$n $k: an empty result is not covered by a missing-or-malformed check" \
    "$S" 1 "$L" 'does not cover an empty result at all'

  assert_present "$n $k: the remedy is one follow-up message restating the output format" \
    "$S" 1 "$L" '\*\*send one follow-up message\*\* restating the required output format'

  assert_present "$n $k: the reply body is named as the deliverable" \
    "$S" 1 "$L" 'the reply body is the deliverable'

  assert_present "$n $k: the nudge is not a remedy and must not be treated as one" \
    "$S" 1 "$L" '\*\*The nudge is not a remedy, and must never be treated as one\.\*\*'

  assert_present "$n $k: the two conditions are indistinguishable when they fail" \
    "$S" 1 "$L" '\*\*indistinguishable at the moment of failure\*\*'

  assert_present "$n $k: a still-empty result after the nudge is a failure, never a clean verdict" \
    "$S" 1 "$L" 'treat a still-empty result as the failure it is'

  assert_present "$n $k: going idle is never read as finishing successfully" \
    "$S" 1 "$L" 'Never read "the agent went idle" as "the agent finished'

  # Order is the mechanism: the nudge has to read as a step inside the failure
  # handling, and the "not a remedy" warning has to follow the nudge it qualifies.
  # Hoisted above it, the warning reads as advice against nudging at all.
  assert_order "$n $k: the failure shape and its nudge precede the warning that the nudge is no remedy" \
    "$S" 1 "$L" \
    "failure shape and nudge" 'A zero-byte result is its own failure shape' \
    "no remedy"               '\*\*The nudge is not a remedy'
done

[ "$zero_byte_sites" -ge 4 ] \
  && ok "every plan-review and flow-triage seat was checked ($zero_byte_sites)" \
  || bad "expected at least 4 zero-byte dispatch sites, walked $zero_byte_sites"

# The retry conditions themselves must admit the empty case, or the paragraphs
# above guard a branch the control flow never reaches.
for S in plugins/*/skills/plan-review/SKILL.md; do
  [ -f "$S" ] || continue
  n=$(plugin_of "$S"); L=$(total_lines "$S")
  assert_present "$n plan-review: the degradation trigger names returning nothing at all" \
    "$S" 1 "$L" 'If the agent fails, returns nothing at all, or its output is unusable'
done
for S in plugins/*/skills/flow-triage/SKILL.md; do
  [ -f "$S" ] || continue
  n=$(plugin_of "$S"); L=$(total_lines "$S")
  assert_present "$n flow-triage: the scout retry trigger names returning nothing at all" \
    "$S" 1 "$L" 'If the scout fails, returns nothing at all, or its output lacks'
done

# ---------------------------------------------------------------------------
# flow-triage — a failed scout does not discard findings the caller already holds
# ---------------------------------------------------------------------------
# The degradation path assumes nothing else is known. On tickets whose gate
# involves empirical probing the caller has usually already established the
# affected files by direct reads, and nulling those dimensions pushed a
# well-evidenced ticket into the gray zone on a technicality.
for S in plugins/*/skills/flow-triage/SKILL.md; do
  [ -f "$S" ] || continue
  n=$(plugin_of "$S"); L=$(total_lines "$S")
  echo "== $n flow-triage — scout failure with findings in hand =="

  assert_present "$n flow-triage: a scout failure with findings in hand is a distinct case" \
    "$S" 1 "$L" 'the caller already holds equivalent findings'

  assert_present "$n flow-triage: a dimension the caller answered directly is scored, not nulled" \
    "$S" 1 "$L" '\*\*score that dimension from them\*\*'

  assert_present "$n flow-triage: the substitution is recorded on the DRIFT line" \
    "$S" 1 "$L" '`DRIFT:` line as `scout unavailable — scored from caller'

  # The carve-out must not read as licence to invent evidence — an unbounded
  # version of it would let every dimension be scored from nothing.
  assert_present "$n flow-triage: a dimension with no direct finding behind it is still null" \
    "$S" 1 "$L" 'is still `null`'
done

# ---------------------------------------------------------------------------
# review-and-merge — the completeness gate's degradation
# ---------------------------------------------------------------------------
# Every default in that paragraph was stated per criterion, so on a standalone
# run with no criteria file it produced zero items — a gate whose charges 2 and 3
# never ran reported nothing wrong. Measured against a PR body carrying eight
# checkable factual assertions, none read by an independent party.
#
# The correlated-failure rule is the other half: the fallback for a dead reviewer
# is itself a subagent, so on a host where subagent delivery is broken, losing
# the configured reviewer leaves no degradation path at all.
rm_sites=0
for S in plugins/*/skills/review-and-merge/SKILL.md; do
  [ -f "$S" ] || continue
  rm_sites=$((rm_sites + 1))
  n=$(plugin_of "$S"); L=$(total_lines "$S")

  echo "== $n review-and-merge — completeness degradation =="

  assert_present "$n: the degradation is keyed to the failed charge, not to the criteria list" \
    "$S" 1 "$L" '\*\*Key the degradation to which charge failed, not to the criteria list\.\*\*'

  assert_present "$n: per-criterion indexing degrades to a no-op at zero criteria" \
    "$S" 1 "$L" 'silently degrades to a \*\*no-op\*\* when `CRITERIA-TOTAL` is `0`'

  assert_present "$n: charges 2 and 3 are independent of whether any criteria exist" \
    "$S" 1 "$L" 'independent of whether any criteria exist'

  assert_present "$n: an undispatchable verifier raises one item for the charges themselves" \
    "$S" 1 "$L" '\*\*one item for the charges themselves\*\*'

  assert_present "$n: that item is \`blocked\` and names charges 2 and 3 as unrun" \
    "$S" 1 "$L" '`blocked — charges 2 and 3 did not run'

  assert_present "$n: an empty item list on a degraded gate reads as a clean gate" \
    "$S" 1 "$L" 'reports `degraded` with an empty item list, which reads as a clean gate'

  assert_present "$n: the interactive branch carries the charges item at any criteria count" \
    "$S" 1 "$L" 'the charges item above, always and regardless of the criteria count'

  assert_present "$n: the non-interactive branch carries the charges item too" \
    "$S" 1 "$L" 'per criterion \*\*together with the charges item above\*\*'

  assert_present "$n: neither per-mode branch may drop the charges item" \
    "$S" 1 "$L" '\*\*The charges item is never dropped by either branch'

  echo "== $n review-and-merge — reviewer and fallback are correlated =="

  assert_present "$n: a dead reviewer and a dead fallback are not independent conditions" \
    "$S" 1 "$L" '\*\*A dead reviewer and a dead fallback are not independent conditions\.\*\*'

  assert_present "$n: the fallback is itself a dispatched subagent" \
    "$S" 1 "$L" 'the fallback \*is\* a dispatched subagent'

  assert_present "$n: losing both seats stops before the merge instead of self-reading the diff" \
    "$S" 1 "$L" '\*\*stop before the merge and report it\*\* rather than substituting your own'

  # ---------------------------------------------------------------------------
  # review-and-merge — a copilot review that is exclusively a refusal
  # ---------------------------------------------------------------------------
  # The codex branch always had this rule; the copilot branch had only a rule for
  # a rejected *request*. A 2xx review whose body is only an inability-to-review
  # notice therefore matched nothing. Measured in two clients.
  echo "== $n review-and-merge — copilot refusal review =="

  assert_present "$n: a copilot review that is exclusively an inability-to-review notice is a signal" \
    "$S" 1 "$L" 'A \*\*submitted review that is exclusively an inability-to-review notice\*\*'

  assert_present "$n: the exclusivity guard keeps a review carrying findings a normal round" \
    "$S" 1 "$L" 'The \*\*exclusivity guard\*\*: a normal review that merely mentions an error'

  assert_present "$n: a refusal review is \`reason=error\`, never \`not-configured\`" \
    "$S" 1 "$L" '`reason=error`, \*\*not\*\* `not-configured`'

  # ---------------------------------------------------------------------------
  # review-and-merge — an empty requested_reviewers is evidence of nothing
  # ---------------------------------------------------------------------------
  # On some repos the bot is never surfaced under .users[], so the pending check
  # and the POST's own 2xx body both read empty for the whole life of a live
  # request, with no error anywhere. Four rounds across three PRs in one client;
  # one run came within a judgment call of recording not-configured and
  # discarding a working cross-model review.
  echo "== $n review-and-merge — empty requested_reviewers =="

  assert_present "$n: an empty \`requested_reviewers\` is evidence of nothing" \
    "$S" 1 "$L" 'an empty `requested_reviewers` is$'

  assert_present "$n: the neither branch is inconclusive rather than a retry verdict" \
    "$S" 1 "$L" '\*\*Neither is not a verdict\*\* — it is inconclusive, and the'

  assert_present "$n: the neither branch never retries the post on its own" \
    "$S" 1 "$L" 'Do \*\*not\*\* retry the post from this state'

  assert_present "$n: the POST's own 2xx response body carries the same empty array" \
    "$S" 1 "$L" 'the POST.s \*\*own 2xx response body\*\* carries'

  assert_present "$n: \`not-configured\` is never concluded from an absence" \
    "$S" 1 "$L" '\*\*Never conclude `not-configured` from an absence\.\*\*'

  assert_present "$n: the issues timeline is consulted before re-requesting" \
    "$S" 1 "$L" '\*\*Confirm with the issues timeline before re-requesting\.\*\*'

  assert_present "$n: a repo that never lists Copilot cannot use the confirmed-gone test" \
    "$S" 1 "$L" '\*\*On a repo where this endpoint never lists Copilot at all, that "genuinely gone" test is'

  assert_present "$n: the timeline is not a pending marker for the silence rule" \
    "$S" 1 "$L" '\*\*The timeline does not substitute for the pending check here\.\*\*'

  assert_present "$n: an indeterminate pending state polls to the bound instead of re-triggering" \
    "$S" 1 "$L" '\*\*indeterminate, never "confirmed gone"\*\*'

  assert_present "$n: the timeline reviewer login is \`Copilot\`, not the bot form" \
    "$S" 1 "$L" '`Copilot` — note \*\*that\*\* login, not `copilot-pull-request-reviewer'

  assert_count "$n: the timeline read is a \`review_requested\` event on the requested reviewer (the before and after reads)" \
    "$S" 1 "$L" 'select\(\.event == .{0,2}review_requested' 2

  assert_present "$n: the timeline read filters on the \`Copilot\` reviewer login" \
    "$S" 1 "$L" 'select\(\.requested_reviewer\.login == "Copilot"\)'

  assert_present "$n: an unfiltered timeline read is the stale-comment bug in a new place" \
    "$S" 1 "$L" 'correlate with this attempt.s baseline — an unfiltered read is$'

  assert_present "$n: only an event absent from the pre-post snapshot proves this attempt landed" \
    "$S" 1 "$L" 'Non-zero → \*\*this attempt\*\* landed'

  # ---------------------------------------------------------------------------
  # review-and-merge — a poll read that fails is not silence
  # ---------------------------------------------------------------------------
  # The rule existed for the trigger re-read but not at the poll, which is where
  # it was actually violated: a poll is a loop, and the cheapest loop body
  # suppresses its own errors. Measured: silence reported across a full 20-poll
  # window while the review had landed ~5 minutes in.
  echo "== $n review-and-merge — a failed poll read is not silence =="

  assert_present "$n: every poll read must succeed before it is allowed to mean anything" \
    "$S" 1 "$L" '\*\*Every poll read must succeed before it is allowed to mean anything'

  assert_present "$n: a poll read's stderr is never suppressed and never falls through" \
    "$S" 1 "$L" '\*\*Never redirect a poll read.s stderr away'

  assert_present "$n: \`reason=silent\` may only be reached from reads that succeeded" \
    "$S" 1 "$L" '`reason=silent` is a claim that the reviewer did not respond'

  assert_present "$n: the failed-poll-read retry is bounded, or the rule deadlocks the run" \
    "$S" 1 "$L" '\*\*Bound that retry, or this rule deadlocks the run\.\*\*'

  assert_present "$n: a sustained outage would otherwise let neither the silence timeout nor the cap fire" \
    "$S" 1 "$L" 'neither the silence timeout nor the round cap can ever fire'

  assert_present "$n: the bound is 3 retries, then stop and report the API unavailable" \
    "$S" 1 "$L" 'retry a failed poll read at most .{0,4}3 .{0,4}times with a short backoff.*stop and report the API as unavailable'

  # ---------------------------------------------------------------------------
  # review-and-merge — the local review loop's own zero-byte case
  # ---------------------------------------------------------------------------
  assert_present "$n: the local loop discards an empty reviewer output, not only an unusable one" \
    "$S" 1 "$L" 'no parseable findings at all\) \*\*or empty\*\*'

  assert_present "$n: the local loop nudges once before discarding a zero-byte result" \
    "$S" 1 "$L" '\*\*A zero-byte result is its own failure shape\*\*, distinct from a malformed one'
done

[ "$rm_sites" -ge 2 ] \
  && ok "every review-and-merge fork was checked ($rm_sites)" \
  || bad "expected at least 2 review-and-merge forks, walked $rm_sites"

# The pending-request reference carries the same empty-is-not-evidence rule, and
# it is the file the skill points callers at for this check.
for G in plugins/*/skills/review-and-merge/references/github-api.md; do
  [ -f "$G" ] || continue
  n=$(plugin_of "$G"); L=$(total_lines "$G")
  echo "== $n github-api — the pending endpoint may never list Copilot =="

  assert_present "$n github-api: on some repos the endpoint never lists Copilot at all" \
    "$G" 1 "$L" '\*\*On some repos this endpoint never lists Copilot at all\*\*'

  assert_present "$n github-api: a definite \`NOT_PENDING\` is not evidence the request failed" \
    "$G" 1 "$L" '`NOT_PENDING` is therefore \*\*not\*\* evidence the request failed'

  assert_count "$n github-api: the timeline confirms the request landed (the before and after reads)" \
    "$G" 1 "$L" 'select\(\.event == .{0,2}review_requested' 2

  assert_present "$n github-api: the timeline read filters on the \`Copilot\` reviewer login" \
    "$G" 1 "$L" 'select\(\.requested_reviewer\.login == "Copilot"\) \| \.id\]'

  assert_present "$n github-api: presence alone is not evidence the request landed" \
    "$G" 1 "$L" 'presence alone is not$'

  assert_present "$n github-api: the timeline login is \`Copilot\`, not the bot form" \
    "$G" 1 "$L" 'The login to match is `Copilot`, \*\*not\*\* `copilot-pull-request-reviewer'
done

# ---------------------------------------------------------------------------
# plan-review rubric — a GAP commits to a blocking finding
# ---------------------------------------------------------------------------
# A reviewer marked GAP for an item its own prose argued was not actionable, then
# paired it with a non-blocking finding. The contract check reads that as
# self-contradictory and spends the one permitted retry on it.
for RB in plugins/*/skills/plan-review/references/reviewer-rubric.md; do
  [ -f "$RB" ] || continue
  n=$(plugin_of "$RB"); L=$(total_lines "$RB")
  echo "== $n reviewer-rubric — GAP commits to a blocking finding =="

  assert_present "$n rubric: a \`GAP\` is a commitment to a blocking finding" \
    "$RB" 1 "$L" 'A `GAP` is a commitment to a \*blocking\* finding'

  assert_present "$n rubric: pairing a GAP with a non-blocking finding is self-contradictory" \
    "$RB" 1 "$L" 'makes the output self-contradictory'

  assert_present "$n rubric: an unverifiable axis is skipped rather than marked GAP" \
    "$RB" 1 "$L" '\*\*skip the axis\*\* — do not mark'

  assert_present "$n rubric: concluding no cheap fix exists is the same judgment, not a GAP" \
    "$RB" 1 "$L" '^`GAP`\. If you have concluded, and are about to write, that no cheap fix exists'
done

# ---------------------------------------------------------------------------
# ticket-system — Notion escapes the brackets it hands back
# ---------------------------------------------------------------------------
# The escape tolerance was stated only for the title prefix. The two other
# read-back sites carry the same brackets: an unescaped Resolution Log parse
# finds zero entries on a populated log, so epic-update's idempotency check can
# never fire and a recovery invocation appends a duplicate entry.
TS=plugins/notion-dev/skills/ticket-system/SKILL.md
if [ -f "$TS" ]; then
  L=$(total_lines "$TS")
  echo "== ticket-system — escaped brackets bind every read-back =="

  assert_present "ticket-system: the escaping binds every read-back, not just the title" \
    "$TS" 1 "$L" 'bracket form this plugin writes, not just the title'

  assert_present "ticket-system: this is the canonical statement the other sites cite" \
    "$TS" 1 "$L" 'This is the$'

  assert_present "ticket-system: an unescaped Resolution Log parse defeats \`already-recorded\`" \
    "$TS" 1 "$L" '`already-recorded`$'

  assert_present "ticket-system: the consequence is a duplicated log entry, not lost work" \
    "$TS" 1 "$L" 'entry\*\*\. Per-follow-up `PROVENANCE` dedup still prevents duplicate'

  assert_count "ticket-system: an unescaped write fails with No matches found (canonical rule + the Tasks-update site)" \
    "$TS" 1 "$L" '`validation_error: No matches found`' 2

  assert_present "ticket-system: the Resolution Log parse tolerates the escaped bracket form" \
    "$TS" 1 "$L" '`## Resolution Log`.*\*\*Tolerate the backslash-escaped bracket form\*\*'

  assert_present "ticket-system: the Tasks line update matches the escaped bracket form too" \
    "$TS" 1 "$L" '\*\*When updating an existing line rather than'

  # ---------------------------------------------------------------------------
  # ticket-system — a 404 on the configured database is a workspace binding
  # ---------------------------------------------------------------------------
  # A run hard-stopped with the configured ids perfectly correct: the session was
  # authenticated to a different workspace. The dangerous half is the obvious
  # recovery — a workspace-scoped search by key — because ticket-key prefixes are
  # not globally unique, and the reachable workspace held a different project's
  # tickets under the same prefix.
  echo "== ticket-system — a 404 is a workspace binding, not a wrong id =="

  assert_present "ticket-system: a 404 on the configured database is a workspace-binding problem" \
    "$TS" 1 "$L" 'workspace-binding problem, not a wrong id'

  assert_present "ticket-system: \`notion-fetch \"self\"\` reports the bound workspace" \
    "$TS" 1 "$L" 'Diagnose it with `notion-fetch "self"`'

  assert_present "ticket-system: the lookup is never widened to recover from it" \
    "$TS" 1 "$L" '\*\*Never widen the lookup to recover from it\.\*\*'

  assert_present "ticket-system: ticket-key prefixes are not globally unique" \
    "$TS" 1 "$L" 'ticket-key prefixes are$'
fi

EU=plugins/notion-dev/skills/epic-update/SKILL.md
if [ -f "$EU" ]; then
  L=$(total_lines "$EU")
  assert_present "epic-update: step 1a's parse is the reason the escape tolerance matters" \
    "$EU" 1 "$L" 'it tolerates the backslash-escaped bracket'
fi

# ---------------------------------------------------------------------------
# Worktree provisioning — two failures that are not findings about the branch
# ---------------------------------------------------------------------------
# Both cost a run its diagnosis rather than its correctness, and both present as
# a regression in the branch under test right before a merge gate — the exact
# wrong conclusion. The submodule refusal is deterministic in a submodule-bearing
# repo (3 for 3 in one client), not the incidental leftovers case the text named.
echo "== worktree provisioning =="

T=plugins/notion-dev/commands/ticket.md
if [ -f "$T" ]; then
  L=$(total_lines "$T")

  assert_present "ticket.md: the submodule refusal is named as a cause of the --force retry" \
    "$T" 1 "$L" 'retry with `git worktree remove --force <worktree-path>`.*working trees containing submodules cannot be moved or removed'

  assert_present "ticket.md: the submodule refusal is deterministic, not an anomaly" \
    "$T" 1 "$L" '\*\*deterministic, not an anomaly\*\*'

  assert_present "ticket.md: gitignored local files are not carried into the worktree" \
    "$T" 1 "$L" '\*\*Gitignored local files are not carried into the worktree'

  assert_present "ticket.md: the missing file is recreated before the failure is read as a finding" \
    "$T" 1 "$L" '\*\*Recreate it from its committed example before treating'

  assert_present "ticket.md: the harness-managed local settings file is exempt from the clean-tree stop" \
    "$T" 1 "$L" '\*\*harness-managed local settings file\*\* \(`\.claude/settings\.local\.json`\)'

  assert_present "ticket.md: the exemption list is exhaustive" \
    "$T" 1 "$L" 'Exactly two kinds of dirt are exempt, and the list is exhaustive'

  assert_present "ticket.md: a failed pull is diagnosed against the primary checkout's status" \
    "$T" 1 "$L" '\*\*A failed pull must be diagnosed, not merely reported'

  assert_present "ticket.md: the primary checkout is asserted unchanged after each build task" \
    "$T" 1 "$L" '\*\*Assert the primary checkout is unchanged after each build task\.\*\*'

  assert_present "ticket.md: a long PR body goes through --body-file, never \`@-\`" \
    "$T" 1 "$L" '\*\*Pass a long PR body with `--body-file`, never `--body`, and never `@-`'

  assert_present "ticket.md: the created body is read back and its length confirmed" \
    "$T" 1 "$L" '\*\*read the body back and confirm a realistic length\*\*'

  assert_present "ticket.md: \`--body-file -\` reads the body from standard input" \
    "$T" 1 "$L" '`--body-file -` is the correct spelling of what `@-` was reaching for'

  assert_present "ticket.md: a body file left in the worktree blocks the clean-tree gate" \
    "$T" 1 "$L" 'would stop every run before review'
fi

F=plugins/notion-dev/commands/finalize.md
if [ -f "$F" ]; then
  L=$(total_lines "$F")
  assert_present "finalize.md: the submodule refusal is named alongside untracked leftovers" \
    "$F" 1 "$L" 'deterministic in any repo that vendors dependencies as submodules'
fi

D=plugins/quick-dev/skills/develop/SKILL.md
if [ -f "$D" ]; then
  L=$(total_lines "$D")

  assert_present "develop: the --force retry names the submodule refusal as a second cause" \
    "$D" 1 "$L" 'add `--force` only if it fails — on untracked leftovers, or on the submodule refusal, which is deterministic rather than incidental'

  assert_present "develop: gitignored local files are not carried into the worktree" \
    "$D" 1 "$L" '\*\*Gitignored local files are not carried into the worktree'

  assert_present "develop: a failed pull is diagnosed against the primary checkout's status" \
    "$D" 1 "$L" '\*\*A failed pull must be diagnosed, not merely reported'

  assert_present "develop: the primary checkout is asserted unchanged after each build task" \
    "$D" 1 "$L" '\*\*Assert the primary checkout is unchanged after each build task\.\*\*'

  assert_present "develop: a long PR body goes through --body-file, never \`@-\`" \
    "$D" 1 "$L" '\*\*Pass a long PR body with `--body-file`, never `--body`, and never `@-`'

  assert_present "develop: the PR is created with --body-file rather than an inline body" \
    "$D" 1 "$L" 'gh pr create --base "\$MAIN" --head "\$BRANCH" --title "<feature title>" --body-file'

  assert_present "develop: \`--body-file -\` reads the body from standard input" \
    "$D" 1 "$L" '`--body-file -` is the correct spelling of what `@-` was reaching for'

  assert_present "develop: a body file left in the worktree blocks the clean-tree gate" \
    "$D" 1 "$L" 'would stop every run before review'
fi

E=plugins/quick-dev/skills/develop/references/environment-setup.md
if [ -f "$E" ]; then
  L=$(total_lines "$E")
  assert_present "environment-setup: the submodule refusal is its own edge case, deterministic not incidental" \
    "$E" 1 "$L" '\*\*deterministic, not incidental\*\*'
fi

# ---------------------------------------------------------------------------
echo
if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
  exit 0
fi
echo "$fails CHECK(S) FAILED"
exit 1
