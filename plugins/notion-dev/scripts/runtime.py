#!/usr/bin/env python3
"""Local lifecycle/evidence guards. No provider calls, merge, or agent spawning.

Use the interpreter configured by knowledge.python. State is per invocation, not
per ticket. Consumers use the CLI, never edit the state file. Exit 1 is a closed
gate/pending wait; exit 2 is invalid input or an operational error.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


_BASH_EXE = None


def _wsl_stub(path):
    """True when `path` is the System32 WSL launcher rather than a real bash.

    Resolved against %SystemRoot% rather than a hard-coded `C:\\Windows`, because the
    Windows directory is not always on C:.
    """
    try:
        root = os.environ.get("SystemRoot") or os.environ.get("windir") or "C:\\Windows"
        system32 = os.path.normcase(os.path.join(os.path.abspath(root), "system32"))
        return os.path.normcase(os.path.abspath(path)).startswith(system32 + os.sep)
    except (OSError, ValueError):
        return False


def bash_exe():
    """Resolve `bash` once; never spawn the bare name.

    Windows `CreateProcess` — what `subprocess.run` uses with `shell=False` — searches
    `System32` BEFORE `PATH`, so a bare `"bash"` resolves to the WSL launcher stub at
    `C:\\Windows\\System32\\bash.exe` rather than the Git for Windows bash this plugin
    requires. With no WSL distribution installed that stub exits 1 without running the
    command, which this module would otherwise record as a failed verification rather
    than as a missing interpreter.

    `shutil.which` searches `PATH` in order instead, which is the whole fix wherever
    `PATH` is sane. Where it still lands in System32, walk `PATH` for a `bash.exe` that
    is not the stub before falling back to the Git for Windows roots: that install is
    routinely per-user, portable, or placed by scoop/choco, and none of those live under
    a `Program Files` root. The rejected stub is never retained as the fallback — a bare
    `"bash"` fails visibly, where the stub fails as a command that silently did not run.

    On POSIX the whole function is a no-op: `shutil.which("bash")` returns exactly what
    `"bash"` alone would resolve to.
    """
    global _BASH_EXE
    if _BASH_EXE is None:
        found = shutil.which("bash")
        if os.name == "nt" and (not found or _wsl_stub(found)):
            found = None
            directories = [entry for entry in os.environ.get("PATH", "").split(os.pathsep) if entry]
            directories += [os.path.join(base, "Git", "bin") for base in
                            (os.environ.get("PROGRAMW6432"), os.environ.get("PROGRAMFILES"),
                             os.environ.get("PROGRAMFILES(X86)")) if base]
            for directory in directories:
                candidate = os.path.join(directory, "bash.exe")
                try:
                    usable = not _wsl_stub(candidate) and os.path.isfile(candidate)
                except (OSError, ValueError):
                    continue
                if usable:
                    found = candidate
                    break
        _BASH_EXE = found or "bash"
    return _BASH_EXE


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".runtime-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # Windows readers/scanners can briefly hold the destination open.
        for attempt in range(5):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Clock:
    def stamp(self):
        return {"utc": datetime.now(timezone.utc).isoformat(),
                "wall": time.time(), "mono": time.monotonic()}


def elapsed(start, now):
    monotonic = now["mono"] - start["mono"]
    wall = now["wall"] - start["wall"]
    # Across a reboot or a material clock adjustment, do not infer a timeout.
    if monotonic < 0 or abs(monotonic - wall) > 60:
        return None
    return round(monotonic, 3)


def git(worktree, *args):
    return subprocess.check_output(["git", "-C", str(worktree), *args],
                                   encoding="utf-8", stderr=subprocess.PIPE).strip()


def revision(worktree):
    """Includes unstaged/staged and untracked code; never treats HEAD alone as tree."""
    root = Path(worktree).resolve()
    head = git(root, "rev-parse", "HEAD")
    diff = subprocess.check_output(["git", "-C", str(root), "diff", "--no-ext-diff", "--no-textconv", "HEAD", "--binary"])
    untracked = []
    names = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard", "-z"]
    ).decode("utf-8").split("\0")
    for name in sorted(n for n in names if n):
        path = root / name
        symlink = path.is_symlink()
        content = os.readlink(path).encode("utf-8") if symlink else path.read_bytes()
        untracked.append({"path": name, "kind": "symlink" if symlink else "file",
                          "executable": bool(path.lstat().st_mode & stat.S_IXUSR),
                          "sha256": hashlib.sha256(content).hexdigest()})
    manifest = {"head": head, "diff_sha256": hashlib.sha256(diff).hexdigest(), "untracked": untracked}
    fingerprint = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode("utf-8")).hexdigest()
    return {"worktree": str(root), "head": head, "fingerprint": fingerprint}


class Runtime:
    def __init__(self, path, clock=None):
        self.path = Path(path).resolve()
        self.clock = clock or Clock()

    @contextmanager
    def transaction(self, create=False):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix(".lock")
        deadline = time.monotonic() + 5
        while True:
            try:
                lock.mkdir()
                break
            except FileExistsError:
                require(time.monotonic() < deadline,
                        "runtime lock busy; inspect its owner before recovery, never break it automatically")
                time.sleep(0.05)
        try:
            if self.path.exists():
                state = read_json(self.path)
                require(state.get("schema") == 1, "unsupported runtime schema")
            else:
                require(create, "runtime state missing; initialize this invocation first")
                state = {}
            original = json.dumps(state, sort_keys=True)
            yield state
            if json.dumps(state, sort_keys=True) != original:
                atomic_json(self.path, state)
        finally:
            lock.rmdir()

    def event(self, state, kind, **values):
        event = {"seq": len(state["events"]) + 1, "kind": kind,
                 "stage": state.get("stage"), **self.clock.stamp(), **values}
        state["events"].append(event)
        return event

    def init(self, run, ticket):
        with self.transaction(create=True) as state:
            if state:
                require(state["run"] == run and state["ticket"] == ticket,
                        "state belongs to a different invocation")
                return {"state": str(self.path), "run": run, "resumed": True}
            state.update(schema=1, run=run, ticket=ticket, stage=None, events=[],
                         workers={}, requirements=None, awaiting_worker=None)
            self.event(state, "run_started")
        return {"state": str(self.path), "run": run, "resumed": False}

    def stage(self, name):
        require(bool(name.strip()), "stage name required")
        with self.transaction() as state:
            if state["stage"] != name:
                if state["stage"]:
                    self.event(state, "stage_ended")
                state["stage"] = name
                self.event(state, "stage_started")
        return {"stage": name}

    def requirements(self, source, inventory):
        source = Path(source).resolve()
        text = source.read_text(encoding="utf-8")
        require(isinstance(inventory, dict), "requirements inventory must be an object")
        require(inventory.get("source_sha256") == digest(source), "inventory source hash mismatch")
        require(inventory.get("reviewed_whole_ticket") is True,
                "review the whole ticket, including prerequisites outside the acceptance section")
        items = inventory.get("items")
        require(isinstance(items, list) and items, "requirements inventory must not be empty")
        seen = set()
        for item in items:
            require(isinstance(item, dict), "requirement items must be objects")
            key = item.get("id")
            require(isinstance(key, str) and key.strip() and key not in seen, "unique requirement ID required")
            seen.add(key)
            require(item.get("kind") in {"requirement", "acceptance", "prerequisite", "constraint"},
                    "invalid requirement kind")
            require(isinstance(item.get("text"), str) and item["text"].strip()
                    and item["text"] in text, "requirement must quote the source verbatim")
            require(item.get("readiness") in {"ready", "unknown", "blocked"}, "invalid readiness")
            if item["kind"] == "prerequisite" and item["readiness"] == "ready":
                require(isinstance(item.get("evidence"), str) and item["evidence"].strip(),
                        "a satisfied prerequisite needs evidence, not an assumption")
        stored = {**inventory, "source": str(source)}
        with self.transaction() as state:
            state["requirements"] = stored
            self.event(state, "requirements_recorded", count=len(items), source_sha256=digest(source))
        return {"requirements": len(items), "source_sha256": digest(source)}

    @staticmethod
    def readiness(state):
        inventory = state["requirements"]
        if not inventory:
            return ["requirements inventory missing"]
        if digest(inventory["source"]) != inventory["source_sha256"]:
            return ["ticket source changed; refresh requirements and review"]
        return [f"{item['id']}: {item['readiness']}" for item in inventory["items"]
                if item["readiness"] != "ready"]

    def ready(self):
        with self.transaction() as state:
            reasons = self.readiness(state)
            self.event(state, "readiness_checked", passed=not reasons)
        return {"passed": not reasons, "reasons": reasons}

    def prepare(self, role, files, worktree=None, timeout=900):
        require(role in {"plan", "scout", "local-review", "completeness", "record"}, "invalid worker role")
        require(math.isfinite(timeout) and 0 < timeout <= (2700 if role == "record" else 900),
                "timeout must be positive and within the role's bound")
        snapshots = {name: {"path": str(Path(path).resolve()), "sha256": digest(path)}
                     for name, path in files.items()}
        require(bool(snapshots), "at least one input artifact is required")
        require(role not in {"plan", "local-review", "completeness"} or worktree,
                "review workers require a worktree revision")
        current = revision(worktree) if worktree else None
        with self.transaction() as state:
            require(role != "completeness" or not self.readiness(state), "completeness requires ready requirements")
            require(not any(w["role"] == role and w["status"] != "consumed" and not w["terminated"]
                            for w in state["workers"].values()),
                    "previous worker in this role must be consumed or confirmed terminated before replacement")
            key = uuid.uuid4().hex
            worker = {"id": key, "role": role, "status": "pending", "agent_id": None,
                      "started": self.clock.stamp(), "timeout_seconds": timeout,
                      "files": snapshots, "revision": current, "result": None,
                      "terminated": False, "requirements": state["requirements"]}
            state["workers"][key] = worker
            self.event(state, "worker_prepared", worker=key, role=role)
        return {"worker": key, "state": str(self.path), "role": role,
                "timeout_seconds": timeout, "revision": current, "files": snapshots,
                "requirements": worker["requirements"]}

    @staticmethod
    def worker(state, key):
        require(key in state["workers"], "unknown worker ID")
        return state["workers"][key]

    def attach(self, key, agent_id):
        require(bool(agent_id.strip()), "actual host agent ID required")
        with self.transaction() as state:
            worker = self.worker(state, key)
            require(worker["agent_id"] in {None, agent_id}, "worker already bound to a different agent")
            require(all(w["id"] == key or w["agent_id"] != agent_id for w in state["workers"].values()),
                    "one host agent cannot impersonate multiple fresh workers")
            worker["agent_id"] = agent_id
            if worker["status"] == "pending":
                worker["status"] = "running"
            self.event(state, "worker_attached", worker=key, agent_id=agent_id)
        return {"worker": key, "status": worker["status"]}

    def publish(self, key, result):
        require(isinstance(result, dict) and isinstance(result.get("report"), str)
                and result["report"].strip(), "result requires a nonempty report, not a launch acknowledgement")
        with self.transaction() as state:
            worker = self.worker(state, key)
            require(not worker["terminated"], "worker was confirmed terminated; reconcile late output explicitly")
            if worker["result"] is not None:
                require(worker["result"] == result, "result is immutable; create a new attempt for a revision")
                return {"worker": key, "status": worker["status"]}
            require(worker["status"] in {"pending", "running", "timed_out", "cancellation_requested"},
                    "worker cannot publish in its current state")
            worker.update(result=result, status="result_ready", result_ready=self.clock.stamp())
            self.event(state, "worker_result_ready", worker=key)
        return {"worker": key, "status": "result_ready"}

    def inspect(self, key):
        with self.transaction() as state:
            worker = self.worker(state, key)
            duration = elapsed(worker["started"], self.clock.stamp())
            if worker["status"] in {"pending", "running"} and duration is not None and duration >= worker["timeout_seconds"]:
                worker["status"] = "timed_out"
                self.event(state, "worker_timed_out", worker=key)
            return {"worker": key, "status": worker["status"], "elapsed_seconds": duration,
                    "clock_uncertain": duration is None, "terminated": worker["terminated"],
                    "result_available": worker["result"] is not None}

    def wait(self, key, seconds=30):
        require(math.isfinite(seconds) and 0 <= seconds <= 60, "one wait must be between 0 and 60 seconds")
        deadline = time.monotonic() + seconds
        while True:
            result = self.inspect(key)
            if result["clock_uncertain"] or result["status"] not in {"pending", "running"} or time.monotonic() >= deadline:
                return result
            time.sleep(min(0.25, max(0, deadline - time.monotonic())))

    def consume(self, key):
        with self.transaction() as state:
            worker = self.worker(state, key)
            require(worker["agent_id"], "attach the actual host agent before consuming its result")
            require(worker["status"] in {"result_ready", "consumed"}, "no completed result to consume")
            if worker["status"] != "consumed":
                worker["status"] = "consumed"
                self.event(state, "worker_result_consumed", worker=key,
                           delivery_lag_seconds=elapsed(worker["result_ready"], self.clock.stamp()))
            if state["awaiting_worker"] == key:
                state["awaiting_worker"] = None
        return {"worker": key, "status": "consumed", "result": worker["result"]}

    def end_worker(self, key, reason, confirmed=False, host_failed=False, user_requested=False, invalid_result=False):
        require(bool(reason.strip()), "a termination reason is required")
        observed = self.inspect(key)
        require(observed["status"] in {"timed_out", "cancellation_requested", "cancelled", "failed"}
                or host_failed or user_requested or (invalid_result and observed["status"] == "consumed"),
                "deadline has not elapsed; only an actual host failure or explicit user cancellation can end early")
        with self.transaction() as state:
            worker = self.worker(state, key)
            require(worker["status"] != "result_ready", "consume the available result before terminating")
            worker["status"] = ("failed" if host_failed or invalid_result else "cancelled") if confirmed else "cancellation_requested"
            worker["terminated"] = confirmed
            self.event(state, "worker_termination", worker=key, confirmed=confirmed, reason=reason)
        return {"worker": key, "status": worker["status"], "safe_to_replace": confirmed}

    def resolve_citations(self, key, citations):
        require(isinstance(citations, list), "citation resolutions must be a list")
        resolved = []
        for citation in citations:
            path = Path(citation["artifact"]).resolve()
            quote = citation.get("quote")
            require(isinstance(quote, str) and quote.strip() and quote in path.read_text(encoding="utf-8"),
                    "citation quote must resolve in its actual evidence artifact")
            resolved.append({"id": citation["id"], "artifact": str(path),
                             "quote": quote, "sha256": digest(path)})
        with self.transaction() as state:
            worker = self.worker(state, key)
            require(worker["role"] == "completeness" and worker["status"] == "consumed",
                    "resolve citations only after consuming independent completeness")
            expected = {item["id"] for item in worker["requirements"]["items"]}
            require(len(resolved) == len(expected) and {c["id"] for c in resolved} == expected,
                    "resolve every requirement exactly once")
            worker["citation_resolutions"] = resolved
            self.event(state, "citations_resolved", worker=key, count=len(resolved))
        return {"worker": key, "resolved": len(resolved)}

    def yield_once(self, key, marker, session):
        """One owned, short-lived permission for the Stop hook to deliver mailbox events."""
        marker = Path(marker).resolve()
        body = read_json(marker)
        require(session and body.get("claude_session") == session and body.get("state") == "running",
                "yield marker must be live and owned by this Claude session")
        with self.transaction() as state:
            worker = self.worker(state, key)
            require(worker["status"] in {"pending", "running", "result_ready"}, "worker is not awaiting delivery")
            state["awaiting_worker"] = key
            self.event(state, "worker_yield", worker=key)
        safe = lambda value: re.sub(r"[^A-Za-z0-9._-]", "_", value)
        permit = marker.parent / f".awaiting-worker-{safe(marker.stem)}--{safe(session)}"
        atomic_json(permit, {"worker": key, "runtime": str(self.path)})
        return {"awaiting_worker": key, "permit": str(permit), "complete": False}

    def merge_gate(self, key, worktree):
        current = revision(worktree)
        with self.transaction() as state:
            worker = self.worker(state, key)
            reasons = self.readiness(state)
            if worker["role"] != "completeness" or worker["status"] != "consumed":
                reasons.append("independent completeness result has not been consumed")
            if worker["revision"] != current:
                reasons.append("reviewed worktree/head/content changed")
            if worker["requirements"] != state["requirements"]:
                reasons.append("requirements inventory changed since review")
            for name, source in worker["files"].items():
                if digest(source["path"]) != source["sha256"]:
                    reasons.append(f"review input changed: {name}")
            result = worker["result"] or {}
            if result.get("requirements_complete") is not True:
                reasons.append("independent full-source requirement coverage was not confirmed")
            verdicts = result.get("requirements", [])
            expected = {item["id"] for item in (state["requirements"] or {}).get("items", [])}
            resolutions = worker.get("citation_resolutions", [])
            if len(resolutions) != len(expected) or {c["id"] for c in resolutions} != expected:
                reasons.append("parent citation resolution is incomplete")
            for citation in resolutions:
                if digest(citation["artifact"]) != citation["sha256"]:
                    reasons.append(f"resolved evidence changed: {citation['id']}")
            require(isinstance(verdicts, list), "invalid requirement verdicts")
            ids = [v.get("id") for v in verdicts if isinstance(v, dict)]
            if set(ids) != expected or len(ids) != len(expected):
                reasons.append("verdicts must cover every requirement exactly once")
            for verdict in verdicts:
                if (not isinstance(verdict, dict) or verdict.get("verdict") != "met"
                        or not isinstance(verdict.get("citation"), str) or not verdict["citation"].strip()):
                    reasons.append("mandatory requirement unmet, unverified, or missing citation")
            report = result.get("report", "")
            def header(field):
                values = re.findall(r"^" + re.escape(field) + r":[ \t]*([^\r\n]*)$", report, re.M)
                return values[0].strip() if len(values) == 1 else None
            if header("COMPLETENESS") not in {"clean", "blocked"}:
                reasons.append("completeness report missing or degraded")
            for field in ("CRITERIA-NOT-MET", "CRITERIA-UNVERIFIED"):
                if header(field) != "0":
                    reasons.append(f"{field} must be zero")
            total = sum(item["kind"] == "acceptance" for item in (state["requirements"] or {}).get("items", []))
            for field in ("CRITERIA-TOTAL", "CRITERIA-MET"):
                if header(field) != str(total):
                    reasons.append(f"{field} must match the acceptance inventory ({total})")
            if result.get("blocking_findings") != []:
                reasons.append("blocking claims/caveats unresolved or not checked")
            pending = [w["id"] for w in state["workers"].values()
                       if w["id"] != key and w["status"] != "consumed" and not w["terminated"]]
            if pending:
                reasons.append("other worker results or termination outcomes remain outstanding")
            self.event(state, "merge_gate_checked", passed=not reasons, worker=key, head=current["head"])
        return {"passed": not reasons, "reasons": reasons, "head": current["head"]}

    def verify(self, worktree, command):
        before = revision(worktree)
        key = uuid.uuid4().hex
        log = self.path.parent / f"verify-{key}.log"
        command_hash = hashlib.sha256(command.encode("utf-8")).hexdigest()
        started = self.clock.stamp()
        with self.transaction() as state:
            self.event(state, "verification_started", verification=key,
                       command_sha256=command_hash, revision=before, log=str(log))
        with log.open("wb") as output:
            process = subprocess.run([bash_exe(), "-e", "-o", "pipefail", "-c", command],
                                     cwd=worktree, stdout=output, stderr=subprocess.STDOUT)
        receipt = {"verification": key, "exit_code": process.returncode, "log": str(log),
                   "duration_seconds": elapsed(started, self.clock.stamp()),
                   "command_sha256": command_hash, "revision": before,
                   "changed_during_verification": revision(worktree) != before}
        with self.transaction() as state:
            self.event(state, "verification_finished", **receipt)
        return receipt

    def summary(self):
        with self.transaction() as state:
            workers = [{k: w[k] for k in ("id", "role", "status", "agent_id", "terminated")}
                       for w in state["workers"].values()]
            tests = [e for e in state["events"] if e["kind"] == "verification_finished"]
            signatures = [(e["command_sha256"], e["revision"]["fingerprint"]) for e in tests]
            spans, starts = [], {}
            for event in state["events"]:
                if event["kind"] == "stage_started":
                    starts[event["stage"]] = event
                elif event["kind"] == "stage_ended" and event["stage"] in starts:
                    spans.append({"stage": event["stage"],
                                  "seconds": elapsed(starts.pop(event["stage"]), event)})
            return {"run": state["run"], "stage": state["stage"], "workers": workers,
                    "stage_spans": spans, "open_stages": list(starts),
                    "verification_runs": len(tests),
                    "repeated_verification_signatures": len(signatures) - len(set(signatures)),
                    "delivery_lags": [e for e in state["events"] if e["kind"] == "worker_result_consumed"],
                    "model_usage": "unknown until raw telemetry is imported; never inferred from characters"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, help="per-invocation state.json outside disposable worktrees")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("init"); p.add_argument("--run", required=True); p.add_argument("--ticket", required=True)
    p = commands.add_parser("stage"); p.add_argument("name")
    p = commands.add_parser("requirements"); p.add_argument("--source", required=True); p.add_argument("--inventory", required=True)
    commands.add_parser("ready")
    p = commands.add_parser("prepare"); p.add_argument("--role", required=True); p.add_argument("--file", action="append", default=[])
    p.add_argument("--worktree"); p.add_argument("--timeout", type=float, default=900)
    for name in ("attach", "publish", "inspect", "wait", "consume", "resolve-citations", "end-worker", "yield", "merge-gate"):
        p = commands.add_parser(name); p.add_argument("--worker", required=True)
        if name == "attach": p.add_argument("--agent", required=True)
        if name == "publish": p.add_argument("--result", required=True)
        if name == "resolve-citations": p.add_argument("--citations", required=True)
        if name == "wait": p.add_argument("--seconds", type=float, default=30)
        if name == "end-worker":
            p.add_argument("--reason", required=True); p.add_argument("--confirmed", action="store_true")
            p.add_argument("--host-failed", action="store_true"); p.add_argument("--user-requested", action="store_true")
            p.add_argument("--invalid-result", action="store_true")
        if name == "yield": p.add_argument("--marker", required=True); p.add_argument("--session", required=True)
        if name == "merge-gate": p.add_argument("--worktree", required=True)
    p = commands.add_parser("verify"); p.add_argument("--worktree", required=True); p.add_argument("--shell-command", required=True)
    commands.add_parser("summary")
    args = parser.parse_args()
    runtime = Runtime(args.state)
    name = args.command
    if name == "init": result = runtime.init(args.run, args.ticket)
    elif name == "stage": result = runtime.stage(args.name)
    elif name == "requirements": result = runtime.requirements(args.source, read_json(args.inventory))
    elif name == "ready": result = runtime.ready()
    elif name == "prepare":
        files = {}
        for item in args.file:
            require("=" in item, "--file must be name=path")
            key, path = item.split("=", 1)
            require(key and key not in files, "unique artifact name required")
            files[key] = path
        result = runtime.prepare(args.role, files, args.worktree, args.timeout)
    elif name == "attach": result = runtime.attach(args.worker, args.agent)
    elif name == "publish": result = runtime.publish(args.worker, read_json(args.result))
    elif name == "inspect": result = runtime.inspect(args.worker)
    elif name == "wait": result = runtime.wait(args.worker, args.seconds)
    elif name == "consume": result = runtime.consume(args.worker)
    elif name == "resolve-citations": result = runtime.resolve_citations(args.worker, read_json(args.citations))
    elif name == "end-worker": result = runtime.end_worker(args.worker, args.reason, args.confirmed, args.host_failed, args.user_requested, args.invalid_result)
    elif name == "yield": result = runtime.yield_once(args.worker, args.marker, args.session)
    elif name == "merge-gate": result = runtime.merge_gate(args.worker, args.worktree)
    elif name == "verify": result = runtime.verify(args.worktree, args.shell_command)
    else: result = runtime.summary()
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    if result.get("passed") is False or (name == "wait" and result["status"] not in {"result_ready", "consumed"}):
        return 1
    if name == "verify" and (result["exit_code"] != 0 or result["changed_during_verification"]):
        return 1
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", newline="\n")
    try:
        sys.exit(main())
    except (Invalid, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        sys.exit(2)
