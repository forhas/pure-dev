#!/usr/bin/env bash
# Structural verification for the completeness gate.
# This repo ships markdown instruction files, not code — these greps are the
# test suite. Run from anywhere: ./scripts/verify-completeness.sh
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

echo "== spec status =="
SPEC=docs/superpowers/specs/2026-08-28-completeness-design.md
# The spec ships in the same PR as the implementation, so a "not yet implemented"
# status is a stale claim of exactly the kind this change's own gate exists to catch.
assert_lacks "spec status is not stale" "$SPEC" 'Not yet planned or implemented'
assert_has   "spec status names its plan"  "$SPEC" '../plans/2026-08-28-completeness.md'

echo "== Task 1: ticket-system write path =="
TS=$ND/skills/ticket-system/SKILL.md
assert_has "ticket-system tables refreshAcceptanceCriteria" "$TS" '| `refreshAcceptanceCriteria` |'
assert_has "refreshAcceptanceCriteria has its own section"  "$TS" '## refreshAcceptanceCriteria(id, verdicts)'
assert_has "it renders from the criteria file"              "$TS" 'never from the verifier'
assert_has "it owns the Acceptance Criteria format"         "$TS" 'single owner of the `Acceptance Criteria` section'

echo "== Task 2: completeness gate =="
for RM in $ND/skills/review-and-merge/SKILL.md $QD/skills/review-and-merge/SKILL.md; do
  n=${RM#plugins/}
  assert_has "$n documents --criteria-file"          "$RM" '--criteria-file'
  assert_has "$n dispatches the verifier"            "$RM" 'the gate needs the verdict before it can decide'
  assert_has "$n states the anti-circularity rule"   "$RM" 'never cite the deliverable'
  assert_has "$n names the Completeness gate"        "$RM" '**Completeness gate**: **Nothing incomplete may be unlabeled at merge.**'
  assert_has "$n resolves citations gate-side"       "$RM" 'the gate resolves every citation'
  assert_has "$n matches code citations by content"  "$RM" 'by content, never by line number'
  assert_has "$n defines the unverified state"       "$RM" 'a third state that is not `met` and not `not-met`'
  # The degraded path splits by WHICH failure occurred. A verifier that never ran
  # says nothing about the work, so its default is `blocked` (external: no check
  # ran), not `file` — filing there records a scope reduction per criterion against
  # work the evidence may fully support. Only a citation that failed to resolve is
  # genuine `unverified`. Collapsing the two is the defect this pair pins.
  assert_has "$n defaults a never-run verifier to blocked" "$RM" 'blocked — completeness verifier unavailable'
  assert_has "$n keeps unresolved citations unverified"    "$RM" 'unverified — citation did not resolve'
  assert_lacks "$n no longer files on a degraded verifier" "$RM" 'unverified — completeness check degraded'
  assert_has "$n emits the COMPLETENESS key"         "$RM" 'COMPLETENESS:'
  assert_has "$n uses NONE for empty blocks"         "$RM" 'the literal `NONE`'
  assert_has "$n emits the COMPLETENESS-REPORT block" "$RM" 'a **`COMPLETENESS-REPORT`** section'
  assert_has "$n takes the report counts from the gate, not the verifier" \
    "$RM" "the counts a caller consumes are always the gate's, never the verifier's raw ones"
  assert_has "$n requires one verdict per criterion"  "$RM" 'one per criterion, in criteria-file order'

  # The keyed output block itself — the interface all four callers parse. Deleting the
  # block left both harnesses green before these three assertions existed: `COMPLETENESS:`
  # occurs three times, so it survived the block's removal. These literals occur only
  # inside the block.
  assert_has "$n keys the not-met count in its output block"     "$RM" 'CRITERIA-NOT-MET: <n>'
  assert_has "$n keys the unverified count in its output block"  "$RM" 'CRITERIA-UNVERIFIED: <n>'
  assert_has "$n specifies the VERDICTS line shape"              "$RM" '- [<met|not-met|unverified>] <criterion verbatim>'
  # The four rules that were deletable with both harnesses green.
  assert_has "$n re-runs the gate stack unconditionally" "$RM" 'The gate stack then re-runs on the new HEAD,'
  assert_has "$n caps the verifier at two passes"        "$RM" 'The verifier runs at most twice.'
  assert_has "$n dispatches artifacts as file paths"     "$RM" 'as **file paths, not inline text**'
  assert_has "$n excludes the implementer's material"    "$RM" 'Pass **nothing** from the implementer'
  # C2: the interactive degraded branch still raises items.
  assert_has "$n raises items even when the user merges past a degraded check" "$RM" 'the user decides, every unverified criterion still becomes an item'
  # I1: the verification output the gate resolves test citations against has a producer.
  assert_has "$n runs verification itself when the loop retained none" "$RM" 'before dispatching, and retains that as `VERIFY_OUTPUT`'
  # I2: pass 2 can still resolve a re-citation into pass 1's own commits.
  assert_has "$n scopes pass 2 to the new commits plus the original diff" "$RM" 'the new commits plus the original diff'
  # I4: the stated limitation, at the gate a reader of the gate meets. The disclaimer
  # literal below is a NEGATION — it survives the removal of the triage rule that is the
  # only thing standing behind the decision to state this limitation rather than fix it.
  # So the rule gets its own anchor, on the sentence that carries it.
  assert_has "$n states that completeness-absorb work is not code-reviewed" "$RM" '`absorb` work is not code-reviewed'
  assert_has "$n keeps the triage rule that mitigates it"                   "$RM" 'prefer `file` over `absorb` for any'
  # `blocked` has a defined producer rather than being an undefined enum member.
  assert_has "$n defines when the block reads blocked" "$RM" '- **`blocked`** — the check ran and produced at least one item'
done

echo "== Task 3: quick-dev criteria derivation =="
FT=$QD/skills/flow-triage/SKILL.md
assert_has "flow-triage emits CRITERIA"           "$FT" '- <observable criterion 1>'
assert_has "flow-triage emits COVERAGE-MAP"       "$FT" '- "<sentence from feature description>" ->'
assert_has "flow-triage caps the criteria count"  "$FT" '3-6 observable criteria'
assert_has "flow-triage marks uncovered clauses"  "$FT" '-> not covered —'
assert_has "flow-triage freezes before the build" "$FT" 'before any code exists'

echo "== Task 4: quick-dev develop wiring =="
D=$QD/skills/develop/SKILL.md
assert_has "develop writes a criteria file"          "$D" 'one criterion per line, verbatim, no bullet markers'
assert_has "develop freezes criteria in the PR"      "$D" 'Compose the PR body to include the frozen acceptance criteria verbatim'
assert_has "develop passes --criteria-file"          "$D" 'if set), plus `--criteria-file'
assert_has "develop writes Unmet: trailers"          "$D" 'Append one `Unmet:` line for every criterion the completeness gate did not settle as `met`:'
assert_has "develop reports unmet criteria"          "$D" 'acceptance criteria were not met'
assert_has "local mode runs its own completeness check" "$D" '**Completeness check** (local mode)'
assert_has "local mode mirrors the verifier contract"   "$D" 'The completeness verifier'
assert_has "local mode resolves citations gate-side"    "$D" 'gate resolves every citation'
assert_has "local mode folds findings into the merge gate" "$D" 'completeness findings fold into this gate'
assert_has "local mode distinguishes zero criteria from a check that never ran" "$D" 'this step running at all is what makes `0` the correct value here, never `null`'
assert_has "develop posts the completeness report as a PR comment" "$D" 'gh pr comment <pr-number> --body-file <path>'
assert_has "develop states review-and-merge does not post the report" "$D" 'produces the `COMPLETENESS-REPORT` section but does not post it'
assert_has "local mode degrades without deadlocking non-interactive runs" "$D" 'unverified — completeness check degraded'
assert_has "local mode states absorb as the triage default" "$D" '`absorb` is the default, `file` must cite its blast-radius criterion number, and `drop` must carry a rationale'
assert_has "local mode restates the completeness counts" "$D" "never the agent's raw counts, since it cannot know which of its own citations resolved"
assert_has "local mode falls back to Phase 2c's output on a clean pass" "$D" 'pass `VERIFY_OUTPUT` (2c'"'"'s retained output) instead'
assert_has "develop keeps Unmet separate from Deferred for criteria items" "$D" 'never `Deferred:`, even when the merge gate'
assert_has "develop reports coverage gaps from COVERAGE_MAP" "$D" 'from `COVERAGE_MAP`: report any `-> not covered` lines verbatim'
assert_has "2c retains its verification output for the completeness check" "$D" 'Record the output as `VERIFY_OUTPUT`'
assert_has "local mode resolves test citations without enumerating step numbers" "$D" 'the named test must appear, passing, in the verification output the gate already holds'
assert_has "local mode raises items even when the user merges past a degraded check" "$D" 'the user decides, every unverified criterion still becomes an item'
assert_has "local mode fixes its absorb items and caps itself at two passes" "$D" 'This check runs at most twice.'
assert_has "local mode reclassifies rather than halting a non-interactive run" "$D" 'must be reclassified to `file` or `drop` with a rationale'
assert_has "local mode states that completeness-absorb work is not code-reviewed" "$D" '`absorb` work is not code-reviewed'
assert_has "local mode states the editable-criteria weakness honestly" "$D" 'byte-identical to a genuinely complete run'
assert_has "a reclassified criterion item takes an Unmet: trailer, not a Deferred: one" \
  "$D" "as a \`Deferred:\` trailer **when it is a review finding**, or as an \`Unmet:\` trailer when it is a completeness criterion's own item"
assert_lacks "develop drops the resume case the flow does not have" "$D" 'a resumed run that skipped 2a'

echo "== Task 5: notion-dev caller wiring =="
for C in $ND/commands/ticket.md $ND/commands/finalize.md; do
  n=${C#plugins/}
  assert_has "$n writes a criteria file"          "$C" 'criteria-<KEY>-<id>.md'
  assert_has "$n passes --criteria-file"          "$C" '--criteria-file'
  assert_has "$n ticks the acceptance criteria"   "$C" 'refreshAcceptanceCriteria(id, verdicts)'
  assert_has "$n appends (never upserts) the Completeness block" \
    "$C" '`appendToSection(id, "Implementation", …)` with a **Completeness** block — never `upsertSection`'
  assert_has "$n reports unmet criteria"          "$C" 'acceptance criteria were not met'
  # C1: `refreshAcceptanceCriteria` renders `- [x]`, so a re-run sees ticked boxes.
  # Stripping only `- [ ]` would embed the old marker and accumulate one per run.
  assert_has "$n strips ticked and bare-bullet markers too" "$C" 'or a bare `- ` bullet'
done
assert_lacks "quick-dev's review-and-merge drops the resume case the flow does not have" \
  "$QD/skills/review-and-merge/SKILL.md" 'resumed after its criteria file went missing'
assert_has "finalize splits the persisted report at ## Completeness on recovery" \
  "$ND/commands/finalize.md" 'Split its contents at the `## Completeness` heading Phase 2 appends'
assert_has "finalize degrades to today's behaviour when there is no such heading" \
  "$ND/commands/finalize.md" 'the whole file becomes `REVIEW_REPORT`, unchanged, and `COMPLETENESS_REPORT` is simply absent'

echo "== Task 6: completeness metrics =="
for L in $ND/skills/flow-triage/references/ledger.md $QD/skills/flow-triage/references/ledger.md; do
  n=${L#plugins/}
  assert_has "$n documents completeness_criteria"   "$L" 'completeness_criteria'
  assert_has "$n documents completeness_unverified" "$L" 'completeness_unverified'
  assert_has "$n distinguishes a real completeness 0 from the null case" "$L" 'a check that ran and found nothing, not one that never ran'
done
assert_has "ticket.md writes completeness counts"   "$ND/commands/ticket.md"      'completeness_criteria'
assert_has "finalize.md writes completeness counts" "$ND/commands/finalize.md"    'completeness_criteria'
assert_has "develop writes completeness counts"     "$QD/skills/develop/SKILL.md" 'completeness_criteria'
assert_has "develop's ledger site distinguishes a real completeness 0 from the null case" "$QD/skills/develop/SKILL.md" 'a check that ran and found nothing, not one that never ran'
# An unset CRITERIA_FILE must NOT skip the whole record: the gate still runs charges 2
# and 3 without a criteria file, so CLAIMS/CAVEATS/TRIAGE can carry real findings.
for C in $ND/commands/ticket.md $ND/commands/finalize.md; do
  n=${C#plugins/}
  assert_has "$n records claims/caveats even with no criteria file" "$C" 'An unset `CRITERIA_FILE` is not that case'
done
assert_has "ticket.md's ledger site distinguishes a real completeness 0 from the null case"   "$ND/commands/ticket.md"   'a check that ran and found nothing, not one that never ran'
assert_has "finalize.md's ledger site distinguishes a real completeness 0 from the null case" "$ND/commands/finalize.md" 'a check that ran and found nothing, not one that never ran'

echo "== Task 6b: the spec documents what the implementation does =="
SPEC=docs/superpowers/specs/2026-08-28-completeness-design.md
assert_has "spec names local mode's own gate"           "$SPEC" 'a local-mode Completeness gate, not a duplicate verifier'
assert_has "spec names the Completeness gate as the trailers' producer" \
  "$SPEC" "**The producer is local mode's own Completeness gate**"
assert_has "spec gives the verification output a producer" "$SPEC" 'must be *retained* by whatever ran it'
assert_has "spec scopes pass 2 to the new commits plus the original diff" "$SPEC" 'the new commits plus the original diff'
assert_has "spec raises items on the interactive degraded branch" "$SPEC" 'Whatever the user decides, every unverified criterion still becomes an item'
assert_has "spec disclaims review of completeness-absorb work" "$SPEC" 'That work absorbed at this gate is code-reviewed.'
assert_has "spec states the local-mode freeze weakness honestly" "$SPEC" 'byte-identical to a genuinely complete run'
assert_has "spec defines when the block reads blocked" "$SPEC" '`blocked` means the check ran and produced at least one item'
assert_lacks "spec drops the resume case quick-dev does not have" "$SPEC" 'resumed after its criteria file went missing'

echo "== Task 7: docs, versions, and shared-wording parity =="
assert_has "notion-dev README covers the gate" "$ND/README.md" 'completeness gate'
assert_has "quick-dev README covers the gate"  "$QD/README.md" 'completeness gate'
assert_version_above "notion-dev version bumped" "$ND/.claude-plugin/plugin.json" 0.13.0
assert_version_above "quick-dev version bumped"  "$QD/.claude-plugin/plugin.json" 0.8.0

# Parity guard: the completeness-report bullet is near-verbatim shared between the two
# plugins' review-and-merge skills, and nothing else asserts the two copies stay in sync.
SHARED_COMPLETENESS_REPORT_BULLET='The report also carries a **`COMPLETENESS-REPORT`** section: the verifier'"'"'s keyed block, with the four `CRITERIA-*` counts restated after citation resolution and each `met` verdict'"'"'s citation replaced by the gate'"'"'s resolution of it — the counts a caller consumes are always the gate'"'"'s, never the verifier'"'"'s raw ones, because the verifier cannot know which of its own citations resolved.'
for RM in $ND/skills/review-and-merge/SKILL.md $QD/skills/review-and-merge/SKILL.md; do
  n=${RM#plugins/}
  assert_has "$n keeps the completeness-report bullet in parity with its sibling plugin" "$RM" "$SHARED_COMPLETENESS_REPORT_BULLET"
done

if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
fi
exit $(( fails > 0 ? 1 : 0 ))
