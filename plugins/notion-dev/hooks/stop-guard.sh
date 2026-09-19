#!/usr/bin/env bash
# notion-dev Stop guard — the mechanism behind "a --non-interactive run never hands back".
#
# The rule was shipped as prose in 0.28.1 and did not hold. A client run on
# 0.28.1 stopped at the end of Phase 7, and when asked why, correctly quoted the
# rule it had just broken. That is not a comprehension failure: ending a turn is
# the *absence* of an action, so no instruction can gate it. Only the harness
# can, and `Stop` is the harness event for exactly this.
#
# Blocks the stop while this project has a live `--non-interactive` run marker,
# naming the phase to resume at. The prose stays — it is what tells the run what
# to do when this hook sends it back — but this file is the enforcement.
#
# FAIL OPEN, ALWAYS. A blocking hook that errors is a wedged session, which is
# worse than the stop it exists to prevent. Every unexpected condition here ends
# in "allow the stop", and nothing below is permitted to exit non-zero.
#
# Blocks are bounded twice over, because a guard that cannot give up is a trap:
#   * freshness — the marker is rewritten at every phase boundary, verify
#     iteration and review round, so its mtime tracks the heartbeat. Older than
#     STALE_MINUTES and the run is abandoned, not live: allow. A stop happens
#     right after a unit of work returns, which is exactly when the marker was
#     just touched, so the live case is never the stale one.
#   * count — at most MAX_BLOCKS per run per session. A run that means to stop
#     stops on the fourth try, with the guard saying so rather than going quiet.
#
# `stop_hook_active` is deliberately not consulted: it is true precisely when a
# previous block sent the run back, which is when this guard most wants to block
# again. The count is the bound, not that flag.
#
# Both platforms: POSIX shell plus `git` and `find`, no `date -d`, no `stat -c`,
# no `jq` — this runs on every stop in every session, so it takes no dependency
# the plugin does not already guarantee, and it never parses a timestamp.

STALE_MINUTES=30
MAX_BLOCKS=3

# No `set -e` and no ERR trap. An ERR trap looks like the way to fail open and
# is the opposite: it fires on the first ordinary non-zero return — `cat` on a
# counter file that does not exist yet — and allows the stop before the guard
# has decided anything. Measured: it allowed every case, including the one it
# exists to block. Failing open here is structural instead: no command's exit
# status can end the script early, every branch reaches an explicit exit, and a
# crash exits non-zero, which Claude Code treats as a non-blocking error — a
# stop allowed. The guard can only ever fail towards letting the run stop.
allow() { exit 0; }

input=$(cat 2>/dev/null)
[ -n "$input" ] || allow
flat=$(printf '%s' "$input" | tr -d '\n\r' 2>/dev/null)

field() { printf '%s' "$2" | sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" 2>/dev/null; }

session=$(field session_id "$flat")
[ -n "$session" ] || session="unknown-session"
# Strip anything that is not filename-safe: the session id reaches a path below.
session=$(printf '%s' "$session" | tr -c 'A-Za-z0-9._-' '_' 2>/dev/null)
[ -n "$session" ] || session="unknown-session"

dir=${CLAUDE_PROJECT_DIR:-}
[ -n "$dir" ] || dir=$(field cwd "$flat")
[ -n "$dir" ] || dir=$(pwd)
[ -d "$dir" ] || allow

# The run happens inside a worktree; the marker lives in the primary checkout.
# `git worktree list` names that first, from anywhere in the repository.
# Everything after "worktree " is the path, spaces included — `{print $2}` would
# truncate `/path/repo with space` to `/path/repo`, and the runs lookup would
# then either fail open on a live run or, if that shorter path happens to exist,
# read a different checkout's markers.
root=$(git -C "$dir" worktree list --porcelain 2>/dev/null | sed -n 's/^worktree //p' | head -1)
[ -n "$root" ] || root=$dir
runs="$root/.claude/notion-dev/runs"
[ -d "$runs" ] || allow

# Prune counters left by runs that have finished (Phase 9 deletes the marker) or
# by sessions long gone, so this directory cannot grow without bound.
find "$runs" -maxdepth 1 -name '.stop-guard-*' -mtime +1 -exec rm -f {} + 2>/dev/null

live_run=""
live_phase=""
for marker in "$runs"/*.json; do
  [ -f "$marker" ] || continue
  # Fresh? The marker is touched at every boundary, so mtime is the heartbeat.
  find "$marker" -maxdepth 0 -mmin "-$STALE_MINUTES" 2>/dev/null | grep -q . || continue
  body=$(tr -d '\n\r' < "$marker" 2>/dev/null) || continue
  printf '%s' "$body" | grep -q '"state"[[:space:]]*:[[:space:]]*"running"' || continue
  # Absent means interactive: an interactive run ends its turn to ask, and
  # blocking that would break the flow this guard is meant to protect. Only an
  # explicit true qualifies, so a marker written by an older version is ignored.
  printf '%s' "$body" | grep -q '"non_interactive"[[:space:]]*:[[:space:]]*true' || continue
  live_run=$(field run "$body")
  live_phase=$(field phase "$body")
  [ -n "$live_run" ] || live_run=$(basename "$marker" .json)
  [ -n "$live_phase" ] || live_phase="an earlier phase"
  break
done

[ -n "$live_run" ] || allow

safe_run=$(printf '%s' "$live_run" | tr -c 'A-Za-z0-9._-' '_' 2>/dev/null)
[ -n "$safe_run" ] || safe_run="run"
counter="$runs/.stop-guard-$safe_run-$session"
blocks=""
[ -f "$counter" ] && blocks=$(cat "$counter" 2>/dev/null)
case "$blocks" in (''|*[!0-9]*) blocks=0 ;; esac

if [ "$blocks" -ge "$MAX_BLOCKS" ]; then
  printf '{"systemMessage":"notion-dev stop guard: %s is still at %s, but this session has already been sent back %s times — allowing the stop. The run is unfinished; resume it with /notion-dev:ticket or /notion-dev:finalize."}\n' \
    "$live_run" "$live_phase" "$MAX_BLOCKS"
  exit 0
fi

blocks=$((blocks + 1))
printf '%s' "$blocks" > "$counter" 2>/dev/null

printf '{"decision":"block","reason":"notion-dev: %s is a --non-interactive run and its marker still reads state=running at %s. This run does not end its turn mid-run: no question was asked, so nothing is waiting on an answer, and nobody is watching to type continue. Do not summarise and stop. Continue from %s and carry on through the phases that follow it, to the final report or to one of the stop conditions the command names explicitly — those write state=stopped with a cause, which is what tells this guard a stop is real. Block %s of %s."}\n' \
  "$live_run" "$live_phase" "$live_phase" "$blocks" "$MAX_BLOCKS"
exit 0
