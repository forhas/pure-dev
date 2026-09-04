#!/usr/bin/env bash
# Standing invariant: an item that cannot be done from anywhere, for a named
# EXTERNAL cause, has its own disposition — `blocked` — and never becomes a
# ticket, a `Deferred:` trailer, or anything else a later run is expected to
# pick up.
#
# Why this is an invariant and not a change-scoped check: before `blocked`
# existed, the triage axis was `absorb` / `file` / `drop`, and an externally
# impossible item had no honest home. `drop` asserts it is not worth doing;
# `absorb` asserts it can be done here. Both are false, so the item acquired a
# stretched blast-radius criterion and turned into permanent backlog. Measured
# on notion-dev 0.20.2: BTC-Gateway STO-77 filed three follow-up tickets and two
# were this — one citing "a design decision" for a deployment history the run
# could not read, one citing "a new interface" for a metric electrs does not
# emit. Neither ticket can ever be worked as written.
#
# Every check below pins a MECHANISM, not wording: the disposition's presence in
# an enum, the externality bound, the never-filed rule at each call site, and
# the counts that keep BLOCKED separate from FILED.
set -uo pipefail
cd "$(dirname "$0")/.."

ND=plugins/notion-dev
QD=plugins/quick-dev
fails=0

ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

. ./scripts/lib/assert.sh

echo "== the disposition itself =="
for RM in $ND/skills/review-and-merge/SKILL.md $QD/skills/review-and-merge/SKILL.md; do
  n=${RM#plugins/}
  assert_has "$n carries blocked in the ledger disposition enum" "$RM" '`file` / `drop` / `blocked` |'
  assert_has "$n records a blocked_cause field"                  "$RM" '| `blocked_cause` |'
  assert_has "$n requires the cause to be external"              "$RM" '**The cause must be external'
  # The externality bound is the whole load-bearing part: without it every item
  # a run finds inconvenient becomes `blocked`. Name the internal causes that
  # are explicitly NOT this state, so the exclusion cannot quietly lapse.
  assert_has "$n excludes the round cap as an internal cause"    "$RM" 'the round cap" are internal causes'
  assert_has "$n never files a blocked item as a ticket"         "$RM" '**A `blocked` item is never filed as a ticket**'
done

echo "== the two meanings of the word =="
for RM in $ND/skills/review-and-merge/SKILL.md $QD/skills/review-and-merge/SKILL.md; do
  n=${RM#plugins/}
  # `COMPLETENESS: blocked` is a GATE STATUS; a TRIAGE `blocked` is a
  # DISPOSITION. The same token on two keys in one block is a live conflation
  # hazard, and the disambiguation is what stops a reader collapsing them.
  assert_has "$n disambiguates the gate status from the disposition" "$RM" '**`blocked` appears twice in this block and means two different things.**'
  assert_has "$n forbids inferring one from the other"               "$RM" 'Never infer one from the other'
done

echo "== the completeness gate's terminal rule =="
for RM in $ND/skills/review-and-merge/SKILL.md $QD/skills/review-and-merge/SKILL.md; do
  n=${RM#plugins/}
  assert_has "$n offers three terminal dispositions" "$RM" '`file`, `drop`, or `blocked` with a rationale'
  # A free choice among the three is what produced every one of STO-77's
  # tickets. The decision ORDER, and `file` being narrowest rather than the
  # fallback, is the mechanism that bounds it.
  assert_has "$n falls back to \`blocked\`, never to \`file\`" "$RM" '`blocked` — not `file`'
  assert_has "$n makes filing the narrowest option, not the fallback" "$RM" 'narrowest of the three, not the fallback'
  assert_has "$n keeps the blast-radius citation required at pass 2" "$RM" 'That requirement does not
      relax because the passes are spent'
  assert_has "$n denies that blocked is a scope reduction" "$RM" '**`blocked` is not a scope reduction**'
done

echo "== the PR body must match the gate's final counts =="
for RM in $ND/skills/review-and-merge/SKILL.md $QD/skills/review-and-merge/SKILL.md; do
  n=${RM#plugins/}
  # Charge 2 audits the body BEFORE pass 2 can change a verdict, so nothing
  # re-reads it afterwards. PR #83 merged claiming "4/4 met" against a recorded
  # 3 met / 1 unverified.
  assert_has "$n reconciles the body before merging" "$RM" '**Reconcile the pull request body against the gate'"'"'s final counts before merging.**'
  assert_has "$n treats a contradicting count as an unsupported claim" "$RM" 'unsupported claim by charge 2'
done

echo "== the sweep does not collect blocked =="
for RM in $ND/skills/review-and-merge/SKILL.md $QD/skills/review-and-merge/SKILL.md; do
  n=${RM#plugins/}
  assert_has "$n keeps blocked out of the final sweep" "$RM" '**A `blocked` item is not swept either'
done

echo "== reporting keeps BLOCKED separate from FILED =="
for RM in $ND/skills/review-and-merge/SKILL.md $QD/skills/review-and-merge/SKILL.md; do
  n=${RM#plugins/}
  assert_has "$n names BLOCKED in the CONVERGENCE block" "$RM" 'DROPPED: <n>  BLOCKED: <n>'
  assert_has "$n counts five exhaustive dispositions"    "$RM" 'The five disposition counts are exhaustive'
  assert_has "$n keeps BLOCKED a bucket, not a slice of FILED" "$RM" '**`BLOCKED` is a fifth bucket, not a slice of `FILED`**'
  assert_has "$n emits BLOCKED as a named report list"   "$RM" '- `BLOCKED` — items nobody can do until'
  assert_has "$n forbids callers filing BLOCKED"         "$RM" '**`BLOCKED` in particular must never be filed.**'
done

echo "== notion-dev call sites =="
for CMD in $ND/commands/ticket.md $ND/commands/finalize.md; do
  n=${CMD#plugins/}
  assert_has "$n never passes BLOCKED to epic-update"  "$CMD" '`BLOCKED` items'
  assert_has "$n reports each as a blocked: line"      "$CMD" 'blocked: <item> — <external cause>; unblocked by <what>'
  assert_has "$n records triage_blocked in the ledger" "$CMD" '"triage_blocked":N'
  # Both artifact writes are best-effort, so a skipped one and a completed one
  # are indistinguishable afterwards unless the caller checks. STO-77 filed
  # three tickets, wrote zero packets and no persisted report, and said nothing.
  assert_has "$n asserts the review report persisted"  "$CMD" '`unexpected:review-report-not-persisted`'
  assert_has "$n asserts packets written vs filed"     "$CMD" '`unexpected:followup-packet-missing`'
done
assert_has "notion-dev/skills/issue-log registers review-report-not-persisted" \
  "$ND/skills/issue-log/references/signatures.md" '| `unexpected:review-report-not-persisted` |'
assert_has "notion-dev/skills/issue-log registers followup-packet-missing" \
  "$ND/skills/issue-log/references/signatures.md" '| `unexpected:followup-packet-missing` |'
assert_has "notion-dev/skills/flow-triage ledger carries triage_blocked" \
  "$ND/skills/flow-triage/references/ledger.md" '"triage_blocked":0'

echo "== quick-dev call sites =="
assert_has "quick-dev/skills/develop gives a BLOCKED item no trailer" \
  "$QD/skills/develop/SKILL.md" '**A `BLOCKED` item never takes a trailer of either kind.**'
assert_has "quick-dev/skills/develop records triage_blocked in the ledger" \
  "$QD/skills/develop/SKILL.md" '"triage_blocked":<n>'
assert_has "quick-dev/skills/flow-triage ledger carries triage_blocked" \
  "$QD/skills/flow-triage/references/ledger.md" '"triage_blocked":0'

echo "== session-closeout does not demand a URL for a blocked item =="
for SC in $ND/skills/session-closeout/SKILL.md $QD/skills/session-closeout/SKILL.md; do
  n=${SC#plugins/}
  assert_has "$n excludes the BLOCKED list from the filed-issues source" "$SC" 'A review report'"'"'s `BLOCKED` list is not part of this source.'
  assert_has "$n scopes the tracked: requirement to FILED items"         "$SC" 'Each `FILED` item needs `tracked:` with its URL'
  # `blocked` already means the same thing in this skill's own three states.
  # Keeping one word across triage and closeout is what stops the relabelling
  # that loses the external cause on the way through.
  assert_has "$n keeps blocked for external causes only" "$SC" '**`blocked` is for external causes only**'
done

echo
if [ "$fails" -eq 0 ]; then
  echo "All checks passed."
else
  echo "$fails CHECK(S) FAILED"
fi
exit $((fails > 0))
