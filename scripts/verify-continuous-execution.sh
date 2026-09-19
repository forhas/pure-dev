#!/usr/bin/env bash
# Non-interactive runs must not hand the turn back.
#
# `--non-interactive` was specified in both plugins as "never pause for user
# input ... self-answer" — a rule about QUESTIONS. Ending the turn is not a
# question, so nothing forbade it, and two client runs on the same day stopped
# mid-`Phase 4` with a `Next: ...` line and no question asked: one after
# `writing-plans` returned, one after `plan-review` returned. Nothing was
# logged either, because a run cannot observe its own ending.
#
# Three mechanisms close that, and this harness pins all three:
#
#   1. Every non-interactive entry point states that the mode also means
#      *never hand back*, and names the `Next:` shape as the defect.
#   2. Both callers of `superpowers:writing-plans` suppress its
#      `## Execution Handoff` — a scripted "Which approach?" hand-back sitting
#      in the middle of a flow that continues past it.
#   3. `/notion-dev:ticket` 1.2 records `unexpected:run-ended-mid-phase` when a
#      resume finds a marker still reading `running`, which is the only place
#      the condition is observable at all.
#
# Standing invariant, not a change-scoped check: no baseline beyond the one
# release that shipped it.
#
# Run from anywhere: ./scripts/verify-continuous-execution.sh
set -uo pipefail
cd "$(dirname "$0")/.."

fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# shellcheck source=lib/assert.sh
. ./scripts/lib/assert.sh

ND=plugins/notion-dev
QD=plugins/quick-dev
TK=$ND/commands/ticket.md
NT=$ND/commands/next-task.md
NI=$ND/commands/new-info.md
CT=$ND/commands/create-task.md
FIN=$ND/commands/finalize.md
RM=$QD/skills/review-and-merge/SKILL.md
NRM=$ND/skills/review-and-merge/SKILL.md
DEV=$QD/skills/develop/SKILL.md
SIG=$ND/skills/issue-log/references/signatures.md
NDREADME=$ND/README.md
QDREADME=$QD/README.md

# ---------------------------------------------------------------------------
echo "== the rule, at every non-interactive entry point =="
# ---------------------------------------------------------------------------
# One phrasing, three orchestrators. Keyed on the mechanism — the two halves of
# what the mode means, and the shape of the failure — never on a whole sentence.
for f in "$TK" "$NT" "$FIN" "$DEV" "$RM" "$NRM"; do
  assert_has "$f: non-interactive mode is never hand back, not only never ask" \
    "$f" 'non-interactive mode is *never hand back*, not only *never ask*'
  assert_has "$f: names the \`Next: <the thing you were about to do>\` stopping shape" \
    "$f" '`Next: <the thing you were about to do>` and then stops'
  assert_has "$f: announcing it instead of doing it is the defect" \
    "$f" 'announcing it *instead of doing it* is the defect'
done

assert_has "$NI: the run does not end its turn between epics or between steps" \
  "$NI" 'do not end your turn between epics, between steps'
assert_has "$NI: a stopping line naming what comes next is not a question" \
  "$NI" 'and then stopping is not a question'

assert_has "$CT: the run does not end its turn between phases" \
  "$CT" 'do not end your turn between phases or after a delegated skill or subagent returns'
assert_has "$CT: a stopping line naming what comes next is not a question" \
  "$CT" 'and then stopping is not a question'

# The rule is worthless if it does not say what DOES end the run — an
# unqualified "never stop" would swallow the real stop conditions.
for f in "$TK" "$FIN"; do
  assert_has "$f: only the stop conditions this command names explicitly end the run" \
    "$f" 'The only things that end a non-interactive run are the stop conditions this command names explicitly'
done
for f in "$DEV" "$RM" "$NRM"; do
  assert_has "$f: only the stop conditions this skill names explicitly end the run" \
    "$f" 'The only things that end a non-interactive run are the stop conditions this skill names explicitly'
done

# review-and-merge is mostly waiting, so every return reads like a stopping
# point. Name the shape rather than the general rule, or the next editor reads
# the general rule as already covered by the "never pause" sentence above it.
for f in "$RM" "$NRM"; do
  assert_has "$f: the skill is unusually exposed because it is mostly waiting" \
    "$f" 'This skill is unusually exposed, because it is mostly waiting'
  assert_has "$f: stopping before the sweep or the gates leaves a PR reviewed and not merged" \
    "$f" 'leaves a pull request that is reviewed and not merged with nobody watching'
done
assert_has "$TK: \`PLAN-REVIEW: blocked\` stays one of those stop conditions" \
  "$TK" '`PLAN-REVIEW: blocked` (4.2b)'
assert_has "$TK: the epic guard and the \`held elsewhere\` ownership check are among those stops" \
  "$TK" 'the epic guard and the `held elsewhere` ownership check, both of which non-interactive mode must obey'

# Every enumerated stop list must say it is not closed. Written as exhaustive it
# conflicts with any stop it forgot — a rule against handing back then reads as
# a licence to continue past a hard abort.
for f in "$TK" "$FIN" "$DEV"; do
  assert_has "$f: the enumerated stop list is illustrative, never exhaustive" \
    "$f" '**This list is illustrative, never exhaustive**'
done

# finalize's exposed boundary is its own: a long delegation that ends with a
# merged PR reads like a finish line while three phases of work still follow it.
assert_has "$FIN: \`notion-dev:review-and-merge\` returning is the most exposed boundary" \
  "$FIN" 'most exposed boundary is `notion-dev:review-and-merge` returning at the end of Phase 2'
assert_has "$FIN: stopping there leaves the PR merged with none of the rest done" \
  "$FIN" 'a run that stops there leaves the PR merged with none of them done'

# ---------------------------------------------------------------------------
echo "== writing-plans' Execution Handoff is suppressed at both call sites =="
# ---------------------------------------------------------------------------
L=$(total_lines "$TK")
P42=$(find_line "$TK" 1 "$L" '^### 4\.2 `FLOW=superpowers`$')
P43=$(find_line "$TK" 1 "$L" '^### 4\.3 ')

if [ -n "$P42" ] && [ -n "$P43" ]; then
  assert_present "ticket.md 4.2 names \`superpowers:writing-plans\`' \`## Execution Handoff\`" \
    "$TK" "$P42" "$P43" '`superpowers:writing-plans` ends with an `## Execution Handoff` section'
  assert_present "ticket.md 4.2: writing the plan file completes the step — go straight to (b)" \
    "$TK" "$P42" "$P43" 'completes\*\* this step; go straight to \(b\)'
else
  bad "ticket.md: could not anchor 4.2/4.3 (found '$P42'/'$P43')"
fi

assert_has "develop suppresses writing-plans' \`## Execution Handoff\`" \
  "$DEV" 'Suppress its `## Execution Handoff`'
assert_has "develop: writing the plan file completes the step — go straight to step 3" \
  "$DEV" 'completes** this step; go straight to step 3'

# Both call sites must say WHY self-answering cannot recover it: the offer ends
# the turn, not the missing answer. Drop that and the next editor "simplifies"
# the suppression back out on the grounds that non-interactive already answers.
for f in "$TK" "$DEV"; do
  assert_has "$f: the offer ends the turn, not the absence of an answer" \
    "$f" 'what ends the turn is the offer, not the absence of an answer'
  # ...and therefore the self-answer rule CANNOT recover it. ticket.md stated
  # only the first half and drew the opposite conclusion from it, which read as
  # licence to keep the handoff and self-answer it.
  assert_has "$f: a self-answer rule cannot recover the handoff" \
    "$f" 'so a self-answer rule cannot recover it'
done

# ---------------------------------------------------------------------------
echo "== a mid-phase end is recorded on the next resume =="
# ---------------------------------------------------------------------------
assert_has "ticket.md 1.2: a protected re-read still saying \`running\` is a mid-phase end" \
  "$TK" 'A marker whose protected re-read still read `running` is a mid-phase end'
# The condition is only observable in the values captured BEFORE the resume claim
# rewrites the marker: afterwards every marker reads `running` with a fresh
# heartbeat, so the test matches every resume and its stale-heartbeat qualifier
# can never be true. Pin both the capture and the reason.
assert_has "ticket.md 1.2: \`state\`, \`phase\` and \`heartbeat\` are captured before the rewrite" \
  "$TK" 'capture `state`, `phase` and `heartbeat` from that re-read, and test the captured values here'
assert_has "ticket.md 1.2: testing the marker as it stands at that line matches everything" \
  "$TK" 'Testing the marker as it stands at this line instead reports nothing while appearing to match everything'
assert_has "ticket.md 1.2: it records \`unexpected:run-ended-mid-phase\`" \
  "$TK" 'Record `unexpected:run-ended-mid-phase` per `notion-dev:issue-log`'
assert_has "ticket.md 1.2: the captured \`phase\` is carried as \`Where\`" \
  "$TK" 'carrying the **captured** `phase` as `Where`'
# The two non-conditions matter as much as the condition: a missing marker is a
# pre-marker worktree and `stopped` is a clean stop. Without them the entry
# fires on ordinary resumes and stops being worth reading.
assert_has "ticket.md 1.2: a missing marker is not the condition, and neither is a captured \`stopped\`" \
  "$TK" 'is not this condition (a worktree from before markers existed), and neither is a captured `stopped`'
assert_has "signature registry: the condition lives in the protected re-read" \
  "$SIG" 'in the protected re-read taken before the resume claim rewrote it'
assert_has "signature registry carries the \`unexpected:run-ended-mid-phase\` row" \
  "$SIG" '| `unexpected:run-ended-mid-phase` |'
assert_has "signature registry: the one signature no run can record about itself" \
  "$SIG" 'the one signature no run can record about itself'

# ---------------------------------------------------------------------------
echo "== the rule names the mechanism that enforces it =="
# ---------------------------------------------------------------------------
# Prose shipped alone in 0.28.1 and did not hold. The document must point at the
# hook, or the next editor reads the paragraph as the enforcement and the guard
# looks like belt-and-braces it is safe to drop.
assert_has "$TK: the rule is enforced by a \`Stop\` hook, because prose alone did not hold" \
  "$TK" 'This rule is enforced by a `Stop` hook, because as prose alone it did not hold'
assert_has "$TK: names \`hooks/stop-guard.sh\` as the enforcement" \
  "$TK" '`hooks/stop-guard.sh` blocks the stop'
assert_has "$TK: \`/notion-dev:finalize\` writes no marker, so the guard does not cover it" \
  "$TK" '`/notion-dev:finalize` writes no run marker, so the guard does not cover it at all'
assert_has "$TK: the run marker carries \`non_interactive\`" \
  "$TK" '"non_interactive": <true|false>'
# Without an owning session the guard blocks whoever stops first, which in a
# checkout running two tickets is the guard doing the wedging it exists to stop.
assert_has "$TK: the run marker carries \`claude_session\`, the harness session id" \
  "$TK" '"claude_session": "<$CLAUDE_CODE_SESSION_ID>"'
assert_has "$TK: the guard blocks only the session that owns this run" \
  "$TK" 'the guard blocks **only the session that owns this run**'
assert_has "$TK: the resume rewrite sets this invocation's \`non_interactive\`" \
  "$TK" "and this invocation's \`non_interactive\`"
assert_has "notion-dev README documents the \`Stop\` hook" \
  "$NDREADME" 'enforced by a `Stop` hook this plugin ships'
assert_has "notion-dev README states the block bound" \
  "$NDREADME" 'at most **3 blocks per run per'
assert_has "notion-dev README states the staleness bound" \
  "$NDREADME" '**2 hours** stale'
assert_has "notion-dev README: the guard blocks only the session that owns the run" \
  "$NDREADME" 'owns the run** — a second parallel ticket'

# ---------------------------------------------------------------------------
echo "== READMEs and release =="
# ---------------------------------------------------------------------------
assert_has "notion-dev README: \`--non-interactive\` means two things, not one" \
  "$NDREADME" '`--non-interactive` means two things, not one'
assert_has "notion-dev README names \`unexpected:run-ended-mid-phase\`" \
  "$NDREADME" '`unexpected:run-ended-mid-phase`'
# The detection is `/notion-dev:ticket`-only — it is the one command with a run
# marker and a resume path. An unqualified promise here would claim it for
# finalize, new-info, create-task and next-task, none of which can emit it.
assert_has "notion-dev README scopes the detection to \`/notion-dev:ticket\` only" \
  "$NDREADME" 'In `/notion-dev:ticket` only'
assert_has "notion-dev README: the other commands get the rule and not the detection" \
  "$NDREADME" 'The other commands get the rule and not the detection'
assert_has "quick-dev README: the flag also never hands the turn back" \
  "$QDREADME" 'It also never hands the turn back'

assert_version_above "notion-dev version bumped above the pre-change 0.28.0" \
  "$ND/.claude-plugin/plugin.json" 0.28.0
assert_version_above "quick-dev version bumped above the pre-change 0.15.1" \
  "$QD/.claude-plugin/plugin.json" 0.15.1

echo
if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
  echo
  echo "This harness pins the continuous-execution contract: a --non-interactive"
  echo "run never hands the turn back, writing-plans' Execution Handoff is"
  echo "suppressed at both call sites, and a mid-phase end is recorded by the"
  echo "next resume. If a failure above is a deliberate change, change the"
  echo "assertion with it — in the same commit, with the reasoning."
fi
exit $(( fails > 0 ? 1 : 0 ))
