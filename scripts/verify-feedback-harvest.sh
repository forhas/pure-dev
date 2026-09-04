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

echo
if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
fi
exit $(( fails > 0 ? 1 : 0 ))
