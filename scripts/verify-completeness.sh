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

if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
fi
exit $(( fails > 0 ? 1 : 0 ))
