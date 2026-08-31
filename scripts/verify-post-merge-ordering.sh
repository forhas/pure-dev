#!/usr/bin/env bash
# Post-merge cleanup ordering — the contract PRs #20 and #23 shipped.
#
# A ticket run merges a PR, then cleans up: remove the worktree, delete the
# local branch, move the primary checkout onto the base branch, run post-merge
# hooks. Get that order wrong and the primary's `checkout` collides with a
# worktree still holding the base branch, or a hook commits and pushes from
# whatever branch the primary happened to be on. That defect recurred on five
# consecutive ticket runs before #20 fixed it.
#
# The fix is prose — an ordering and a set of assertions written in markdown —
# which is exactly the kind of thing an edit reverts by accident. Same argument
# as verify-mirror.sh beside this file: a written reminder is not a mechanism;
# this is.
#
# Like verify-mirror.sh and unlike verify-completeness.sh / verify-convergence.sh,
# this asserts a standing invariant. It carries no baseline and no version floor,
# so it has nothing to go stale against.
#
# It matches MECHANISM, not wording: command strings, the relative order of the
# lines that carry them, the presence of each assertion line. Where prose must be
# matched, it matches the shortest distinctive fragment. Rewording a paragraph
# must not fail this harness; changing what the flow does must.
#
# Run from anywhere: ./scripts/verify-post-merge-ordering.sh
set -uo pipefail
cd "$(dirname "$0")/.."

fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# The two flows that own a worktree and clean it up.
TICKET=plugins/notion-dev/commands/ticket.md
FINALIZE=plugins/notion-dev/commands/finalize.md
DEVELOP=plugins/quick-dev/skills/develop/SKILL.md

# Every copy of the merge-and-delete sequence. The .claude/ mirror is included
# deliberately: verify-mirror.sh proves it matches the plugin, this proves the
# thing it matches is still correct, and the mirror is the copy this repo drives
# its own PRs with.
MERGE_DOCS=(
  plugins/notion-dev/skills/review-and-merge/SKILL.md
  plugins/notion-dev/skills/review-and-merge/references/github-api.md
  plugins/quick-dev/skills/review-and-merge/SKILL.md
  plugins/quick-dev/skills/review-and-merge/references/github-api.md
  .claude/skills/review-and-merge/SKILL.md
  .claude/skills/review-and-merge/references/github-api.md
)

# quick-dev resolves the head repository and percent-encodes the ref (#23).
# notion-dev still deletes from `origin` unconditionally — a known gap, tracked
# separately. Listing the files that must have the fix, rather than asserting it
# repo-wide, is what keeps this harness honest about which copies actually do.
HEADREPO_DOCS=(
  plugins/quick-dev/skills/review-and-merge/SKILL.md
  plugins/quick-dev/skills/review-and-merge/references/github-api.md
  .claude/skills/review-and-merge/SKILL.md
  .claude/skills/review-and-merge/references/github-api.md
)

# Only the SKILL.md copies carry the encoding TABLE with the `% → %25` mapping;
# the reference copies state the rule in prose and never give the %25 literal.
# That asymmetry is in PR #23's text, not this PR's, so it is recorded as
# follow-up rather than papered over by asserting %25 where it does not exist.
PCT25_DOCS=(
  plugins/quick-dev/skills/review-and-merge/SKILL.md
  .claude/skills/review-and-merge/SKILL.md
)

# ---------------------------------------------------------------- primitives

# first line number matching <regex> in <file> within [<start>,<end>]; empty if none
find_line() {
  awk -v s="$2" -v e="$3" -v re="$4" \
    'NR >= s && NR <= e && $0 ~ re { print NR; exit }' "$1"
}

# how many lines match <regex> in <file> within [<start>,<end>]
count_lines() {
  awk -v s="$2" -v e="$3" -v re="$4" \
    'NR >= s && NR <= e && $0 ~ re { n++ } END { print n + 0 }' "$1"
}

total_lines() { wc -l < "$1" | tr -d ' '; }

# assert_present <label> <file> <start> <end> <regex>
assert_present() {
  if [ -n "$(find_line "$2" "$3" "$4" "$5")" ]; then ok "$1"; else bad "$1"; fi
}

# assert_order <label> <file> <start> <end> <name> <regex> [<name> <regex>]...
# Fails on the first anchor that is missing or out of sequence, and says which.
assert_order() {
  local label=$1 file=$2 start=$3 end=$4; shift 4
  local prev=0 prev_name="" name re ln
  while [ $# -gt 1 ]; do
    name=$1; re=$2; shift 2
    ln=$(find_line "$file" "$start" "$end" "$re")
    if [ -z "$ln" ]; then
      bad "$label — nothing matches '$name'"; return
    fi
    if [ "$ln" -le "$prev" ]; then
      bad "$label — '$name' (line $ln) does not follow '$prev_name' (line $prev)"; return
    fi
    prev=$ln; prev_name=$name
  done
  ok "$label"
}

# ------------------------------------------------- 1-2. cleanup step ordering

# Asserts, for one flow's cleanup section: the worktree goes first, the local
# branch next, the primary's checkout second-to-last, the rmdir last — and that
# the pull is --ff-only. Returns the section bounds via CLEAN_START/CLEAN_END so
# the hook checks below can reuse them.
check_cleanup() {
  local label=$1 file=$2 start_re=$3 end_re=$4 base=$5
  CLEAN_START=""; CLEAN_END=""

  if [ ! -f "$file" ]; then bad "$label cleanup section (missing: $file)"; return; fi

  local start end
  start=$(find_line "$file" 1 "$(total_lines "$file")" "$start_re")
  if [ -z "$start" ]; then bad "$label — no cleanup section heading in $file"; return; fi
  end=$(find_line "$file" $((start + 1)) "$(total_lines "$file")" "$end_re")
  [ -n "$end" ] || end=$(total_lines "$file")
  CLEAN_START=$start; CLEAN_END=$end

  assert_order "$label cleanup order: worktree -> branch -> checkout -> rmdir" \
    "$file" "$start" "$end" \
    "git worktree remove"           'git worktree remove' \
    "git branch -D"                 'git branch -D' \
    "git checkout <base> && git pull" "git checkout $base && git pull" \
    "rmdir"                         'rmdir'

  # Separate from the ordering check on purpose: dropping --ff-only is its own
  # regression (a diverged primary would manufacture a merge commit, which is
  # the original STO-97 damage) and deserves its own named failure.
  #
  # Both anchors carry the base-branch operand. Without it, retargeting the
  # cleanup to `git checkout <headRefName> && git pull --ff-only origin
  # <headRefName>` satisfied every check while the primary ended up on the wrong
  # branch — which is the entire invariant, not a detail of it.
  assert_present "$label pull is --ff-only onto the base branch" \
    "$file" "$start" "$end" "git pull --ff-only origin $base"
}

echo "== cleanup step ordering =="
check_cleanup "ticket.md Phase 9" "$TICKET" '^## Phase 9 .*[Cc]lean' '^### ' '<baseRefName>'
TICKET_CLEAN_END=$CLEAN_END
check_cleanup "finalize.md Phase 4" "$FINALIZE" '^## Phase 4 .*[Cc]lean' '^### ' '<baseRefName>'
FINALIZE_CLEAN_END=$CLEAN_END
check_cleanup "develop Phase 5" "$DEVELOP" '^## Phase 5 .*[Cc]lean' '^## Phase 6' '"[$]MAIN"'

# ------------------------------------------- 3-4. hooks run after the cleanup

# Only notion-dev has post-merge hooks (git.postMergeHooks); quick-dev's develop
# flow has no hook step, so it is not checked here.
#
# Anchored on the hook INVOCATION line, not on the section heading. An earlier
# draft keyed on `### Post-merge hooks` and failed the moment that heading was
# reworded with nothing else changed — which is the failure this harness is
# supposed to avoid, not cause.
# The affirmative directive, not just the hook name: `Never run
# `git.postMergeHooks` skills in order` contains the name fragment too, so a
# name-only match would report a flow that invokes no hooks at all as compliant.
HOOK_RUN='^Run .git[.]postMergeHooks. skills in order'

check_hooks() {
  local label=$1 file=$2 clean_end=$3
  local total; total=$(total_lines "$file")

  # Exactly one place invokes the hooks. A reinstated pre-cleanup hook step (the
  # `8.4` this ordering removed) brings its own invocation line, so it shows up
  # here as a second one — no need to hardcode the section number it carried.
  local n; n=$(count_lines "$file" 1 "$total" "$HOOK_RUN")
  if [ "$n" -eq 1 ]; then
    ok "$label invokes postMergeHooks in exactly one place"
  else
    bad "$label invokes postMergeHooks in $n places (expected 1)"
  fi

  local hooks; hooks=$(find_line "$file" 1 "$total" "$HOOK_RUN")
  if [ -z "$hooks" ]; then
    bad "$label — nothing invokes git.postMergeHooks"; return
  fi
  if [ "$hooks" -gt "$clean_end" ]; then
    ok "$label hooks run after cleanup (invocation line $hooks)"
  else
    bad "$label hooks run BEFORE cleanup ends (invocation line $hooks <= $clean_end)"
  fi

  # The three preconditions a hook must clear before it is invoked. Each catches
  # something the others do not — name-only, contains-the-merge, and only-the-merge
  # — so all three are asserted individually rather than as one block.
  # Each anchor carries the CONDITION, not just the command name. Matching the
  # name alone let `# must equal <baseRefName>` be deleted outright, and let the
  # ancestor test be reversed to `--is-ancestor HEAD <merge-commit>` — which
  # inverts the check into one that passes while the merge is absent from HEAD.
  assert_present "$label hook assertion 1/3: HEAD is on <baseRefName>" \
    "$file" "$hooks" "$total" 'rev-parse --abbrev-ref HEAD.*<baseRefName>'
  assert_present "$label hook assertion 2/3: <merge-commit> is an ancestor of HEAD" \
    "$file" "$hooks" "$total" 'merge-base --is-ancestor <merge-commit> HEAD'
  # Both halves as ONE assertion, bound by adjacency. The test spans two lines,
  # and searching for them independently anywhere in the section let the equality
  # compare HEAD to any ref at all while a stray `rev-parse origin/<baseRefName>`
  # in the prose below satisfied the operand half. Requiring `" = ` rather than a
  # bare `=` also rejects an inverted `" != `.
  local eq_ln; eq_ln=$(find_line "$file" "$hooks" "$total" '^test .*rev-parse HEAD.*" = ')
  if [ -z "$eq_ln" ]; then
    bad "$label hook assertion 3/3: no HEAD equality test"
  else
    assert_present "$label hook assertion 3/3: HEAD == origin/<base>, both halves" \
      "$file" $((eq_ln + 1)) $((eq_ln + 1)) 'rev-parse origin/<baseRefName>'
  fi
}

echo
echo "== post-merge hooks run after cleanup =="
if [ -n "$TICKET_CLEAN_END" ]; then check_hooks "ticket.md" "$TICKET" "$TICKET_CLEAN_END"; fi
if [ -n "$FINALIZE_CLEAN_END" ]; then check_hooks "finalize.md" "$FINALIZE" "$FINALIZE_CLEAN_END"; fi

# ----------------------------------------------------- 5. no --delete-branch

echo
echo "== gh pr merge --delete-branch is not used =="
# Two assertions, because the invariant is two things and the original check was
# neither of them precisely. It filtered out any line containing `never`, which
# let `Never omit --delete-branch` — an instruction to REINSTATE the flag — pass
# as though it were a ban. Tightening that filter then flagged SKILL.md:905,
# which legitimately *refers* to the flag ("`--delete-branch` got this right by
# resolving the head repository") and was only passing before because the same
# sentence happens to say "never from `origin`".
#
# So: a mention is not the thing to police. A USE is.
if grep -rqn --include='*.md' --include='*.json' --exclude-dir=.git -E \
     'gh pr merge[^`]*--delete-branch' .; then
  bad "--delete-branch is passed to gh pr merge:"
  grep -rn --include='*.md' --include='*.json' --exclude-dir=.git -E \
    'gh pr merge[^`]*--delete-branch' . | sed 's/^/          /'
else
  ok "no gh pr merge command passes --delete-branch"
fi

# And the ban must stay written down in every copy that documents the merge, so
# deleting the paragraph is caught too. The verb list is closed on purpose: a new
# phrasing fails loudly and gets read by a person, which is the right outcome for
# a rule this load-bearing.
for f in "${MERGE_DOCS[@]}"; do
  if [ ! -f "$f" ]; then bad "$f (missing)"; continue; fi
  assert_present "$f: states the --delete-branch prohibition" \
    "$f" 1 "$(total_lines "$f")" '[Nn]ever( pass| use| add)? .?--delete-branch'
done

# ------------------------------- 6. MERGED gate sits between merge and delete

# Position alone is not the invariant: the order check proves a state lookup sits
# between the merge and the deletion, not which state permits it. MERGED is the
# API's own value, so requiring it pins mechanism rather than comment wording.
#
# It must be bound to THAT line rather than searched for across the file. Each
# references/github-api.md carries a second standalone `--json state` example
# further down — the non-zero-exit recovery path — which also says MERGED, so a
# whole-file search stays green while the real gate is reworded to OPEN.
check_merged_gate() {
  local f=$1 total=$2
  local merge_ln del_ln gate_ln
  # Each bail-out below is a case assert_order has already failed on and
  # explained; re-reporting it here would double-count one regression.
  merge_ln=$(find_line "$f" 1 "$total" '^gh pr merge <pr> --')
  [ -n "$merge_ln" ] || return 0
  del_ln=$(find_line "$f" "$merge_ln" "$total" '^(git push origin --delete|gh api --method DELETE)')
  [ -n "$del_ln" ] || return 0
  gate_ln=$(find_line "$f" "$merge_ln" "$del_ln" '^gh pr view <pr> --json state')
  [ -n "$gate_ln" ] || return 0
  assert_present "$f: the gate line itself requires MERGED" \
    "$f" "$gate_ln" "$gate_ln" 'MERGED'
}

echo
echo "== merge -> MERGED gate -> branch deletion =="
for f in "${MERGE_DOCS[@]}"; do
  if [ ! -f "$f" ]; then bad "$f (missing)"; continue; fi
  assert_order "$f: merge, then MERGED, then delete" \
    "$f" 1 "$(total_lines "$f")" \
    "gh pr merge"                  '^gh pr merge <pr> --' \
    "gh pr view --json state"      '^gh pr view <pr> --json state' \
    "remote branch deletion"       '^(git push origin --delete|gh api --method DELETE)'
  check_merged_gate "$f" "$(total_lines "$f")"
done

# --------------------- 7. quick-dev deletes from the head repo, ref encoded

echo
echo "== head-repository resolution and ref encoding (quick-dev) =="
for f in "${HEADREPO_DOCS[@]}"; do
  if [ ! -f "$f" ]; then bad "$f (missing)"; continue; fi
  total=$(total_lines "$f")
  # The resolution must sit between the MERGED gate and the deletion: a DELETE
  # that runs before the head repo is known is the fork bug #23 fixed.
  assert_order "$f: resolve head repo before deleting" \
    "$f" 1 "$total" \
    "gh pr view --json state"          '^gh pr view <pr> --json state' \
    "head repo + repo + ref fields"    '^gh pr view <pr> --json headRepositoryOwner,headRepository,headRefName' \
    "DELETE targets the encoded ref"   '^gh api --method DELETE "repos/<headOwner>/<headRepo>/git/refs/heads/<head-branch-encoded>"'
  # Two separate things, and the DELETE anchor above is the load-bearing one.
  # Matching %23 anywhere in the file only proves the encoding is *explained*:
  # the command could regress from <head-branch-encoded> to <head-branch> with
  # the paragraph left intact, which is why the anchor pins the placeholder the
  # command actually substitutes. These checks keep the rule documented.
  assert_present "$f: documents the %23 encoding" "$f" 1 "$total" '%23'
  # BOTH characters, and the order between them. `%` is the escape character, so
  # encoding it second mangles the escapes just written — dropping that half left
  # %23 present and the harness green. The bracket class matches the literal `%`;
  # `[*]*` absorbs the bold markers one copy uses and the other does not.
  assert_present "$f: encodes % before #" "$f" 1 "$total" 'Encode .%. [*]*first'
done

# The mapping itself, wherever it is stated. Ordering alone is not enough: with
# every %25 rewritten to %24 the harness stayed green, and a branch containing a
# literal `%` would then encode to a ref that does not exist.
for f in "${PCT25_DOCS[@]}"; do
  if [ ! -f "$f" ]; then bad "$f (missing)"; continue; fi
  assert_present "$f: the % row maps to %25" "$f" 1 "$(total_lines "$f")" '^%.*%25'
done

echo
if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
  echo
  echo "This harness pins the post-merge cleanup contract from PRs #20 and #23."
  echo "If a failure above is a deliberate change to that contract, change the"
  echo "assertion with it — in the same commit, with the reasoning. If it is not,"
  echo "the ordering has regressed; see:"
  echo "  $TICKET (Phase 9)"
  echo "  $FINALIZE (Phase 4)"
  echo "  $DEVELOP (Phase 5)"
fi
exit $(( fails > 0 ? 1 : 0 ))
