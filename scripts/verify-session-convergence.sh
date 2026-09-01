#!/usr/bin/env bash
# Standing-invariant checks for the session-convergence design:
#   1. the narrowed blast-radius `file` criteria (widening a PR beats splitting it)
#   2. `review-and-merge`'s final sweep, and its terminality
#   3. the `session-closeout` zero-tails gate, and that every flow invokes it
#
# This repo ships markdown instruction files, not code — the verify-*.sh
# harnesses are the test suite, discovered by glob in .github/workflows/verify.yml.
#
# Modelled on verify-mirror.sh, not on the change-scoped harnesses beside it:
# every assertion here is a standing invariant with no baseline to go stale, so
# there are no version floors to rot. It matches MECHANISM — command strings,
# heading anchors, the relative order of sections, the presence of each keyed
# line — never whole sentences, so a wording tweak cannot turn it red and train
# someone to edit the harness instead of thinking.
#
# Run from anywhere: ./scripts/verify-session-convergence.sh
set -uo pipefail
cd "$(dirname "$0")/.."

fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# Assertions come from the shared library: it is what makes every anchor here
# unique-or-declared and every label covered by its own regex. See scripts/lib/
# assert.sh for why, and scripts/verify-assertions.sh for the proof that its
# checks can fail.
# (cd to the repo root already happened above, so this path is stable.)
. ./scripts/lib/assert.sh

QD=plugins/quick-dev
ND=plugins/notion-dev
MIRROR=.claude/skills

# Every copy of the review-and-merge skill that ships or drives this repo.
RAM_DOCS="$QD/skills/review-and-merge/SKILL.md
$ND/skills/review-and-merge/SKILL.md
$MIRROR/review-and-merge/SKILL.md"

# Every document carrying the blast-radius triage criteria.
CRITERIA_DOCS="$RAM_DOCS
$QD/skills/plan-review/references/reviewer-rubric.md
$ND/skills/plan-review/references/reviewer-rubric.md"

# Every copy of the closeout skill.
CLOSEOUT_DOCS="$QD/skills/session-closeout/SKILL.md
$ND/skills/session-closeout/SKILL.md
$MIRROR/session-closeout/SKILL.md"

echo "== blast-radius criteria: widening beats splitting =="

for f in $CRITERIA_DOCS; do
  if [ ! -f "$f" ]; then bad "$f is missing"; continue; fi
  n=$(total_lines "$f")

  # The mechanism: "reaches code ... not already changing" must not survive as a
  # NUMBERED criterion. It still appears in prose, negated, which is the point —
  # so anchor on the numbered-list form, not on the phrase.
  assert_absent "$f: 'reaches code the PR/ticket was not already changing' is no longer a numbered criterion" \
    "$f" 1 "$n" '^[[:space:]]*[0-9]+[.] It [*][*]reaches code'

  # ...and the replacement is stated, not merely absent.
  # NOT the bare fragment: the Contract check's "A missing verdict line is not a criterion
  # silently met" satisfies it, so re-instating file location as "criterion 4" left this
  # green — the harness stayed silent about the exact regression it exists to prevent.
  assert_present "$f: states that reaching a new file is not a criterion" \
    "$f" 1 "$n" 'was not already changing. is not a criterion'

  assert_order "$f: criteria are renumbered 1=interface 2=design-decision 3=obscures-the-change" \
    "$f" 1 "$n" \
    "1. new public interface"  '^[[:space:]]*1[.] It requires a [*][*]new public interface' \
    "2. design decision"       '^[[:space:]]*2[.] It needs a design decision' \
    "3. obscures the change"   '^[[:space:]]*3[.] Its .*[*][*]large enough'

  assert_present "$f: every file item still cites its criterion number" \
    "$f" 1 "$n" 'cite the criterion number'
done

echo "== review-and-merge: the final sweep =="

for f in $RAM_DOCS; do
  if [ ! -f "$f" ]; then bad "$f is missing"; continue; fi
  n=$(total_lines "$f")

  loop=$(find_line "$f" 1 "$n" '^## 4[.] Review loop')
  merge=$(find_line "$f" 1 "$n" '^## 5[.] Merge')
  sweep=$(find_line "$f" 1 "$n" '^### The final sweep')

  if [ -z "$loop" ] || [ -z "$merge" ] || [ -z "$sweep" ]; then
    bad "$f: missing '## 4. Review loop', '## 5. Merge', or '### The final sweep'"
    continue
  fi

  # Position is the invariant: the sweep runs after the loop and before the gates.
  if [ "$sweep" -gt "$loop" ] && [ "$sweep" -lt "$merge" ]; then
    ok "$f: the sweep sits after the review loop and before the merge gates"
  else
    bad "$f: the sweep is out of position (loop $loop, sweep $sweep, merge $merge)"
  fi

  assert_present "$f: the sweep runs at most once per run" \
    "$f" "$sweep" "$merge" 'at most once per run'
  assert_present "$f: the sweep collects termination-ground drops, not merit-ground ones" \
    "$f" "$sweep" "$merge" 'on a [*]termination[*] ground'
  assert_present "$f: a merit-ground drop is never swept" \
    "$f" "$sweep" "$merge" 'never swept'
  assert_present "$f: sweep eligibility is 'none of the three file criteria is true'" \
    "$f" "$sweep" "$merge" 'none of the three .file. criteria'
  assert_present "$f: the sweep keeps one commit per item with its Finding trailer" \
    "$f" "$sweep" "$merge" 'one item per commit[*][*] with its .Finding:. trailer'
  assert_present "$f: the sweep round bars another review round, not another fix" \
    "$f" "$sweep" "$merge" 'buys no further review [*]round[*]; it does not forbid'
  assert_present "$f: a reviewless sweep-round fix must stay small and in-scope" \
    "$f" "$sweep" "$merge" 'never do is trigger'
  assert_present "$f: anything larger is still filed or dropped" \
    "$f" "$sweep" "$merge" 'remains the answer for anything larger'
  assert_present "$f: a sweep-induced blocking finding is reverted, not fixed" \
    "$f" "$sweep" "$merge" 'reverted, not fixed'
  assert_present "$f: a blocking finding the sweep did not induce is fixed, not filed" \
    "$f" "$sweep" "$merge" 'fixed, not filed'
  assert_present "$f: the sweep round is an allowance on top of the cap" \
    "$f" "$sweep" "$merge" 'allowance [*]on top of[*] .reviewsCap'
  # The contradiction was that only one of the two places said so.
  assert_present "$f: the Safety rules grant the same sweep allowance" \
    "$f" "$merge" "$n" 'at most one final-sweep round'

  # The gate list must actually require the sweep, or it is advisory.
  assert_present "$f: entry to the merge gates requires the sweep to have run" \
    "$f" "$merge" $((merge + 8)) 'final sweep has run'

  # Multi-PR batching is recorded as considered-and-rejected so it is not re-proposed.
  assert_present "$f: records why the skill takes one pull request, not several" \
    "$f" "$sweep" "$merge" '^### Why this skill takes one pull request'

  # The CONVERGENCE block reports the sweep.
  conv=$(find_line "$f" 1 "$n" '^CONVERGENCE:')
  if [ -z "$conv" ]; then
    bad "$f: no CONVERGENCE block"
  else
    assert_order "$f: CONVERGENCE reports SWEPT and SWEEP-ROUND" \
      "$f" "$conv" $((conv + 12)) \
      "SWEPT"       '^SWEPT: ' \
      "SWEEP-ROUND" '^SWEEP-ROUND: '
    assert_present "$f: SWEPT is a subset of ABSORBED, not a fifth bucket" \
      "$f" "$conv" "$n" '.SWEPT. is a [*][*]subset[*][*] of .ABSORBED'
  fi
done

echo "== session-closeout: zero tails =="

for f in $CLOSEOUT_DOCS; do
  if [ ! -f "$f" ]; then bad "$f is missing"; continue; fi
  n=$(total_lines "$f")

  assert_present "$f: declares name session-closeout" "$f" 1 10 '^name: session-closeout$'

  # The two passes, and the ordering constraint that is the whole point of them.
  assert_order "$f: defines a completion pass before the merge and a workspace pass after" \
    "$f" 1 "$n" \
    "When to run"      '^## When to run — two passes' \
    "completion pass"  '^- [*][*]Completion pass — before the merge' \
    "workspace pass"   '^- [*][*]Workspace pass — after cleanup'
  assert_present "$f: names --pre-merge-check as the completion pass's hook" \
    "$f" 1 "$n" 'pre-merge-check' 

  assert_order "$f: the three states are defined in order, and there is no fourth" \
    "$f" 1 "$n" \
    "resolved"        '[|] .resolved. [|]' \
    "tracked: <url>"  '[|] .tracked: <url>. [|]' \
    "blocked: <cause>" '[|] .blocked: <cause>. [|]'
  assert_present "$f: states there is no fourth state" "$f" 1 "$n" 'There is no fourth'
  assert_present "$f: tracked requires a ticket that exists now" \
    "$f" 1 "$n" 'ticket that exists right now'
  assert_present "$f: blocked is external causes only" \
    "$f" 1 "$n" '[*][*].blocked. is for external causes only[*][*]'
  assert_present "$f: time is explicitly not a blocker" "$f" 1 "$n" 'Time is not a blocker'

  # Enumerate-from-sources, not from memory: the eight queried sources.
  enum=$(find_line "$f" 1 "$n" '^## 1[.] Enumerate')
  phrase=$(find_line "$f" 1 "$n" '^## 2[.] The phrase check')
  if [ -z "$enum" ] || [ -z "$phrase" ]; then
    bad "$f: missing the enumerate or phrase-check section"
  else
    assert_present "$f: enumerates by query, not by recall" "$f" "$enum" "$phrase" 'never from memory'
    assert_present "$f: FILED URLs are required by the workspace pass, not before filing" \
      "$f" 1 "$n" 'spans both passes, because filing often happens after the merge'
    assert_present "$f: pre-existing dirty state is excluded, and reported" \
      "$f" "$enum" "$phrase" 'PREEXISTING_DIRTY'
    # Cited twice on purpose — the prose states the scope, the snippet runs it.
    # Declared rather than loosened: if either citation goes, this goes red.
    assert_count "$f: the unpushed check spans every worktree" \
      "$f" "$enum" "$phrase" 'git worktree list --porcelain' 2
    assert_present "$f: a Deferred: trailer counts as durable tracking where there is no backend" \
      "$f" "$enum" "$phrase" 'durable record its flow actually uses'
    assert_present "$f: open PRs are correlated to this run, not listed wholesale" \
      "$f" "$enum" "$phrase" 'A bare$'
    assert_present "$f: unpushed work is judged only for worktrees this run owns" \
      "$f" "$enum" "$phrase" '[*][*]judge[*][*] only'
    # Anchored on the emitting line, not the phrase: the no-remote qualification
    # below quotes the same string in prose, and an anchor matching both pins neither.
    assert_present "$f: the unpushed check handles a branch with no upstream" \
      "$f" "$enum" "$phrase" '^ *echo "[$]w [(][$]b[)]: no upstream — never pushed"'
    # ...and that a no-upstream branch is judged only where pushing is part of the
    # flow. Without this, local mode's pre-squash gate gets a tail it cannot clear.
    assert_present "$f: a no-upstream branch is a tail only where pushing is part of the flow" \
      "$f" "$enum" "$phrase" '^   [*][*]A branch with no upstream is a tail only where pushing'
    assert_present "$f: with no remote, nothing is judged under the unpushed source" \
      "$f" "$enum" "$phrase" 'no remote — nothing to push to'
    # A gh-checked-out fork PR has no remote-tracking ref, so @{upstream} fails on a
    # branch that IS pushed. The probe must ask the configured push target before
    # concluding anything.
    assert_present "$f: a failed @{upstream} is not taken as evidence of never pushed" \
      "$f" "$enum" "$phrase" 'No remote-tracking ref is not the same as never pushed'
    assert_order "$f: the unpushed check consults the configured push target" \
      "$f" "$enum" "$phrase" \
      "branch.<b>.remote" 'config --get "branch[.][$]b[.]remote"' \
      "branch.<b>.merge"  'config --get "branch[.][$]b[.]merge"' \
      "fetch the ref"     'fetch -q "[$]r" "[$]m"'
    # Direction, not difference: a sha inequality is equally true of a branch that
    # is merely BEHIND, and reporting that as a tail on a pre-merge gate demands a
    # push that would clobber whoever pushed to the fork.
    assert_present "$f: a behind branch is observed, not judged a tail" \
      "$f" "$enum" "$phrase" 'behind [$]r [$]m — observed, NOT a tail'
    assert_present "$f: a diverged branch is a tail a plain push must not resolve" \
      "$f" "$enum" "$phrase" 'diverged from [$]r [$]m — a tail, and one a plain push must not resolve'
    assert_order "$f: ahead and behind are told apart by ancestry, in that order" \
      "$f" "$enum" "$phrase" \
      "remote is ancestor of local" 'merge-base --is-ancestor "[$]remote_sha" "[$]local_sha"' \
      "local is ancestor of remote" 'merge-base --is-ancestor "[$]local_sha" "[$]remote_sha"'
    assert_absent "$f: does not use git branch --merged (blind to squash merges)" \
      "$f" "$enum" "$phrase" '^[^#]*git branch --merged <base>'
    assert_present "$f: detects a stale branch by its PR state, not by ancestry" \
      "$f" "$enum" "$phrase" 'gh pr list --head'
    assert_present "$f: only MERGED means the work landed" \
      "$f" "$enum" "$phrase" 'Only .MERGED. is evidence the work landed'
    assert_present "$f: a closed-unmerged branch is never deleted" \
      "$f" "$enum" "$phrase" 'CLOSED WITHOUT MERGING'
    assert_order "$f: enumerates uncommitted, unpushed, worktrees, PRs, issues, deferred, verification, and the draft" \
      "$f" "$enum" "$phrase" \
      "git status"      'git status --porcelain' \
      "unpushed"        'rev-list --count .@[{]upstream[}][.][.]HEAD.' \
      "worktrees"       '^   git worktree list$' \
      "open PRs"        'gh pr list --state open --json' \
      "filed issues"    'Query the set this run recorded' \
      "deferred"        "git log --grep '\\^Deferred:'" \
      "own draft"       'own draft report'

    # The user's own signal phrases are the check's payload — each must be listed.
    for p in 'one thing left' 'one honest note' 'worth flagging' 'remaining open' \
             'the only remaining item' 'for a follow-up' 'should probably'; do
      assert_present "$f: the phrase check lists \"$p\"" "$f" "$phrase" "$n" "$p"
    done
    assert_present "$f: the completion list excludes the draft report" \
      "$f" 1 "$n" 'Source 8 is deliberately not here'
    assert_present "$f: the draft is inspected only once it is finished" \
      "$f" 1 "$n" 'compose the full draft, then run this source'
    assert_present "$f: rewording instead of resolving is named as the failure" \
      "$f" "$phrase" "$n" 'Do not soften the sentence'
  fi

  assert_present "$f: resolved is the default disposition" "$f" 1 "$n" '.resolved. is the default'
  assert_present "$f: the retry bound is counted per lifecycle pass" \
    "$f" 1 "$n" 'Each lifecycle pass runs at most twice'
  assert_present "$f: the retry bound is not a budget the two passes share" \
    "$f" 1 "$n" 'not a budget of'
  assert_present "$f: the closeout must not start new scope" "$f" 1 "$n" 'Do not start new scope'

  cl=$(find_line "$f" 1 "$n" '^CLOSEOUT:')
  if [ -z "$cl" ]; then
    bad "$f: no CLOSEOUT report block"
  else
    assert_order "$f: CLOSEOUT block carries all five keys" \
      "$f" "$cl" $((cl + 8)) \
      "TAILS-FOUND" '^TAILS-FOUND: ' \
      "RESOLVED"    '^RESOLVED: ' \
      "TRACKED"     '^TRACKED: ' \
      "BLOCKED"     '^BLOCKED: ' \
      "PASSES"      '^PASSES: '
  fi
done

echo "== every flow invokes the closeout before reporting =="

# <file> <report-heading ere> <plugin prefix for the skill reference>
check_caller() {
  local label=$1 file=$2 heading=$3 skillref=$4
  local n rep inv
  if [ ! -f "$file" ]; then bad "$label: $file is missing"; return; fi
  n=$(total_lines "$file")
  rep=$(find_line "$file" 1 "$n" "$heading")
  if [ -z "$rep" ]; then bad "$label: no report section matching $heading"; return; fi
  inv=$(find_line "$file" "$rep" "$n" "$skillref")
  if [ -z "$inv" ]; then bad "$label: never invokes $skillref in its report phase"; return; fi
  # Anchor on the invocation sentence's own leading "Before", not on the word
  # appearing anywhere nearby. A bare 'before' within five lines was satisfied by
  # "its completion pass already ran *before* the merge" later in the same
  # sentence, so inverting all three callers to "After …" left this green — an
  # assertion that cannot fail on the thing its label names.
  assert_present "$label invokes the closeout before writing the report" \
    "$file" "$rep" "$n" '^[*][*]Closeout — zero tails[.][*][*] Before '
  ok "$label references $skillref in its report phase"
}

# The completion pass must be wired BEFORE the merge, or the split is decorative.
check_premerge() {
  local label=$1 file=$2 n
  n=$(total_lines "$file")
  assert_present "$label passes the closeout completion pass as a pre-merge check" \
    "$file" 1 "$n" 'completion pass of (quick|notion)-dev:session-closeout'
  # NOT '(last moment|before the merge)': the second alternative is satisfied by the
  # closeout invocation sentence ("already ran before the merge") and, in the notion-dev
  # callers, by an unrelated appendToSection line — so deleting the mechanism and flipping
  # the heading to "after the merge" left this green. Anchor on the mechanism alone.
  assert_present "$label states the merge is the last moment a fix can enter the PR" \
    "$file" 1 "$n" 'last moment a fix can still enter'
}
check_premerge "develop"  "$QD/skills/develop/SKILL.md"
# Local mode squash-merges itself and never enters review-and-merge, so the
# --pre-merge-check hook cannot reach it. It needs its own wire-in or the split
# is GitHub-only.
# The sweep only ever sees review-and-merge's own ledger, in GitHub mode. Claiming
# it covered plan-review items or local-mode items is an unsupported claim.
assert_present "develop does not claim the sweep covered plan-review or local-mode items" \
  "$QD/skills/develop/SKILL.md" 1 "$(total_lines "$QD/skills/develop/SKILL.md")" \
  'only one of the two sources of .file. items is ever swept'
assert_present "develop local mode runs the completion pass before its own squash" \
  "$QD/skills/develop/SKILL.md" 1 "$(total_lines "$QD/skills/develop/SKILL.md")" \
  'Local mode never enters .quick-dev:review-and-merge'
check_premerge "ticket"   "$ND/commands/ticket.md"
check_premerge "finalize" "$ND/commands/finalize.md"
# Phase 2 is the only place the pre-merge hook is wired, and the MERGED recovery
# path skips Phase 2 — so that path needs its own wire-in or Phase 5 asserts a
# pass that never ran.
assert_present "finalize's MERGED recovery path still runs the completion pass" \
  "$ND/commands/finalize.md" 1 "$(total_lines "$ND/commands/finalize.md")" \
  'The .MERGED. recovery path must still run the completion pass'

check_caller "develop Phase 6" \
  "$QD/skills/develop/SKILL.md" '^## Phase 6 ' 'quick-dev:session-closeout'
check_caller "ticket Phase 10" \
  "$ND/commands/ticket.md" '^## Phase 10 ' 'notion-dev:session-closeout'
check_caller "finalize Phase 5" \
  "$ND/commands/finalize.md" '^## Phase 5 ' 'notion-dev:session-closeout'

echo "== one pull request per session =="

# <label> <file> <start ere> <end ere>
check_one_pr() {
  local label=$1 file=$2 start_re=$3 end_re=$4
  local n s e
  if [ ! -f "$file" ]; then bad "$label: $file is missing"; return; fi
  n=$(total_lines "$file")
  s=$(find_line "$file" 1 "$n" "$start_re")
  if [ -z "$s" ]; then bad "$label: no section matching $start_re"; return; fi
  e=$(find_line "$file" $((s + 1)) "$n" "$end_re"); [ -n "$e" ] || e=$n
  assert_present "$label states the one-PR default" "$file" "$s" "$e" 'One pull request per'
  assert_present "$label checks for an already-open PR first" \
    "$file" "$s" "$e" 'gh pr list --state open'
  assert_present "$label requires a technical reason to split" \
    "$file" "$s" "$e" '[*][*]technical[*][*] reason'
}

check_one_pr "develop Phase 3" "$QD/skills/develop/SKILL.md" '^## Phase 3 ' '^## Phase 4 '
check_one_pr "ticket 6.4"      "$ND/commands/ticket.md"      '^### 6[.]4 Open PR' '^### 6[.]5 '

echo "== this repo's own development rules =="

if [ ! -f CLAUDE.md ]; then
  bad "CLAUDE.md is missing (this repo's own sessions would have no convergence rule)"
else
  n=$(total_lines CLAUDE.md)
  assert_present "CLAUDE.md sets the one-PR-per-session default" \
    CLAUDE.md 1 "$n" 'One pull request per session is the default'
  assert_present "CLAUDE.md requires the closeout before reporting done" \
    CLAUDE.md 1 "$n" 'session-closeout. skill before reporting'
  assert_present "CLAUDE.md names the signal phrases as unfinished work" \
    CLAUDE.md 1 "$n" 'one thing left'
  assert_present "CLAUDE.md states that widening a PR beats splitting it" \
    CLAUDE.md 1 "$n" '[*]not[*] a reason to defer'
  assert_count "CLAUDE.md points at the harness suite" \
    CLAUDE.md 1 "$n" 'scripts/verify-[*][.]sh' 2
  # The assertion-sensitivity rules from issue #30. Without these three lines the
  # mechanism exists but nothing tells the next session it is the rule.
  assert_present "CLAUDE.md routes every assertion through scripts/lib/assert.sh" \
    CLAUDE.md 1 "$n" '^Every assertion comes from .scripts/lib/assert[.]sh'
  assert_present "CLAUDE.md states the exactly-one-line anchor rule" \
    CLAUDE.md 1 "$n" 'requires its regex to match [*][*]exactly one[*][*] line'
  assert_present "CLAUDE.md states that a declared count is not an allowlist" \
    CLAUDE.md 1 "$n" 'that is not an allowlist, because it is'
  assert_present "CLAUDE.md states that the label is a claim the regex must honour" \
    CLAUDE.md 1 "$n" '^- [*][*]The label is a claim the regex has to honour'
fi

if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
fi
exit $(( fails > 0 ? 1 : 0 ))
