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
  # The disposition is unreachable unless the loops that actually triage findings
  # offer it. Both operational enumerations — the reviewer round and the local
  # fallback — and the local loop's own termination clause listed only
  # absorb/file/drop, so an externally impossible REVIEW finding could never
  # reach the BLOCKED list from either loop.
  assert_has_n "$n offers blocked in both operational triage enumerations" "$RM" 'every agreed-but-unfixed finding gets `absorb`, `file`, `drop`, or `blocked`' 2
  assert_has "$n lets the local loop terminate on a blocked routing" "$RM" 'routed every one of them to `file`, `drop`, or `blocked`'
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
  # A free choice among the three is what produced every one of STO-77's tickets.
  # The decision ORDER bounds it — but the RESIDUAL is what decides which way the
  # ordering leaks. An earlier revision of this PR defaulted the residual to
  # `blocked`, which laundered internally-actionable unfinished work into a state
  # that yields no ticket and no owner: the same failure running backwards, and
  # worse, since a wrongly-filed item is at least visible. Pin both halves.
  assert_has "$n makes the residual filing, never blocking" "$RM" '**The residual is `file`, and it must never be `blocked`.**'
  assert_has "$n reaches the blocked state only through test 1" "$RM" 'reachable only through test 1, and only on a named external cause'
  # An acceptance criterion is work the ticket already promised; the blast-radius
  # criteria size a review FINDING. Requiring one for a criterion strands the
  # common case with no true test at all — so the two populations cite different
  # grounds, and both halves of that split need pinning.
  assert_has "$n files an unmet criterion on its own ground" "$RM" '**An unmet acceptance criterion is filed on its own ground — that the criterion'
  # Single-line fragment on purpose: these files are hard-wrapped and a literal
  # lifted across a wrap degrades to alternation (see assert.sh's third trap).
  assert_has "$n still cites blast radius for a claim or caveat item" "$RM" 'and 3 *is* review-finding-shaped, and it does cite its blast-radius criterion number'
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
  # `BLOCKED` items appears twice in ticket.md, so it is vocabulary, not a place —
  # mutating one occurrence left the other and the check stayed green. Pin the
  # never-file rule itself, which each command states exactly once.
  assert_has_n "$n never files a BLOCKED item" "$CMD" 'A `BLOCKED` item filed as a ticket is strictly worse than a forgotten one' 1
  assert_has "$n reports each as a blocked: line"      "$CMD" 'blocked: <item> — <external cause>; unblocked by <what>'
  assert_has "$n records triage_blocked in the ledger" "$CMD" '"triage_blocked":N'
  # Both artifact writes are best-effort, so a skipped one and a completed one
  # are indistinguishable afterwards unless the caller checks. STO-77 filed
  # three tickets, wrote zero packets and no persisted report, and said nothing.
  assert_has "$n asserts the review report persisted"  "$CMD" '`unexpected:review-report-not-persisted`'
  # Existence alone is not evidence: the path is deterministic per ticket and
  # both entry points are re-runnable, so a stale report from an earlier run of
  # the SAME ticket satisfies it while this run's write failed.
  assert_has "$n checks this run's write, not mere presence" "$CMD" "confirm **this run's** write landed"
  assert_has "$n asserts packets written vs filed"     "$CMD" '`unexpected:followup-packet-missing`'
  # `<KEY>` is the PROJECT key, shared by every ticket in the repo, so a
  # `followup-<KEY>-*.md` glob counts the whole project's packets and fires a
  # false mismatch on nearly every run. The producer's path carries `<id>`.
  assert_has "$n scopes the packet glob to this ticket's id" "$CMD" 'Scope it to `followup-<KEY>-<id>-*.md`'
  assert_has "$n states the producer's real packet path" "$CMD" 'writes one `followup-<KEY>-<id>-<n>.md` context packet'
  # epic-update step 1a retries a historical FAILED item by REUSING the packet the
  # original attempt wrote, and reports it in this invocation's FILED. Asserting
  # the packet was created by this run would flag that successful retry as a
  # missing packet. Assert existence at the recorded identity, not authorship.
  assert_has "$n accepts a packet reused by a successful retry" "$CMD" 'that is the producer'"'"'s contract working, not a missing packet'
done
assert_has "notion-dev/skills/issue-log registers review-report-not-persisted" \
  "$ND/skills/issue-log/references/signatures.md" '| `unexpected:review-report-not-persisted` |'
assert_has "notion-dev/skills/issue-log registers followup-packet-missing" \
  "$ND/skills/issue-log/references/signatures.md" '| `unexpected:followup-packet-missing` |'
# signatures.md is the MANDATORY authority for each logging site, so a row that
# still describes the superseded trigger lets an agent follow the registry and
# suppress (or falsely emit) the entry regardless of the corrected caller text.
# Both rows must carry the same trigger the callers now state.
assert_has "the registry judges the report write, not mere existence" \
  "$ND/skills/issue-log/references/signatures.md" '**Never by the file merely existing**'
assert_has "the registry names the id-scoped report path" \
  "$ND/skills/issue-log/references/signatures.md" "**this invocation's** \`review-report-<KEY>-<id>.md\` write did not land"
assert_has "the registry forbids the project-wide packet glob" \
  "$ND/skills/issue-log/references/signatures.md" '**Never glob `followup-<KEY>-*.md`**'
assert_has "notion-dev/skills/flow-triage ledger carries triage_blocked" \
  "$ND/skills/flow-triage/references/ledger.md" '"triage_blocked":0'

echo "== quick-dev call sites =="
assert_has "quick-dev/skills/develop gives a BLOCKED item no trailer" \
  "$QD/skills/develop/SKILL.md" '**A `BLOCKED` item never takes a trailer of either kind.**'
# Local mode never enters review-and-merge, so develop's OWN completeness gate is
# the sole producer of a blocked outcome there. Fixing only the trailer and
# reporting consumers left the producer enumerating absorb/file/drop, so an
# externally impossible local-mode item still had no route but the backlog.
assert_has "quick-dev/skills/develop produces a blocked outcome in local mode" \
  "$QD/skills/develop/SKILL.md" 'this enumeration is the sole producer of a `blocked` outcome here'
assert_has "quick-dev/skills/develop offers all three at its terminal rule" \
  "$QD/skills/develop/SKILL.md" '**must be reclassified to `file`, `drop`, or `blocked` with a rationale**'
assert_has "quick-dev/skills/develop keeps filing as the residual" \
  "$QD/skills/develop/SKILL.md" 'so it must never fall through to `blocked`'
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
