#!/usr/bin/env bash
# Parity check for this repo's own copies of the skills it ships.
#
# Every directory under `.claude/skills/` is a verbatim mirror of the
# same-named directory under `plugins/quick-dev/skills/`, so this repo can
# drive its own work with the skills it ships. The review-and-merge mirror
# drifted twice — first silently, then again after a README told contributors
# to re-sync in the same commit. A written reminder is not a mechanism; this is.
#
# The mirror set is discovered, never listed: a skill mirrored tomorrow is
# checked tomorrow with no edit here. A fixed list would silently exempt it,
# which is the failure mode this file exists to remove.
#
# Unlike the change-scoped harnesses beside it, this asserts a standing
# invariant, so it has no baseline to go stale against.
#
# Run from anywhere: ./scripts/verify-mirror.sh
set -uo pipefail
cd "$(dirname "$0")/.."

PLUGIN_SKILLS=plugins/quick-dev/skills
MIRROR_ROOT=.claude/skills
fails=0

ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# assert_identical <label> <fileA> <fileB>
assert_identical() {
  if [ ! -f "$2" ]; then bad "$1 (missing: $2)"; return; fi
  if [ ! -f "$3" ]; then bad "$1 (missing: $3)"; return; fi
  if diff -q "$2" "$3" >/dev/null 2>&1; then ok "$1"; else bad "$1"; fi
}

# Tracked-ness is only a meaningful question inside a git work tree. Outside one
# — an extracted tarball, a vendored copy — `git ls-files` fails for every file
# and would report four spurious failures, which is how a harness teaches people
# to ignore it. Resolve once and say plainly which mode this run is in.
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  IN_GIT=yes
else
  IN_GIT=no
fi

mirrored=0
for mdir in "$MIRROR_ROOT"/*/; do
  [ -d "$mdir" ] || continue
  skill=$(basename "$mdir")
  src="$PLUGIN_SKILLS/$skill"
  mirrored=$((mirrored + 1))

  echo "== $skill mirror parity =="

  if [ ! -d "$src" ]; then
    bad "$skill exists only in the mirror (project-local fork)"
    continue
  fi

  assert_identical "$skill: SKILL.md matches the quick-dev plugin" \
    "$src/SKILL.md" "$mdir/SKILL.md"

  # Present on disk is not the invariant — *versioned* is. A mirror file that
  # .gitignore excludes passes every content check locally and then vanishes on a
  # fresh checkout, which is how a mirrored skill first shipped untracked: `git
  # add -A` skipped it silently and only CI noticed. Ask git, not the filesystem.
  if [ "$IN_GIT" = yes ]; then
    for f in "$mdir"SKILL.md "$mdir"references/*; do
      [ -e "$f" ] || continue
      if git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
        ok "$skill: ${f#"$MIRROR_ROOT"/} is tracked by git"
      else
        bad "$skill: ${f#"$MIRROR_ROOT"/} is NOT tracked by git (check .gitignore)"
      fi
    done
  fi

  # Every reference the plugin ships must be mirrored, byte for byte. Looping
  # rather than naming them keeps a newly added reference from being silently
  # unmirrored — the failure mode a fixed list would miss.
  for f in "$src"/references/*; do
    [ -e "$f" ] || continue
    base=$(basename "$f")
    assert_identical "$skill: references/$base matches the quick-dev plugin" \
      "$f" "$mdir/references/$base"
  done

  # The reverse direction: a file in the mirror with no counterpart in the
  # plugin is a project-local fork, invisible to everyone who installs the
  # plugin. README.md is the one legitimate exception — it documents the
  # mirroring rule itself and has no plugin counterpart.
  for f in "$mdir"/references/*; do
    [ -e "$f" ] || continue
    base=$(basename "$f")
    if [ -f "$src/references/$base" ]; then
      ok "$skill: references/$base has a plugin counterpart"
    else
      bad "$skill: references/$base exists only in the mirror (project-local fork)"
    fi
  done
done

echo "== mirror set =="

if [ "$mirrored" -gt 0 ]; then
  ok "$mirrored skill(s) mirrored under $MIRROR_ROOT"
else
  bad "no skills mirrored under $MIRROR_ROOT (the mirror set cannot be empty)"
fi

if [ "$IN_GIT" = yes ]; then
  ok "run inside a git work tree — tracked-ness of every mirrored file was checked"
else
  echo "  SKIP  not a git work tree — tracked-ness not checked (content parity still was)"
fi

# One README documents the rule this script enforces, for the whole mirror set.
if [ -f "$MIRROR_ROOT/review-and-merge/README.md" ]; then
  ok "mirror README present (documents the rule this script enforces)"
else
  bad "mirror README missing"
fi

if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
  echo
  echo "Re-sync a drifted skill with:"
  echo "  cp -r $PLUGIN_SKILLS/<skill>/. $MIRROR_ROOT/<skill>/"
  echo "Then confirm: diff -r --exclude=README.md $PLUGIN_SKILLS/<skill>/ $MIRROR_ROOT/<skill>/"
fi
exit $(( fails > 0 ? 1 : 0 ))
