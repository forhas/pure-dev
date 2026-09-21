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
    return {"worktree": str(root), "head": head, "fingerprint": fingerprint,
            "clean": not diff and not untracked}


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

    def prepare(self, role, files, worktree=None, timeout=900, previous=None, slot=None):
        require(role in {"plan", "scout", "implementation", "branch-review", "local-review",
                         "completeness", "record"}, "invalid worker role")
        require(slot is None or (role in {"implementation", "scout", "plan", "local-review", "branch-review"}
                                and isinstance(slot, str) and slot.strip()),
                "only build-flow workers may have a stable task/review slot")
        require(previous is None or role == "completeness", "only completeness supports delta review")
        require(math.isfinite(timeout) and 0 < timeout <= (2700 if role == "record" else 900),
                "timeout must be positive and within the role's bound")
        snapshots = {name: {"path": str(Path(path).resolve()), "sha256": digest(path)}
                     for name, path in files.items()}
        require(bool(snapshots), "at least one input artifact is required")
        require(role not in {"plan", "implementation", "branch-review", "local-review", "completeness"} or worktree,
                "review workers require a worktree revision")
        current = revision(worktree) if worktree else None
        with self.transaction() as state:
            require(role != "completeness" or not self.readiness(state), "completeness requires ready requirements")
            # CONSUMPTION IS NOT ACCEPTANCE, and conflating them reopened the exact race
            # this protocol exists to close. A contract-invalid report must be consumed
            # BEFORE it can be judged -- `end_worker(--invalid-result)` is itself gated on
            # `status == "consumed"` -- so a predicate that reads `consumed` as "finished"
            # lets a rejected worker be replaced while it may still be running, with no
            # confirmed termination anywhere. For `record`, that is two live workers with
            # provider side effects.
            #
            # So a worker is replaceable on exactly two positive signals, never on the
            # absence of one: it was ACCEPTED (the parent judged its result valid) or it
            # was CONFIRMED TERMINATED. Fail closed -- a caller that forgets is stopped
            # here and told which of the two to record, rather than silently permitted.
            require(not any(w["role"] == role and (not slot or not w.get("slot") or w["slot"] == slot)
                            and not w["terminated"] and not w.get("accepted")
                            for w in state["workers"].values()),
                    "previous worker in this role must be accepted or confirmed terminated "
                    "before replacement; consuming a result is not accepting it")
            key = uuid.uuid4().hex
            directory = self.path.parent / ("worker-" + key)
            delta = self.delta_manifest(state, previous, current, snapshots) if previous else None
            # Owned snapshots preserve old PR claims/evidence without transporting them
            # through every parent/tool response. Artifact names are never used as paths.
            for index, source in enumerate(snapshots.values()):
                saved = directory / ("input-" + str(index))
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source["path"], saved)
                require(digest(saved) == source["sha256"], "input changed during preparation")
                source["snapshot"] = str(saved)
            inventory_path = directory / "requirements.json"
            atomic_json(inventory_path, state["requirements"])
            packet = {"worker": key, "role": role, "slot": slot, "revision": current,
                      "inputs": snapshots, "requirements": {"path": str(inventory_path),
                      "sha256": digest(inventory_path)}}
            if delta is not None:
                patch_path = directory / "changes.patch"
                patch_path.write_bytes(delta.pop("patch"))
                delta["patch"] = {"path": str(patch_path), "sha256": digest(patch_path),
                                  "bytes": patch_path.stat().st_size}
                delta_path = directory / "delta.json"
                atomic_json(delta_path, delta)
                packet["delta"] = {"path": str(delta_path), "sha256": digest(delta_path)}
            packet_path = directory / "context.json"
            atomic_json(packet_path, packet)
            worker = {"id": key, "role": role, "status": "pending", "agent_id": None,
                      "started": self.clock.stamp(), "timeout_seconds": timeout,
                      "files": snapshots, "revision": current, "result": None,
                      "terminated": False, "accepted": False,
                      "requirements": state["requirements"], "slot": slot,
                      "packet": str(packet_path), "packet_sha256": digest(packet_path),
                      "inventory_snapshot": packet["requirements"], "previous": previous,
                      "delta": packet.get("delta")}
            state["workers"][key] = worker
            self.event(state, "worker_prepared", worker=key, role=role)
        return {"worker": key, "state": str(self.path), "role": role,
                "timeout_seconds": timeout, "revision": current, "packet": str(packet_path)}

    def delta_manifest(self, state, previous, current, snapshots):
        baseline = self.worker(state, previous)
        reviews = [w for w in state["workers"].values() if w["role"] == "completeness"]
        require(reviews and reviews[-1]["id"] == previous and baseline.get("accepted")
                and baseline["status"] == "consumed", "delta requires the latest accepted completeness result")
        require(sum(bool(w.get("previous")) for w in reviews) < 2, "delta attempt budget exhausted")
        require(baseline["requirements"] == state["requirements"],
                "changed requirements require a full review")
        self.validate_packet(baseline)
        require(not baseline.get("previous") or (baseline["result"] or {}).get("delta_review", {}).get(
            "disposition") == "sufficient", "escalated delta requires a full review")
        old = baseline["revision"]
        require(old and old.get("clean") and current and current.get("clean")
                and old["worktree"] == current["worktree"], "delta needs clean committed trees in the same worktree")
        expected = {item["id"] for item in state["requirements"]["items"]}
        verdicts = (baseline["result"] or {}).get("requirements", [])
        require(baseline["result"].get("requirements_complete") is True
                and len(verdicts) == len(expected)
                and {v.get("id") for v in verdicts if isinstance(v, dict)} == expected,
                "baseline must cover all requirements; missing coverage requires a full review")
        args = ["git", "-C", current["worktree"], "diff", "--no-ext-diff", "--no-textconv",
                "--no-renames", old["head"], current["head"]]
        names = subprocess.check_output(args + ["--name-only", "-z"]).decode("utf-8").split("\0")
        patch_bytes = subprocess.check_output(args + ["--binary"])
        old_inputs = baseline["files"]
        changed = [name for name in sorted(set(old_inputs) | set(snapshots))
                   if {k: old_inputs.get(name, {}).get(k) for k in ("path", "sha256")}
                   != {k: snapshots.get(name, {}).get(k) for k in ("path", "sha256")}]
        resolutions = baseline.get("citation_resolutions", [])
        changed_evidence = [c["id"] for c in resolutions if not Path(c["artifact"]).is_file()
                            or digest(c["artifact"]) != c["sha256"]]
        return {"previous": previous, "before": old, "after": current,
                "changed_paths": [n for n in names if n], "patch": patch_bytes,
                "changed_inputs": changed, "before_inputs": old_inputs, "after_inputs": snapshots,
                "changed_evidence_ids": changed_evidence,
                "unresolved_evidence_ids": sorted(expected - {c["id"] for c in resolutions}),
                "previous_result": baseline["result"], "previous_citations": resolutions,
                "instruction": "Check indirect effects for EVERY requirement, claims and caveats. "
                "Unchanged bytes are not proof of unchanged behavior. Escalate if scope is not bounded."}

    @staticmethod
    def validate_packet(worker):
        # Legacy full reviews can still be consumed, but cannot provide delta history.
        if not worker.get("packet"):
            return
        require(digest(worker["packet"]) == worker["packet_sha256"], "context packet changed")
        inventory = worker["inventory_snapshot"]
        require(digest(inventory["path"]) == inventory["sha256"], "requirement snapshot changed")

    @staticmethod
    def validate_delta(worker, result):
        if not worker.get("previous"):
            return
        delta = result.get("delta_review")
        expected = {item["id"] for item in worker["requirements"]["items"]}
        require(isinstance(delta, dict) and delta.get("previous") == worker["previous"]
                and delta.get("manifest_sha256") == worker["delta"]["sha256"]
                and digest(worker["delta"]["path"]) == worker["delta"]["sha256"],
                "delta review must identify the exact baseline and unchanged manifest")
        checked = delta.get("checked_requirement_ids")
        require(isinstance(checked, list) and len(checked) == len(expected)
                and all(isinstance(key, str) for key in checked) and set(checked) == expected,
                "delta review must check indirect impact on every requirement")
        require(delta.get("disposition") in {"sufficient", "full-review-required"},
                "delta review must assess whether its scope is sufficient")
        manifest = read_json(worker["delta"]["path"])
        require(digest(manifest["patch"]["path"]) == manifest["patch"]["sha256"],
                "delta patch changed")
        for inputs in (manifest["before_inputs"], manifest["after_inputs"]):
            for source in inputs.values():
                require(source.get("snapshot") and digest(source["snapshot"]) == source["sha256"],
                        "delta input snapshot changed or missing; require a full review")

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
            self.validate_packet(worker)
            self.validate_delta(worker, result)
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
                    "accepted": worker.get("accepted", False),
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

    def accept(self, key):
        """Record that the parent judged this worker's result valid.

        The counterpart to `end-worker --invalid-result`: together they are the only two
        exits from `consumed`, and `prepare` refuses a same-role replacement until one of
        them has been taken. Acceptance is deliberately a separate call from `consume`,
        because the contract can only be judged after the result has been read.
        """
        with self.transaction() as state:
            worker = self.worker(state, key)
            require(not worker["terminated"],
                    "a confirmed-terminated worker's result is not acceptable")
            require(worker["status"] == "consumed",
                    "consume the result before accepting it")
            if not worker["accepted"]:
                worker["accepted"] = True
                self.event(state, "worker_result_accepted", worker=key, role=worker["role"])
        return {"worker": key, "status": worker["status"], "accepted": True}

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
            self.validate_packet(worker)
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
                if source.get("snapshot") and digest(source["snapshot"]) != source["sha256"]:
                    reasons.append(f"review snapshot changed: {name}")
            result = worker["result"] or {}
            if worker.get("previous"):
                self.validate_delta(worker, result)
                if result["delta_review"]["disposition"] != "sufficient":
                    reasons.append("delta reviewer requires full review")
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
            # Same two positive signals as `prepare`: a consumed-but-unjudged worker is an
            # outstanding outcome, not an accounted-for one.
            pending = [w["id"] for w in state["workers"].values()
                       if w["id"] != key and not w["terminated"] and not w.get("accepted")]
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
                    "full_completeness_attempts": sum(w["role"] == "completeness" and not w.get("previous")
                                                       for w in state["workers"].values()),
                    "delta_attempts": sum(bool(w.get("previous")) for w in state["workers"].values()),
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
    p.add_argument("--previous"); p.add_argument("--slot")
    for name in ("attach", "publish", "inspect", "wait", "consume", "accept", "resolve-citations", "end-worker", "yield", "merge-gate"):
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
        result = runtime.prepare(args.role, files, args.worktree, args.timeout, args.previous, args.slot)
    elif name == "attach": result = runtime.attach(args.worker, args.agent)
    elif name == "publish": result = runtime.publish(args.worker, read_json(args.result))
    elif name == "inspect": result = runtime.inspect(args.worker)
    elif name == "wait": result = runtime.wait(args.worker, args.seconds)
    elif name == "consume": result = runtime.consume(args.worker)
    elif name == "accept": result = runtime.accept(args.worker)
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
