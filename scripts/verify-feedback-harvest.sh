#!/usr/bin/env bash
# Standing invariant: the harvest reaches a decision about every signature it
# reads, redacts before anything leaves the client repo, and resets a client log
# only after the fixes have merged.
#
# Why an invariant and not a change-scoped check: the failure this skill exists
# to remove is a harvest that reads selectively and records nothing about what it
# skipped. That failure is silent — a well-reasoned rejection and an unread entry
# look identical afterwards — so the only defence is that the disposition set is
# closed and the orderings are pinned. Neither has a baseline to go stale
# against.
#
# Every check pins a MECHANISM: the presence of each disposition in the table,
# the externality bound on `blocked`, the relative order of the phases whose
# order is load-bearing, and the matching rule the reset uses.
#
# Run from anywhere: ./scripts/verify-feedback-harvest.sh
set -uo pipefail
cd "$(dirname "$0")/.."

SK=.claude/skills/feedback-harvest/SKILL.md
fails=0

ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

. ./scripts/lib/assert.sh

if [ ! -f "$SK" ]; then
  bad "$SK is missing — nothing below can mean anything"
  echo "1 CHECK(S) FAILED"
  exit 1
fi
L=$(total_lines "$SK")

# ---------------------------------------------------------------------------
# The disposition set is closed
# ---------------------------------------------------------------------------
echo "== the five dispositions =="

assert_present "the set is closed at five and admits no sixth" \
  "$SK" 1 "$L" 'exactly \*\*one\*\* of five dispositions.*There is no sixth'

for d in apply stale decline track blocked; do
  assert_present "the disposition table carries \`$d\`" \
    "$SK" 1 "$L" "^\\| \`$d\` \\|"
done

# The externality bound is the whole load-bearing part of `blocked`. Without it,
# every item a harvest finds inconvenient becomes blocked, which is how the
# three-state rule is defeated everywhere else in this repo.
#
# The disposition name is bound into both sentences (not just the table row),
# so a future rename of `blocked` to anything else fails these two, not just
# the table check — un-backticking the labels instead would have satisfied
# assert_covers without requiring the regex to be about `blocked` at all.
assert_present "\`blocked\` requires an external cause" \
  "$SK" 1 "$L" '\*\*A `blocked` disposition requires an external cause\.\*\*'
assert_present "\`blocked\` excludes a plugin-internal cause" \
  "$SK" 1 "$L" 'A plugin-internal cause on a `blocked` item is a tail wearing a label'

# A non-state phrased to read like a decision is the failure mode this names.
# R1: the prose bolds the phrase (`are **not dispositions**`) — the regex has to
# match the raw markdown, emphasis included, or it matches nothing at all.
assert_present "a deferral is not a disposition" \
  "$SK" 1 "$L" 'are \*\*not dispositions\*\*'

# ---------------------------------------------------------------------------
# Sources and collection
# ---------------------------------------------------------------------------
echo "== sources and collection =="

assert_present "the client list is an untracked local file" \
  "$SK" 1 "$L" '`\.claude/notion-dev/clients\.txt`'
assert_present "an unreadable client is reported, never silently skipped" \
  "$SK" 1 "$L" 'reported and skipped.*never silently dropped'

# Phase 1 is what makes `decline` durable rather than a per-run coin flip. Drop
# it and every rejection is re-argued from scratch on the next harvest, with the
# reasoning written last time never read.
assert_present "prior harvests are read before any client log" \
  "$SK" 1 "$L" 'Read every `docs/feedback/\*\.md` archive \*\*before\*\* reading any client log'
assert_present "a reappearing signature is re-evaluated, not re-declined by rote" \
  "$SK" 1 "$L" 're-evaluated against the \*\*new\*\* evidence'

# issue-log dedups per repo, so one signature in two logs may be two conditions.
assert_present "cross-client grouping is a candidate, confirmed by reading both entries" \
  "$SK" 1 "$L" 'then \*\*confirm or split\*\* by reading both `Observed` fields'

# ---------------------------------------------------------------------------
# The triage rules
# ---------------------------------------------------------------------------
echo "== the triage rules =="

# Each rule exists because a specific live entry defeats the obvious reading.
assert_present "a host-caused entry is still evaluated for a documentation fix" \
  "$SK" 1 "$L" 'is not the same as \*\*no plugin change\*\*'
assert_present "an entry-s stated cause is evidence, never an inherited finding" \
  "$SK" 1 "$L" 'Triage re-derives the cause; it never inherits'
assert_present "an old first-seen version is a candidate, not a verdict" \
  "$SK" 1 "$L" 'is a `stale` \*\*candidate\*\*, never a `stale` verdict'
assert_present "a recurrence outranks the original entry" \
  "$SK" 1 "$L" 'A recurrence subsection \*\*outranks\*\* the original'

# Order: the rules qualify the table, so they must follow it. A rule hoisted
# above the disposition set reads as the primary instruction, which inverts it.
assert_order "triage: the closed set precedes the table precedes the rules that qualify it" \
  "$SK" 1 "$L" \
  "closed set"  'There is no sixth' \
  "table row"   '^\| `blocked` \|' \
  "first rule"  'is not the same as \*\*no plugin change\*\*'

# ---------------------------------------------------------------------------
# Phase 4 — Apply
# ---------------------------------------------------------------------------
echo "== applying the fixes =="

assert_present "every applied fix is covered by an assertion in a verify harness" \
  "$SK" 1 "$L" 'covered by an assertion in some `scripts/verify-\*\.sh`'
assert_present "a standing invariant is preferred over a change-scoped harness" \
  "$SK" 1 "$L" 'rather than minting a change-scoped one with a version floor'
assert_present "each new assertion is mutation-tested against the file it guards" \
  "$SK" 1 "$L" 'break the file it guards, confirm `FAIL`, restore'
assert_present "the work is committed before any mutation" \
  "$SK" 1 "$L" 'Commit \*\*first\*\*'
# notion-dev vendors adapted forks of several quick-dev skills; a fix to shared
# behaviour that lands in one copy silently diverges the other.
assert_present "a shared-behaviour fix lands in both plugins" \
  "$SK" 1 "$L" 'change both copies and check the wording that differs'
assert_present "a fix is widened into this pull request rather than deferred" \
  "$SK" 1 "$L" 'is explicitly \*not\* a reason to defer'

# ---------------------------------------------------------------------------
# Phase 5 and 6 — redact, then archive
# ---------------------------------------------------------------------------
echo "== redaction gate, then archive =="

assert_present "redaction is a gate before publication, not a cleanup after it" \
  "$SK" 1 "$L" 'Nothing is written to `docs/feedback/` until this gate has passed'
# The gate bound only the archive file; Phase 4's plugin edits, their commit
# messages, and Phase 7's PR body land in the same public repo and were
# unbound (final review, Important 2).
assert_present "the gate also binds plugin commits, commit messages, and the pr body" \
  "$SK" 1 "$L" 'Nor committed under `plugins/`, nor placed in a commit message or pull request body'
assert_present "the gate applies the issue-log forbidden list verbatim" \
  "$SK" 1 "$L" 'applies `notion-dev:issue-log`'\''s \*\*Forbidden, without exception\*\* list'
assert_present "the client logs are known to violate that list today" \
  "$SK" 1 "$L" 'This is measured, not hypothetical'
# Without a rule per category, an executing agent has to invent the
# omit/placeholder/generalize convention on the spot for four of the five
# forbidden kinds — this pins that the rule exists and names the default.
assert_present "each forbidden category carries a stated redaction rule" \
  "$SK" 1 "$L" 'A rule per forbidden category — what an executing agent writes in its place'
assert_present "generalize-to-the-kind is stated as the default redaction rule" \
  "$SK" 1 "$L" 'Generalize to the kind is the default'
# The violation table above already writes richer, non-identifying descriptors
# ("a Windows checkout path," "a Notion workspace named after a person") than
# the flat per-category rule allows. Without this line the flat form
# contradicts the richer example the same section sets.
assert_present "the generalization may carry the kind's own non-identifying attribute" \
  "$SK" 1 "$L" 'may\*\* carry the kind'\''s own non-identifying attribute'
assert_present "an unredactable finding is paraphrased, never reproduced" \
  "$SK" 1 "$L" 'paraphrase the finding and do not reproduce the original'
assert_present "the archive is the durable record once a client log is reset" \
  "$SK" 1 "$L" 'the only place the occurrence counts'

# THE ordering this task exists for. A cleanup pass after publication is not a
# gate: the bytes have already been committed to a public repo by then.
assert_order "the redaction gate precedes the archive write" \
  "$SK" 1 "$L" \
  "redact heading"  '^### Phase 5 — Redact' \
  "gate rule"       'Nothing is written to `docs/feedback/` until this gate has passed' \
  "archive heading" '^### Phase 6 — Archive'

# ---------------------------------------------------------------------------
# Phase 7 and 8 — merge, then reset
# ---------------------------------------------------------------------------
echo "== merge, then reset =="

# Nothing upstream of Phase 7 opens the pull request `review-and-merge` needs —
# a bare "hand the branch to review-and-merge" was an artifact that did not
# exist yet (final review, Important 1). These pin the mechanism that creates
# it: `gh pr create` does not take `@-` for `--body`, the body is read back to
# confirm that failure did not recur, and the PR *number* — not the branch —
# is what actually gets handed to the review loop, with the pre-merge-check
# flag supplied explicitly rather than assumed automatic.
assert_present "gh pr create does not support @- for --body" \
  "$SK" 1 "$L" 'does \*\*not\*\* support `@-`'
assert_present "the pull request is created with --body-file, not --body" \
  "$SK" 1 "$L" 'create the pull request with `--body-file`'
assert_present "the pull request body is read back and its length confirmed" \
  "$SK" 1 "$L" 'confirm a realistic length'
assert_present "the pull request number, not a branch, is handed to review-and-merge" \
  "$SK" 1 "$L" 'the resulting \*\*pull request number\*\* — not the branch — to `review-and-merge`'
assert_present "--pre-merge-check is supplied explicitly, not assumed automatic" \
  "$SK" 1 "$L" 'with `--pre-merge-check` supplied explicitly'
assert_present "an unsupplied --pre-merge-check is a hook that never fires" \
  "$SK" 1 "$L" 'not a hook that fires on its own'
assert_present "the body names every disposition, including the ones with no diff" \
  "$SK" 1 "$L" 'invisible in a diff-shaped review'

# The reset destroys the client's only copy. Doing it before the merge loses the
# feedback for a pull request that then does not land.
assert_present "the reset runs only after the merge has landed" \
  "$SK" 1 "$L" '\*\*only after the merge has landed\*\*'
assert_present "removal matches on signature and occurrence count as harvested" \
  "$SK" 1 "$L" 'signature \*\*and\*\* occurrence count as harvested'
assert_present "a mismatched section is left in place and reported" \
  "$SK" 1 "$L" 'leave the section in place and report it'
assert_present "the file is never truncated and never deleted" \
  "$SK" 1 "$L" 'Never truncate the file and never delete it'
assert_present "all five dispositions are removed, not only the applied ones" \
  "$SK" 1 "$L" 'All five dispositions are removed'
assert_present "the reset is an untracked file edit with no commit in the client repo" \
  "$SK" 1 "$L" 'no commit and no push into a client repo'

assert_order "the merge precedes the reset" \
  "$SK" 1 "$L" \
  "merge heading" '^### Phase 7 — Pull request and merge' \
  "reset heading" '^### Phase 8 — Reset' \
  "after rule"    '\*\*only after the merge has landed\*\*'

# ---------------------------------------------------------------------------
# Closeout and honesty about limits
# ---------------------------------------------------------------------------
echo "== closeout and honesty about limits =="

assert_present "closeout confirms the reset ran for every client that was read" \
  "$SK" 1 "$L" 'confirm the reset ran for \*\*every\*\* client this harvest read'
assert_present "a short client log is not evidence of a healthy client" \
  "$SK" 1 "$L" 'A short log is not evidence of a healthy client'
assert_present "a concurrent increment can be lost, and that is accepted" \
  "$SK" 1 "$L" 'diagnostics, not accounting'

echo
if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
fi
exit $(( fails > 0 ? 1 : 0 ))
