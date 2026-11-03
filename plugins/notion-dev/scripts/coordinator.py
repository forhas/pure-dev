#!/usr/bin/env python3
"""The mechanics behind /notion-dev:run-epic: background ticket sessions, judged between tickets.

The command owns every judgment; this helper owns everything mechanical. It drives the
`claude` CLI's background sessions (`claude --bg`, never `claude -p`, never a permission
bypass), keeps the coordinator's state file and its per-epic exclusivity marker, waits on a
session, locates its outcome, parses its report and relays a user-given approval.

The background-session facts it rests on are measured, not assumed — spec
docs/superpowers/specs/2026-11-03-epic-coordinator-design.md facts 3-13, re-checked live by
scripts/analysis/probe-background-sessions.sh. Two of them shape the code below:

* a session started with a slash command never reads `state: done`; it settles as
  `status: idle` (fact 12);
* `claude stop` returns before the process exits, and a resume inside that window forks a
  copy under a new id even after `claude rm` (fact 13). `stop()` therefore waits for the
  process to exit, and `resume()` refuses any id other than the original.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from runtime import Invalid, atomic_json, read_json, require, state_lock

# Bounds for the CLI's asynchronous edges, seconds. Module-level so tests can shorten them.
EXIT_WAIT = 30      # stopped process -> exited (fact 13 measured ~1 s)
LIST_WAIT = 10      # rm -> gone from the list
APPEAR_WAIT = 15    # printed id -> listed with its sessionId

STALE_MINUTES = 120  # = hooks/stop-guard.sh STALE_MINUTES: an older marker is abandoned
REMEDIATION_BOUND = 2
VERDICTS = {"accepted", "remediate", "escalate", "declined"}
KINDS = {"next-task", "followup", "new-info"}

SHORT_ID = re.compile(r"(?:backgrounded · |claude logs )([0-9a-f]{8})")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def claude_command():
    """The CLI to run: the test fake when $NOTION_DEV_CLAUDE_FAKE names one, else `claude`."""
    fake = os.environ.get("NOTION_DEV_CLAUDE_FAKE")
    if fake:
        return [sys.executable, fake]
    found = shutil.which("claude")
    require(found, "claude is not on PATH; run-epic launches each ticket with `claude --bg` "
            "(Claude Code 2.1.317 or later)")
    return [found]


def claude(*args, cwd=None, timeout=120):
    """Run one CLI call; UTF-8 both ways whatever the platform's code page."""
    try:
        done = subprocess.run(claude_command() + list(args), cwd=str(cwd) if cwd else None,
                              capture_output=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise Invalid("`claude " + " ".join(args[:2]) + "` did not return within " + str(timeout) + " s")
    return done


def agents():
    done = claude("agents", "--json", "--all")
    try:
        value = json.loads(done.stdout)
    except ValueError:
        value = None
    require(isinstance(value, list), "`claude agents --json --all` did not print a JSON list "
            "(exit " + str(done.returncode) + "); run-epic needs Claude Code 2.1.317 or later")
    return [e for e in value if isinstance(e, dict)]


def entry(session):
    """The agents entry for a full session id. The host's own entry may lack `id`."""
    return next((e for e in agents() if e.get("sessionId") == session), None)


def short_entry(short_id):
    return next((e for e in agents() if e.get("id") == short_id), None)


def printed_id(output):
    found = SHORT_ID.findall(ANSI.sub("", output or ""))
    return found[-1] if found else None


def alive(pid):
    """Whether a process still runs. POSIX signal 0; Windows asks for the exit code.

    Never `os.kill(pid, 0)` on Windows: there it terminates the process.
    """
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def settle_entry(short_id):
    """A just-printed id can take a moment to appear in the list."""
    deadline = time.monotonic() + APPEAR_WAIT
    while True:
        found = short_entry(short_id)
        if found and found.get("sessionId") or time.monotonic() >= deadline:
            return found
        time.sleep(0.5)


def launch(cwd, prompt):
    done = claude("--bg", prompt, cwd=cwd)
    short = printed_id(done.stdout + "\n" + done.stderr)
    require(short, "`claude --bg` printed no session id (exit " + str(done.returncode) + "): " +
            ANSI.sub("", (done.stderr or done.stdout).strip())[-300:])
    found = settle_entry(short)
    require(found and found.get("sessionId", "").startswith(short),
            "background session " + short + " is not listed by `claude agents --json --all`")
    return {"id": short, "session": found["sessionId"]}


def stop(short_id):
    """Stop a session and return only once its process has exited (fact 13)."""
    found = short_entry(short_id)
    pid = found.get("pid") if found else None
    claude("stop", short_id)
    deadline = time.monotonic() + EXIT_WAIT
    while alive(pid):
        require(time.monotonic() < deadline, "session " + short_id + " was stopped but its process " +
                str(pid) + " is still running after " + str(EXIT_WAIT) + " s")
        time.sleep(0.25)


def remove(short_id):
    claude("rm", short_id)
    deadline = time.monotonic() + LIST_WAIT
    while short_entry(short_id) and time.monotonic() < deadline:
        time.sleep(0.5)


def resume(cwd, session, prompt):
    """Continue a session under its own id: stop -> exit -> rm -> `--bg --resume` (facts 10, 13).

    Any other id is a forked copy holding the whole run's context: it is stopped and removed
    at once and the resume is refused, never accepted as the session.
    """
    short = session[:8]
    if short_entry(short):
        stop(short)
        remove(short)
    done = claude("--bg", "--resume", session, prompt, cwd=cwd)
    got = printed_id(done.stdout + "\n" + done.stderr)
    require(got, "`claude --bg --resume` printed no session id (exit " + str(done.returncode) + ")")
    if got != short:
        stop(got)
        remove(got)
        raise Invalid("resume forked " + session + " into a copy " + got + " (removed); the "
                      "original was still listed — retry after it has left `claude agents`")
    found = settle_entry(short)
    require(found and found.get("sessionId") == session, "resumed session " + short + " is not listed")
    return {"id": short, "session": session}


# ---------------------------------------------------------------- state and marker

def stamp(seconds=None):
    return datetime.fromtimestamp(time.time() if seconds is None else seconds, timezone.utc).isoformat()


def age_minutes(value):
    try:
        then = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return float("inf")
    return (datetime.now(timezone.utc) - then).total_seconds() / 60


def safe(value):
    return re.sub(r"[^A-Za-z0-9._-]", "_", value)


def paths(root, epic):
    from workflow import local_dir
    directory = local_dir(Path(root))
    (directory / "runs").mkdir(exist_ok=True)
    return directory / "runs" / ("coordinator-" + epic + ".json"), directory / "coordinator"


def session_live(session):
    """Whether a session is listed by the CLI and, when the entry names a pid, still running."""
    found = entry(session)
    if found is None:
        return False
    return alive(found.get("pid")) if found.get("pid") else found.get("status") in {"busy", "idle"}


def open_launches(state):
    return [l["session"] for l in state["launches"] if l.get("verdict") is None]


def start(project, epic, session, non_interactive):
    """Begin or resume this epic's coordinator run; one live coordinator per epic per machine.

    The marker carries the stop guard's five keys, so a --non-interactive coordinator is held
    to its run exactly like a ticket. A marker that is running, fresh and owned by another
    session that is still listed refuses the start; a stale one, or one whose session ended,
    is adopted with its unfinished state.
    """
    from workflow import primary
    require(re.fullmatch(r"[A-Za-z0-9_-]+", epic or ""), "epic must be a ticket key such as STO-67")
    require(session, "NOTION_DEV_SESSION_ID missing; the SessionStart hook publishes it")
    root = primary(project)
    marker_path, states = paths(root, epic)
    with state_lock(marker_path.with_suffix(".claim.lock"), 5):
        marker = read_json(marker_path) if marker_path.is_file() else None
        adopted = None
        state_path = None
        if marker and marker.get("state") == "running" and marker.get("claude_session") != session:
            owner = marker.get("claude_session")
            fresh = age_minutes(marker.get("heartbeat")) < STALE_MINUTES
            if fresh:
                # The other session's absence proves it ended only where the list shows
                # this one: a CLI that does not list the host's session proves nothing.
                require(session_live(session) and not session_live(owner),
                        "coordinator-" + epic + " is live in session " + str(owner) + " (heartbeat " +
                        str(marker.get("heartbeat")) + "); attach to that session, or, if it has ended, remove " +
                        str(marker_path) + " and re-invoke")
            adopted = owner
        if marker and marker.get("state_path") and Path(marker["state_path"]).is_file():
            candidate = read_json(marker["state_path"])
            if candidate.get("status") != "complete":
                state_path = Path(marker["state_path"])
        if state_path is None and states.is_dir():
            unfinished = sorted(p for p in states.glob(safe(epic) + "-*.json")
                                if read_json(p).get("status") != "complete")
            state_path = unfinished[-1] if unfinished else None
        resumed = state_path is not None
        if resumed:
            state = read_json(state_path)
            if adopted:
                state.setdefault("adopted", []).append({"from": adopted, "by": session, "at": stamp()})
            state.update(status="running", cause=None, non_interactive=non_interactive, session=session)
        else:
            invocation = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + os.urandom(4).hex()
            state_path = states / (safe(epic) + "-" + invocation + ".json")
            state = {"epic": epic, "root": str(root), "mode": "serial", "non_interactive": non_interactive,
                     "invocation": invocation, "session": session, "started": stamp(), "launches": [],
                     "remediations": {}, "status": "running", "cause": None}
        atomic_json(state_path, state)
        atomic_json(marker_path, {"run": "coordinator-" + epic, "phase": "iterate", "state": "running",
                                  "non_interactive": non_interactive, "claude_session": session,
                                  "heartbeat": stamp(), "state_path": str(state_path)})
    return {"state": str(state_path), "marker": str(marker_path), "resumed": resumed,
            "open": open_launches(state), "adopted_from": adopted}


def heartbeat(state, terminal=None):
    """Rewrite the marker (its mtime is the stop guard's heartbeat); refuse a lost run."""
    marker_path, _ = paths(state["root"], state["epic"])
    with state_lock(marker_path.with_suffix(".claim.lock"), 5):
        marker = read_json(marker_path)
        require(marker.get("claude_session") == state["session"],
                "coordinator-" + state["epic"] + " was adopted by session " + str(marker.get("claude_session")) +
                "; this session no longer owns the run")
        marker["heartbeat"] = stamp()
        if terminal:
            marker.update(state=terminal, phase=terminal)
        atomic_json(marker_path, marker)


def update(state_path, change):
    """Apply `change(state)` under the state lock, write it, and refresh the heartbeat."""
    state_path = Path(state_path)
    with state_lock(state_path.with_suffix(".lock"), 5):
        state = read_json(state_path)
        result = change(state)
        atomic_json(state_path, state)
    heartbeat(state)
    return result


def find_launch(state, session):
    found = next((l for l in state["launches"] if l["session"] == session), None)
    require(found, str(session) + " is not a launch of this coordinator run")
    return found


def bound_key(state, launch):
    """Remediations are counted per ticket; a follow-up counts toward the ticket it came from."""
    if launch.get("kind") == "followup" and launch.get("parent"):
        launch = find_launch(state, launch["parent"])
    return launch.get("ticket") or launch["session"]


def spend(state, key):
    used = state["remediations"].get(key, 0)
    require(used < REMEDIATION_BOUND, "remediation bound reached for " + key + " (" + str(REMEDIATION_BOUND) +
            " per ticket); escalate to the user instead of launching again")
    state["remediations"][key] = used + 1


def record_launch(state_path, kind, prompt, ticket, parent):
    """Launch one background session and record it before anything waits on it (§A3.1)."""
    require(kind in KINDS, "launch kind must be one of " + ", ".join(sorted(KINDS)))
    state = read_json(state_path)
    if kind == "followup":
        require(parent, "a follow-up launch names the session it came from")
        spend(state, bound_key(state, find_launch(state, parent)))
    launched = launch(state["root"], prompt)
    record = {"id": launched["id"], "session": launched["session"], "kind": kind, "prompt": prompt,
              "ticket": ticket, "parent": parent, "launched": stamp(), "verdict": None, "notes": [],
              "relays": [], "remediations": [], "retired": False}

    def change(current):
        if kind == "followup":
            spend(current, bound_key(current, find_launch(current, parent)))
        current["launches"].append(record)
    update(state_path, change)
    return record


def remediate(state_path, session, prompt):
    """Send an instruction back to the ticket's own session (decision 12), within the bound."""
    state = read_json(state_path)
    target = find_launch(state, session)
    spend(state, bound_key(state, target))           # refuse before resuming anything
    resume(state["root"], session, prompt)

    def change(current):
        launch = find_launch(current, session)
        spend(current, bound_key(current, launch))
        launch["remediations"].append({"prompt": prompt, "at": stamp()})
        launch.update(verdict=None, retired=False)
        return {"session": session, "remediations": current["remediations"][bound_key(current, launch)]}
    return update(state_path, change)


def judge(state_path, session, verdict, note):
    require(verdict in VERDICTS, "verdict must be one of " + ", ".join(sorted(VERDICTS)))

    def change(state):
        launch = find_launch(state, session)
        launch["verdict"] = verdict
        launch["notes"].append({"verdict": verdict, "note": note, "at": stamp()})
    update(state_path, change)
    return {"session": session, "verdict": verdict}


def retire(state_path, session):
    """Stop the session after its judgment; it stays listed so the user can still resume it."""
    state = read_json(state_path)
    launch = find_launch(state, session)
    if short_entry(launch["id"]):
        stop(launch["id"])

    def change(current):
        find_launch(current, session)["retired"] = True
    update(state_path, change)
    return {"session": session, "retired": True}


def finish(state_path, status, cause):
    """End the run: remove every retired session, write the terminal status to state and marker."""
    require(status in {"complete", "stopped"}, "finish status is complete or stopped")
    state = read_json(state_path)
    removed = []
    for launch in state["launches"]:
        if launch.get("retired") and short_entry(launch["id"]):
            remove(launch["id"])
            removed.append(launch["id"])
    kept = [l["id"] for l in state["launches"] if not l.get("retired")]
    with state_lock(Path(state_path).with_suffix(".lock"), 5):
        state = read_json(state_path)
        state.update(status=status, cause=cause, finished=stamp())
        atomic_json(state_path, state)
    heartbeat(state, terminal=status)
    return {"status": status, "cause": cause, "removed": removed, "kept": kept}


def emit(result):
    print(json.dumps(result, ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("agents")
    args = parser.parse_args()
    if args.command == "agents":
        return emit({"agents": agents()})
    return 2


if __name__ == "__main__":
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", newline="\n")
    try:
        sys.exit(main())
    except (Invalid, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        sys.exit(2)
