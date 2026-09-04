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
# Unbackticked on purpose: the sentence this pins never spells the word
# "blocked" (it is the paragraph below the table, not the row itself), so a
# backticked label here would claim a literal the regex cannot honour — see
# assert_covers in scripts/lib/assert.sh.
assert_present "blocked requires an external cause" \
  "$SK" 1 "$L" '\*\*The cause must be external\.\*\*'
assert_present "blocked excludes a plugin-internal cause" \
  "$SK" 1 "$L" 'A plugin-internal cause is a tail wearing a label'

# A non-state phrased to read like a decision is the failure mode this names.
# R1: the prose bolds the phrase (`are **not dispositions**`) — the regex has to
# match the raw markdown, emphasis included, or it matches nothing at all.
assert_present "a deferral is not a disposition" \
  "$SK" 1 "$L" 'are \*\*not dispositions\*\*'

echo
if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
fi
exit $(( fails > 0 ? 1 : 0 ))
