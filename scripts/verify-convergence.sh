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

# assert_version_above <label> <plugin.json> <pre-change baseline version>
# Pinning the exact version turns this suite red on the next unrelated bump.
# Assert instead that a version key exists and is strictly greater than the
# version this change started from.
assert_version_above() {
  local v
  v=$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$2" | head -1)
  if [ -z "$v" ]; then bad "$1 (no version key)"; return; fi
  if [ "$v" = "$3" ]; then bad "$1 (still at the pre-change $3)"; return; fi
  # Portable dotted-numeric compare. `sort -V` would be shorter, but it is a GNU
  # extension with uneven BSD/macOS support, and this harness is meant to run
  # wherever the repo does. awk is POSIX and numeric, so 0.10.0 > 0.9.0 holds —
  # which a plain lexical compare gets wrong.
  if awk -v a="$v" -v b="$3" 'BEGIN{
        na=split(a,A,"."); nb=split(b,B,".");
        n=(na>nb?na:nb);
        for(i=1;i<=n;i++){ x=(i<=na?A[i]+0:0); y=(i<=nb?B[i]+0:0);
          if(x>y) exit 0; if(x<y) exit 1 }
        exit 1 }'; then
    ok "$1 ($v > $3)"
  else
    bad "$1 ($v is not above $3)"
  fi
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
  assert_has   "$n r&m has the severity ratchet"     "$S" 'From round 3 onward, only a `blocking` finding may be triaged'
  assert_has   "$n r&m keeps the decline path"       "$S" 'a decline is not a `drop`'
  assert_lacks "$n r&m drops the stale runaway claim" "$S" 'That is why this cannot run away'
  assert_has "$n r&m has the induced cap"        "$S" 'A finding at `depth ≥ 2` is never absorbed'
  assert_has "$n r&m reverts non-blocking roots" "$S" 'revert the chain'
  assert_has "$n r&m keeps blocking-root fixes"  "$S" 'keep the fixes'
  assert_has "$n r&m has the minimal-patch rule" "$S" 'smallest edit that resolves that finding'
  assert_has "$n r&m bounds the fix by file"     "$S" 'touches no file the finding did not name'
  assert_has "$n r&m names the paired-edit case" "$S" 'stated repository invariant'
done

echo
if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
fi
exit $(( fails > 0 ? 1 : 0 ))
