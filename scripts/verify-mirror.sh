#!/usr/bin/env bash
# Parity check for this repo's own copy of the review-and-merge skill.
#
# `.claude/skills/review-and-merge/` is a verbatim mirror of
# `plugins/quick-dev/skills/review-and-merge/`, so this repo can drive its own
# PRs with the loop it ships. It has drifted twice — first silently, then again
# after a README told contributors to re-sync in the same commit. A written
# reminder is not a mechanism; this is.
#
# Unlike the change-scoped harnesses beside it, this asserts a standing
# invariant, so it has no baseline to go stale against.
#
# Run from anywhere: ./scripts/verify-mirror.sh
set -uo pipefail
cd "$(dirname "$0")/.."

SRC=plugins/quick-dev/skills/review-and-merge
MIRROR=.claude/skills/review-and-merge
fails=0

ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# assert_identical <label> <fileA> <fileB>
assert_identical() {
  if [ ! -f "$2" ]; then bad "$1 (missing: $2)"; return; fi
  if [ ! -f "$3" ]; then bad "$1 (missing: $3)"; return; fi
  if diff -q "$2" "$3" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi
}

echo "== review-and-merge mirror parity =="

assert_identical "SKILL.md matches the quick-dev plugin" \
  "$SRC/SKILL.md" "$MIRROR/SKILL.md"

# Every reference the plugin ships must be mirrored, byte for byte. Looping
# rather than naming them keeps a newly added reference from being silently
# unmirrored — the failure mode a fixed list would miss.
for f in "$SRC"/references/*; do
  [ -e "$f" ] || continue
  base=$(basename "$f")
  assert_identical "references/$base matches the quick-dev plugin" \
    "$f" "$MIRROR/references/$base"
done

# The reverse direction: a file in the mirror with no counterpart in the plugin
# is a project-local fork, which is invisible to everyone who installs the
# plugin. README.md is the one legitimate exception — it documents the mirroring
# rule itself and has no plugin counterpart.
for f in "$MIRROR"/references/*; do
  [ -e "$f" ] || continue
  base=$(basename "$f")
  if [ -f "$SRC/references/$base" ]; then
    ok "references/$base has a plugin counterpart"
  else
    bad "references/$base exists only in the mirror (project-local fork)"
  fi
done

if [ -f "$MIRROR/README.md" ]; then
  ok "mirror README present (documents the rule this script enforces)"
else
  bad "mirror README missing"
fi

if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
  echo
  echo "Re-sync with:"
  echo "  cp -r $SRC/. $MIRROR/"
  echo "Then confirm: diff -r --exclude=README.md $SRC/ $MIRROR/"
fi
exit $(( fails > 0 ? 1 : 0 ))
