#!/usr/bin/env bash
# Publish this session's id to the session's own environment, so a run can
# stamp it into its run marker and the Stop guard can match the two.
#
# Why this exists rather than reading an environment variable directly: the
# guard identifies the owner of a run by the `session_id` the harness passes on
# a hook's stdin, and that value is only reliably available *inside a hook*.
# A command reading some ambient `CLAUDE_CODE_*` variable may find it unset —
# it is not part of the documented hook contract — and would then write an
# empty owner, which the guard skips, leaving the enforcement present and
# inert. That failure is silent, which is the worst kind here.
#
# `$CLAUDE_ENV_FILE` is the documented SessionStart mechanism for persisting an
# environment variable into the session, so the id reaches every later Bash
# call in exactly the session it belongs to — no shared file for two concurrent
# sessions in one checkout to overwrite.
#
# Fails open like the guard: no id, no env file, nothing written, and the
# marker records an empty owner, which blocks nobody.

[ -n "${CLAUDE_ENV_FILE:-}" ] || exit 0

input=$(cat 2>/dev/null)
[ -n "$input" ] || exit 0

field_cwd() {
  printf '%s' "$1" | tr -d '\n\r' 2>/dev/null \
    | sed -n 's/.*"cwd"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p'
}

sid=$(printf '%s' "$input" | tr -d '\n\r' 2>/dev/null \
      | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
[ -n "$sid" ] || exit 0

# Only the characters a session id is actually made of. This value is written
# into a file that the harness sources, so nothing else may reach it.
case "$sid" in
  *[!A-Za-z0-9._-]*) exit 0 ;;
esac

printf 'export NOTION_DEV_SESSION_ID=%s\n' "$sid" >> "$CLAUDE_ENV_FILE" 2>/dev/null

# Also capture the primary checkout, NOW, while it is still resolvable.
#
# The Stop guard needs the primary checkout because that is where run markers
# live, and every way of finding it at stop time starts from a directory the
# session names. On the supported no-argument resume path the session is
# launched *inside the ticket worktree*, and Phase 9 deletes that worktree
# while the run is still going — so by the time the guard wants the primary,
# `$CLAUDE_PROJECT_DIR`, the hook's `cwd` and its `pwd` can all name a
# directory that no longer exists. A `cd` inside an earlier Bash call does not
# move the process these values come from, so none of them recovers.
#
# At session start that worktree does exist, and `git worktree list` names the
# primary checkout first from anywhere inside the repository. Resolving it here
# and carrying it in the session's own environment is what survives the
# deletion — no file, no state for a later run to inherit.
start=${CLAUDE_PROJECT_DIR:-}
[ -n "$start" ] || start=$(field_cwd "$input")
[ -d "${start:-}" ] || exit 0

primary=$(git -C "$start" worktree list --porcelain 2>/dev/null | sed -n 's/^worktree //p' | head -1)
[ -n "$primary" ] || exit 0
[ -d "$primary" ] || exit 0
case "$primary" in *[\'\"\$\`]*) exit 0 ;; esac

printf 'export NOTION_DEV_PRIMARY_ROOT=%s\n' "$primary" >> "$CLAUDE_ENV_FILE" 2>/dev/null
exit 0
