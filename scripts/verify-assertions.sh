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

# <name> is the shared library's helper set. Three definition forms:
#   name()            name ()            function name  [()]
HELPER_NAMES='assert_[a-z_]+|find_line|count_lines|scan_region|skeleton|label_[a-z_]+'
HELPER_DEF_RE="^[[:space:]]*(function[[:space:]]+($HELPER_NAMES)[[:space:]]*(\(\))?|($HELPER_NAMES)[[:space:]]*\(\))[[:space:]]*\{?"

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
  #
  # All three shell definition forms, not just `name()`. POSIX allows whitespace
  # between the name and the parens, and bash also accepts `function name { … }`
  # with no parens at all — so a matcher keyed on `name()` alone lets a harness
  # define `assert_present () { … }` after sourcing the library, shadowing the
  # shared implementation while this check reports that nothing was defined.
  # That is A3 defeated by whitespace. The forms are proven in the fixture below.
  if locals=$(grep -nE "$HELPER_DEF_RE" "$h"); then
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

echo
echo "== the no-opt-out matcher catches every shell definition form =="

# A matcher that misses a form is a matcher that lets a harness shadow the shared
# implementation while this file reports it clean — A3 defeated by whitespace.
DEFS=$(mktemp)
cat > "$DEFS" <<'FORMS'
assert_present() { :; }
assert_present () { :; }
function assert_present { :; }
function assert_present() { :; }
  scan_region() { :; }
FORMS
n=$(grep -cE "$HELPER_DEF_RE" "$DEFS")
if [ "$n" -eq 5 ]; then
  ok "all 5 definition forms are caught (name(), name (), function name, function name(), indented)"
else
  bad "only $n of 5 definition forms caught — a harness could shadow the library undetected"
fi

# ...and does not fire on a mention. Every harness discusses these names in prose.
cat > "$DEFS" <<'FORMS'
# assert_present requires exactly one matching line
  assert_present "label" "$f" 1 10 'regex'
echo "see assert_present() in the library"
FORMS
n=$(grep -cE "$HELPER_DEF_RE" "$DEFS" || true)
if [ "$n" -eq 0 ]; then
  ok "a call, a comment and a prose mention are not definitions"
else
  bad "the matcher fired on $n non-definition line(s) — every harness would fail"
fi
rm -f "$DEFS"

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

# Fixture 3c: the label's SUBJECT leads, and it is the only literal it names.
# This is what isolates the leading-token rule — in a label naming two literals,
# dropping the first still leaves the second to fail on, so such a fixture passes
# either way and proves nothing.
cat > "$FIX/leading.md" <<'FIXTURE'
The final report line reports `SWEPT` for items the sweep fixed.
FIXTURE

# Fixture 3 is the benign case the issue insists must not be a failure: the same
# mechanism cited twice on purpose.
cat > "$FIX/twice.md" <<'FIXTURE'
Enumerate every worktree (`git worktree list --porcelain`).
    git worktree list --porcelain | awk '/^worktree /{print $2}'
FIXTURE

# Fixture 4: a hard-wrapped sentence, the shape every document here has. A
# literal lifted across the wrap becomes two grep -F patterns, so it matches on
# either line alone — the assertion then cannot fail on the half it names.
cat > "$FIX/wrapped.md" <<'FIXTURE'
The blast-radius citation requirement does not
relax because the passes are spent.
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

# --- a label whose SUBJECT leads: the first word is exempt from the Capitalized
#     class only, never from the ALL-CAPS / --flag / <placeholder> classes ---
# Dropping the leading token outright defeated A2 for every label of the form
# "SWEPT is …", "FILED items …", "--pre-merge-check is …" — precisely the labels
# whose first word IS the mechanism.
expect FAIL "a leading ALL-CAPS key is still required" \
  assert_present "leading.md: SWEPT is reported for items the sweep fixed" \
  "$FIX/leading.md" 1 1 'The final report line reports'
expect PASS "...and satisfied once the regex reaches it" \
  assert_present "leading.md: SWEPT is reported for items the sweep fixed" \
  "$FIX/leading.md" 1 1 'The final report line reports .SWEPT.'
# The exemption that does survive: an ordinary sentence-initial capital.
expect PASS "an ordinary sentence-initial capital names nothing and is exempt" \
  assert_present "partial.md: Keeps one commit per item with its \`Finding:\` trailer" \
  "$FIX/partial.md" 1 1 'one item per commit[*][*] with its .Finding:. trailer'

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

# --- assert_order honours A2, per anchor and per label ---
# It did neither until the sweep round of the pull request that added this file:
# it checked uniqueness and ordering and never called `assert_covers`, so every
# anchor name and every ordered label was an unchecked claim. The hole was live —
# an eight-item label carrying seven anchors let a whole guarded section be
# deleted with the suite green.
expect FAIL "an anchor whose NAME names what its regex omits" \
  assert_order "partial.md: the sweep rule" "$FIX/partial.md" 1 1 \
  "keeps one item per commit with its \`Finding:\` trailer" 'one item per commit'
expect PASS "...and satisfied once that anchor reaches it" \
  assert_order "partial.md: the sweep rule" "$FIX/partial.md" 1 1 \
  "keeps one item per commit with its \`Finding:\` trailer" \
  'one item per commit[*][*] with its .Finding:. trailer'
expect FAIL "an ordered LABEL naming a literal no anchor pins" \
  assert_order "adjacent.md: the block keys are SWEPT ABSORBED in that order" \
  "$FIX/adjacent.md" 1 1 \
  "block keys" 'The block keys are .SWEPT.'
expect PASS "...and satisfied once an anchor pins it" \
  assert_order "adjacent.md: the block keys are SWEPT ABSORBED in that order" \
  "$FIX/adjacent.md" 1 1 \
  "block keys" 'The block keys are .SWEPT. .ABSORBED.'

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
pipe_sc=$( . "./$LIB"; scan_region "$FIX/pipe.md" 1 2 'pipe \|' )
if [ "$pipe_sc" = "$(printf '1\na line ending in a pipe |')" ]; then
  ok "scan_region: a trailing \\| still means a literal pipe (ENVIRON pass-through intact)"
else
  bad "scan_region: a trailing \\| returned '$pipe_sc' — the awk -v escape-processing trap is back"
fi

# --- the third silent trap: a literal that spans a line break ---
# grep -F reads the newline as a pattern separator, so this literal matched the
# SECOND line while its own first line was mutated away, and reported PASS. It
# must be an authoring failure, not a match.
expect FAIL "multi-line literal is rejected rather than silently alternating" \
  assert_has "wrapped.md: the requirement does not relax" \
  "$FIX/wrapped.md" 'requirement does not
relax because the passes are spent'
# The half-match that proves the trap was real: the mutated first line is gone,
# yet the second still matches, so an unguarded assert_has would report PASS.
expect FAIL "...and the same literal cannot pass on its second line alone" \
  assert_has "wrapped.md: the requirement does not relax" \
  "$FIX/wrapped.md" 'requirement is waived and does
relax because the passes are spent'
expect PASS "a single-line fragment of the same sentence is the correct form" \
  assert_has "wrapped.md: the requirement does not relax" \
  "$FIX/wrapped.md" 'requirement does not'
expect FAIL "assert_lacks rejects a multi-line literal too" \
  assert_lacks "wrapped.md: says nothing about relaxing" \
  "$FIX/wrapped.md" 'requirement does not
relax because the passes are spent'
expect PASS "assert_lacks still passes on a single-line literal it does not find" \
  assert_lacks "wrapped.md: says nothing about ratchets" \
  "$FIX/wrapped.md" 'the ratchet judged it'
# assert_has_n was exercised in NEITHER direction, so the guard could have been
# dropped from it without this file noticing — the one failure mode A4 exists to
# prevent. Both directions now.
# The count must be the one the ALTERNATION would satisfy, or this case cannot
# discriminate. Each of the two lines matches exactly one line of the fixture, so
# an unguarded `grep -cF` returns 2: with want=1 the assertion would fail on the
# COUNT and `expect FAIL` would pass whether or not the guard exists. With want=2
# an unguarded assert_has_n PASSES, so only the guard can make this FAIL —
# verified by deleting the guard and watching this case go green.
expect FAIL "assert_has_n rejects a multi-line literal rather than counting its alternation" \
  assert_has_n "wrapped.md: the requirement does not relax" \
  "$FIX/wrapped.md" 'requirement does not
relax because the passes are spent' 2
expect PASS "assert_has_n counts a single-line literal correctly" \
  assert_has_n "wrapped.md: the requirement does not relax" \
  "$FIX/wrapped.md" 'requirement does not' 1
expect FAIL "assert_has_n still fails on the wrong count" \
  assert_has_n "wrapped.md: the requirement does not relax" \
  "$FIX/wrapped.md" 'requirement does not' 2

echo
if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
fi
exit $(( fails > 0 ? 1 : 0 ))
