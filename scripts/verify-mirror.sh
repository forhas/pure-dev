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

# Assertions come from the shared library, like every other harness here, so
# that verify-assertions.sh's no-opt-out check has nothing to except.
# (cd to the repo root already happened above, so this path is stable.)
. ./scripts/lib/assert.sh

# Tracked-ness is only a meaningful question inside a git work tree. Outside one
# — an extracted tarball, a vendored copy — `git ls-files` fails for every file
# and would report four spurious failures, which is how a harness teaches people
# to ignore it. Resolve once and say plainly which mode this run is in.
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  IN_GIT=yes
else
  IN_GIT=no
fi

# ---------------------------------------------------------------------------
# Repo-local skills — the one documented exception to mirror parity
# ---------------------------------------------------------------------------
#
# `feedback-harvest` is a maintainer workflow for this marketplace. It belongs to
# neither shipped plugin: putting it in quick-dev would ship a notion-dev-specific
# harvester to everyone installing a generic feature-development plugin, and
# notion-dev's skills are not mirrored, so it would not be invocable here at all.
#
# The exemption is a TRACKED MANIFEST, never a naming convention. A directory
# under the mirror root that is in neither set still FAILs, which is the property
# .gitignore's comment depends on — the whole mirror directory is un-ignored, and
# this loop is what makes that exposure safe.
LOCAL_MANIFEST=$MIRROR_ROOT/REPO-LOCAL

is_repo_local() {
  [ -f "$LOCAL_MANIFEST" ] || return 1
  grep -qxF -- "$1" <(sed -e 's/#.*//' -e 's/[[:space:]]*$//' "$LOCAL_MANIFEST")
}

echo "== repo-local skill manifest =="

if [ -f "$LOCAL_MANIFEST" ]; then
  ok "REPO-LOCAL manifest present"
else
  bad "REPO-LOCAL manifest missing at $LOCAL_MANIFEST"
fi

if [ "$IN_GIT" = yes ]; then
  if git ls-files --error-unmatch "$LOCAL_MANIFEST" >/dev/null 2>&1; then
    ok "REPO-LOCAL manifest is tracked by git"
  else
    bad "REPO-LOCAL manifest is NOT tracked by git (check .gitignore)"
  fi
fi

# Every declared name must exist, and must NOT have a plugin counterpart. The
# second half is the guard that matters: without it a drifted mirror could be
# relabelled repo-local and skip parity entirely.
while IFS= read -r name; do
  [ -n "$name" ] || continue
  if [ -d "$MIRROR_ROOT/$name" ]; then
    ok "repo-local '$name' exists on disk"
  else
    bad "repo-local '$name' is declared in REPO-LOCAL but absent from $MIRROR_ROOT"
  fi
  if [ -d "$PLUGIN_SKILLS/$name" ]; then
    bad "repo-local '$name' also exists in $PLUGIN_SKILLS — a mirror cannot declare itself repo-local"
  else
    ok "repo-local '$name' has no plugin counterpart"
  fi
done < <(sed -e 's/#.*//' -e 's/[[:space:]]*$//' "$LOCAL_MANIFEST" 2>/dev/null | grep -v '^$')

mirrored=0
for mdir in "$MIRROR_ROOT"/*/; do
  [ -d "$mdir" ] || continue
  skill=$(basename "$mdir")
  src="$PLUGIN_SKILLS/$skill"

  echo "== $skill mirror parity =="

  if [ ! -d "$src" ]; then
    if is_repo_local "$skill"; then
      ok "$skill is a declared repo-local skill (no mirror parity expected)"
      # Content parity is meaningless without a counterpart, but *tracked-ness*
      # is not — that is the failure a fresh checkout caught once already.
      if [ "$IN_GIT" = yes ]; then
        while IFS= read -r f; do
          if git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
            ok "$skill: ${f#"$MIRROR_ROOT"/} is tracked by git"
          else
            bad "$skill: ${f#"$MIRROR_ROOT"/} is NOT tracked by git (check .gitignore)"
          fi
        done < <(find "$mdir" -type f | sort)
      fi
    else
      bad "$skill exists only in the mirror and is not declared in REPO-LOCAL (project-local fork)"
    fi
    continue
  fi

  mirrored=$((mirrored + 1))

  # Forward: every file the plugin ships must be mirrored, byte for byte. Walking
  # the tree rather than naming paths keeps a newly added file from being silently
  # unmirrored — the failure mode a fixed list would miss.
  while IFS= read -r f; do
    rel=${f#"$src"/}
    assert_identical "$skill: $rel matches the quick-dev plugin" "$f" "$mdir$rel"
  done < <(find "$src" -type f | sort)

  # Reverse: EVERY file in the mirror must have a plugin counterpart — recursively,
  # not only SKILL.md and references/*. A file with none is a project-local fork,
  # invisible to everyone who installs the plugin, and .gitignore no longer hides
  # one: the whole mirror directory is un-ignored, so an unmatched scratch file
  # here is visible to `git add -A`. This loop is the mechanism that makes that
  # exposure safe, and it only works if it inspects every path. README.md is the
  # one legitimate exception — it documents the mirroring rule and has no plugin
  # counterpart.
  while IFS= read -r f; do
    rel=${f#"$mdir"}
    # The exception is ONE documented path, not the basename in every mirror.
    # Exempting `README.md` anywhere let a staged README under a newly mirrored
    # skill satisfy both the counterpart check and the tracked check.
    if [ "$mdir$rel" = "$MIRROR_ROOT/review-and-merge/README.md" ]; then
      ok "$skill: README.md is the documented mirror-only exception"
      continue
    fi
    if [ -f "$src/$rel" ]; then
      ok "$skill: $rel has a plugin counterpart"
    else
      bad "$skill: $rel exists only in the mirror (project-local file)"
    fi
  done < <(find "$mdir" -type f | sort)

  # Present on disk is not the invariant — *versioned* is. A mirror file that
  # .gitignore excludes passes every content check locally and then vanishes on a
  # fresh checkout, which is how a mirrored skill first shipped untracked: `git
  # add -A` skipped it silently and only CI noticed. Ask git, not the filesystem.
  if [ "$IN_GIT" = yes ]; then
    while IFS= read -r f; do
      if git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
        ok "$skill: ${f#"$MIRROR_ROOT"/} is tracked by git"
      else
        bad "$skill: ${f#"$MIRROR_ROOT"/} is NOT tracked by git (check .gitignore)"
      fi
    done < <(find "$mdir" -type f | sort)
  fi
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
