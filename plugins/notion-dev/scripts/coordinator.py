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
    if found.lower().endswith((".cmd", ".bat")):
        return shim_target(found)
    return [found]


def shim_target(shim):
    """The program behind an npm `claude.cmd` shim, run directly instead of through cmd.exe.

    cmd.exe re-parses every argument of a .cmd it runs, so `&`, `|`, `^` or `%` in a ticket's
    guidance or a fact's text would execute as commands. An npm shim only forwards `%*` to
    the program it names (`"%dp0%\\node_modules\\...\\bin\\claude.exe"` for current Claude
    Code, a `cli.js` under node for older ones), so run that program with the arguments
    untouched. A shim this cannot read is refused rather than run through cmd.exe.
    """
    refuse = ("claude resolves to " + shim + ", a script cmd.exe would re-parse each prompt through, "
              "and its target could not be read; install the native Claude Code "
              "(https://code.claude.com/docs/en/setup) and put it first on PATH")
    try:
        text = Path(shim).read_text(encoding="utf-8", errors="replace")
    except OSError:
        raise Invalid(refuse)
    targets = re.findall(r'"%dp0%\\([^"%]+)"', text)
    require(targets, refuse)
    target = Path(shim).parent.joinpath(*targets[-1].split("\\")).resolve()
    require(target.is_file(), refuse)
    if target.suffix.lower() == ".exe":
        return [str(target)]
    require(target.suffix.lower() in {".js", ".cjs", ".mjs"}, refuse)
    local = Path(shim).parent / "node.exe"
    node = str(local) if local.is_file() else shutil.which("node")
    require(node, refuse)
    return [node, str(target)]


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
    if not (found and found.get("sessionId", "").startswith(short)):
        stop(short)                     # never leave an unrecorded session running
        remove(short)
        raise Invalid("background session " + short + " is not listed by `claude agents --json --all` "
                      "(stopped and removed it)")
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
    """Remove a session from the list, and fail unless it is actually gone.

    A session still listed would make a later resume fork (fact 10) and a finished run
    report a removal that never happened.
    """
    done = claude("rm", short_id)
    deadline = time.monotonic() + LIST_WAIT
    while short_entry(short_id):
        require(time.monotonic() < deadline, "session " + short_id + " is still listed after `claude rm` (exit " +
                str(done.returncode) + "): " + ANSI.sub("", (done.stderr or done.stdout).strip())[-200:])
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
        # The copy holds the whole run's context and started on the prompt; it runs for the
        # second this takes. Its run ownership checks key on the original id, so it cannot
        # complete the original run in that window.
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


def caller_session(caller=None):
    """The session making this call: explicit, or the host's $NOTION_DEV_SESSION_ID."""
    value = caller or os.environ.get("NOTION_DEV_SESSION_ID", "")
    require(value, "NOTION_DEV_SESSION_ID missing; the SessionStart hook publishes it")
    return value


def own(state, caller=None):
    """Refuse a coordinator session that no longer owns this run, before any side effect.

    Adoption rewrites the marker and the state for the new owner; the old session, resumed
    later (an answer to a question it asked hours ago), must stop rather than drive the epic
    alongside it.
    """
    caller = caller_session(caller)
    marker_path, _ = paths(state["root"], state["epic"])
    marker = read_json(marker_path) if marker_path.is_file() else {}
    require(marker.get("claude_session") == caller and state.get("session") == caller,
            "session " + caller + " no longer owns coordinator-" + state["epic"] + " (now " +
            str(marker.get("claude_session")) + "); stop here")
    return caller


def open_launches(state):
    return [l["session"] for l in state["launches"] if l.get("verdict") is None]


def pending_facts(state):
    """Facts the user accepted whose new-info session was never launched (§A6b).

    The yes is recorded before the coordinator goes back to waiting, so a restart, compaction
    or adoption in between still launches it rather than losing the user's confirmation.
    """
    return [{"session": l["session"], "fact": f["fact"], "run": f.get("run")}
            for l in state["launches"] for f in l.get("facts", [])
            if f.get("verdict") == "accepted" and not f.get("launched")]


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
    agents()                            # claude present and new enough, before anything is written
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
            "open": open_launches(state), "pending_facts": pending_facts(state), "adopted_from": adopted}


def heartbeat(state, caller=None, terminal=None):
    """Rewrite the marker (its mtime is the stop guard's heartbeat); refuse a lost run."""
    caller = caller_session(caller)
    marker_path, _ = paths(state["root"], state["epic"])
    with state_lock(marker_path.with_suffix(".claim.lock"), 5):
        marker = read_json(marker_path)
        require(marker.get("claude_session") == caller,
                "session " + caller + " no longer owns coordinator-" + state["epic"] + " (now " +
                str(marker.get("claude_session")) + "); stop here")
        marker["heartbeat"] = stamp()
        if terminal:
            marker.update(state=terminal, phase=terminal)
        atomic_json(marker_path, marker)


def update(state_path, change, caller=None):
    """Apply `change(state)` under the state lock as its owner, write it, refresh the heartbeat."""
    state_path = Path(state_path)
    with state_lock(state_path.with_suffix(".lock"), 5):
        state = read_json(state_path)
        own(state, caller)
        result = change(state)
        atomic_json(state_path, state)
    heartbeat(state, caller)
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


def record_launch(state_path, kind, prompt, ticket, parent, fact=None):
    """Launch one background session and record it before anything waits on it (§A3.1)."""
    require(kind in KINDS, "launch kind must be one of " + ", ".join(sorted(KINDS)))
    state = read_json(state_path)
    own(state)
    if kind == "followup":
        require(parent, "a follow-up launch names the session it came from")
        spend(state, bound_key(state, find_launch(state, parent)))
    now = stamp()                       # before the spawn, as the resume paths do: a fast session
    launched = launch(state["root"], prompt)   # may save its report before launch() returns
    record = {"id": launched["id"], "session": launched["session"], "kind": kind, "prompt": prompt,
              "ticket": ticket, "parent": parent, "launched": now, "since": now, "verdict": None, "notes": [],
              "relays": [], "remediations": [], "retired": False}

    def change(current):
        if kind == "followup":
            spend(current, bound_key(current, find_launch(current, parent)))
        if fact:                        # the accepted fact this new-info session routes
            for entry in find_launch(current, parent).get("facts", []):
                if entry["fact"] == fact and entry["verdict"] == "accepted" and not entry.get("launched"):
                    entry["launched"] = record["session"]
        current["launches"].append(record)
    update(state_path, change)
    return record


def remediate(state_path, session, prompt):
    """Send an instruction back to the ticket's own session (decision 12), within the bound."""
    state = read_json(state_path)
    own(state)
    target = find_launch(state, session)
    spend(state, bound_key(state, target))           # refuse before resuming anything
    since = stamp()
    resume(state["root"], session, prompt)

    def change(current):
        launch = find_launch(current, session)
        spend(current, bound_key(current, launch))
        launch["remediations"].append({"prompt": prompt, "at": since})
        launch.update(verdict=None, retired=False, since=since)
        return {"session": session, "remediations": current["remediations"][bound_key(current, launch)]}
    return update(state_path, change)


def judge(state_path, session, verdict, note, fact=None, run=None):
    """Record the coordinator's verdict on a launch, or with `fact` its decision on a handed-off fact."""
    require(verdict in VERDICTS, "verdict must be one of " + ", ".join(sorted(VERDICTS)))

    def change(state):
        launch = find_launch(state, session)
        if fact:
            launch.setdefault("facts", []).append({"fact": fact, "verdict": verdict, "note": note, "run": run,
                                                   "launched": None, "at": stamp()})
            return
        launch["verdict"] = verdict
        launch["notes"].append({"verdict": verdict, "note": note, "at": stamp()})
    update(state_path, change)
    return {"session": session, "verdict": verdict, "fact": fact}


def retire(state_path, session):
    """Stop the session after its judgment; it stays listed so the user can still resume it."""
    state = read_json(state_path)
    own(state)
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
    own(state)
    removed = []
    for launch in state["launches"]:
        if launch.get("retired") and short_entry(launch["id"]):
            remove(launch["id"])
            removed.append(launch["id"])
    kept = [l["id"] for l in state["launches"] if not l.get("retired")]
    with state_lock(Path(state_path).with_suffix(".lock"), 5):
        state = read_json(state_path)
        own(state)
        state.update(status=status, cause=cause, finished=stamp())
        atomic_json(state_path, state)
    heartbeat(state, terminal=status)
    return {"status": status, "cause": cause, "removed": removed, "kept": kept}


# ---------------------------------------------------------------- waiting and outcomes

STARTUP_SECONDS = 120   # a just-launched entry lists no status or pid for a few seconds
EXEMPT = {".claude/notion-dev.config.json", ".mcp.json", ".claude/settings.local.json"}  # = workflow.preflight


def report_path(root, session):
    """Where next-task, ticket and finalize save their finished report (decision 10)."""
    from workflow import local_dir
    return local_dir(Path(root)) / "reports" / (safe(session) + ".md")


def run_marker(root, session):
    """The ticket run marker this session owns, never a preflight or coordinator marker."""
    from workflow import local_dir
    found = []
    for path in (local_dir(Path(root)) / "runs").glob("*.json"):
        if path.name.startswith(("preflight-", "coordinator-")):
            continue
        try:
            marker = read_json(path)
        except (OSError, ValueError):
            continue
        if isinstance(marker, dict) and marker.get("claude_session") == session:
            found.append((path.stat().st_mtime, path, marker))
    if not found:
        return None
    _, path, marker = max(found, key=lambda item: item[0])
    return {**marker, "path": str(path)}


def agent_state(found, launched):
    """One word for the entry: busy | idle | blocked | failed | stopped | exited | missing | starting.

    `status` is the settle signal; `state` alone never is (fact 12).
    """
    if found is None:
        return "missing"
    if found.get("state") in {"blocked", "failed", "stopped"}:
        return found["state"]
    if found.get("status") == "waiting":     # a permission prompt or dialog (measured: waitingFor says which)
        return "blocked"
    if found.get("status") in {"busy", "idle"}:
        return found["status"]
    if found.get("state") == "done":
        return "idle"
    return "starting" if age_minutes(launched) * 60 < STARTUP_SECONDS else "exited"


def epoch(value):
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return 0.0


def recording(marker):
    """§A5.5 from the run's own record, not the report: the `record-result.json` that
    `workflow.py record-summary` wrote next to the runtime. `passed: None` means no record."""
    runtime_state = (marker or {}).get("runtime_state")
    if not runtime_state:
        return {"passed": None, "unresolved": [], "source": None}
    source = Path(runtime_state).parent / "record-result.json"
    try:
        result = read_json(source)
    except (OSError, ValueError):
        return {"passed": None, "unresolved": [], "source": str(source)}
    return {"passed": result.get("passed"), "unresolved": result.get("unresolved", []),
            "record": result.get("record", {}), "source": str(source)}


def wait(state_path, session, seconds=540, interval=15):
    """Poll until the session settles or `seconds` pass; keeps the coordinator's marker fresh.

    One bounded slice per call, so the coordinator stays in the foreground and never ends its
    turn while a ticket works (anti-goal). A settled session counts as `done` only with a report
    saved since its latest launch or resume, and a run marker that is not still `running`
    (§A4, Review Focus 4). The startup grace also counts from that latest launch or resume.
    """
    state = read_json(state_path)
    caller = own(state)
    launch = find_launch(state, session)
    since = launch.get("since") or launch["launched"]
    deadline = time.monotonic() + seconds
    while True:
        heartbeat(state, caller)
        word = agent_state(entry(session), since)
        left = deadline - time.monotonic()
        if word not in {"busy", "starting"} or left <= 0:
            break
        time.sleep(min(interval, left))
    report = report_path(state["root"], session)
    marker = run_marker(state["root"], session)
    fresh = report.is_file() and report.stat().st_mtime >= epoch(since) - 1
    settled = word not in {"busy", "starting"}
    finished = fresh and (marker is None or marker.get("state") != "running")
    if not settled:
        outcome = "working"
    elif word == "blocked":
        outcome = "blocked"
    elif finished:
        outcome = "done"
    elif word == "idle":
        outcome = "handback"
    elif word == "failed":
        outcome = "failed"
    else:
        outcome = "stopped"
    if marker and not launch.get("ticket") and marker.get("run"):
        ticket = marker["run"]

        def change(current):
            found = find_launch(current, session)
            moved = current["remediations"].pop(found["session"], 0)
            if moved:
                current["remediations"][ticket] = current["remediations"].get(ticket, 0) + moved
            found["ticket"] = ticket
        update(state_path, change, caller)
    return {"settled": settled, "agent_state": word, "outcome": outcome,
            "report": str(report) if fresh else None, "run_marker": marker,
            "recording": recording(marker)}


def workspace(project, ticket):
    """§A5.6 from git itself: the ticket's worktree and branch are gone, the primary is clean on its base."""
    from workflow import primary
    from runtime import git
    root = primary(project)
    prefix = "ticket/" + ticket + "-"
    branches = git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines()
    trees, current = [], {}
    for line in git(root, "worktree", "list", "--porcelain").splitlines() + [""]:
        if line.startswith("worktree "):
            current = {"path": line[9:]}
        elif line.startswith("branch "):
            current["branch"] = line[len("branch refs/heads/"):]
        elif not line and current:
            trees.append(current)
            current = {}
    owned = lambda name: name == "ticket/" + ticket or name.startswith(prefix)
    config_path = root / ".claude/notion-dev.config.json"
    config = read_json(config_path) if config_path.is_file() else {}
    bases = [b for b in (config.get("git", {}).get(k) for k in ("prTargetBranch", "baseBranch")) if b]
    status = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all", "-z"],
                                     encoding="utf-8")
    dirty = [row for row in status.split("\0") if row and row[3:] not in EXEMPT]
    return {"worktree_gone": not any(owned(t.get("branch", "")) for t in trees[1:]),
            "branch_gone": not any(owned(b) for b in branches),
            "primary_on_base": bool(bases) and git(root, "branch", "--show-current") in bases,
            "primary_clean": not dirty}


# ---------------------------------------------------------------- approval relay

def user_answer(transcript, session, expect, asked_at):
    """The latest parent user row of `session`, typed after `asked_at`, reading exactly `expect`.

    The same row rules as host_capture.user_approval: never an assistant, sidechain, meta,
    compact-summary or tool-result row. An AskUserQuestion answer is a tool result, so the
    coordinator asks in plain text and the user types the answer.
    """
    from host_capture import timestamp
    found = None
    with Path(transcript).open("rb") as stream:
        for raw in stream:
            if not raw.endswith(b"\n"):
                break
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            if (row.get("type") != "user" or row.get("sessionId") != session or row.get("isSidechain")
                    or row.get("isMeta") or row.get("isCompactSummary") or row.get("toolUseResult") is not None):
                continue
            message = row.get("message", {})
            content = message.get("content")
            if isinstance(content, list):
                if not all(isinstance(c, dict) and c.get("type") == "text" for c in content):
                    continue
                content = "\n".join(c.get("text", "") for c in content)
            if message.get("role") != "user" or not isinstance(content, str) or content.strip() != expect.strip():
                continue
            try:
                when = timestamp(row["timestamp"])
            except (KeyError, TypeError, ValueError):
                continue
            if when >= asked_at and isinstance(row.get("uuid"), str) and row["uuid"]:
                found = {"uuid": row["uuid"], "text": content.strip(), "at": row["timestamp"]}
    return found


def relay(state_path, session, phrase, transcript, coordinator_session, asked_at):
    """Send the user's explicit approval, as the exact phrase, into the owning session (§A6a).

    The phrase lands as a user message in the ticket's own session, which is what its approval
    capture requires. Only a phrase the user typed, verbatim, is ever sent: the answer is matched
    against the phrase itself, so nothing the user did not type can cross into the ticket. A
    relay is not a remediation and does not spend the bound.
    """
    state = read_json(state_path)
    require(not state.get("non_interactive"), "a --non-interactive coordinator never relays an approval; "
            "stop with the cause and the session to attach to")
    require(coordinator_session and coordinator_session == state.get("session"),
            "the answer must come from this coordinator's own session (" + str(state.get("session")) + ")")
    own(state, coordinator_session)
    require(transcript and Path(transcript).is_file(), "the coordinator's transcript is unavailable "
            "($NOTION_DEV_TRANSCRIPT); a relay needs the user's answer as a transcript row")
    find_launch(state, session)
    answer = user_answer(transcript, coordinator_session, phrase, asked_at)
    require(answer, "no matching user answer typed after the question; relay only what the user typed, never a "
            "composed approval")
    since = stamp()
    resume(state["root"], session, phrase)

    def change(current):
        find_launch(current, session)["since"] = since
        find_launch(current, session)["relays"].append(
            {"phrase": phrase, "user_message": answer["uuid"], "user_text": answer["text"],
             "answered": answer["at"], "at": stamp()})
    update(state_path, change, coordinator_session)
    return {"session": session, "relayed": phrase, "user_message": answer["uuid"]}


# ---------------------------------------------------------------- reports

CLOSEOUT_KEYS = ("TAILS-FOUND", "RESOLVED", "TRACKED", "BLOCKED", "PASSES")
FIELD = re.compile(r"^([A-Z][A-Z0-9-]+):[ \t]*(.*?)\s*$")
SEPARATOR = re.compile(r"\s+[—-]\s+")   # the plugin writes an em dash; tolerate a hyphen


def report_view(text):
    """The open items a finished report declares, in the formats the plugin writes.

    `OUTCOME:`; the session-closeout block and its `- tracked:` / `- blocked:` lines; record.md's
    `NEW-INFO:` block. `problems` lists everything the coordinator must treat as an open item
    on the report's own evidence: a missing OUTCOME or CLOSEOUT, a count that disagrees with
    its lines, a tracked item without a URL, a blocked item without its unblocker, and any
    outcome field (KNOWLEDGE-DELTA, EPIC-BRIEF, ...) reading failed or unknown.
    """
    lines = (text or "").replace("\r\n", "\n").split("\n")
    view = {"outcome": None, "closeout": None, "tracked": [], "blocked": [], "facts": [],
            "fields": {}, "problems": []}
    counts, fact, in_facts = {}, None, False
    for raw in lines:
        line = raw.rstrip()
        if in_facts:
            if line.startswith("- fact:"):
                fact = {"fact": line[len("- fact:"):].strip(), "evidence": None, "epics": None,
                        "route": None, "run": None}
                view["facts"].append(fact)
                continue
            if fact is not None and raw[:1] in {" ", "\t"} and ":" in line:
                key, _, value = line.strip().partition(":")
                if key in {"evidence", "epics", "route", "run"}:
                    fact[key] = value.strip()
                    continue
            in_facts = False
        field = FIELD.match(line)
        if field:
            key, value = field.groups()
            if key == "OUTCOME":
                view["outcome"] = value
            elif key == "NEW-INFO":
                in_facts, fact = value.lower() != "none", None
            elif key == "CLOSEOUT":
                view["closeout"] = {}
            elif key in CLOSEOUT_KEYS and view["closeout"] is not None:
                counts[key] = int(value) if value.isdigit() else value
            else:
                view["fields"][key] = value
            continue
        if line.startswith("- tracked:"):
            body = line[len("- tracked:"):].strip()
            linked = re.match(r"(.*?)\s+[—-]\s+([a-z][a-z0-9+.-]*://\S+)$", body)
            item, url = linked.groups() if linked else (body, None)
            view["tracked"].append({"item": item, "url": url})
            if not url:
                view["problems"].append("tracked item without a URL: " + body)
        elif line.startswith("- blocked:"):
            body = line[len("- blocked:"):].strip()
            parts = SEPARATOR.split(body, maxsplit=1)
            cause, sep, unblock = (parts[1] if len(parts) > 1 else "").partition("; unblocked by ")
            view["blocked"].append({"item": parts[0], "cause": cause.strip(), "unblock": unblock.strip()})
            if not sep or not cause.strip() or not unblock.strip():
                view["problems"].append("blocked item without its external cause and `unblocked by`: " + body)
    if view["outcome"] is None:
        view["problems"].insert(0, "no OUTCOME line: the report is not a finished ticket report")
    if view["closeout"] is None:
        view["problems"].append("no CLOSEOUT block: the session-closeout never ran")
    else:
        view["closeout"] = {key: counts.get(key) for key in CLOSEOUT_KEYS}
        # session-closeout's contract: every key present as a count, PASSES 1 or 2, and every
        # tail found is resolved, tracked or blocked — there is no fourth state.
        bad = [key for key in CLOSEOUT_KEYS if not isinstance(counts.get(key), int)]
        for key in bad:
            view["problems"].append("CLOSEOUT " + key + ": " + ("missing" if key not in counts else
                                    "not a count: " + str(counts[key])))
        if "PASSES" not in bad and counts["PASSES"] not in (1, 2):
            view["problems"].append("CLOSEOUT PASSES: " + str(counts["PASSES"]) + " — the closeout runs once or twice")
        if not {"TAILS-FOUND", "RESOLVED", "TRACKED", "BLOCKED"} & set(bad):
            total = counts["RESOLVED"] + counts["TRACKED"] + counts["BLOCKED"]
            if counts["TAILS-FOUND"] != total:
                view["problems"].append("CLOSEOUT TAILS-FOUND: " + str(counts["TAILS-FOUND"]) + " but RESOLVED + "
                                        "TRACKED + BLOCKED = " + str(total))
        for key, listed in (("TRACKED", view["tracked"]), ("BLOCKED", view["blocked"])):
            if counts.get(key) != len(listed):
                view["problems"].append("CLOSEOUT " + key + ": " + str(counts.get(key)) + " but " +
                                        str(len(listed)) + " " + key.lower() + " line(s)")
    for key, value in view["fields"].items():
        if re.match(r"(failed|unknown)\b", value, re.I):
            view["problems"].append(key + ": " + value)
    return view


def emit(result):
    print(json.dumps(result, ensure_ascii=False))
    return 0


def main():
    session = os.environ.get("NOTION_DEV_SESSION_ID", "")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("agents", help="the CLI's background-session list")
    commands.add_parser("now", help="epoch seconds, for relay --asked-at")
    p = commands.add_parser("start"); p.add_argument("--project", default="."); p.add_argument("--epic", required=True)
    p.add_argument("--session", default=session); p.add_argument("--non-interactive", action="store_true")
    p = commands.add_parser("launch"); p.add_argument("--state", required=True); p.add_argument("--prompt", required=True)
    p.add_argument("--kind", required=True, choices=sorted(KINDS)); p.add_argument("--ticket"); p.add_argument("--parent")
    p.add_argument("--fact", help="new-info: the accepted fact this launch routes")
    p = commands.add_parser("wait"); p.add_argument("--state", required=True); p.add_argument("--session", required=True)
    p.add_argument("--seconds", type=int, default=540); p.add_argument("--interval", type=int, default=15)
    p = commands.add_parser("report-view"); p.add_argument("--report", required=True)
    p = commands.add_parser("workspace"); p.add_argument("--project", default="."); p.add_argument("--ticket", required=True)
    p = commands.add_parser("remediate"); p.add_argument("--state", required=True); p.add_argument("--session", required=True)
    p.add_argument("--prompt", required=True)
    p = commands.add_parser("relay"); p.add_argument("--state", required=True); p.add_argument("--session", required=True)
    p.add_argument("--phrase", required=True)
    p.add_argument("--asked-at", type=float, required=True)
    p.add_argument("--transcript", default=os.environ.get("NOTION_DEV_TRANSCRIPT", ""))
    p.add_argument("--coordinator-session", default=session)
    p = commands.add_parser("judge"); p.add_argument("--state", required=True); p.add_argument("--session", required=True)
    p.add_argument("--verdict", required=True, choices=sorted(VERDICTS)); p.add_argument("--note", default="")
    p.add_argument("--fact", help="record a decision on this handed-off fact instead of the launch's verdict")
    p.add_argument("--run", help="with --fact and --verdict accepted: the fact's run: line, launched later")
    p = commands.add_parser("retire"); p.add_argument("--state", required=True); p.add_argument("--session", required=True)
    p = commands.add_parser("finish"); p.add_argument("--state", required=True)
    p.add_argument("--status", required=True, choices=["complete", "stopped"]); p.add_argument("--cause")
    args = parser.parse_args()
    if args.command == "agents":
        return emit({"agents": agents()})
    if args.command == "now":
        return emit({"epoch": time.time()})
    if args.command == "start":
        return emit(start(args.project, args.epic, args.session, args.non_interactive))
    if args.command == "launch":
        return emit(record_launch(args.state, args.kind, args.prompt, args.ticket, args.parent, args.fact))
    if args.command == "wait":
        result = wait(args.state, args.session, args.seconds, args.interval)
        emit(result)
        return 0 if result["settled"] else 1
    if args.command == "report-view":
        return emit(report_view(Path(args.report).read_text(encoding="utf-8")))
    if args.command == "workspace":
        return emit(workspace(args.project, args.ticket))
    if args.command == "remediate":
        return emit(remediate(args.state, args.session, args.prompt))
    if args.command == "relay":
        return emit(relay(args.state, args.session, args.phrase, args.transcript,
                          args.coordinator_session, args.asked_at))
    if args.command == "judge":
        return emit(judge(args.state, args.session, args.verdict, args.note, args.fact, args.run))
    if args.command == "retire":
        return emit(retire(args.state, args.session))
    return emit(finish(args.state, args.status, args.cause))


if __name__ == "__main__":
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", newline="\n")
    try:
        sys.exit(main())
    except (Invalid, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        sys.exit(2)
