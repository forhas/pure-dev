#!/usr/bin/env bash
# Live probe of the Claude Code background-session behaviour /notion-dev:run-epic rests on
# (spec docs/superpowers/specs/2026-11-03-epic-coordinator-design.md, facts 3-11, gate G1).
#
#   bash scripts/analysis/probe-background-sessions.sh <trusted-dir>
#
# <trusted-dir> is a folder Claude Code already trusts (a client checkout you work in);
# `claude --bg` refuses any other. Prints one `PASS|FAIL <check>` line per check and exits
# non-zero on any FAIL (8 checks). It starts real sessions, so it spends a little usage and needs a
# logged-in CLI; that is why it is not part of scripts/run-verifications.sh. Every session
# it starts is stopped and removed on exit, also on failure. Runs unchanged from WSL and
# from Git Bash on Windows (PYBIN defaults to python3, then python).
set -u
target=${1:-}
[ -n "$target" ] && [ -d "$target" ] || { echo "usage: $0 <trusted-dir>" >&2; exit 2; }
cd "$target" || exit 2
if [ -z "${PYBIN:-}" ]; then
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys' >/dev/null 2>&1; then PYBIN=python3; else PYBIN=python; fi
fi
# `claude` is resolved by coordinator.py's own claude_command(), never by the bare name:
# Windows Python finds a bare name only as a real .exe, and an npm install provides a
# claude.cmd shim (plus an extensionless sh script that only Git Bash can run).
here=$(cd "$(dirname "$0")" && pwd)
PROBE_PLUGIN_SCRIPTS="$here/../../plugins/notion-dev/scripts"
command -v cygpath >/dev/null 2>&1 && PROBE_PLUGIN_SCRIPTS=$(cygpath -m "$PROBE_PLUGIN_SCRIPTS")
[ -f "$PROBE_PLUGIN_SCRIPTS/coordinator.py" ] || { echo "FAIL coordinator.py not found at $PROBE_PLUGIN_SCRIPTS" ; exit 1; }
export PROBE_PLUGIN_SCRIPTS

mkdir -p .claude/notion-dev
[ -f .claude/notion-dev/.gitignore ] || printf '*\n' > .claude/notion-dev/.gitignore
tok=$($PYBIN -c 'import uuid; print(uuid.uuid4().hex[:10])')
work="$PWD/.claude/notion-dev/probe-$tok"
mkdir -p "$work/plugin/.claude-plugin" "$work/plugin/commands"
created=""
fails=0
pass() { printf 'PASS %s\n' "$1"; }
fail() { printf 'FAIL %s\n' "$1"; fails=$((fails + 1)); }
cleanup() {
  for id in $created; do "${CLAUDE[@]}" stop "$id" >/dev/null 2>&1; "${CLAUDE[@]}" rm "$id" >/dev/null 2>&1; done
  rm -rf "$work"
}
trap cleanup EXIT

printf '{"name": "probe", "version": "0.0.1"}\n' > "$work/plugin/.claude-plugin/plugin.json"
cat > "$work/plugin/commands/gated.md" <<'EOF'
---
description: probe command that only a user can start
disable-model-invocation: true
---
Reply with exactly the text GATED-RAN-$ARGUMENTS and nothing else.
EOF
cat > "$work/plugin/commands/yield.md" <<'EOF'
---
description: probe command that yields on a background worker
disable-model-invocation: true
---
Use the Agent tool to launch ONE general-purpose subagent with run_in_background true whose task is: run the shell command `sleep 60` and then reply DONE. Right after launching it, end your turn with the single word WAITING. When you are later notified that the subagent finished, reply with exactly: WOKE-$ARGUMENTS
EOF
cat > "$work/plugin/commands/ask.md" <<'EOF'
---
description: probe command that hits a permission prompt
disable-model-invocation: true
---
Run exactly the shell command `echo PROBE-ASK $ARGUMENTS` with the Bash tool, then reply DONE.
EOF
cat > "$work/hook.py" <<'EOF'
import json, os, sys
data = json.load(sys.stdin)
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), sys.argv[1] + ".log"), "a", encoding="utf-8") as log:
    log.write(json.dumps(data) + "\n")
EOF
cat > "$work/tool.py" <<'EOF'
import json, os, re, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8", newline="\n")
work = os.path.dirname(os.path.abspath(__file__))
def command():
    sys.path.insert(0, os.environ["PROBE_PLUGIN_SCRIPTS"])
    import coordinator
    return coordinator.claude_command()      # exactly what run-epic will run
def agents():
    out = subprocess.run(command() + ["agents", "--json", "--all"], capture_output=True, encoding="utf-8").stdout
    return json.loads(out)
def entry(short):
    return next((a for a in agents() if a.get("id") == short), None)
def log(name):
    path = os.path.join(work, name + ".log")
    return [json.loads(l) for l in open(path, encoding="utf-8")] if os.path.exists(path) else []
cmd = sys.argv[1]
if cmd == "cmd":              # the resolved claude command, one argv element per line
    print("\n".join(command()))
elif cmd == "id":
    found = re.findall(r"(?:backgrounded · |claude logs )([0-9a-f]{8})", sys.stdin.read())
    print(found[-1] if found else "")
elif cmd == "wait":           # wait <short> <seconds>: every distinct state/status pair seen, then the sessionId
    # Settled is `status: idle`, not `state: done`: a session STARTED WITH A SLASH COMMAND
    # keeps reading `state: working` after its turn ends (measured on 2.1.317), while
    # `status` goes busy -> idle for every session and stays busy through a yield.
    short, deadline, seen = sys.argv[2], time.monotonic() + int(sys.argv[3]), []
    session = ""
    while time.monotonic() < deadline:
        e = entry(short)
        if e:
            session = e.get("sessionId", "")
            pair = str(e.get("state")) + "/" + str(e.get("status"))
            if e.get("status") and (not seen or seen[-1] != pair): seen.append(pair)
            if e.get("status") == "idle" or e.get("state") in ("done", "failed", "stopped", "blocked"): break
        time.sleep(3)
    print(" ".join(seen) + "|" + session)
elif cmd == "retire":         # retire <short>: stop, wait for the process to EXIT, then rm
    # `claude stop` returns before the session's process has exited (~1 s later on
    # 2.1.317); a resume inside that window forks a copy with a new id (fact 10).
    def alive(pid):
        if os.name == "nt":
            import ctypes
            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
            if not handle: return False
            code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            ctypes.windll.kernel32.CloseHandle(handle)
            return code.value == 259  # STILL_ACTIVE
        try: os.kill(pid, 0)
        except ProcessLookupError: return False
        except PermissionError: return True
        return True
    short = sys.argv[2]
    pid = (entry(short) or {}).get("pid")
    subprocess.run(command() + ["stop", short], capture_output=True)
    deadline = time.monotonic() + 30
    while pid and alive(pid) and time.monotonic() < deadline: time.sleep(0.25)
    subprocess.run(command() + ["rm", short], capture_output=True)
    deadline = time.monotonic() + 10
    while entry(short) and time.monotonic() < deadline: time.sleep(0.5)
    print("no" if (pid and alive(pid)) or entry(short) else "yes")
elif cmd == "hooked":         # hooked <event> <session> [source]
    rows = [r for r in log(sys.argv[2]) if r.get("session_id") == sys.argv[3]]
    if len(sys.argv) > 4: rows = [r for r in rows if r.get("source") == sys.argv[4]]
    print("yes" if rows else "no")
elif cmd == "transcript":     # transcript <session>
    rows = [r for r in log("stop") if r.get("session_id") == sys.argv[2]]
    print(rows[-1].get("transcript_path", "") if rows else "")
elif cmd == "said":           # said <session> <text>: an assistant row of that session contains the text
    rows = [r for r in log("stop") if r.get("session_id") == sys.argv[2]]
    path = rows[-1].get("transcript_path", "") if rows else ""
    found = False
    if path and os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            content = r.get("message", {}).get("content", "") if r.get("type") == "assistant" else ""
            if isinstance(content, list):
                content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
            found = found or (r.get("sessionId") == sys.argv[2] and sys.argv[3] in str(content))
    print("yes" if found else "no")
elif cmd == "user-row":       # user-row <transcript> <session> <text>
    def text(c):
        if isinstance(c, str): return c
        return "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    ok = False
    for line in open(sys.argv[2], encoding="utf-8"):
        r = json.loads(line)
        if (r.get("type") == "user" and r.get("sessionId") == sys.argv[3] and not r.get("isSidechain")
                and not r.get("isMeta") and text(r.get("message", {}).get("content", "")).strip() == sys.argv[4]):
            ok = True
    print("yes" if ok else "no")
EOF
hook() { printf '\\"%s\\" \\"%s/hook.py\\" %s' "$PYBIN" "$work" "$1"; }
cat > "$work/settings.json" <<EOF
{"permissions": {"allow": ["Bash(sleep 60)", "Bash(sleep:*)"], "ask": ["Bash(echo PROBE-ASK:*)"]},
 "hooks": {"SessionStart": [{"matcher": "*", "hooks": [{"type": "command", "command": "$(hook start)"}]}],
           "Stop": [{"matcher": "*", "hooks": [{"type": "command", "command": "$(hook stop)"}]}]}}
EOF
tool() { $PYBIN "$work/tool.py" "$@"; }
strip() { sed 's/\x1b\[[0-9;]*[A-Za-z]//g'; }
CLAUDE=()
while IFS= read -r part; do [ -n "$part" ] && CLAUDE+=("$part"); done < <(tool cmd)
[ "${#CLAUDE[@]}" -gt 0 ] || { echo "FAIL claude could not be resolved the way coordinator.py does: $(tool cmd 2>&1 | tail -1)"; exit 1; }
echo "claude runs as: ${CLAUDE[*]}"
launch() { timeout 90 "${CLAUDE[@]}" --bg "$@" --plugin-dir "$work/plugin" --settings "$work/settings.json" 2>&1 | strip | tool id; }

# 1. A gated plugin command starts in a background session and prints its short id.
id=$(launch "/probe:gated $tok")
if [ -n "$id" ]; then created="$created $id"; pass "1 claude --bg prints a short id ($id)"; else fail "1 claude --bg prints a short id"; exit 1; fi

# 2. The documented machine-readable states, and the id is the session's prefix.
seen=$(tool wait "$id" 180); states=${seen%%|*}; session=${seen##*|}
# A slash-command session settles as status idle; its state may still read working (tool.py wait).
case " $states" in *"/busy "*"/idle") pass "2 claude agents --json --all: $states; sessionId $session" ;; *) fail "2 state/status seen: '$states' (expected busy, then idle)" ;; esac
case "$session" in "$id"*) : ;; *) fail "2 sessionId '$session' does not start with $id" ;; esac

# 3. SessionStart and Stop hooks fire inside the background session with its sessionId.
sleep 3
if [ "$(tool hooked start "$session")" = yes ] && [ "$(tool hooked stop "$session")" = yes ]; then
  pass "3 SessionStart and Stop hooks carry the sessionId"
else fail "3 SessionStart/Stop hooks did not log $session"; fi

# 4. The gated command really ran (a model cannot invoke it; only the prompt can).
if "${CLAUDE[@]}" logs "$id" 2>&1 | strip | grep -q "GATED-RAN-$tok"; then pass "4 the gated command ran"; else fail "4 GATED-RAN-$tok missing from claude logs"; fi

# 5. stop -> rm -> resume continues the SAME session (fact 10).
tok2="PROBE-RELAY-$tok"
[ "$(tool retire "$id")" = yes ] || fail "5 the stopped session did not exit and leave the list within 40 s"
rid=$(timeout 90 "${CLAUDE[@]}" --bg --resume "$session" "$tok2" --plugin-dir "$work/plugin" --settings "$work/settings.json" 2>&1 | strip | tool id)
[ -n "$rid" ] && created="$created $rid"
seen=$(tool wait "${rid:-none}" 180); session2=${seen##*|}
sleep 3
if [ "$rid" = "$id" ] && [ "$session2" = "$session" ] && [ "$(tool hooked start "$session" resume)" = yes ]; then
  pass "5 stop, rm, --resume keeps the session id (source: resume)"
else fail "5 resume gave id '$rid' session '$session2' (expected $id / $session, source resume)"; fi

# 6. The resume prompt lands as a parent user row in the owning transcript (the relay premise).
transcript=$(tool transcript "$session")
if [ -n "$transcript" ] && [ -f "$transcript" ] && [ "$(tool user-row "$transcript" "$session" "$tok2")" = yes ]; then
  pass "6 the resumed prompt is a non-sidechain user row of that session"
else fail "6 no user row '$tok2' for $session in '${transcript:-no transcript}'"; fi

# 7. A slash-command session that yields on a background worker stays busy and wakes itself
#    (fact 11): idle before the wake would make the coordinator judge a run still in progress.
yid=$(launch "/probe:yield $tok")
[ -n "$yid" ] && created="$created $yid"
seen=$(tool wait "${yid:-none}" 420); states=${seen%%|*}; ysession=${seen##*|}
# Read the transcript the moment idle shows: the wake must already be in it, or idle came early.
woke=$(tool said "$ysession" "WOKE-$tok")
case " $states" in *"/busy "*"/idle") yield_ok=yes ;; *) yield_ok=no ;; esac
if [ "$yield_ok" = yes ] && [ "$woke" = yes ]; then
  pass "7 a yielding session stays busy until it wakes itself"
else fail "7 yield state/status '$states' (expected busy until WOKE-$tok, then idle)"; fi

# 8. A slash-command session at a permission prompt reads blocked (state blocked, status waiting),
#    so the coordinator surfaces it instead of waiting on a `working` that never ends.
bid=$(launch "/probe:ask $tok")
[ -n "$bid" ] && created="$created $bid"
seen=$(tool wait "${bid:-none}" 180); states=${seen%%|*}
case " $states" in *" blocked/waiting") pass "8 a permission prompt reads blocked/waiting" ;; *) fail "8 permission prompt state/status '$states' (expected to end blocked/waiting)" ;; esac

[ "$fails" -eq 0 ] && echo "all 8 checks passed" || echo "$fails check(s) failed"
[ "$fails" -eq 0 ]
