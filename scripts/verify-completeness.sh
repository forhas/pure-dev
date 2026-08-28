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

# assert_has <label> <file> <literal string>
assert_has() {
  if grep -qF -- "$3" "$2"; then ok "$1"; else bad "$1"; fi
}

# assert_lacks <label> <file> <literal string>
assert_lacks() {
  if grep -qF -- "$3" "$2"; then bad "$1"; else ok "$1"; fi
}

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
  assert_has "$n names the Completeness gate"        "$RM" 'Nothing incomplete may be unlabeled at merge'
  assert_has "$n resolves citations gate-side"       "$RM" 'the gate resolves every citation'
  assert_has "$n matches code citations by content"  "$RM" 'by content, never by line number'
  assert_has "$n defines the unverified state"       "$RM" 'a third state that is not `met` and not `not-met`'
  assert_has "$n files unverified when degraded"     "$RM" 'unverified — completeness check degraded'
  assert_has "$n emits the COMPLETENESS key"         "$RM" 'COMPLETENESS:'
  assert_has "$n uses NONE for empty blocks"         "$RM" 'the literal `NONE`'
  assert_has "$n emits the COMPLETENESS-REPORT block" "$RM" 'the counts a caller consumes'
  assert_has "$n requires one verdict per criterion"  "$RM" 'one per criterion, in criteria-file order'
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
assert_has "develop freezes criteria in the PR"      "$D" 'The PR body is the freeze'
assert_has "develop passes --criteria-file"          "$D" 'if set), plus `--criteria-file'
assert_has "develop writes Unmet: trailers"          "$D" 'Append one `Unmet:` line for every criterion the completeness gate did not settle as'
assert_has "develop reports unmet criteria"          "$D" 'acceptance criteria were not met'
assert_has "local mode runs its own completeness check" "$D" '**Completeness check** (local mode)'
assert_has "local mode mirrors the verifier contract"   "$D" 'The completeness verifier'
assert_has "local mode resolves citations gate-side"    "$D" 'gate resolves every citation'
assert_has "local mode folds findings into the merge gate" "$D" 'completeness findings fold into this gate'
assert_has "local mode skips cleanly with no criteria"  "$D" 'reporting zero criteria'

if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
fi
exit $(( fails > 0 ? 1 : 0 ))
