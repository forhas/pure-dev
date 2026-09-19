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
#     STALE_MINUTES and the run is abandoned, not live: allow.
#
#     STALE_MINUTES matches `commands/ticket.md`'s own 2-hour staleness rule,
#     and must not be shortened below it. A heartbeat says *this run reached
#     that boundary*, never *this run is alive right now*: it is written
#     BETWEEN units of work and never inside one, because a flow blocked in a
#     build task, a verify command or a reviewer round cannot write anything
#     until that unit returns. So the threshold has to exceed the longest
#     single unit, which is exactly why that file picked two hours. A 30-minute
#     window shipped in the first draft of this guard and was wrong in the one
#     case that matters: a Phase 7 review loop runs 3-20 minutes per round for
#     up to 15 rounds, so the marker is routinely older than 30 minutes at the
#     moment Phase 7 ends — the precise boundary the run in the bug report
#     stopped at. The guard would have watched it stop.
#
#     The short window was there to stop an abandoned run blocking a later
#     session, and that reason is gone: the session match below means a marker
#     can only ever block the session that created it, so an abandoned run
#     blocks nobody but itself, whatever the threshold. The cap still bounds
#     it either way.
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

STALE_MINUTES=120
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

# Two forms, and they are not interchangeable. The RAW id is what a marker is
# matched against; the sanitised one is only ever a filename component.
session_raw=$(field session_id "$flat")
session=$(printf '%s' "$session_raw" | tr -c 'A-Za-z0-9._-' '_' 2>/dev/null)
[ -n "$session" ] || session="unknown-session"
# No separate guard for an absent id: an empty `$session_raw` cannot equal any
# marker's `claude_session`, so the match below already allows that case. A
# redundant early return here would read as a live check and be unprovable.

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
  # THE MARKER MUST BELONG TO THE SESSION THAT IS STOPPING. A checkout can hold
  # several runs at once — parallel tickets on one machine are a supported
  # scenario — and it can hold an interactive session alongside a
  # non-interactive one. Without this test the first fresh marker blocks
  # whoever happens to stop, so an unrelated session is refused its stop up to
  # three times and told to continue another run's ticket from another run's
  # phase. That is the wedge this guard exists to avoid, built into the guard.
  # `claude_session` is Claude Code's own session id, which `## 2.1` records
  # from $CLAUDE_CODE_SESSION_ID; it is not the marker's `session` field, which
  # is the plugin's own run token and means something else.
  marker_session=$(field claude_session "$body")
  # Absent means the marker cannot be attributed — a pre-0.29.0 marker, or a
  # host that does not set the variable. Never block on an unattributable
  # marker: a guard that cannot tell whose run it is has no business refusing
  # anyone's stop.
  [ -n "$marker_session" ] || continue
  [ "$marker_session" = "$session_raw" ] || continue
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

# A block is only legitimate once the increment is on disk. If the counter
# cannot be written — read-only directory, a directory sitting on the path, a
# full filesystem — every invocation re-reads nothing, stays at "block 1 of 3",
# and the cap never engages: unbounded blocking, which is the wedge this guard
# is supposed to be incapable of. Read it back rather than trusting the write,
# and allow the stop when it did not land.
blocks=$((blocks + 1))
printf '%s' "$blocks" > "$counter" 2>/dev/null
persisted=""
[ -f "$counter" ] && persisted=$(cat "$counter" 2>/dev/null)
[ "$persisted" = "$blocks" ] || allow

printf '{"decision":"block","reason":"notion-dev: %s is a --non-interactive run and its marker still reads state=running at %s. This run does not end its turn mid-run: no question was asked, so nothing is waiting on an answer, and nobody is watching to type continue. Do not summarise and stop. Continue from %s and carry on through the phases that follow it, to the final report or to one of the stop conditions the command names explicitly — those write state=stopped with a cause, which is what tells this guard a stop is real. Block %s of %s."}\n' \
  "$live_run" "$live_phase" "$live_phase" "$blocks" "$MAX_BLOCKS"
exit 0
