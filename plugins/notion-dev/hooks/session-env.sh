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
#
# THIS filter is the guarantee for the id, not the quoting below: with it in
# place no id can reach `shquote` that needed quoting, so no test can tell the
# quoted form from the unquoted one. The id is quoted anyway for uniformity
# with the path, which genuinely needs it. Do not remove this filter on the
# grounds that the values are quoted — quoting is what makes a *path* safe, and
# an id is not a path.
case "$sid" in
  *[!A-Za-z0-9._-]*) exit 0 ;;
esac

# Single-quote every value written here. The harness SOURCES this file, so an
# unquoted value is shell input: a path with a space truncates the variable at
# the space, and a `;` or a `&` would execute. The id is already restricted to
# safe characters above; the path below cannot be, because a real checkout path
# legitimately contains spaces — Windows user profiles routinely do.
shquote() {  # wrap in single quotes, escaping any single quote within
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

printf 'export NOTION_DEV_SESSION_ID=%s\n' "$(shquote "$sid")" >> "$CLAUDE_ENV_FILE" 2>/dev/null

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
# A newline is the one thing quoting cannot carry through a line-oriented file,
# and no character class rejection is needed beyond it: `shquote` makes every
# other byte literal, including the spaces a real Windows checkout path has.
# Counted, not matched: `case $x in *"$(printf '\n')"*)` looks like the test and
# is not one — command substitution strips the trailing newline, so the pattern
# is `**`, every path matches, and nothing is ever written. It shipped that way
# for one commit and the round-trip test caught it.
[ "$(printf '%s' "$primary" | wc -l | tr -d ' ')" = "0" ] || exit 0

printf 'export NOTION_DEV_PRIMARY_ROOT=%s\n' "$(shquote "$primary")" >> "$CLAUDE_ENV_FILE" 2>/dev/null
exit 0
