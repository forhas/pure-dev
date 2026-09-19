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
# NOT covered: `/notion-dev:finalize`. It writes no run marker, so a
# marker-keyed guard has nothing to match and a finalize run is unguarded end
# to end. That is a boundary of this design, not an oversight to be patched
# here — giving `finalize` a marker is its own lifecycle question.
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

# Take the first candidate that EXISTS, not the first that is merely set. On
# the no-arg resume path Claude is launched inside the ticket worktree, so
# `$CLAUDE_PROJECT_DIR` names it — and Phase 9 removes that worktree while the
# run is still going. Treating a vanished project dir as "nothing to guard"
# allowed every stop for the whole of cleanup, the post-merge hooks and Phase
# 10, which is the window the delayed marker deletion exists to cover. The
# hook's own `cwd` is the useful fallback there: by then the run is operating
# from the primary checkout, which is where the marker lives anyway.
# `$NOTION_DEV_PRIMARY_ROOT` FIRST, and it is not an optimisation. The other
# three candidates all describe where the session was launched, and on the
# no-argument resume path that is the ticket worktree — which Phase 9 deletes
# while the run is still going. A `cd` in an earlier Bash call does not move
# the process those values come from, so once the worktree is gone none of
# them names an existing directory and the guard would fall open for cleanup,
# the post-merge hooks and all of Phase 10. The SessionStart hook resolved the
# primary checkout while the worktree still existed and put it here.
dir=""
for candidate in "${NOTION_DEV_PRIMARY_ROOT:-}" "${CLAUDE_PROJECT_DIR:-}" "$(field cwd "$flat")" "$(pwd 2>/dev/null)"; do
  if [ -n "$candidate" ] && [ -d "$candidate" ]; then dir=$candidate; break; fi
done
[ -n "$dir" ] || allow

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

# Prune counters whose RUN is over — never by the counter's own age. Age alone
# deleted the counter of a run that was still heart-beating, which reset it to
# "block 1 of 3" and left the cap bounding nothing: the pruning meant to keep
# this directory small quietly undid the guard's other bound. A counter is
# spent exactly when its marker is gone, stale, or no longer `running`, which
# is also when the directory pressure it was added for disappears.
#
# The name is `.stop-guard-<run>--<session>`: a single `-` cannot separate them
# because both halves contain one — run ids look like `STO-355`, session ids
# are UUIDs — so `--` is the delimiter and `%%--*` is what reads it back.
for counter in "$runs"/.stop-guard-*; do
  [ -f "$counter" ] || continue
  base=${counter##*/.stop-guard-}
  run_of=${base%%--*}
  [ -n "$run_of" ] && [ "$run_of" != "$base" ] || { rm -f "$counter" 2>/dev/null; continue; }
  m="$runs/$run_of.json"
  if [ ! -f "$m" ]; then rm -f "$counter" 2>/dev/null; continue; fi
  if ! find "$m" -maxdepth 0 -mmin "-$STALE_MINUTES" 2>/dev/null | grep -q .; then
    rm -f "$counter" 2>/dev/null; continue
  fi
  tr -d '\n\r' < "$m" 2>/dev/null | grep -q '"state"[[:space:]]*:[[:space:]]*"running"' \
    || rm -f "$counter" 2>/dev/null
done

# EVERY qualifying marker, not the first one found. One session can hold two
# live runs — a ticket that reached the block cap, and another started before
# the first marker aged out — and `break`ing at the first took whichever
# filename sorted earlier. If that one's counter was spent, the cap branch
# allowed every stop without ever looking at the run that was actually going;
# if it was not, the guard blocked with another ticket's phase in the message.
# So: gather them, then block on the first whose counter is not yet spent.
live_run=""
live_phase=""
exhausted_run=""
exhausted_phase=""
for marker in "$runs"/*.json; do
  [ -f "$marker" ] || continue
  # Fresh? The marker is touched at every boundary, so mtime is the heartbeat.
  find "$marker" -maxdepth 0 -mmin "-$STALE_MINUTES" 2>/dev/null | grep -q . || continue
  body=$(tr -d '\n\r' < "$marker" 2>/dev/null) || continue
  # Structurally whole before it is believed. The flow rewrites this file in
  # place rather than atomically, so a torn write can leave a fragment that
  # still contains `"non_interactive":true` and a `"claude_session"` — enough
  # for the greps below to accept it and block on a marker that is not a
  # marker, which contradicts the fail-open handling of an unparseable one.
  #
  # This is a STRUCTURAL check, not a parse, and the difference is deliberate.
  # A marker that is brace-delimited, carries every key, and is still invalid
  # JSON — a missing comma between two fields, say — passes here and can
  # produce a block. Parsing JSON properly in shell is not a small change, and
  # this hook may not take a `jq` or python dependency: it runs on every stop
  # in every session. The residual is bounded rather than argued away: the
  # worst such a marker can do is spend the block cap, at most MAX_BLOCKS
  # refusals before the guard gives up and allows the stop, and the realistic
  # corruption from an in-place rewrite is a truncated file, which the brace
  # test does catch. Raised as a review finding and dropped on that basis.
  case "$body" in
    '{'*'}') : ;;
    *) continue ;;
  esac
  for required in '"run"' '"phase"' '"state"' '"non_interactive"' '"claude_session"'; do
    printf '%s' "$body" | grep -q "$required[[:space:]]*:" || { body=""; break; }
  done
  [ -n "$body" ] || continue
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

  this_run=$(field run "$body")
  this_phase=$(field phase "$body")
  [ -n "$this_run" ] || this_run=$(basename "$marker" .json)
  [ -n "$this_phase" ] || this_phase="an earlier phase"

  this_safe=$(printf '%s' "$this_run" | tr -c 'A-Za-z0-9._-' '_' 2>/dev/null)
  [ -n "$this_safe" ] || this_safe="run"
  this_counter="$runs/.stop-guard-$this_safe--$session"
  this_blocks=""
  [ -f "$this_counter" ] && this_blocks=$(cat "$this_counter" 2>/dev/null)
  case "$this_blocks" in (''|*[!0-9]*) this_blocks=0 ;; esac

  if [ "$this_blocks" -lt "$MAX_BLOCKS" ]; then
    live_run=$this_run; live_phase=$this_phase
    counter=$this_counter; blocks=$this_blocks
    break
  fi
  # Spent, but remember it: if every live run is spent, that is what the
  # give-up message should name rather than reporting no run at all.
  exhausted_run=$this_run; exhausted_phase=$this_phase
done

if [ -z "$live_run" ]; then
  [ -n "$exhausted_run" ] || allow
  printf '{"systemMessage":"notion-dev stop guard: %s is still at %s, but this session has already been sent back %s times — allowing the stop. The run is unfinished; resume it with /notion-dev:ticket or /notion-dev:finalize."}\n' \
    "$exhausted_run" "$exhausted_phase" "$MAX_BLOCKS"
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
