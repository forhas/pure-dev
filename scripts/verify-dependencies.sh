#!/usr/bin/env bash
# Standing invariant: a command that needs a build-flow skill probes the HOST for
# it, and never gates on the cached `dependencies.*` booleans in the config.
#
# Why this is an invariant and not a change-scoped check: 0.34.0 removed
# `dependencies` from the config schema's required set and redescribed those
# booleans as setup-time hints that are "not an availability gate". That makes a
# gate on their value wrong in BOTH directions -- a schema-valid config omitting
# the block aborts a build whose skill is live, and a stale cached `true` admits
# one whose skill is gone. The same release wired four commands to the live probe
# and missed the fifth: `new-info --pr` still hard-required
# `dependencies.superpowers == true`, contradicting the release's own acceptance
# criterion that "stale true/false/missing setup hints cannot falsely permit or
# block a build". Nothing caught it, because no harness asserted the wiring.
# That is what this file exists to stop recurring.
#
# Every check pins a MECHANISM -- the probe reference, its mode, the schema's
# required set, the hint-not-gate rule -- never a sentence.
set -uo pipefail
cd "$(dirname "$0")/.."

ND=plugins/notion-dev
fails=0

ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

. ./scripts/lib/assert.sh

echo "== the probe exists and is reachable =="
assert_has "dependencies.md documents the ticket mode"  "$ND/references/dependencies.md" '--mode ticket'
assert_has "dependencies.md names the review mode"      "$ND/references/dependencies.md" 'mode `review`'
assert_has "dependencies.py is invoked through the configured interpreter" \
  "$ND/references/dependencies.md" 'scripts/dependencies.py'

echo "== every command that needs a build-flow skill probes live =="
# The fifth entry is the one 0.34.0 shipped without. It is listed here by name so
# a future command added without the probe is a missing line in this loop, not an
# absence nobody notices.
for C in ticket next-task finalize new-info init; do
  F="$ND/commands/$C.md"
  assert_has "commands/$C.md references references/dependencies.md" "$F" 'references/dependencies.md'
done

echo "== the cached booleans are hints, never gates =="
# Each command that still MENTIONS the flags must say they do not gate. A command
# may legitimately not mention them at all; what it may not do is read one as
# permission.
assert_has "commands/ticket.md calls the flags cached hints only" \
  "$ND/commands/ticket.md" 'cached hints only'
assert_has "commands/finalize.md calls the flags hints only" \
  "$ND/commands/finalize.md" 'Cached config flags are hints only'
assert_has "commands/new-info.md calls dependencies.superpowers a cached hint only" \
  "$ND/commands/new-info.md" '`dependencies.superpowers` is a cached hint only'

# The gate-shaped phrasing the release removed. If any command reintroduces
# "must be `true`" against a dependencies flag, the invariant has lapsed.
for C in ticket next-task finalize new-info; do
  F="$ND/commands/$C.md"
  assert_lacks "commands/$C.md does not require dependencies.superpowers to be true" \
    "$F" '`dependencies.superpowers` must be `true`'
  assert_lacks "commands/$C.md does not require dependencies.featureDev to be true" \
    "$F" '`dependencies.featureDev` must be `true`'
done

echo "== the schema agrees that the block is optional =="
# The doc claim and the schema must not drift apart: this is the pair whose
# disagreement produced the new-info regression.
# assert_lacks is grep -F: a FIXED string. Regex-escaping the brackets here put
# literal backslashes in the pattern, so the check passed against a schema that
# did require the block -- the silent-pass trap, not a failure.
assert_lacks "the schema does not require the dependencies block" \
  "$ND/schema/notion-dev.config.schema.json" '"required": ["project", "ticketSystem", "git", "verify", "dependencies"]'
assert_has "the schema calls the block optional setup-time hints" \
  "$ND/schema/notion-dev.config.schema.json" 'Optional setup-time hints'

echo
if [ "$fails" -eq 0 ]; then
  echo "All checks passed."
else
  echo "$fails CHECK(S) FAILED"
fi
exit $((fails > 0))
