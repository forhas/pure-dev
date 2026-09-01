#!/usr/bin/env bash
# Structural verification for the absorb-by-default triage change.
# This repo ships markdown instruction files, not code — these greps and
# diffs are the test suite. Run from anywhere: ./scripts/verify-convergence.sh
set -uo pipefail
cd "$(dirname "$0")/.."

ND=plugins/notion-dev
QD=plugins/quick-dev
fails=0

ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# Assertions come from the shared library: `assert_has` there requires the
# literal to occur on EXACTLY ONE line, so a fragment that also appears somewhere
# unrelated fails instead of passing on the wrong line. A literal a document
# repeats on purpose declares its count with `assert_has_n`.
# (cd to the repo root already happened above, so this path is stable.)
. ./scripts/lib/assert.sh

echo "== Task 1: rubric =="
RUBRIC=$ND/skills/plan-review/references/reviewer-rubric.md
assert_has    "rubric declares 'absorb'"            "$RUBRIC" '`absorb`'
assert_has    "rubric declares 'file'"              "$RUBRIC" '`file`'
assert_has    "rubric declares 'drop'"              "$RUBRIC" '`drop`'
assert_has    "rubric has blast-radius criterion 1" "$RUBRIC" 'new public interface, dependency, config key, or data migration'
assert_has    "rubric has blast-radius criterion 2" "$RUBRIC" 'acceptance criteria do not already settle'
assert_has    "rubric has blast-radius criterion 3" "$RUBRIC" "obscure the plan's own"
# The criterion that used to be number 1 was removed deliberately: deferring a
# small fix because it lands in a new file cost a whole extra review-and-merge
# cycle. Assert its absence so it cannot creep back in as a fourth criterion.
assert_lacks  "rubric no longer defers on file location" "$RUBRIC" 'reaches code the ticket was not already changing'
assert_has    "rubric emits TRIAGE-COMPLETE"        "$RUBRIC" 'TRIAGE-COMPLETE:'
assert_lacks  "rubric drops NOT-IN-SCOPE-PRESENT"   "$RUBRIC" 'NOT-IN-SCOPE-PRESENT'
assert_identical "rubric copies are byte-identical" \
  "$QD/skills/plan-review/references/reviewer-rubric.md" "$RUBRIC"

echo "== Task 2: plan-review skill =="
for P in "$ND" "$QD"; do
  S=$P/skills/plan-review/SKILL.md
  n=$(basename "$P")
  assert_has   "$n plan-review parses TRIAGE-COMPLETE" "$S" 'TRIAGE-COMPLETE'
  assert_has   "$n plan-review block has TRIAGE key"   "$S" 'TRIAGE:'
  assert_has   "$n plan-review keeps nine-key rule"    "$S" 'nine keys'
  assert_lacks "$n plan-review drops NOT-IN-SCOPE"     "$S" 'NOT-IN-SCOPE'
  assert_has   "$n plan-review absorb→plan tasks"      "$S" 'absorb'
done

echo "== Task 3: review-and-merge =="
for P in "$ND" "$QD"; do
  S=$P/skills/review-and-merge/SKILL.md
  n=$(basename "$P")
  assert_has "$n r&m has the absorb merge gate"  "$S" 'No `absorb` item may be outstanding at merge'
  assert_has "$n r&m has the reclassify escape"  "$S" 'reclassification, not a bypass'
  assert_has "$n r&m reports ABSORBED"           "$S" 'ABSORBED'
  assert_has "$n r&m reports FILED"              "$S" 'FILED'
  assert_has "$n r&m reports DROPPED"            "$S" 'DROPPED'
done

echo "== Task 4: quick-dev develop =="
D=$QD/skills/develop/SKILL.md
assert_has "develop merge gate covers absorb" "$D" 'outstanding `absorb`'
assert_has "develop reports FILED items"      "$D" 'FILED'
assert_lacks "develop drops stale NOT-IN-SCOPE key" "$D" 'NOT-IN-SCOPE'

echo "== Task 5: REVIEW_REPORT three lists =="
for F in $ND/commands/ticket.md $ND/commands/finalize.md; do
  n=$(basename "$F")
  assert_has "$n records ABSORBED" "$F" 'ABSORBED'
  assert_has "$n records DROPPED"  "$F" 'DROPPED'
  assert_has "$n passes only FILED to epic-update" "$F" 'the `FILED` list'
done
assert_has "ticket-system renders Absorbed" "$ND/skills/ticket-system/SKILL.md" 'Absorbed'
assert_has "ticket-system renders Dropped"  "$ND/skills/ticket-system/SKILL.md" 'Dropped'
assert_lacks "ticket.md drops stale NOT-IN-SCOPE key" "$ND/commands/ticket.md" 'NOT-IN-SCOPE'

echo "== Task 6: epic-update =="
E=$ND/skills/epic-update/SKILL.md
assert_has   "epic-update sources FILED only"        "$E" 'only the `FILED` list'
assert_has   "epic-update gate offers Drop"          "$E" 'Drop (with rationale)'
assert_has   "epic-update records DROPPED"           "$E" 'DROPPED'
assert_has   "epic-update writes new log line"       "$E" '**Follow-ups dropped**'
assert_has   "epic-update parses legacy log line"    "$E" '**Follow-ups skipped**'
assert_lacks "epic-update: SKIPPED no longer blocks" "$E" '`SKIPPED` is empty'
assert_lacks "epic-update: SKIPPED key removed"      "$E" 'SKIPPED:'

echo "== Task 7: docs and versions =="
assert_has   "README describes absorb-first"   "$ND/README.md" 'absorb'
assert_lacks "README drops old epic claim"     "$ND/README.md" 'no follow-ups are outstanding'
assert_has   "create-task notes file-only"     "$ND/commands/create-task.md" 'already triaged `file`'
assert_version_above "notion-dev version bumped" "$ND/.claude-plugin/plugin.json" 0.12.2
assert_version_above "quick-dev version bumped"  "$QD/.claude-plugin/plugin.json" 0.7.2
assert_has   "spec carries a worked trace"     docs/superpowers/specs/2026-08-28-convergence-design.md 'Appendix: worked trace'
assert_lacks "issue-log signature drops SKIPPED" "$ND/skills/issue-log/references/signatures.md" 'SKIPPED'
assert_lacks "ticket.md has no stale SKIPPED"   "$ND/commands/ticket.md"   'SKIPPED'
assert_lacks "finalize.md has no stale SKIPPED" "$ND/commands/finalize.md" 'SKIPPED'

# The spec requires that no plugin invent a synonym for the vocabulary.
for S in $ND/skills/plan-review/SKILL.md $QD/skills/plan-review/SKILL.md \
         $ND/skills/plan-review/references/reviewer-rubric.md \
         $QD/skills/plan-review/references/reviewer-rubric.md \
         $ND/skills/review-and-merge/SKILL.md $QD/skills/review-and-merge/SKILL.md \
         $ND/skills/epic-update/SKILL.md; do
  n=${S#plugins/}
  assert_lacks "$n avoids synonym 'fold in'"   "$S" 'fold in'
  assert_lacks "$n avoids synonym 'inline it'" "$S" 'inline it'
done

echo "== quick-dev deferred trailer =="
D=$QD/skills/develop/SKILL.md
assert_has   "develop writes a Deferred: trailer"   "$D" 'Deferred:'
assert_has   "develop trailer names the criterion"  "$D" 'criterion <n>'
assert_has   "develop gate requires reclassify"     "$D" 'reclassify and merge'
assert_lacks "develop drops the bare merge-anyway"  "$D" 'merge anyway /'

echo "== triage metrics =="
for L in $ND/skills/flow-triage/references/ledger.md $QD/skills/flow-triage/references/ledger.md; do
  n=${L#plugins/}
  assert_has "$n documents triage_reclassified" "$L" 'triage_reclassified'
  assert_has "$n documents triage_filed"        "$L" 'triage_filed'
done
assert_has "ticket.md writes triage counts"    "$ND/commands/ticket.md"   'triage_reclassified'
assert_has "finalize.md writes triage counts"  "$ND/commands/finalize.md" 'triage_reclassified'
assert_has "develop writes triage counts"      "$QD/skills/develop/SKILL.md" 'triage_reclassified'
assert_has "develop surfaces the reclassify rate" "$QD/skills/develop/SKILL.md" 'reclassified to `file`'
assert_has "ticket.md surfaces the reclassify rate" "$ND/commands/ticket.md" 'reclassified to `file`'

echo "== legacy skip disclosure =="
assert_has "epic-update discloses legacy skips" "$E" 'recorded before `0.13.0`'
assert_has "epic-update comments on the epic"   "$E" 'postComment'
assert_has "epic-update logs legacy disclosure" "$E" '**Legacy follow-ups closed over**'
assert_has "epic-update reads its legacy line back" "$E" 'unioned with what the legacy-spelling line yielded'

echo "== review-loop convergence =="
for P in "$ND" "$QD"; do
  S=$P/skills/review-and-merge/SKILL.md
  n=$(basename "$P")
  assert_has "$n r&m has the convergence controls" "$S" '### Convergence controls'
  assert_has "$n r&m has the findings ledger"      "$S" '**The findings ledger.**'
  assert_has "$n r&m normalizes severity"          "$S" 'normalizes mechanically'
  assert_has "$n r&m names both severity values"   "$S" '`non-blocking`'
  assert_has "$n r&m pins the induced baseline"    "$S" 'R1_SHA'
  assert_has "$n r&m defines chain depth"          "$S" 'git blame -L'
  assert_has "$n r&m defines the locationless case"  "$S" '**Findings with no location.**'
  assert_has   "$n r&m matches the Rule 1 completeness carve-out" "$S" 'Rules 3 and 4 still reach'
  assert_lacks "$n r&m does not claim Rule 2 reaches completeness items" "$S" 'Rules 2, 3 and 4 still reach'
  assert_has "$n r&m has a locatable ledger field"   "$S" '| `locatable` |'
  assert_has "$n r&m keys locatable on a reviewed sha" "$S" 'no reviewed commit sha to read that line against'
  assert_has "$n r&m keeps local findings locatable"   "$S" '**a local-reviewer finding has both**'
  assert_lacks "$n r&m drops the review-object clause" "$S" 'or belongs to no review object'
  assert_has "$n r&m parses the Copilot header"      "$S" 'header and use that as the location'
  assert_has "$n r&m pins locatable = no"            "$S" '`locatable = no`'
  assert_has "$n r&m states the root/descendant asymmetry" "$S" 'may be a chain root, and can never be a chain descendant'
  assert_has "$n r&m covers a locationless Rule 2 root"    "$S" 'A root may be locationless'
  assert_has "$n r&m discloses unlocatable in INDUCED"     "$S" 'INDUCED: <n> (<pct> of findings after round 1, excluding <n> unlocatable)'
  assert_has   "$n r&m has the severity ratchet"     "$S" 'From round 3 onward, only a `blocking` finding may be triaged'
  assert_has   "$n r&m keeps the decline path"       "$S" 'a decline is not a `drop`'
  assert_lacks "$n r&m drops the stale runaway claim" "$S" 'That is why this cannot run away'
  assert_has "$n r&m has the induced cap"        "$S" 'A finding at `depth ≥ 2` is never absorbed'
  assert_has "$n r&m reverts non-blocking roots" "$S" 'revert the chain'
  assert_has "$n r&m keeps blocking-root fixes"  "$S" 'keep the fixes'
  assert_has   "$n r&m gives Rule 2 its own drop ground" "$S" "Rule 2's \`drop\` ground is the cap, not the ratchet"
  assert_has   "$n r&m detaches that ground from the round" "$S" 'carries no round precondition'
  assert_has   "$n r&m drops depth-2 non-blocking on the cap" "$S" '`drop` it citing **the induced cap**'
  assert_has   "$n r&m keeps Rule 1's ground round-scoped"  "$S" "**This ground is Rule 1's alone**, and it carries the round-3 precondition"
  assert_lacks "$n r&m drops the stale blocking-root cite"  "$S" '`drop` it on Rule 1'
  assert_lacks "$n r&m drops the stale revert-branch cite"  "$S" '`drop` on Rule 1'
  assert_has "$n r&m has the minimal-patch rule" "$S" 'smallest edit that resolves that finding'
  assert_has "$n r&m bounds the fix by scope"    "$S" 'touches no file beyond the finding'"'"'s scope'
  assert_has "$n r&m scopes unnamed findings"    "$S" 'smallest set of files that actually'
  assert_has "$n r&m names the paired-edit case" "$S" 'stated repository invariant'
  assert_has "$n r&m has verify-before-push" "$S" 'Rule 4 — verify before push'
  assert_has "$n r&m emits a CONVERGENCE block"      "$S" 'CONVERGENCE:'
  assert_has "$n r&m emits ABSORB-RATE"             "$S" 'ABSORB-RATE:'
  assert_has "$n r&m defines the disposition partition"  "$S" 'never a reported one'
  assert_has "$n r&m emits INDUCED"                  "$S" 'INDUCED:'
  assert_has "$n r&m emits INDUCED-CHAINS-CUT"       "$S" 'INDUCED-CHAINS-CUT:'
  assert_has "$n r&m emits RATCHET-ENGAGED-AT-ROUND" "$S" 'RATCHET-ENGAGED-AT-ROUND:'
  assert_has "$n r&m forbids an absent key"          "$S" 'never absence'
  assert_has "$n r&m scopes the unlocatable count"   "$S" 'scoped to the same population as the percentage'
  assert_has "$n r&m defines the zero-denominator rate" "$S" 'When the denominator is zero, `<pct>` reads `n/a`'
  assert_has "$n r&m emits ROUNDS"          "$S" 'ROUNDS:'
  assert_has "$n r&m emits FINDINGS-TOTAL"  "$S" 'FINDINGS-TOTAL:'
  assert_has "$n r&m emits ABSORBED"        "$S" 'ABSORBED:'
  assert_has "$n r&m binds the ratchet run-global" "$S" 'run-global'
  assert_has "$n r&m exempts completeness from Rule 1" "$S" 'outside Rule 1'
  assert_has "$n r&m terminates the local loop on no-change" "$S" 'never as "everything was'
done

assert_has   "quick-dev r&m verifies at the step-2 push" \
  "$QD/skills/review-and-merge/SKILL.md" "run Rule 4's verification first"
assert_lacks "quick-dev r&m drops the stale never-runs-tests claim" \
  "$QD/skills/review-and-merge/SKILL.md" 'the reviewer loop never runs tests at all'

assert_identical "r&m mirror matches the quick-dev copy" \
  "$QD/skills/review-and-merge/SKILL.md" .claude/skills/review-and-merge/SKILL.md
assert_version_above "notion-dev bumped for review-loop convergence" "$ND/.claude-plugin/plugin.json" 0.14.0
assert_version_above "quick-dev bumped for review-loop convergence"  "$QD/.claude-plugin/plugin.json" 0.9.0
assert_lacks "2026-08-28 spec no longer claims within-ticket loops converge" \
  docs/superpowers/specs/2026-08-28-convergence-design.md 'The *within-ticket* loops converge.'
assert_lacks "2026-08-28 spec no longer claims the failure is entirely across-ticket" \
  docs/superpowers/specs/2026-08-28-convergence-design.md 'The failure is entirely in *across-ticket filing*.'
assert_has "review-loop spec carries the measurement" \
  docs/superpowers/specs/2026-08-29-review-loop-convergence-design.md '68%'

echo
if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
fi
exit $(( fails > 0 ? 1 : 0 ))
