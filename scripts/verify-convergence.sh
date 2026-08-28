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

# assert_has <label> <file> <literal string>
assert_has() {
  if grep -qF -- "$3" "$2"; then ok "$1"; else bad "$1"; fi
}

# assert_lacks <label> <file> <literal string>
assert_lacks() {
  if grep -qF -- "$3" "$2"; then bad "$1"; else ok "$1"; fi
}

# assert_identical <label> <fileA> <fileB>
assert_identical() {
  if diff -q "$2" "$3" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi
}

echo "== Task 1: rubric =="
RUBRIC=$ND/skills/plan-review/references/reviewer-rubric.md
assert_has    "rubric declares 'absorb'"            "$RUBRIC" '`absorb`'
assert_has    "rubric declares 'file'"              "$RUBRIC" '`file`'
assert_has    "rubric declares 'drop'"              "$RUBRIC" '`drop`'
assert_has    "rubric has blast-radius criterion 1" "$RUBRIC" 'reaches code the ticket was not already changing'
assert_has    "rubric has blast-radius criterion 2" "$RUBRIC" 'new public interface, dependency, config key, or data migration'
assert_has    "rubric has blast-radius criterion 3" "$RUBRIC" 'acceptance criteria do not already settle'
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

echo
if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
fi
exit $(( fails > 0 ? 1 : 0 ))
