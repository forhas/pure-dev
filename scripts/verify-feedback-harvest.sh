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

# The label claimed "untracked" but the regex only ever checked the path
# token, which A2 cannot catch on its own — "untracked" is a plain word, not a
# backtick/ALLCAPS/flag/placeholder/Capitalized literal (Minor 6). Pin both on
# the same line instead of dropping the claim.
assert_present "the client list is an untracked local file" \
  "$SK" 1 "$L" 'untracked `\.claude/notion-dev/clients\.txt`'
assert_present "an unreadable client is reported, never silently skipped" \
  "$SK" 1 "$L" 'reported and skipped.*never silently dropped'

# Phase 1 is what makes `decline` durable rather than a per-run coin flip. Drop
# it and every rejection is re-argued from scratch on the next harvest, with the
# reasoning written last time never read.
assert_present "prior harvests are read before any client log" \
  "$SK" 1 "$L" 'Read every `docs/feedback/\*\.md` archive \*\*before\*\* reading any client log'
assert_present "a reappearing signature is re-evaluated, not re-declined by rote" \
  "$SK" 1 "$L" 're-evaluated against the \*\*new\*\* evidence'
# `docs/feedback/` does not exist on the first harvest, and an empty glob is not
# an error to stall on — Minor 4 from the final review. Round 3: the old regex
# stopped short of the label's own "not an error" half, so inverting the
# instruction to "stop and report it" stayed green — extend the regex to cover
# what the label actually claims, the same defect class as Minor 6.
assert_present "an empty archive glob means the first harvest, not an error" \
  "$SK" 1 "$L" 'first harvest, not an error to stop on'
# `blocked` sections are removed from the client log at Phase 8 same as every
# other disposition, so the archive is their only durable record. Without this,
# an item whose external cause clears is never revisited — Minor 5.
assert_present "still-open blocked items from prior archives are re-enumerated" \
  "$SK" 1 "$L" 'enumerate every still-open `blocked` item from those archives'

# issue-log dedups per repo, so one signature in two logs may be two conditions.
assert_present "cross-client grouping is a candidate, confirmed by reading both entries" \
  "$SK" 1 "$L" 'then \*\*confirm or split\*\* by reading both `Observed` fields'

# Finding 3937770051: a free-form recurrence or correction can be appended
# without changing `Occurrences` or `Last seen`, so a guard keyed on those two
# fields alone reports a false match and Phase 8 deletes untriaged text. Phase
# 2 has to record enough of the section to catch that.
assert_present "phase 2 records a digest of each section's complete text for phase 8 to compare" \
  "$SK" 1 "$L" '\*\*Also record a digest of the section'\''s complete text\*\*'

# ---------------------------------------------------------------------------
# Not an automatic fixer
# ---------------------------------------------------------------------------
echo "== triage is not an automatic fixer =="

# The spec's "Not an automatic fixer" non-goal. Delete this paragraph and the
# suite stays green while the skill becomes an auto-applier — this is the
# highest-value assertion in this wave (final review, Minor 8.1).
assert_present "an entry is a suggestion to evaluate, never an instruction to follow" \
  "$SK" 1 "$L" 'suggestion to evaluate, not an instruction to follow'
assert_present "a change is applied only when statable in one sentence why it helps" \
  "$SK" 1 "$L" 'Apply a change only when you can state, in one sentence, why it improves the plugin'

# `track`'s Requires cell is otherwise proven present but not proven to say
# anything: the five-row loop above only checks `^\| \`track\` \|`, which a
# weakened Requires column would still satisfy (final review, Minor 8.5).
assert_present "\`track\` requires a ticket that exists right now, with its url" \
  "$SK" 1 "$L" '^\| `track` \|.*A ticket that exists right now, with its URL \|'

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

# Finding 3937770045: a Phase 4 commit whose diff or message carries a
# client-derived identifier is already in branch history by the time Phase
# 5's gate runs — redacting the working tree afterward cannot reach back into
# an earlier commit. The obligation has to bind at the moment of writing.
assert_present "plugin edits and commit messages are redacted before the commit, not at phase 5" \
  "$SK" 1 "$L" '\*\*Redact before you commit, not at Phase 5\.\*\*'
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
# The widening rule above was already pinned; its sibling ("don't file what
# you're about to fix") was not — half the pair was unguarded (Minor 8.2).
assert_present "the harvest never files what it is about to fix" \
  "$SK" 1 "$L" '\*\*Do not file what you are about to fix\.\*\*'
assert_present "each touched plugin's manifest version is bumped exactly once" \
  "$SK" 1 "$L" 'Bump each touched plugin'\''s manifest version exactly once'
assert_present "a harvest touching no plugin file bumps no version" \
  "$SK" 1 "$L" 'A harvest that changes no plugin file bumps nothing'

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
# Only the per-category table's headline was pinned; every row beneath — the
# keep list and the rows themselves, the db=…a41f9c truncation exception most
# of all — could be deleted with the suite green (Minor 8.4).
assert_present "the forbidden list is the gate, never a per-field whitelist" \
  "$SK" 1 "$L" 'The forbidden list is the gate, not the per-field whitelist'
# Re-review, Minor 8(d) round 2: the old assertion pinned only the keep-list's
# sentence OPENER ("So these are kept: the"), so truncating the list itself —
# dropping `Kind`, occurrence counts, timestamps, versions, ticket keys, the
# truncated-id form, repo names, PR numbers, commit shas — changed no
# assertion. Pin the content, not the opener.
assert_present "the keep list names what redaction leaves untouched" \
  "$SK" 1 "$L" 'Kept: the signature, `Kind`, occurrence counts, timestamps, plugin versions, and ticket keys'
assert_present "the keep list also covers truncated ids, repo names, pr numbers, and shas" \
  "$SK" 1 "$L" 'Also kept: the `db=…a41f9c` truncated form, client repo names, PR numbers, and commit shas'
assert_present "a database or page id keeps six characters as the one exception" \
  "$SK" 1 "$L" 'Truncate to its last six characters, `db=…a41f9c` form — the one exception'
# Same round 2 gap for the other four rows: only the table headline and the
# "Generalize to the kind is the default" summary were pinned, so all four
# remaining rows — the ones that actually tell an executing agent what to
# write instead — could be deleted in one edit with the suite green.
assert_present "an email address is generalized to the kind, never reproduced" \
  "$SK" 1 "$L" '\| Email address \| Generalize to the kind: "an email address," never the address \|'
assert_present "a personal name is generalized to the kind, never reproduced" \
  "$SK" 1 "$L" '\| Personal name \| Generalize to the kind: "a personal name," never the name \|'
assert_present "an absolute path is generalized to the kind, never reproduced" \
  "$SK" 1 "$L" '\| Absolute filesystem path \| Generalize to the kind: "an absolute path," never the path \|'
assert_present "a url is generalized to the kind, never reproduced" \
  "$SK" 1 "$L" '\| URL of any kind \| Generalize to the kind: "a URL," never the URL \|'
# Belt and suspenders: "Generalize to the kind:" is a mechanism deliberately
# cited once per generalized category (email, name, path, URL) — declaring the
# count means collapsing or duplicating a row goes red in both directions,
# not just when a row vanishes outright.
assert_count "generalize-to-the-kind is cited exactly once per generalized category" \
  "$SK" 1 "$L" 'Generalize to the kind:' 4
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
# Finding 3937770059: `track` requires a ticket that exists right now, with its
# URL (Phase 3), and Phase 6 archives that URL — but the forbidden list bans
# "URLs of any kind" outright. A tracker URL this run creates in this public
# repo is not client data, so it needs its own narrow exemption, distinct from
# a client-derived URL found in the evidence.
assert_present "a \`track\` item's ticket url is not client data" \
  "$SK" 1 "$L" '\*\*A `track` item'\''s ticket URL is not client data\.\*\*'
assert_present "the track url exemption is narrow: this run's own url, never a client-derived one" \
  "$SK" 1 "$L" 'The exemption is narrow'
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
# Mandating the flag without the text just moves the reinvention to the call
# site — copy develop's own --pre-merge-check wording instead (final review,
# item 3 of the addendum).
assert_present "the pre-merge-check text is copied from develop's own call, not reinvented" \
  "$SK" 1 "$L" 'Copy the form `plugins/quick-dev/skills/develop/SKILL.md`'\''s own `--pre-merge-check` call'
assert_present "the body names every disposition, including the ones with no diff" \
  "$SK" 1 "$L" 'invisible in a diff-shaped review'

# Finding 3937770056: a harvest bumps plugin versions in Phase 4 by definition,
# so the same stale-bump race develop.md guards against — git merges identical
# version-line bumps without conflict — can land a harvest whose version equals
# the base's. The guard has to be folded into this skill's own --pre-merge-check,
# not left implicit in a sibling skill's doc.
assert_present "the pre-merge-check folds in a clause per plugin manifest phase 4 bumped" \
  "$SK" 1 "$L" 'every plugin manifest bumped in Phase 4'
assert_present "the stale-bump clause requires the branch's version strictly greater than the base's, as semver" \
  "$SK" 1 "$L" 'branch must be strictly greater, as semver, than in'
assert_present "an equal-or-lower version means the base moved: update from it, then recompute the bump" \
  "$SK" 1 "$L" '\(if equal or lower, the base moved: first update the branch with the current base'

# The reset destroys the client's only copy. Doing it before the merge loses the
# feedback for a pull request that then does not land.
assert_present "the reset runs only after the merge has landed" \
  "$SK" 1 "$L" '\*\*only after the merge has landed\*\*'
assert_present "removal matches on the section's complete text, not just two fields" \
  "$SK" 1 "$L" 'matched on the section'\''s \*\*complete text\*\* as harvested'
# Occurrences and Last seen can both stay put while a correction subsection is
# appended below them — this is the specific claim the digest guard rests on.
assert_present "occurrences and last seen alone cannot prove a section is unchanged" \
  "$SK" 1 "$L" '`Occurrences` and `Last seen` alone are not enough'
# A `^##` prefix match stops at the first `###` recurrence subsection and
# leaves it orphaned — recurrences live at depth three or deeper, undocumented
# by `issue-log` at any fixed depth (final review, Important 3).
assert_present "the delete boundary is the next depth-two heading, not any subheading" \
  "$SK" 1 "$L" 'exactly depth two \(`## `\), or end of file'
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
