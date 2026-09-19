#!/usr/bin/env bash
# notion-dev's Stop guard — behavioural, not prose.
#
# The rule "a --non-interactive run never hands back" shipped as prose in 0.28.1
# and did not hold: a client run on that version stopped at the end of Phase 7
# and then quoted the rule it had broken. 0.29.0 moves the enforcement into a
# `Stop` hook, and a hook is code — so this harness RUNS it against fixtures
# rather than grepping the document that describes it.
#
# The two directions that matter are equally important and pull opposite ways:
# it must block a live non-interactive run, and it must fail open on everything
# else. A guard that blocks too eagerly wedges a session, which is worse than
# the stop it prevents — so most of the cases below assert silence.
#
# Run from anywhere: ./scripts/verify-stop-guard.sh
set -uo pipefail
cd "$(dirname "$0")/.."

fails=0
ok()  { printf '  PASS  %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fails=$((fails + 1)); }

# shellcheck source=lib/assert.sh
. ./scripts/lib/assert.sh

HOOKS=plugins/notion-dev/hooks/hooks.json
GUARD=plugins/notion-dev/hooks/stop-guard.sh
GUARD_ABS=$PWD/$GUARD
SENV=plugins/notion-dev/hooks/session-env.sh
SENV_ABS=$PWD/$SENV

# ---------------------------------------------------------------------------
echo "== the hook is registered and runnable =="
# ---------------------------------------------------------------------------
if [ -f "$HOOKS" ]; then
  assert_has "hooks.json registers a \`Stop\` hook"                "$HOOKS" '"Stop"'
  assert_has "hooks.json runs the guard via \`\${CLAUDE_PLUGIN_ROOT}\`" \
    "$HOOKS" '${CLAUDE_PLUGIN_ROOT}/hooks/stop-guard.sh'
  assert_has "hooks.json declares the hook \`type\` as \`command\`"  "$HOOKS" '"type": "command"'
  # Without the SessionStart half there is no session id for a run to stamp
  # into its marker, so every marker records an empty owner, the guard skips
  # every one of them, and the Stop half is present and inert.
  assert_has "hooks.json registers the \`SessionStart\` hook that publishes the session id" \
    "$HOOKS" '"SessionStart"'
  assert_has "hooks.json runs \`session-env.sh\`" "$HOOKS" '${CLAUDE_PLUGIN_ROOT}/hooks/session-env.sh'
  # The captured root is consulted FIRST: every other candidate describes where
  # the session started, which on the resume path is a worktree Phase 9 deletes.
  assert_has "guard prefers \`\$NOTION_DEV_PRIMARY_ROOT\` over launch-derived paths" \
    "$GUARD" 'for candidate in "${NOTION_DEV_PRIMARY_ROOT:-}"'
else
  bad "hooks.json is missing ($HOOKS)"
fi

T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT

# Fixture commits must not depend on the machine's git identity. A CI runner has
# none, so `git commit` fails there and every fixture built on one silently does
# not exist — which is how a harness green on a laptop goes red on both CI legs.
export GIT_AUTHOR_NAME=pure-dev-test GIT_AUTHOR_EMAIL=test@example.invalid
export GIT_COMMITTER_NAME=pure-dev-test GIT_COMMITTER_EMAIL=test@example.invalid

# Two paths naming one directory are not always the same string: Git for
# Windows reports `C:/Users/...` from `git worktree list` while the shell holds
# `/c/Users/...`. Compare what they RESOLVE to, never the spelling.
same_dir() {
  [ -d "${1:-}" ] && [ -d "${2:-}" ] || return 1
  [ "$(cd "$1" 2>/dev/null && pwd -P)" = "$(cd "$2" 2>/dev/null && pwd -P)" ]
}

if [ -f "$GUARD" ]; then
  bash -n "$GUARD" 2>/dev/null && ok "stop-guard.sh parses" || bad "stop-guard.sh does not parse"
  # Assert against the CODE, with whole-line comments stripped. The guard's own
  # header explains why it avoids these tools, so grepping the file as written
  # fails on the sentences that document the rule — a check that goes red for
  # being explained is one that gets deleted rather than fixed.
  CODE=$T/guard-code.sh
  sed 's/^[[:space:]]*#.*$//' "$GUARD" > "$CODE"
  # Both platforms. This runs on EVERY stop in every session, so it may not take
  # a dependency the plugin does not already guarantee, and the GNU-only flags
  # CLAUDE.md names would break the Windows leg silently.
  assert_lacks "guard code does not use \`date -d\`"     "$CODE" 'date -d'
  assert_lacks "guard code does not use \`stat -c\`"     "$CODE" 'stat -c'
  assert_lacks "guard code does not use \`readlink -f\`" "$CODE" 'readlink -f'
  assert_lacks "guard code does not use \`grep -P\`"     "$CODE" 'grep -P'
  assert_lacks "guard code does not shell out to \`jq\`" "$CODE" 'jq '
  # An ERR trap reads as the way to fail open and is the opposite — it fired on
  # the first `cat` of a counter file that did not exist yet and allowed every
  # stop, including the one the guard exists to block. Measured before release.
  assert_lacks "guard code sets no ERR trap" "$CODE" 'trap '
  # Freshness is judged from the marker's mtime, never by parsing its timestamp:
  # there is no portable date arithmetic across both platforms without one of
  # the banned tools above.
  assert_has "guard judges freshness by file mtime (\`-mmin\`)" "$CODE" '-mmin'
  # The threshold must exceed the longest single unit of work, which is why
  # ticket.md picked two hours. Shortening it silently switches the guard off
  # at long phase boundaries — the ones where stops actually happen.
  assert_has "guard's staleness threshold matches ticket.md's 2-hour rule" "$CODE" 'STALE_MINUTES=120'
  assert_has "guard blocks only after the increment is persisted" "$CODE" '[ "$persisted" = "$blocks" ] || allow'
  # The marker check is structural, not a parse, and the limit is recorded at
  # the line rather than left for a reader to discover. Pin the disclosure:
  # dropping it is how a known residual turns into a surprise.
  assert_has "guard records that its marker check is structural, not a parse" \
    "$GUARD" 'This is a STRUCTURAL check, not a parse'
  assert_has "guard's header records that \`/notion-dev:finalize\` is not covered" \
    "$GUARD" 'NOT covered: `/notion-dev:finalize`'
  assert_has "guard records what bounds that residual" \
    "$GUARD" 'is spend the block cap, at most MAX_BLOCKS'
  # Phase 1 uses a second marker shape because the ticket id is not resolved
  # yet (issue #57). The guard is shape-agnostic by design, and the two lines
  # below are the only two that know a preflight marker exists at all.
  assert_has "guard's header records that there are TWO MARKER SHAPES under one rule" \
    "$GUARD" 'TWO MARKER SHAPES, one rule'
  # Keyed by the `run` field the counter is unmappable for a preflight marker,
  # so the prune loop wipes it on every invocation and the cap never engages.
  assert_has "guard derives the block counter key from the marker filename, via \`basename\`" \
    "$CODE" 'this_stem=$(basename "$marker" .json)'
  assert_has "guard's prune loop reads that same stem back" "$CODE" 'm="$runs/$stem_of.json"'
  # A preflight marker is a placeholder and disposable; a run marker is
  # evidence. The sweep must name the one shape it is allowed to delete.
  assert_has "guard sweeps only the \`preflight-\` marker shape" \
    "$CODE" 'for stray in "$runs"/preflight-*.json'
else
  bad "stop-guard.sh is missing ($GUARD)"
  echo; echo "$fails CHECK(S) FAILED"; exit 1
fi

# ---------------------------------------------------------------------------
echo "== behaviour: blocks a live non-interactive run, allows everything else =="
# ---------------------------------------------------------------------------
git init -q "$T/primary" 2>/dev/null
git -C "$T/primary" commit -q --allow-empty -m init 2>/dev/null
REPO=$T/primary
RUNS=$REPO/.claude/notion-dev/runs
mkdir -p "$RUNS"
M=$RUNS/STO-355.json
EF_EARLY=$T/env-file-early
MAX_SPENT=3      # must equal MAX_BLOCKS in the guard
HOOK_EXITS=$T/.hook-exit-failures
: > "$HOOK_EXITS"

marker() { # state, non_interactive-literal-or-empty, [owning-session, default sess-1]
  local owner=${3:-sess-1}
  if [ -n "${2:-}" ]; then
    printf '{\n "run": "STO-355",\n "phase": "Phase 8",\n "state": "%s",\n "non_interactive": %s,\n "claude_session": "%s"\n}\n' "$1" "$2" "$owner" > "$M"
  else
    printf '{\n "run": "STO-355",\n "phase": "Phase 8",\n "state": "%s",\n "claude_session": "%s"\n}\n' "$1" "$owner" > "$M"
  fi
}

hook() { # env=VAL... -- <script> <<stdin>   ; runs it, asserts exit 0, echoes stdout
  local envs=() script="" stdin=""
  while [ "${1:-}" != "--" ]; do envs+=("$1"); shift; done
  shift; script=$1; stdin=$2
  local out rc
  out=$(printf '%s' "$stdin" | env "${envs[@]}" bash "$script" 2>/dev/null); rc=$?
  # Record, do not `bad`, and the difference is load-bearing: almost every
  # caller is `out=$(hook ...)`, a SUBSHELL, so an increment to `fails` there
  # is discarded and `bad`'s own output is captured as if the hook had printed
  # it. Both make a crash look like something other than a crash. A file
  # crosses the subshell; HOOK_EXITS is read once at the end.
  [ "$rc" -eq 0 ] || printf '%s exited %s\n' "$(basename "$script")" "$rc" >> "$HOOK_EXITS"
  printf '%s' "$out"
}

guard() { # [cwd], [session_id] -> stdout; asserts exit 0 every time
  local cwd=${1:-$REPO} sid=${2:-sess-1} out rc
  out=$(printf '{"session_id":"%s","cwd":"%s","hook_event_name":"Stop"}' "$sid" "$cwd" \
        | CLAUDE_PROJECT_DIR="$cwd" bash "$GUARD_ABS" 2>/dev/null)
  rc=$?
  [ "$rc" -eq 0 ] || bad "guard exited $rc (a non-zero exit is a hook error, not a decision)"
  printf '%s' "$out"
}

blocks()  { case "$1" in *'"decision":"block"'*) return 0 ;; *) return 1 ;; esac; }
silent()  { [ -z "$1" ]; }
reset()   { rm -f "$RUNS"/.stop-guard-*; }

expect_silent() { # label, output
  if silent "$2"; then ok "$1"; else bad "$1 (guard spoke: ${2:0:70})"; fi
}
expect_block() { # label, output
  if blocks "$2"; then ok "$1"; else bad "$1 (no block: ${2:0:70})"; fi
}

rm -f "$M"
expect_silent "no run marker at all: silent" "$(guard)"

marker running true
reset
expect_block  "live non-interactive run: blocked"                  "$(guard)"
out=$(guard); expect_block "second stop in the same session: blocked" "$out"
out=$(guard); expect_block "third stop: blocked"                      "$out"
out=$(guard)
case "$out" in
  *'"systemMessage"'*) ok "fourth stop: allowed, with the guard saying it gave up" ;;
  *) bad "fourth stop: expected a systemMessage and no block, got: ${out:0:70}" ;;
esac
case "$out" in *'"decision":"block"'*) bad "fourth stop still blocked — the cap does not bound" ;; esac

# The block message has to be actionable: a bare refusal to stop tells the run
# nothing about where to pick up, which is the whole content of the decision.
reset
out=$(guard)
case "$out" in *STO-355*)   ok "block names the run" ;;      *) bad "block does not name the run" ;; esac
case "$out" in *"Phase 8"*) ok "block names the phase to resume at" ;; *) bad "block does not name the phase" ;; esac

# --- every allow-path, one per line of the guard's own conditions ------------
reset; marker running ""
expect_silent "marker without \`non_interactive\`: silent (pre-0.29.0 marker, treated as interactive)" "$(guard)"

reset; marker running false
expect_silent "interactive run (\`non_interactive: false\`): silent — it ends a turn to ask" "$(guard)"

reset; marker stopped true
expect_silent "\`state: stopped\`: silent — a named stop wrote its own cause" "$(guard)"

reset; marker running true; touch -t 202601010000 "$M"
expect_silent "stale marker: silent — an abandoned run cannot block a later session" "$(guard)"

reset; printf 'not json at all\n' > "$M"
expect_silent "unparseable marker: silent" "$(guard)"

# A checkout can hold two runs at once, or an interactive session beside a
# non-interactive one. A marker that belongs to somebody else must never block
# the session that is stopping — that would be the guard doing the wedging.
reset; marker running true sess-1
expect_silent "another session's marker: silent — never blocks a session that does not own the run" \
  "$(guard "$REPO" sess-2)"
expect_block  "the owning session: still blocked" "$(guard "$REPO" sess-1)"

reset
printf '{\n "run": "STO-355",\n "phase": "Phase 8",\n "state": "running",\n "non_interactive": true\n}\n' > "$M"
expect_silent "marker with no \`claude_session\`: silent — an unattributable marker blocks nobody" "$(guard)"

reset; marker running true sess-1
expect_silent "hook input carrying no \`session_id\`: silent — nothing to match against" \
  "$(hook "CLAUDE_PROJECT_DIR=$REPO" -- "$GUARD_ABS" "$(printf '{"cwd":"%s","hook_event_name":"Stop"}' "$REPO")")"

reset; rm -rf "$REPO/.claude"
expect_silent "no runs directory: silent" "$(guard)"

reset
out=$(hook "CLAUDE_PROJECT_DIR=$REPO" -- "$GUARD_ABS" '')
expect_silent "empty stdin: silent" "$out"

# --- the run lives in a worktree; the marker lives in the primary checkout ---
mkdir -p "$RUNS"; marker running true; reset
if git -C "$REPO" worktree add -q "$T/wt" -b feat 2>/dev/null; then
  expect_block "called from inside the worktree: resolves the primary checkout and blocks" "$(guard "$T/wt")"
else
  bad "could not create a worktree fixture"
fi

# --- the three items the final sweep took -------------------------------------
# 1. A torn marker with the right substrings must not block.
reset
printf '{\n "run": "STO-355",\n "phase": "Phase 8",\n "state": "running",\n "non_interactive": true,\n "claude_session": "sess-1"' > "$M"
expect_silent "marker truncated mid-object (no closing brace): silent, despite carrying every key" "$(guard)"
reset
printf '{ "state": "running", "non_interactive": true, "claude_session": "sess-1" }\n' > "$M"
expect_silent "marker missing \`run\` and \`phase\`: silent — a partial marker is not a marker" "$(guard)"

# 2. A counter is pruned when its run is over, never merely because it is old.
reset; marker running true sess-1
guard >/dev/null                                   # creates the counter
CNT="$RUNS/.stop-guard-STO-355--sess-1"
if [ -f "$CNT" ]; then ok "the block counter is written next to the marker"; else bad "no counter written"; fi
touch -t 202601010000 "$CNT"                       # a day-old counter, live run
out=$(guard)
if [ -f "$CNT" ] && blocks "$out"; then
  ok "an old counter for a LIVE run survives — pruning by age alone unbounds the cap"
else
  bad "the counter of a live run was pruned (exists=$([ -f "$CNT" ] && echo yes || echo no))"
fi
marker stopped true sess-1; guard >/dev/null
[ ! -f "$CNT" ] && ok "the counter is pruned once its run is no longer running" \
                || bad "a finished run's counter was left behind"

# 3. Two live markers in one session: the spent one must not mask the other.
reset; marker running true sess-1
M2=$RUNS/AAA-1.json                                # sorts BEFORE STO-355.json
printf '{\n "run": "AAA-1",\n "phase": "Phase 3",\n "state": "running",\n "non_interactive": true,\n "claude_session": "sess-1"\n}\n' > "$M2"
printf '%s' "$MAX_SPENT" > "$RUNS/.stop-guard-AAA-1--sess-1"   # AAA-1 has hit its cap
out=$(guard)
if blocks "$out"; then
  case "$out" in
    *STO-355*) ok "a spent marker sorting first does not mask the live run behind it" ;;
    *) bad "blocked, but named the spent run: ${out:0:80}" ;;
  esac
else
  bad "a spent marker sorting first suppressed the guard entirely"
fi
rm -f "$M2" "$RUNS/.stop-guard-AAA-1--sess-1"

# --- the two round-2 regressions ---------------------------------------------
# 45 minutes old: past the 30-minute window the first draft shipped, well inside
# `ticket.md`'s 2-hour rule. A Phase 7 review loop runs 3-20 minutes per round
# for up to 15 rounds, so a marker this age at a phase boundary is the ORDINARY
# case, not an abandoned run — and it is the boundary the reported stop happened
# at. Under the short window the guard would have watched it stop.
PY=${KNOWLEDGE_PY:-python3}
if $PY -c 'import os,sys' 2>/dev/null; then
  reset; marker running true sess-1
  $PY -c 'import os,sys,time; p=sys.argv[1]; t=time.time()-45*60; os.utime(p,(t,t))' "$M" 2>/dev/null
  expect_block "marker 45 minutes old: still blocks — the threshold must exceed the longest unit of work" \
    "$(guard)"
else
  bad "no python available to age a fixture ($PY); the 45-minute case did not run"
fi

# An increment that cannot be persisted is not a bounded block: every later
# invocation re-reads nothing, stays at "block 1 of 3", and the cap never
# engages. Unwritable counter must therefore allow, not block.
reset; marker running true sess-1
mkdir -p "$RUNS/.stop-guard-STO-355--sess-1"      # a directory where the counter file goes
expect_silent "counter cannot be written: silent — an uncountable block is an unbounded one" "$(guard)"
rmdir "$RUNS/.stop-guard-STO-355--sess-1"

# The no-arg resume path launches Claude inside the ticket worktree, so
# $CLAUDE_PROJECT_DIR names it — and Phase 9 deletes that worktree while the
# run continues through hooks and Phase 10. A vanished project dir must not
# read as "nothing to guard"; the hook's own cwd (the primary checkout by
# then) is what carries it.
# The hostile version of this case, and the one the earlier fixture was too
# kind about: EVERY launch-derived candidate names the deleted worktree, which
# is what the resume path actually looks like once Phase 9 has run. Only the
# root captured at session start can carry it.
reset; mkdir -p "$RUNS"; marker running true sess-1
GONE=$T/removed-worktree
out=$(hook "CLAUDE_PROJECT_DIR=$GONE" "NOTION_DEV_PRIMARY_ROOT=$REPO" -- "$GUARD_ABS" \
      "$(printf '{"session_id":"sess-1","cwd":"%s","hook_event_name":"Stop"}' "$GONE")")
expect_block "every launch-derived path is a deleted worktree: the captured primary root still blocks" "$out"

out=$(hook "CLAUDE_PROJECT_DIR=$GONE" -- "$GUARD_ABS" \
      "$(printf '{"session_id":"sess-1","cwd":"%s","hook_event_name":"Stop"}' "$GONE")")
expect_silent "...and with no captured root either, it fails open rather than guessing" "$out"

# session-env.sh is what captures that root, from inside the worktree, while
# the worktree still exists.
: > "$EF_EARLY"
if git -C "$REPO" worktree add -q "$T/wt-early" -b early 2>/dev/null; then
  hook "CLAUDE_ENV_FILE=$EF_EARLY" "CLAUDE_PROJECT_DIR=$T/wt-early" -- "$SENV_ABS" \
    "$(printf '{"session_id":"sess-1","cwd":"%s","hook_event_name":"SessionStart"}' "$T/wt-early")" >/dev/null
  got=$( . "$EF_EARLY" 2>/dev/null; printf '%s' "${NOTION_DEV_PRIMARY_ROOT:-}" )
  if same_dir "$got" "$REPO"; then
    ok "session-env.sh resolves the primary checkout from inside a worktree"
  else
    bad "session-env.sh did not capture the primary root (sourced: [$got], file: $(cat "$EF_EARLY" 2>/dev/null))"
  fi
else
  bad "could not create the early-worktree fixture"
fi

# Everything session-env.sh writes is SOURCED by the harness, so a value with
# a space truncates the variable and one with a `;` or `&` executes. Windows
# user profiles routinely contain spaces, so this is the ordinary case, not the
# adversarial one. Round-trip it: write, source, compare.
SPREPO="$T/space repo"
mkdir -p "$SPREPO"
if git init -q "$SPREPO" 2>/dev/null; then
  : > "$EF_EARLY"
  hook "CLAUDE_ENV_FILE=$EF_EARLY" "CLAUDE_PROJECT_DIR=$SPREPO" -- "$SENV_ABS" \
    "$(printf '{"session_id":"s-1","cwd":"%s","hook_event_name":"SessionStart"}' "$SPREPO")" >/dev/null
  got=$( . "$EF_EARLY" 2>/dev/null; printf '%s' "${NOTION_DEV_PRIMARY_ROOT:-}" )
  if same_dir "$got" "$SPREPO"; then
    ok "primary root containing a space survives being sourced back"
  else
    bad "primary root did not round-trip: wrote [$(cat "$EF_EARLY" 2>/dev/null)], sourced [$got]"
  fi
else
  bad "could not create the spaced-path fixture"
fi

# A checkout path with a space in it: `git worktree list --porcelain` emits the
# path unquoted after "worktree ", so a whitespace-delimited field read
# truncates it and the guard silently stops guarding.
SP="$T/dir with space"
git init -q "$SP" 2>/dev/null
git -C "$SP" commit -q --allow-empty -m init 2>/dev/null
mkdir -p "$SP/.claude/notion-dev/runs"
printf '{\n "run": "STO-355",\n "phase": "Phase 8",\n "state": "running",\n "non_interactive": true,\n "claude_session": "sess-1"\n}\n' \
  > "$SP/.claude/notion-dev/runs/STO-355.json"
out=$(hook "CLAUDE_PROJECT_DIR=$SP" -- "$GUARD_ABS" \
      "$(printf '{"session_id":"sess-1","cwd":"%s","hook_event_name":"Stop"}' "$SP")")
expect_block "checkout path containing a space: still blocks" "$out"

# ---------------------------------------------------------------------------
echo "== the preflight marker: Phase 1 is guarded too (issue #57) =="
# ---------------------------------------------------------------------------
# `<KEY>-<id>.json` is written in Phase 2.1, so on its own it leaves the whole
# of Phase 1 unguarded. The id is not known there, so that window uses a second
# shape keyed by the session id. The guard is deliberately shape-agnostic: these
# cases prove that, and prove the one place the shapes differ.
rm -f "$M"
PFM=$RUNS/preflight-sess-1.json
preflight() { # run-field, [state, default running], [owner, default sess-1]
  printf '{\n "run": "%s",\n "session": "preflight",\n "phase": "Phase 1 — preconditions",\n "state": "%s",\n "non_interactive": true,\n "claude_session": "%s"\n}\n' \
    "$1" "${2:-running}" "${3:-sess-1}" > "$PFM"
}

reset; preflight "STO-355"
expect_block "a live preflight marker blocks, exactly as a run marker does" "$(guard)"
reset; preflight "STO-355"
out=$(guard)
case "$out" in *"Phase 1"*) ok "the block names the Phase 1 sub-phase to resume at" ;;
                         *) bad "the block did not name the phase: ${out:0:80}" ;; esac

reset; preflight "STO-355" stopped
expect_silent "preflight marker written \`stopped\` by a Phase 1 stop path: silent — the abort goes through" \
  "$(guard)"

# THE REGRESSION THIS SHAPE INTRODUCES, and the reason the counter is keyed by
# the marker's FILENAME rather than its `run` field. Before 1.1 resolves the
# ticket, `run` holds the argument as supplied — a URL, a UUID, a logical key —
# and there is no `runs/<that>.json`. A counter named after it is unmappable, so
# the prune loop deletes it on every single invocation, the count never reaches
# MAX_BLOCKS, and the guard blocks forever: the one failure it must be incapable
# of. Use the hostile value, not a tidy one.
reset; preflight "https://notion.so/1f2e3d4c5b6a"
PFC="$RUNS/.stop-guard-preflight-sess-1--sess-1"
expect_block "preflight marker whose \`run\` is a raw URL: blocks (1 of 3)" "$(guard)"
if [ -f "$PFC" ]; then
  ok "its counter is named for the marker file, not for the unresolvable \`run\` value"
else
  bad "no counter at $PFC (found: $(ls -1 "$RUNS"/.stop-guard-* 2>/dev/null | tr '\n' ' '))"
fi
expect_block "...blocks (2 of 3)" "$(guard)"
expect_block "...blocks (3 of 3)" "$(guard)"
out=$(guard)
case "$out" in
  *'"decision":"block"'*) bad "the cap never engaged for a preflight marker — unbounded blocking" ;;
  *'"systemMessage"'*)    ok "the cap engages on the fourth stop, as it does for a run marker" ;;
  *) bad "fourth stop: expected the give-up message, got: ${out:0:70}" ;;
esac

# The preflight marker is a placeholder, retired by Phase 2.1 the moment the
# real marker exists — so a stale one is litter and the guard sweeps it. A stale
# run marker is evidence and is never deleted by a hook.
reset; preflight "STO-355"; touch -t 202601010000 "$PFM"
guard >/dev/null
[ ! -f "$PFM" ] && ok "a stale preflight marker is swept off disk" \
                || bad "a stale preflight marker was left behind"
reset; rm -f "$PFM"; marker running true; touch -t 202601010000 "$M"
guard >/dev/null
[ -f "$M" ] && ok "a stale RUN marker is not swept — the hook never deletes one" \
            || bad "the guard deleted a run marker"
rm -f "$M" "$PFM"; reset

# ---------------------------------------------------------------------------
echo "== ticket.md writes and retires the preflight marker =="
# ---------------------------------------------------------------------------
# The guard is shape-agnostic, so nothing in the hook can make Phase 1 write a
# marker or stop writing one. That contract lives in the command, and a
# retirement it skips is worse than the gap: the guard then refuses a stop the
# command itself ordered.
TK=plugins/notion-dev/commands/ticket.md
TKL=$(total_lines "$TK")
PRE=$(find_line "$TK" 1 "$TKL" '^## Preconditions$')
P11=$(find_line "$TK" 1 "$TKL" '^### 1\.1 ')
P12=$(find_line "$TK" 1 "$TKL" '^### 1\.2 ')
P21=$(find_line "$TK" 1 "$TKL" '^### 2\.1 ')
P22=$(find_line "$TK" 1 "$TKL" '^## Phase 3 — Triage$')
STOPS=$(find_line "$TK" 1 "$TKL" '^## Failure and stop conditions$')

if [ -n "$PRE" ] && [ -n "$P11" ] && [ -n "$P12" ] && [ -n "$P21" ] && [ -n "$P22" ] && [ -n "$STOPS" ]; then
  assert_present "ticket.md preconditions: the preflight marker is written before any probe can abort" \
    "$TK" "$PRE" "$P11" 'Write the preflight run marker — first, before any probe below can abort'
  assert_present "ticket.md preconditions: keyed by \`\$NOTION_DEV_SESSION_ID\` at \`runs/preflight-<session>.json\`" \
    "$TK" "$PRE" "$P11" 'runs/preflight-<session>\.json`, where `<session>` is `\$NOTION_DEV_SESSION_ID`'
  # Sanitising the FIELD as well as the filename makes the marker inert, and
  # invisibly so: a session id is a UUID, so the substitution changes nothing
  # on one and the mismatch never shows up in testing.
  assert_present "ticket.md preconditions: \`claude_session\` carries the id verbatim; only the filename is sanitised" \
    "$TK" "$PRE" "$P11" '`claude_session` carries the id verbatim; only the filename is sanitised'
  assert_present "ticket.md preconditions: an empty \`\$NOTION_DEV_SESSION_ID\` writes no file at all" \
    "$TK" "$PRE" "$P11" 'When `\$NOTION_DEV_SESSION_ID` is empty, write no file at all'
  # Retirement is the half that can turn a documented hard abort into a session
  # that cannot stop, so both triggers are pinned, not just the tidy one.
  assert_present "ticket.md preconditions: handover retires it once a \`<KEY>-<id>.json\` marker names this session" \
    "$TK" "$PRE" "$P11" '`rm -f` the file the instant a `<KEY>-<id>\.json` marker naming this session is live'
  assert_present "ticket.md preconditions: every stop before 2.1 writes \`state: stopped\` into it first" \
    "$TK" "$PRE" "$P11" 'rewrite the preflight marker with `"state": "stopped"` and `cause` set to the one-clause reason'
  assert_present "ticket.md preconditions: skipping that has the guard refuse the stop the command ordered" \
    "$TK" "$PRE" "$P11" 'the guard refuses the stop the command itself just ordered'
  assert_present "ticket.md preconditions: the stop enumeration is a checklist, not a boundary" \
    "$TK" "$PRE" "$P11" 'That enumeration is a checklist, not a boundary'

  # The three places a `<KEY>-<id>` marker goes live are the three places the
  # handover can happen. 2.1 is the fresh path; the other two skip it entirely.
  assert_present "ticket.md 2.1: the handover \`rm -f\` runs right after the run marker is written" \
    "$TK" "$P21" "$P22" 'Then `rm -f "\$REPO_ROOT/\.claude/notion-dev/runs/preflight-<session>\.json"` — the handover'
  assert_present "ticket.md 1.2 resume: the claim rewrite also \`rm -f\`s the preflight marker" \
    "$TK" "$P12" "$P21" 'then `rmdir` the claim directory and `rm -f` the preflight marker'
  assert_present "ticket.md 1.2 take-over: that branch is where the handover happens, since 2.1 never runs" \
    "$TK" "$P12" "$P21" '2\.1 never runs on a take-over, so this branch is the only place the handover can happen'
  assert_present "ticket.md 1.2: every abort in the section writes \`\"state\": \"stopped\"\` into the preflight marker" \
    "$TK" "$P12" "$P21" 'Every abort in this section stops before 2\.1.s marker exists, so every one of them writes `"state": "stopped"` with its cause into the preflight marker'

  # "Failure and stop conditions" is the rule every later stop inherits. Left
  # naming one shape, it silently exempts every stop that happens in Phase 1.
  assert_present "ticket.md stop conditions: \"the run marker\" means whichever shape this run holds" \
    "$TK" "$STOPS" "$TKL" '\*\*"The run marker" means whichever one this run currently holds\*\*'
  assert_present "ticket.md stop conditions: the two shapes are never both live" \
    "$TK" "$STOPS" "$TKL" 'The two shapes are never both live'
else
  bad "ticket.md: could not anchor the regions (pre=$PRE 1.1=$P11 1.2=$P12 2.1=$P21 p3=$P22 stops=$STOPS)"
fi

# The 1.1 stops are the ones that fire before the `run` field can even name the
# ticket, and each is a documented HARD abort — the worst thing to have refused.
if [ -n "$P11" ] && [ -n "$P12" ]; then
  assert_present "ticket.md 1.1: the epic guard retires the preflight marker before aborting" \
    "$TK" "$P11" "$P12" 'write `"state": "stopped"` with the cause into `\$REPO_ROOT/\.claude/notion-dev/runs/preflight-<session>\.json` before stopping'
  assert_present "ticket.md 1.1: the \`held elsewhere\` ownership check retires it too" \
    "$TK" "$P11" "$P12" 'for `held elsewhere` non-interactive mode never proceeds — and because this too runs before Phase 2'
  assert_present "ticket.md 1.1: \`run\` becomes \`<KEY>-<id>\` as soon as the numeric id is derived" \
    "$TK" "$P11" "$P12" 'Rewrite the preflight marker now: `run` becomes `<KEY>-<id>`'
fi

# The rule at the top of the command has to say Phase 1 is covered, or the
# guard's own bounds paragraph still reads as "Phase 1 is not".
assert_has "ticket.md: the preflight marker is what guards the whole of Phase 1" \
  "$TK" "the preconditions gate's \`preflight-<session>.json\` for the whole of Phase 1"

# ---------------------------------------------------------------------------
echo "== session-env.sh publishes the id the marker records =="
# ---------------------------------------------------------------------------
# The guard matches a marker's owner against the `session_id` the harness hands
# a hook on stdin. That value is only reliably available inside a hook, so this
# SessionStart hook is what carries it into the session's environment where a
# run can stamp it. If it writes nothing, the whole enforcement is inert.
EF=$T/env-file
senv() { hook "CLAUDE_ENV_FILE=$EF" -- "$SENV_ABS" "$1" >/dev/null; }

# Source it back rather than grepping a literal line: what matters is the value
# the harness ends up with, and every value here is shell-quoted.
: > "$EF"; senv '{"session_id":"abc-123","hook_event_name":"SessionStart"}'
got=$( . "$EF" 2>/dev/null; printf '%s' "${NOTION_DEV_SESSION_ID:-}" )
if [ "$got" = "abc-123" ]; then
  ok "session-env.sh exports the session id to \$CLAUDE_ENV_FILE"
else
  bad "session-env.sh did not export the session id (sourced: [$got], file: $(cat "$EF" 2>/dev/null))"
fi

: > "$EF"; senv '{"hook_event_name":"SessionStart"}'
[ ! -s "$EF" ] && ok "no \`session_id\` in the input: writes nothing" \
              || bad "wrote something with no session_id: $(cat "$EF")"

: > "$EF"; senv ''
[ ! -s "$EF" ] && ok "empty stdin: writes nothing" || bad "wrote something on empty stdin"

# The value lands in a file the harness SOURCES, so a session id carrying shell
# metacharacters would be executed. Nothing but the characters an id is made of
# may pass.
: > "$EF"; senv '{"session_id":"a\"; rm -rf /tmp/pd-x; #"}'
[ ! -s "$EF" ] && ok "session id with shell metacharacters: rejected, writes nothing" \
              || bad "wrote an unsafe session id: $(cat "$EF")"

if printf '{"session_id":"abc-123"}' | bash "$SENV_ABS" >/dev/null 2>&1; then
  ok "no \$CLAUDE_ENV_FILE: exits cleanly, writes nothing"
else
  bad "no \$CLAUDE_ENV_FILE: did not exit 0"
fi

# A hook that CRASHES — non-zero exit, empty stdout — satisfies every
# `expect_silent` case above, so without this the loudest failure mode reads
# as the quietest. Claude Code treats a non-zero exit as a hook error, which
# means a stop allowed: safe, but never a decision the guard made.
if [ -s "$HOOK_EXITS" ]; then
  while IFS= read -r line; do bad "hook exited non-zero: $line"; done < "$HOOK_EXITS"
else
  ok "every hook invocation in this harness exited 0"
fi

echo
if [ "$fails" -eq 0 ]; then
  echo "ALL CHECKS PASSED"
else
  echo "$fails CHECK(S) FAILED"
  echo
  echo "This harness runs plugins/notion-dev/hooks/stop-guard.sh against fixtures."
  echo "It pins both directions: the guard blocks a live --non-interactive run,"
  echo "and stays silent on every other state. A failure in the silent direction"
  echo "is the serious one — that guard can wedge a session."
fi
exit $(( fails > 0 ? 1 : 0 ))
