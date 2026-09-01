#!/usr/bin/env bash
# The harness that checks the harnesses.
#
# Issue #30: two review passes of PR #29 each found, BY HAND, the same defect —
# an assertion whose regex cannot fail on the thing its own label names. Four
# shipped. The sharpest re-instated file location as "criterion 4", the exact
# regression its harness exists to prevent, and the run still said ALL CHECKS
# PASSED.
#
# scripts/lib/assert.sh turns that class into a failure at authoring time. This
# file is what keeps it turned on:
#
#   A3  NO OPT-OUT — every scripts/verify-*.sh sources the library and defines
#       no assertion helper of its own, so tomorrow's harness cannot quietly
#       reintroduce a loose local `assert_present`.
#
#   A4  SELF-PROOF — the library is run against fixtures that reproduce all four
#       #30 defects and must FAIL on each, and against a benign duplicate and a
#       correct assertion and must PASS on those. "Prove every check can fail"
#       stops depending on someone remembering to do it.
#
# A4 is the part that matters most. A checker that silently stopped checking
# would make every other harness here vacuous at once, so it is the one place
# where the checks are proven both directions on every run.
#
# Run from anywhere: ./scripts/verify-assertions.sh
set -uo pipefail
cd "$(dirname "$0")/.."

fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

LIB=scripts/lib/assert.sh

# ---------------------------------------------------------------------------
# A3 — no harness may hand-roll its own assertions
# ---------------------------------------------------------------------------

echo "== every harness uses the shared assertion library =="

if [ ! -f "$LIB" ]; then
  bad "$LIB is missing — nothing below can mean anything"
  echo "1 CHECK(S) FAILED"
  exit 1
fi

harnesses=0
for h in scripts/verify-*.sh; do
  [ "$h" = "scripts/verify-assertions.sh" ] && continue
  harnesses=$((harnesses + 1))

  if grep -qE '^\. \./scripts/lib/assert\.sh$' "$h"; then
    ok "$h sources the shared library"
  else
    bad "$h does not source $LIB"
  fi

  # A local definition would shadow the library's, silently restoring the loose
  # behaviour. Match the definition form, not a mention: these files discuss
  # `assert_present` in their comments.
  if locals=$(grep -nE '^[[:space:]]*(assert_[a-z_]+|find_line|count_lines|matched_text|skeleton|label_[a-z_]+)\(\)' "$h"); then
    bad "$h defines its own assertion helper(s): $(printf '%s' "$locals" | tr '\n' ' ')"
  else
    ok "$h defines no assertion helper of its own"
  fi
done

if [ "$harnesses" -gt 0 ]; then
  ok "$harnesses harness(es) checked (discovered by glob, never listed)"
else
  bad "no scripts/verify-*.sh found — the harness set cannot be empty"
fi

# ---------------------------------------------------------------------------
# A4 — the library's own checks, proven in both directions
# ---------------------------------------------------------------------------

echo
echo "== the sensitivity checks can fail, and do not fail wrongly =="

FIX=$(mktemp -d)
trap 'rm -rf "$FIX"' EXIT

# Fixture 1 reproduces defects 1-3: a document that says the guarded phrase in
# the place the assertion means AND somewhere unrelated. Each of the three
# shipped defects had exactly this shape.
cat > "$FIX/loose.md" <<'FIXTURE'
**Closeout — zero tails.** Before writing the report, run the closeout.
The completion pass already ran before the merge, so only the workspace pass runs.
Reaching code the PR was not already changing is not a criterion.
A missing verdict line is not a criterion silently met.
The merge is the last moment a fix can still enter the PR.
FIXTURE

# Fixture 2 reproduces defect 4: the line says more than the regex checks, and
# the label names the part the regex left out.
cat > "$FIX/partial.md" <<'FIXTURE'
The sweep keeps **one item per commit** with its `Finding:` trailer.
FIXTURE

# Fixture 3b: two literals side by side. Matching the label classes directly
# against the prose missed the second one — `grep -oE` consumes the separating
# space with the first match, so the second has no leading boundary left. The
# library tokenizes before classifying; this is what proves it still does.
cat > "$FIX/adjacent.md" <<'FIXTURE'
The block keys are `SWEPT` `ABSORBED` in that order.
FIXTURE

# Fixture 3 is the benign case the issue insists must not be a failure: the same
# mechanism cited twice on purpose.
cat > "$FIX/twice.md" <<'FIXTURE'
Enumerate every worktree (`git worktree list --porcelain`).
    git worktree list --porcelain | awk '/^worktree /{print $2}'
FIXTURE

# expect <outcome: FAIL|PASS> <case name> <assert invocation...>
#
# Runs one assertion in a subshell with its own counters, so this harness's own
# `fails` is untouched by a fixture assertion that is SUPPOSED to fail.
expect() {
  local want=$1 name=$2; shift 2
  local out got
  out=$(
    fails=0
    ok()  { :; }
    bad() { printf '%s\n' "$1" >&2; fails=$((fails + 1)); }
    . "./$LIB"
    "$@" 2>&1 >/dev/null
    printf '\n__FAILS__%s' "$fails"
  )
  got=FAIL
  case "$out" in *__FAILS__0) got=PASS ;; esac
  if [ "$got" = "$want" ]; then
    ok "$name (expected $want)"
  else
    bad "$name — expected $want, got $got: ${out%%$'\n'__FAILS__*}"
  fi
}

# --- defect 1: an ordering anchor satisfied by an unrelated 'before' ---
expect FAIL "weak anchor: bare 'before' also matches 'ran before the merge'" \
  assert_present "loose.md: invokes the closeout before writing the report" \
  "$FIX/loose.md" 1 5 'Before |before '
expect PASS "the same assertion, anchored on the invocation sentence itself" \
  assert_present "loose.md: invokes the closeout before writing the report" \
  "$FIX/loose.md" 1 5 '^[*][*]Closeout — zero tails[.][*][*] Before '

# --- defect 2: an alternation whose second branch is satisfied elsewhere ---
expect FAIL "weak anchor: alternation's second branch matches an unrelated line" \
  assert_present "loose.md: states the merge is the last moment a fix can enter" \
  "$FIX/loose.md" 1 5 '(last moment|before the merge)'
expect PASS "the same assertion, anchored on the mechanism alone" \
  assert_present "loose.md: states the merge is the last moment a fix can enter" \
  "$FIX/loose.md" 1 5 'last moment a fix can still enter'

# --- defect 3: the one that stayed green through its own regression ---
expect FAIL "weak anchor: 'is not a criterion' also matches the Contract check" \
  assert_present "loose.md: states that reaching a new file is not a criterion" \
  "$FIX/loose.md" 1 5 'is not a criterion'
expect PASS "the same assertion, anchored on the clause that carries the claim" \
  assert_present "loose.md: states that reaching a new file is not a criterion" \
  "$FIX/loose.md" 1 5 'was not already changing is not a criterion'

# --- defect 4: matches exactly once, still does not check what the label says ---
expect FAIL "uncovered literal: label names \`Finding:\`, regex stops short of it" \
  assert_present "partial.md: keeps one commit per item with its \`Finding:\` trailer" \
  "$FIX/partial.md" 1 1 'one item per commit'
expect PASS "the same assertion, once the regex reaches the trailer" \
  assert_present "partial.md: keeps one commit per item with its \`Finding:\` trailer" \
  "$FIX/partial.md" 1 1 'one item per commit[*][*] with its .Finding:. trailer'

# --- the benign duplicate: declarable, not a failure and not a warning ---
expect FAIL "an undeclared duplicate is a failure" \
  assert_present "twice.md: the unpushed check spans every worktree" \
  "$FIX/twice.md" 1 2 'git worktree list --porcelain'
expect PASS "the same duplicate, declared with assert_count" \
  assert_count "twice.md: the unpushed check spans every worktree" \
  "$FIX/twice.md" 1 2 'git worktree list --porcelain' 2
# A declaration that has gone stale must go red, which is what separates it from
# an allowlist entry. Both directions, because only checking "at least n" would
# let the count rot upward.
expect FAIL "a declared count that is now too low" \
  assert_count "twice.md: the unpushed check spans every worktree" \
  "$FIX/twice.md" 1 2 'git worktree list --porcelain' 1
expect FAIL "a declared count that is now too high" \
  assert_count "twice.md: the unpushed check spans every worktree" \
  "$FIX/twice.md" 1 2 'git worktree list --porcelain' 3

# --- two literals side by side: the second must not be lost ---
# The two literals must be genuinely adjacent — one space, no word between them
# — or the fixture does not exercise the bug: with "SWEPT and ABSORBED" the
# separating word gives the second literal its own leading boundary, and with
# "SWEPT is a subset of ABSORBED" the first literal is dropped as the label's
# sentence-initial word before the classes ever run.
expect FAIL "the second of two adjacent literals is still required" \
  assert_present "adjacent.md: the block keys are SWEPT ABSORBED in that order" \
  "$FIX/adjacent.md" 1 1 'The block keys are .SWEPT.'
expect PASS "...and satisfied once the regex reaches it" \
  assert_present "adjacent.md: the block keys are SWEPT ABSORBED in that order" \
  "$FIX/adjacent.md" 1 1 'The block keys are .SWEPT. .ABSORBED.'

# --- the ordinary failures must still be failures ---
expect FAIL "a mechanism that is simply absent" \
  assert_present "loose.md: names a mechanism that is not there" \
  "$FIX/loose.md" 1 5 'no such mechanism anywhere'
expect FAIL "a file that does not exist" \
  assert_present "nope.md: anything at all" "$FIX/nope.md" 1 5 'anything'
expect PASS "assert_absent on something genuinely absent" \
  assert_absent "loose.md: does not mention criterion 4" \
  "$FIX/loose.md" 1 5 'criterion 4'
expect FAIL "assert_absent on something present" \
  assert_absent "loose.md: does not mention a criterion" \
  "$FIX/loose.md" 1 5 'is not a criterion'

# --- assert_order carries the same uniqueness rule ---
expect FAIL "an ordering anchor that matches more than one line" \
  assert_order "loose.md: closeout then criterion" "$FIX/loose.md" 1 5 \
  "closeout"  'closeout' \
  "criterion" 'is not a criterion'
expect PASS "the same ordering, with unique anchors" \
  assert_order "loose.md: closeout then criterion" "$FIX/loose.md" 1 5 \
  "closeout"  '^[*][*]Closeout — zero tails' \
  "criterion" 'was not already changing is not a criterion'

# --- whole-file literals: A2 applies, A1 deliberately does not ---
expect PASS "assert_has does not require uniqueness — vocabulary, not a place" \
  assert_has "twice.md: documents the worktree listing" \
  "$FIX/twice.md" 'git worktree list --porcelain'
expect FAIL "assert_has still fails when the label names what the literal omits" \
  assert_has "partial.md: keeps one commit per item with its \`Finding:\` trailer" \
  "$FIX/partial.md" 'one item per commit'
expect PASS "assert_has passes once the literal reaches the named part" \
  assert_has "partial.md: keeps one commit per item with its \`Finding:\` trailer" \
  "$FIX/partial.md" 'one item per commit** with its `Finding:` trailer'

# --- the awk escape-processing trap, which reading cannot find ---
# A regex containing `\|` must match a literal pipe. `awk -v` performs escape
# processing and delivers a bare `|` instead; the library passes the regex
# through ENVIRON, and this is the check that the pass-through is still in place.
#
# The pipe has to sit at the END of the regex. A `\|` in the middle degrades to
# ordinary alternation, which still matches selectively — the first version of
# this probe used `a line with a \| pipe`, and both the correct and the trapped
# library returned 1 for it, so the probe passed against a library with the trap
# deliberately restored. At the end, the trapped form becomes `pipe |`:
# alternation with an EMPTY right branch, which matches every line. That is the
# shape the trap actually takes, and the only shape that discriminates.
printf 'a plain line\na line ending in a pipe |\n' > "$FIX/pipe.md"
# All three primitives run their own awk, so all three are probed. Checking only
# one would leave the trap free to come back in the other two.
pipe_n=$( . "./$LIB"; count_lines "$FIX/pipe.md" 1 2 'pipe \|' )
if [ "$pipe_n" = 1 ]; then
  ok "count_lines: a trailing \\| still means a literal pipe (ENVIRON pass-through intact)"
else
  bad "count_lines: a trailing \\| matched $pipe_n of 2 lines — the awk -v escape-processing trap is back"
fi
pipe_ln=$( . "./$LIB"; find_line "$FIX/pipe.md" 1 2 'pipe \|' )
if [ "$pipe_ln" = 2 ]; then
  ok "find_line: a trailing \\| still means a literal pipe (ENVIRON pass-through intact)"
else
  bad "find_line: a trailing \\| first matched line $pipe_ln, expected 2 — the awk -v escape-processing trap is back"
fi
pipe_tx=$( . "./$LIB"; matched_text "$FIX/pipe.md" 1 2 'pipe \|' )
if [ "$pipe_tx" = 'a line ending in a pipe |' ]; then
  ok "matched_text: a trailing \\| still means a literal pipe (ENVIRON pass-through intact)"
else
  bad "matched_text: a trailing \\| returned '$pipe_tx' — the awk -v escape-processing trap is back"
fi

echo
if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
fi
exit $(( fails > 0 ? 1 : 0 ))
