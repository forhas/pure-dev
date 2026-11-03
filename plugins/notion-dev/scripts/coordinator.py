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
from runtime import Invalid, require

# Bounds for the CLI's asynchronous edges, seconds. Module-level so tests can shorten them.
EXIT_WAIT = 30      # stopped process -> exited (fact 13 measured ~1 s)
LIST_WAIT = 10      # rm -> gone from the list
APPEAR_WAIT = 15    # printed id -> listed with its sessionId

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
