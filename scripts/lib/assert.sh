#!/usr/bin/env bash
# Shared assertion library for this repo's verify-*.sh harnesses.
#
# WHY THIS FILE EXISTS
#
# Every harness here greps markdown for a mechanism. The failure mode that
# survived two review passes of PR #29 is not a missing assertion — it is an
# assertion that *cannot fail on the thing its own label names*, and therefore
# reports PASS while the mechanism it guards is gone. Four shipped:
#
#   * an ordering check anchored on a bare `before`, satisfied by "already ran
#     *before* the merge" elsewhere in the same sentence;
#   * a pre-merge check anchored on `(last moment|before the merge)`, whose
#     second alternative was satisfied by an unrelated line;
#   * "reaching a new file is not a criterion", anchored on `is not a criterion`,
#     also matched by the Contract check — so re-instating file location as
#     criterion 4, the exact regression it exists to prevent, stayed green;
#   * the sweep's per-commit rule, whose label named the `Finding:` trailer while
#     its regex covered only "one item per commit".
#
# Neither mutation testing (which only ever covers the mechanisms someone thought
# to mutate) nor the global vacuity run (empty every guarded file; everything must
# fail) reaches this class. All four survive an empty-file run, because an empty
# file makes a loose regex fail too.
#
# THE TWO RULES
#
# A1. UNIQUE ANCHOR. `assert_present` requires the regex to match EXACTLY ONE
#     line in its region. The first three defects above are all multi-match, and
#     all three fail here the moment they are written.
#
#     A blanket ban on multi-match would be wrong: instrumenting a full run found
#     4 multi-matching regexes, and 2 were legitimate — the same mechanism cited
#     twice on purpose. Warning on them every run would train people to skim past
#     the harness. So a legitimate duplicate DECLARES its count, inline, with
#     `assert_count`. That is not an allowlist: an allowlist only ever grants
#     permission and rots silently, whereas a declared count is re-verified in
#     BOTH directions on every run — too few fails, too many fails. When the doc
#     stops citing the mechanism twice, the declaration goes red and someone has
#     to look.
#
# A2. NAMED-LITERAL COVERAGE. Everything the LABEL names must be covered by the
#     REGEX. Concretely: any distinctive token in the label — a backticked span,
#     an ALL-CAPS word, a --flag, a <placeholder>, or a Capitalized word — that
#     ALSO occurs in the line the assertion matched must appear in the regex.
#
#     The intersection with the matched line is what keeps this precise. A label
#     is prose and says more than the regex should ("the sweep keeps ..."); only
#     the words the label and the guarded line agree on are claims the regex is
#     obliged to check. That is exactly the fourth defect: the label said
#     `Finding:`, the matched line said `Finding:`, the regex did not.
#
# A3. NO OPT-OUT. scripts/verify-assertions.sh requires every harness to source
#     this file and to define no assertion helper of its own, so a new harness
#     cannot reintroduce a loose local `assert_present`.
#
# A4. SELF-PROOF. scripts/verify-assertions.sh runs this library against fixtures
#     that reproduce all four defects above and requires each to FAIL, and
#     against a benign-duplicate and a clean fixture and requires those to PASS.
#     "Prove every check can fail" stops being a thing someone remembers to do.
#
# Sourced, never executed. The caller owns `fails`, `ok` and `bad`.

# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

# find_line <file> <start> <end> <ere> -> first matching line number, or empty
#
# The regex goes through ENVIRON, never `awk -v`. `-v` performs escape processing
# on the value, so a written `\|` reaches the matcher as a bare `|` — alternation
# with two empty branches, which matches every line — and gawk only *warns*. That
# turned three assertions vacuous once and nearly did it a second time; both were
# caught by mutation testing rather than by reading. ENVIRON passes the string
# through untouched, so an escape means what it says.
find_line() {
  RE="$4" awk -v s="$2" -v e="$3" \
    'NR >= s && NR <= e && $0 ~ ENVIRON["RE"] { print NR; exit }' "$1"
}

# count_lines <file> <start> <end> <ere> -> number of matching lines in region
count_lines() {
  RE="$4" awk -v s="$2" -v e="$3" \
    'NR >= s && NR <= e && $0 ~ ENVIRON["RE"] { n++ } END { print n + 0 }' "$1"
}

# nth_line <file> <start> <end> <ere> -> the TEXT of the first matching line
matched_text() {
  RE="$4" awk -v s="$2" -v e="$3" \
    'NR >= s && NR <= e && $0 ~ ENVIRON["RE"] { print; exit }' "$1"
}

total_lines() { wc -l < "$1" | tr -d ' '; }

# ---------------------------------------------------------------------------
# A2 — named-literal coverage
# ---------------------------------------------------------------------------

# skeleton <string> -> the string reduced to its alphanumeric characters.
#
# Comparison happens on skeletons so that a regex may spell a literal with this
# repo's escaping idioms — `[*][*]Finding` for **Finding, `.Finding:.` for a
# backticked one — without the check demanding the punctuation match too. What it
# still cannot do is let a regex OMIT the literal, which is the whole defect.
skeleton() { printf '%s' "$1" | tr -cd '[:alnum:]'; }

# label_body <label> -> the label with its "<file>: " scaffolding prefix removed.
#
# Harness labels are built as "$f: ..." and "$label ...", so the expanded string
# begins with a path. Left in, every path segment would read as a literal the
# regex must cover.
label_body() { printf '%s' "$1" | sed -E 's@^[^[:space:]]*[/.][^[:space:]]*:[[:space:]]+@@'; }

# label_literals <label> -> newline-separated distinctive tokens named by a label.
#
# Five classes, chosen because each is something a document says literally rather
# than something prose says about it:
#   `backticked`   an explicit literal — always required, matched line or not
#   ALLCAPS        report keys and states: MERGED, SWEPT, CONVERGENCE
#   --flag         command-line switches: --pre-merge-check
#   <placeholder>  template slots: <baseRefName>
#   Capitalized    proper mechanism names: Finding, Phase, Overview
# The first label token is skipped for the Capitalized class only: a label opens
# with a sentence-initial capital that names nothing.
label_literals() {
  local body first
  body=$(label_body "$1")
  # Backticked spans, always required.
  printf '%s' "$body" | grep -oE '`[^`]+`' | sed 's/`//g'
  # Strip backticked spans before scanning for the conditional classes, so a
  # token that is already backticked is not also reported unquoted.
  body=$(printf '%s' "$body" | sed -E 's/`[^`]*`/ /g')
  # Drop the label's first word before tokenizing: a label opens with a
  # sentence-initial capital that names nothing.
  first=${body%% *}
  body=" ${body#"$first"} "

  # TOKENIZE FIRST, then classify. Matching the classes directly against the
  # prose with `(^| )…( |$)` boundaries silently misses the second of two
  # adjacent literals: `grep -oE` consumes the separating space with the first
  # match, so the second no longer has a leading boundary to match against, and
  # a label reading "SWEPT and ABSORBED" reported only SWEPT. Splitting on
  # everything that cannot be part of a token removes the boundary problem
  # rather than working around it.
  printf '%s' "$body" | tr -c 'A-Za-z0-9_<>:-' '\n' | grep -vE '^$' | while IFS= read -r tok; do
    case "$tok" in
      --[A-Za-z]*)                                      printf '%s\n' "$tok" ;;   # --flag
      '<'[A-Za-z]*'>')                                  printf '%s\n' "$tok" ;;   # <placeholder>
      *)
        # ALL-CAPS report keys and states: MERGED, SWEPT, CONVERGENCE, HEAD.
        # Three characters, not two: "PR" is ordinary prose throughout these
        # documents ("an already-open PR", "widening a PR"), and requiring every
        # regex near it to spell it produced only noise.
        if printf '%s' "$tok" | grep -qE '^[A-Z][A-Z0-9_]{2,}([-][A-Z0-9_]+)*:?$'; then
          printf '%s\n' "$tok"
        # Proper mechanism names: Finding, Overview, Phase.
        elif printf '%s' "$tok" | grep -qE '^[A-Z][a-z]+:?$'; then
          printf '%s\n' "$tok"
        fi
        ;;
    esac
  done
}

# assert_covers <label> <regex> <matched line text>
#
# Returns 0 when every literal the label names is covered, 1 otherwise, printing
# the uncovered literal. A backticked literal is required unconditionally; every
# other class is required only when the matched line also contains it, because
# only then is it something both the label and the document actually assert.
assert_covers() {
  local label=$1 re=$2 line=$3
  local re_skel line_skel lit lit_skel backticked
  re_skel=$(skeleton "$re")
  line_skel=$(skeleton "$line")
  backticked=$(printf '%s' "$(label_body "$label")" | grep -oE '`[^`]+`' | sed 's/`//g')

  while IFS= read -r lit; do
    [ -n "$lit" ] || continue
    lit_skel=$(skeleton "$lit")
    [ -n "$lit_skel" ] || continue
    case "$re_skel" in *"$lit_skel"*) continue ;; esac
    # Unconditional for a backticked literal; otherwise only when the guarded
    # line says it too.
    if printf '%s\n' "$backticked" | grep -qxF "$lit"; then
      printf '%s' "$lit"; return 1
    fi
    case "$line_skel" in *"$lit_skel"*) printf '%s' "$lit"; return 1 ;; esac
  done <<EOF
$(label_literals "$label")
EOF
  return 0
}

# ---------------------------------------------------------------------------
# Region-scoped assertions
# ---------------------------------------------------------------------------

# _assert_n <label> <file> <start> <end> <ere> <expected count>
_assert_n() {
  local label=$1 file=$2 start=$3 end=$4 re=$5 want=$6
  local got line missing
  if [ ! -f "$file" ]; then bad "$label (missing file: $file)"; return; fi
  got=$(count_lines "$file" "$start" "$end" "$re")
  if [ "$got" -ne "$want" ]; then
    if [ "$got" -eq 0 ]; then
      bad "$label"
    elif [ "$want" -eq 1 ]; then
      # The anchor-weakness signal: it matched, but not only where it was meant to.
      bad "$label (weak anchor: /$re/ matches $got lines in ${file}:${start}-${end}; tighten it, or declare the count with assert_count)"
    else
      bad "$label (declared $want matches, found $got, for /$re/ in ${file}:${start}-${end})"
    fi
    return
  fi
  line=$(matched_text "$file" "$start" "$end" "$re")
  if ! missing=$(assert_covers "$label" "$re" "$line"); then
    bad "$label (label names '$missing' but /$re/ does not check it)"
    return
  fi
  ok "$label"
}

# assert_present <label> <file> <start> <end> <ere>
# Exactly one matching line. See A1.
assert_present() { _assert_n "$1" "$2" "$3" "$4" "$5" 1; }

# assert_count <label> <file> <start> <end> <ere> <n>
# Exactly <n> matching lines, for a mechanism the document cites <n> times on
# purpose. Checked in both directions on every run, so it cannot rot the way an
# allowlist entry does.
assert_count() { _assert_n "$1" "$2" "$3" "$4" "$5" "$6"; }

# assert_absent <label> <file> <start> <end> <ere>
assert_absent() {
  if [ ! -f "$2" ]; then bad "$1 (missing file: $2)"; return; fi
  if [ -z "$(find_line "$2" "$3" "$4" "$5")" ]; then ok "$1"; else bad "$1"; fi
}

# assert_order <label> <file> <start> <end> <name> <ere> [<name> <ere>]...
# Each anchor must be unique within the region and appear after the one before it.
# Fails on the first anchor that is missing, duplicated, or out of sequence.
assert_order() {
  local label=$1 file=$2 start=$3 end=$4; shift 4
  local prev=$((start - 1)) name re ln n
  if [ ! -f "$file" ]; then bad "$label (missing file: $file)"; return; fi
  while [ "$#" -gt 0 ]; do
    name=$1; re=$2; shift 2
    n=$(count_lines "$file" "$start" "$end" "$re")
    if [ "$n" -gt 1 ]; then
      bad "$label (weak anchor '$name': /$re/ matches $n lines in ${file}:${start}-${end})"
      return
    fi
    ln=$(find_line "$file" $((prev + 1)) "$end" "$re")
    if [ -z "$ln" ]; then bad "$label (no '$name' after line $prev)"; return; fi
    prev=$ln
  done
  ok "$label"
}

# ---------------------------------------------------------------------------
# Whole-file literal assertions
# ---------------------------------------------------------------------------

# A1 does NOT apply here, and the difference is the point. A region-scoped
# `assert_present` names a PLACE — "this line, in this section" — so a second
# match means the anchor is not pinning the place it claims to. A whole-file
# `assert_has` names a VOCABULARY — "this document defines `absorb`" — and a
# document that says `absorb` six times is doing its job. Requiring a count there
# would turn every new mention red, which is the "train people to ignore the
# harness" failure this library exists to avoid. Measured, not assumed: applying
# uniqueness to `assert_has` produced 64 failures across the two literal
# harnesses and not one of them was a defect.
#
# A2 still applies: whatever the label names, the literal must contain.

# assert_has <label> <file> <literal string>
assert_has() {
  local label=$1 file=$2 lit=$3 line missing
  if [ ! -f "$file" ]; then bad "$label (missing file: $file)"; return; fi
  line=$(grep -m1 -F -- "$lit" "$file") || { bad "$label"; return; }
  if ! missing=$(assert_covers "$label" "$lit" "$line"); then
    bad "$label (label names '$missing' but the literal '$lit' does not check it)"
    return
  fi
  ok "$label"
}

# assert_has_n <label> <file> <literal string> <n>
# For the rarer case where the COUNT is the invariant — a key that must be
# defined once, a table with a fixed number of rows. Checked in both directions.
assert_has_n() {
  local label=$1 file=$2 lit=$3 want=$4 got
  if [ ! -f "$file" ]; then bad "$label (missing file: $file)"; return; fi
  got=$(grep -cF -- "$lit" "$file" || true)
  if [ "$got" -ne "$want" ]; then
    bad "$label (declared $want occurrences of '$lit', found $got, in $file)"
    return
  fi
  ok "$label"
}

# assert_lacks <label> <file> <literal string>
assert_lacks() {
  if [ ! -f "$2" ]; then bad "$1 (missing file: $2)"; return; fi
  if grep -qF -- "$3" "$2"; then bad "$1"; else ok "$1"; fi
}

# assert_identical <label> <fileA> <fileB>
assert_identical() {
  if [ ! -f "$2" ]; then bad "$1 (missing: $2)"; return; fi
  if [ ! -f "$3" ]; then bad "$1 (missing: $3)"; return; fi
  if diff -q "$2" "$3" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi
}

# ---------------------------------------------------------------------------
# Version floors
# ---------------------------------------------------------------------------

# assert_version_above <label> <plugin.json> <pre-change baseline version>
# Pinning the exact version turns this suite red on the next unrelated bump.
# Assert instead that a version key exists and is strictly greater than the
# version this change started from.
assert_version_above() {
  local v
  if [ ! -f "$2" ]; then bad "$1 (missing file: $2)"; return; fi
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
