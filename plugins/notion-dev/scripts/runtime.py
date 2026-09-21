#!/usr/bin/env python3
"""Local lifecycle/evidence guards. No provider calls, merge, or agent spawning.

Use the interpreter configured by knowledge.python. State is per invocation, not
per ticket. Consumers use the CLI, never edit the state file. Exit 1 is a closed
gate/pending wait; exit 2 is invalid input or an operational error.
"""
import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import errno
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


SCHEMA = 2
SCHEMAS = (1, SCHEMA)

# A delta index is read by a fresh reviewer as its first act, so it is a table of
# contents, not the material. Lists that do not fit are paged out to a side file and
# marked incomplete rather than silently cut; INDEX_BYTES is the budget that decides.
INDEX_BYTES = 2048
PAGE_ITEMS = 50

RECORD_OUTCOMES = ("planned", "attempted", "confirmed", "unknown-outcome", "failed")


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


def digest_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def environment_signature():
    """Hash of the toolchain facts a verification receipt actually depends on.

    Deliberately NOT the environment: dumping `os.environ` into durable state would
    put credentials in a file that travels with the run, and would also invalidate
    every receipt on an unrelated variable. These four are what decides whether the
    same command on the same tree can produce the same result, and none is a secret.
    """
    facts = {"os_name": os.name, "platform": sys.platform,
             "python": "%d.%d" % sys.version_info[:2],
             "shell": os.path.basename(bash_exe())}
    return {"signature": digest_bytes(json.dumps(facts, sort_keys=True).encode("utf-8")), **facts}


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


def try_state_lock(descriptor):
    """Nonblocking kernel lock. Closing the descriptor (including process death) releases it."""
    if os.name == "nt":
        import msvcrt
        os.lseek(descriptor, 0, os.SEEK_SET)
        # Windows permits a locked region beyond EOF; no pre-lock write is needed.
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


@contextmanager
def state_lock(path, timeout):
    require(not path.is_dir(), "legacy runtime lock directory has no recorded owner; "
            "confirm all old runtime processes are stopped before retiring this empty directory")
    require(not path.is_symlink(), "runtime lock must not be a symlink")
    descriptor = os.open(str(path), os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o600)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                try_state_lock(descriptor)
                break
            except OSError as error:
                if error.errno not in {errno.EACCES, errno.EAGAIN}:
                    raise
                require(time.monotonic() < deadline,
                        "runtime OS-managed lock is held by another process; retry after it exits; "
                        "never delete the lock file")
                time.sleep(0.05)
        yield
    finally:
        # Keep the file/inode: unlinking permits waiters to lock different files.
        os.close(descriptor)


class Runtime:
    def __init__(self, path, clock=None, lock_timeout=5):
        self.path = Path(path).resolve()
        self.clock = clock or Clock()
        require(math.isfinite(lock_timeout) and lock_timeout > 0, "positive lock timeout required")
        self.lock_timeout = lock_timeout

    @contextmanager
    def transaction(self, create=False):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with state_lock(self.path.with_suffix(".lock"), self.lock_timeout):
            if self.path.exists():
                state = read_json(self.path)
                # Schema 1 runs stay schema 1: an in-flight invocation is never force-
                # rewritten into the new version. The additive records below are read
                # through `setdefault`, so a schema 1 state gains them only when this
                # runtime actually writes one, and an old binary still accepts it.
                require(state.get("schema") in SCHEMAS, "unsupported runtime schema")
                for key, empty in (("verifications", []), ("record_journal", [])):
                    state.setdefault(key, empty)
            else:
                require(create, "runtime state missing; initialize this invocation first")
                state = {}
            original = json.dumps(state, sort_keys=True)
            yield state
            if json.dumps(state, sort_keys=True) != original:
                atomic_json(self.path, state)

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
            state.update(schema=SCHEMA, run=run, ticket=ticket, stage=None, events=[],
                         workers={}, requirements=None, awaiting_worker=None,
                         verifications=[], record_journal=[])
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

    def correction_needed(self, worktree, reason=None):
        """Register BEFORE post-round edits. A repeated call cannot erase their history."""
        current = revision(worktree)
        with self.transaction() as state:
            if state.get("correction"):
                require(state["correction"]["before"]["worktree"] == current["worktree"],
                        "correction belongs to a different worktree")
                # The first registration owns the baseline; later ones only add their
                # cause, so a second correction cannot quietly restate why the first ran.
                if reason and reason not in state["correction"].setdefault("reasons", []):
                    state["correction"]["reasons"].append(reason)
                    self.event(state, "correction_cause", correction=state["correction"]["id"],
                               reason=reason)
                return state["correction"]
            require(current["clean"], "register correction before editing a clean committed worktree")
            state["correction"] = {"id": uuid.uuid4().hex, "before": current,
                                   "reasons": [reason] if reason else []}
            self.event(state, "correction_needed", correction=state["correction"]["id"],
                       revision=current, reason=reason)
            return state["correction"]

    @staticmethod
    def correction_manifest(obligation, current):
        before = obligation["before"]
        require(current["clean"] and before["worktree"] == current["worktree"],
                "correction review requires the same clean committed worktree")
        args = ["git", "-C", current["worktree"], "diff", "--no-ext-diff", "--no-textconv",
                "--no-renames", before["head"], current["head"]]
        names = subprocess.check_output(args + ["--name-only", "-z"]).decode("utf-8").split("\0")
        return {"id": obligation["id"], "before": before, "after": current,
                "changed_paths": [name for name in names if name],
                "patch": subprocess.check_output(args + ["--binary"])}

    def prepare(self, role, files, worktree=None, timeout=900, previous=None, slot=None):
        require(role in {"plan", "scout", "implementation", "branch-review", "local-review",
                         "completeness", "record", "probe"}, "invalid worker role")
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
            # Validate the delta BEFORE writing anything: a rejected preparation must
            # not leave half a packet on disk under an unregistered worker directory.
            baseline = self.delta_baseline(state, previous, current) if previous else None
            correction = state.get("correction") if role == "completeness" else None
            correction_manifest = self.correction_manifest(correction, current) if correction else None
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
            input_bytes = sum(Path(s["path"]).stat().st_size for s in snapshots.values())
            packet = {"worker": key, "role": role, "slot": slot, "revision": current,
                      "inputs": snapshots, "requirements": {"path": str(inventory_path),
                      "sha256": digest(inventory_path)}}
            if baseline is not None:
                delta_path = directory / "delta.json"
                atomic_json(delta_path, self.delta_index(baseline, current, snapshots, directory))
                packet["delta"] = {"path": str(delta_path), "sha256": digest(delta_path),
                                   "bytes": delta_path.stat().st_size}
            if correction_manifest is not None:
                patch_path = directory / "correction.patch"
                patch_path.write_bytes(correction_manifest.pop("patch"))
                correction_manifest["patch"] = {"path": str(patch_path), "sha256": digest(patch_path),
                                                "bytes": patch_path.stat().st_size}
                manifest_path = directory / "correction.json"
                atomic_json(manifest_path, correction_manifest)
                packet["correction_manifest"] = {"path": str(manifest_path), "sha256": digest(manifest_path)}
            packet_path = directory / "context.json"
            atomic_json(packet_path, packet)
            worker = {"id": key, "role": role, "status": "pending", "agent_id": None,
                      "started": self.clock.stamp(), "timeout_seconds": timeout,
                      "files": snapshots, "revision": current, "result": None,
                      "terminated": False, "accepted": False,
                      "requirements": state["requirements"], "slot": slot,
                      "packet": str(packet_path), "packet_sha256": digest(packet_path),
                      "inventory_snapshot": packet["requirements"], "previous": previous,
                      "delta": packet.get("delta"), "correction": correction,
                      "correction_manifest": packet.get("correction_manifest")}
            state["workers"][key] = worker
            self.event(state, "worker_prepared", worker=key, role=role,
                       input_bytes=input_bytes, packet_bytes=packet_path.stat().st_size,
                       delta_bytes=(packet.get("delta") or {}).get("bytes"))
        return {"worker": key, "state": str(self.path), "role": role,
                "timeout_seconds": timeout, "revision": current, "packet": str(packet_path)}

    def delta_baseline(self, state, previous, current):
        baseline = self.worker(state, previous)
        reviews = [w for w in state["workers"].values() if w["role"] == "completeness"]
        # A CONFIRMED-TERMINATED attempt is spent, not a baseline. Reading it as "the latest
        # completeness result" strands the second attempt the budget below still grants: after the
        # documented `end-worker --confirmed` recovery, naming the last accepted worker failed this
        # predicate while naming the dead one failed `accepted`, so the two-attempt budget only ever
        # worked when attempt one succeeded. Only `terminated` is skipped -- a running or
        # result_ready worker is still the latest and still blocks a delta, so this is not a way
        # past an in-flight review, and the budget below counts every attempt including the dead one.
        live = [w for w in reviews if not w["terminated"]]
        require(live and live[-1]["id"] == previous and baseline.get("accepted")
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
        return {"worker": baseline, "previous": previous, "before": old,
                "changed_paths": [n for n in names if n],
                "patch_bytes": subprocess.check_output(args + ["--binary"])}

    @staticmethod
    def bound_index(index, sections, budget=INDEX_BYTES, page=PAGE_ITEMS):
        """Inline what fits; page out the rest and SAY SO.

        The reviewer's first read must be a table of contents, not the material —
        the previous manifest inlined the entire prior report, so every "incremental"
        review began by re-reading the full one. But a quietly cut list is worse than
        a long one: it reads as complete. So each section carries its true count and a
        `complete` flag, the whole list stays retrievable by page, and when even the
        first pages do not fit, `within_budget` says that rather than cutting further.
        """
        size = lambda: len(json.dumps(index, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        # One counts map and one list of truncated names, not a metadata object per
        # section: at six sections that ceremony cost more of the budget than the
        # content it described. `pages` is ceil(count / page_items); `section` returns it.
        incomplete = []
        index["sections"] = {"page_items": page, "incomplete": incomplete,
                             "counts": {name: len(items) for name, items in sections.items()}}
        for name, items in sections.items():
            index[name] = list(items)
        # Shrink the LARGEST inlined list, repeatedly, so one wide change does not cost
        # every small section its detail. First cut is to one page; after that it halves,
        # because a fixed page can still exceed the budget on its own. The inlined list
        # stays a PREFIX of page 1, and `incomplete` names every list that was cut, so a
        # short preview is never mistakable for the whole section.
        while size() > budget:
            name = max(sections, key=lambda n: (len(index[n]), n))
            length = len(index[name])
            if length == 0:
                break
            index[name] = index[name][:min(page, length // 2)]
            if len(index[name]) != len(sections[name]) and name not in incomplete:
                incomplete.append(name)
        # Measured BEFORE these three keys are added, so the number is exact rather than
        # a figure that changes the thing it measures. They add well under 100 bytes.
        index["content_bytes"] = size()
        index["within_budget"] = index["content_bytes"] <= budget
        index["complete"] = not incomplete
        return index

    def delta_index(self, baseline, current, snapshots, directory):
        """The compact change/reuse index a delta reviewer reads first."""
        worker = baseline["worker"]
        old_inputs = worker["files"]
        changed_inputs = [name for name in sorted(set(old_inputs) | set(snapshots))
                          if {k: old_inputs.get(name, {}).get(k) for k in ("path", "sha256")}
                          != {k: snapshots.get(name, {}).get(k) for k in ("path", "sha256")}]
        records = self.evidence_records(worker, baseline["changed_paths"])
        buckets = {"reuse_applicable": [], "recheck_needed": [], "blocked": [], "unresolved": []}
        for record in records:
            buckets[{"current": "reuse_applicable", "stale": "recheck_needed",
                     "blocked": "blocked", "unresolved": "unresolved"}[record["applicability"]]
                    ].append(record["id"])

        # Artifacts are named RELATIVE to one `directory`, and the two revisions share
        # one `worktree`, because an index whose fixed overhead is six absolute paths
        # spends its whole budget before listing anything. Resolve with `ref_path`.
        def side(name, value, raw=False):
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if raw:
                path.write_bytes(value)
            else:
                atomic_json(path, value)
            return {"file": name, "sha256": digest(path), "bytes": path.stat().st_size}

        sections = {"changed_paths": baseline["changed_paths"], "changed_inputs": changed_inputs}
        sections.update(buckets)
        index = {"previous": baseline["previous"], "worktree": current["worktree"],
                 "directory": str(directory),
                 "before": {k: baseline["before"][k] for k in ("head", "fingerprint", "clean")},
                 "after": {k: current[k] for k in ("head", "fingerprint", "clean")},
                 "patch": side("changes.patch", baseline["patch_bytes"], raw=True),
                 "inputs": side("delta-inputs.json", {"before": old_inputs, "after": snapshots}),
                 "previous_report": side("previous-report.json", worker["result"]),
                 "sections_file": side("delta-sections.json", sections),
                 "evidence": dict({"index": side("evidence-index.json", records),
                                   "requirements": len(records)},
                                  **{k: len(v) for k, v in buckets.items()}),
                 "instruction": "Read only what this index references. Reuse-applicable is a "
                 "candidate, not a verdict. Check indirect effects on EVERY requirement."}
        return self.bound_index(index, sections)

    @staticmethod
    def ref_path(index, reference):
        """Absolute path of one artifact the delta index names relative to its directory."""
        return str(Path(index["directory"]) / reference["file"])

    def section(self, key, name, page=1):
        """Retrieve one page of a delta section the index could not inline."""
        require(isinstance(page, int) and page >= 1, "section pages are 1-based")
        with self.transaction() as state:
            worker = self.worker(state, key)
            reference = worker.get("delta")
            require(bool(reference), "only a delta worker has paged sections")
            require(digest(reference["path"]) == reference["sha256"], "delta index changed")
            index = read_json(reference["path"])
            source = self.ref_path(index, index["sections_file"])
            require(digest(source) == index["sections_file"]["sha256"], "delta sections changed")
            sections = read_json(source)
            require(name in sections, "unknown delta section: " + name)
            items = sections[name]
            size = index["sections"]["page_items"]
            pages = max(1, -(-len(items) // size))
            require(page <= pages, "section page is past the end")
            self.event(state, "delta_section_read", worker=key, section=name, page=page)
        return {"worker": key, "section": name, "page": page, "pages": pages,
                "count": len(items), "items": items[(page - 1) * size:page * size],
                "complete": page == pages}

    @staticmethod
    def validate_packet(worker):
        # Legacy full reviews can still be consumed, but cannot provide delta history.
        if not worker.get("packet"):
            return
        require(digest(worker["packet"]) == worker["packet_sha256"], "context packet changed")
        inventory = worker["inventory_snapshot"]
        require(digest(inventory["path"]) == inventory["sha256"], "requirement snapshot changed")
        correction = worker.get("correction_manifest")
        if correction:
            require(digest(correction["path"]) == correction["sha256"], "correction manifest changed")
            patch = read_json(correction["path"])["patch"]
            require(digest(patch["path"]) == patch["sha256"], "correction patch changed")

    @staticmethod
    def correction_reviewed(state, worker, result):
        if state.get("correction") != worker.get("correction"):
            return False
        if not state.get("correction"):
            return True
        review = result.get("correction_review")
        if not isinstance(review, dict) or not isinstance(review.get("report"), str):
            return False
        verdicts = re.findall(r"^VERDICT:[ \t]*([^\r\n]*)$", review["report"], re.M)
        return (review.get("id") == worker["correction"]["id"]
                and review.get("manifest_sha256") == worker["correction_manifest"]["sha256"]
                and review.get("verdict") == "clean" and review.get("blocking_findings") == []
                and len(verdicts) == 1 and verdicts[0].strip() == "CLEAN")

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
        # Every artifact the index merely REFERENCES is hash-bound here, because moving
        # the bulk out of the index moved the tampering surface out with it.
        for reference, message in ([(manifest[n], m) for n, m in
                                    (("patch", "delta patch changed"),
                                     ("inputs", "delta input index changed"),
                                     ("sections_file", "delta sections changed"),
                                     ("previous_report", "previous report changed"))] +
                                   [(manifest["evidence"]["index"], "evidence index changed")]):
            require(digest(Runtime.ref_path(manifest, reference)) == reference["sha256"], message)
        inputs = read_json(Runtime.ref_path(manifest, manifest["inputs"]))
        for group in (inputs["before"], inputs["after"]):
            for source in group.values():
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
            # Sizes, not bodies. Knowing a report arrived at 40KB is what identifies
            # prose duplicated into both `report` and the per-criterion records; copying
            # the prose here to measure it would be the same mistake one layer down.
            self.event(state, "worker_result_ready", worker=key, role=worker["role"],
                       result_bytes=len(json.dumps(result, ensure_ascii=False).encode("utf-8")),
                       report_bytes=len(result["report"].encode("utf-8")))
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
        """Ingest evidence PER ITEM, and keep what is still missing visible.

        This used to be all-or-nothing: a report that cited eight of ten requirements
        resolved none of them, so the next delta was built against an empty evidence
        set and its reviewer had nothing to reuse — it re-investigated everything
        while being billed as an incremental pass. Recording the eight, and naming
        the two, is what makes a narrow delta narrow.

        Partial ingestion is not a partial gate. `merge_gate` still requires every
        requirement resolved, unchanged, so the only thing this relaxes is when the
        evidence becomes durable — never whether it is eventually complete.
        """
        require(isinstance(citations, list), "citation resolutions must be a list")
        incoming = {}
        for citation in citations:
            require(isinstance(citation, dict), "each citation resolution must be an object")
            key_id = citation.get("id")
            require(isinstance(key_id, str) and key_id.strip() and key_id not in incoming,
                    "resolve each requirement at most once per call")
            path = Path(citation["artifact"]).resolve()
            quote = citation.get("quote")
            require(isinstance(quote, str) and quote.strip() and quote in path.read_text(encoding="utf-8"),
                    "citation quote must resolve in its actual evidence artifact")
            dependencies = citation.get("depends_on") or []
            require(isinstance(dependencies, list), "depends_on must be a list of paths")
            recorded = []
            for dependency in dependencies:
                # Byte equality of the cited artifact proves the RECEIPT is intact, not
                # that what it describes still holds. Naming the sources a receipt
                # depends on is how a changed helper invalidates a verdict whose own
                # quoted log never changed.
                source = Path(dependency).resolve()
                require(source.is_file(), "evidence dependency must be an existing file")
                recorded.append({"path": str(source), "sha256": digest(source)})
            incoming[key_id] = {"id": key_id, "artifact": str(path), "quote": quote,
                                "sha256": digest(path), "depends_on": recorded,
                                "recorded": self.clock.stamp()["utc"]}
        with self.transaction() as state:
            worker = self.worker(state, key)
            require(worker["role"] == "completeness" and worker["status"] == "consumed",
                    "resolve citations only after consuming independent completeness")
            expected = [item["id"] for item in worker["requirements"]["items"]]
            unknown = sorted(set(incoming) - set(expected))
            require(not unknown, "citation resolves an unknown requirement: " + ", ".join(unknown))
            existing = {c["id"]: c for c in worker.get("citation_resolutions", [])}
            replaced = sorted(set(incoming) & set(existing))
            existing.update(incoming)
            worker["citation_resolutions"] = [existing[i] for i in expected if i in existing]
            unresolved = [i for i in expected if i not in existing]
            self.event(state, "citations_resolved", worker=key, count=len(incoming),
                       replaced=len(replaced), resolved_total=len(existing),
                       unresolved=len(unresolved))
        return {"worker": key, "resolved": len(existing), "accepted_now": len(incoming),
                "replaced": replaced, "unresolved": unresolved,
                "required": len(expected), "complete": not unresolved,
                "passed": not unresolved}

    @staticmethod
    def evidence_records(worker, changed_paths=()):
        """Per-requirement applicability: `current`, `stale`, `blocked`, or `unresolved`.

        Four states, not two, because "reusable" and "present" are different questions
        and collapsing them is how a stale receipt gets a pass. A requirement the
        baseline itself could not verify is `blocked` however intact its bytes are.
        """
        expected = [item["id"] for item in worker["requirements"]["items"]]
        cited = {c["id"]: c for c in worker.get("citation_resolutions", [])}
        verdicts = {v.get("id"): v.get("verdict") for v in (worker.get("result") or {}).get("requirements", [])
                    if isinstance(v, dict)}
        worktree = (worker.get("revision") or {}).get("worktree")
        touched = set()
        for name in changed_paths:
            if worktree:
                touched.add(str((Path(worktree) / name).resolve()))
        records = []
        for item in expected:
            citation = cited.get(item)
            if citation is None:
                records.append({"id": item, "applicability": "unresolved",
                                "reasons": ["no evidence recorded for this requirement"]})
                continue
            reasons = []
            verdict = verdicts.get(item)
            if verdict is not None and verdict != "met":
                reasons.append("baseline verdict is '%s', not 'met'" % verdict)
            blocked = bool(reasons)
            for label, path, expected_hash in \
                    [("evidence artifact", citation["artifact"], citation["sha256"])] + \
                    [("dependency " + d["path"], d["path"], d["sha256"])
                     for d in citation.get("depends_on", [])]:
                source = Path(path)
                if not source.is_file():
                    reasons.append(label + " is missing")
                elif digest(source) != expected_hash:
                    reasons.append(label + " changed since it was recorded")
                elif str(source.resolve()) in touched:
                    reasons.append(label + " is inside this change's diff")
            records.append({"id": item, "artifact": citation["artifact"],
                            "applicability": "blocked" if blocked else
                                             ("stale" if reasons else "current"),
                            "reasons": reasons})
        return records

    def evidence(self, key):
        records = None
        with self.transaction() as state:
            worker = self.worker(state, key)
            records = self.evidence_records(worker)
            counts = Counter(r["applicability"] for r in records)
            self.event(state, "evidence_indexed", worker=key, **{k: counts[k] for k in
                       ("current", "stale", "blocked", "unresolved")})
        buckets = {name: [r["id"] for r in records if r["applicability"] == state_name]
                   for name, state_name in (("reuse_applicable", "current"), ("recheck_needed", "stale"),
                                            ("blocked", "blocked"), ("unresolved", "unresolved"))}
        return {"worker": key, "items": records, "count": len(records),
                "complete": not buckets["unresolved"], "passed": not buckets["unresolved"],
                **buckets}

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
            if not self.correction_reviewed(state, worker, result):
                reasons.append("corrective code needs an independent clean correction review of the exact manifest")
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
                if not Path(citation["artifact"]).is_file():
                    reasons.append(f"resolved evidence is missing: {citation['id']}")
                elif digest(citation["artifact"]) != citation["sha256"]:
                    reasons.append(f"resolved evidence changed: {citation['id']}")
                # A receipt whose own bytes are intact can still have stopped describing
                # the code: the cited log does not change when the helper it exercised
                # does. Declared dependencies are where that shows up.
                for dependency in citation.get("depends_on", []):
                    if not Path(dependency["path"]).is_file():
                        reasons.append(f"evidence dependency is missing: {citation['id']}")
                    elif digest(dependency["path"]) != dependency["sha256"]:
                        reasons.append(f"evidence dependency changed: {citation['id']}")
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

    @staticmethod
    def receipt_applicable(receipt, revision_now, signature):
        """Why a stored receipt may or may not stand in for running the command again.

        Byte equality of a log establishes that the receipt is intact, never that it
        still describes the current tree — so the revision fingerprint, which includes
        dirty and untracked content, and the toolchain signature are both part of the
        answer. A receipt whose command modified the tree is not reusable at all: it
        never described a state that survived its own run.
        """
        reasons = []
        # The fingerprint covers tracked and untracked content, but `revision` builds it
        # with `--exclude-standard`, so IGNORED files are invisible to it — and two
        # worktrees at the same commit routinely differ in exactly those: local config,
        # installed dependencies, this plugin's own state directory. A `--shell-command`
        # is arbitrary and may read any of them, or `$PWD` itself, so a receipt earned in
        # worktree A can be handed back in worktree B for a command that would fail there.
        # `delta_baseline` and `merge_gate` already require the same worktree; this one
        # did not, and it is the only one of the three that skips real work on the answer.
        if receipt["revision"].get("worktree") != revision_now["worktree"]:
            reasons.append("receipt was produced in a different worktree")
        if receipt["revision"]["fingerprint"] != revision_now["fingerprint"]:
            reasons.append("revision changed since this receipt")
        if receipt.get("environment", {}).get("signature") != signature["signature"]:
            reasons.append("toolchain signature changed or unrecorded")
        if receipt.get("changed_during_verification"):
            reasons.append("the command modified the tree it verified")
        log = Path(receipt["log"])
        if not log.is_file():
            reasons.append("verification log is missing")
        elif receipt.get("log_sha256") and digest(log) != receipt["log_sha256"]:
            reasons.append("verification log changed after the run")
        return reasons

    def verifications(self, worktree=None):
        """Index of every command receipt, with why each is or is not reusable now."""
        current = revision(worktree) if worktree else None
        signature = environment_signature()
        with self.transaction() as state:
            items = []
            for receipt in state.get("verifications", []):
                reasons = self.receipt_applicable(receipt, current, signature) if current else \
                    ["applicability needs a worktree"]
                # `{**a, **b}`, not `a | b`: the merge operator is 3.9 and this plugin
                # supports 3.8. verify-python-floor.sh is a smoke filter that does not
                # see this form, so the floor job is what would have caught it.
                items.append({**{k: receipt.get(k) for k in
                                 ("verification", "command_sha256", "exit_code",
                                  "duration_seconds", "log", "log_sha256")},
                              "revision": receipt["revision"]["fingerprint"],
                              "environment": receipt.get("environment", {}).get("signature"),
                              "started": receipt.get("started", {}).get("utc"),
                              "applicable": not reasons, "reasons": reasons})
            self.event(state, "verification_indexed", count=len(items))
        return {"verifications": items, "count": len(items),
                "environment": signature,
                "coverage": "receipts recorded by this runtime only; a command run outside it "
                            "leaves no receipt and is unknown, never passed"}

    def verify(self, worktree, command, reuse=False):
        before = revision(worktree)
        signature = environment_signature()
        command_hash = digest_bytes(command.encode("utf-8"))
        if reuse:
            with self.transaction() as state:
                for receipt in reversed(state.get("verifications", [])):
                    if receipt["command_sha256"] != command_hash or receipt["exit_code"] != 0:
                        continue
                    if self.receipt_applicable(receipt, before, signature):
                        continue
                    self.event(state, "verification_reused", verification=receipt["verification"],
                               command_sha256=command_hash)
                    return {**receipt, "reused": True}
        key = uuid.uuid4().hex
        log = self.path.parent / f"verify-{key}.log"
        started = self.clock.stamp()
        with self.transaction() as state:
            self.event(state, "verification_started", verification=key,
                       command_sha256=command_hash, revision=before, log=str(log))
        with log.open("wb") as output:
            process = subprocess.run([bash_exe(), "-e", "-o", "pipefail", "-c", command],
                                     cwd=worktree, stdout=output, stderr=subprocess.STDOUT)
        receipt = {"verification": key, "exit_code": process.returncode, "log": str(log),
                   "log_sha256": digest(log), "log_bytes": log.stat().st_size,
                   "duration_seconds": elapsed(started, self.clock.stamp()),
                   "command_sha256": command_hash, "revision": before,
                   "environment": signature, "started": started,
                   "changed_during_verification": revision(worktree) != before}
        with self.transaction() as state:
            state.setdefault("verifications", []).append(receipt)
            self.event(state, "verification_finished", **receipt)
        return {**receipt, "reused": False}

    def record_op(self, operation, target, outcome, provider_id=None, data_sha256=None):
        """Append-only journal of an attempted provider operation. Telemetry, not a driver.

        This runtime performs no provider call and holds no credential; the host's
        authorized tools do that. What it can do is make the outcome durable, so an
        interrupted create is visible as `unknown-outcome` to whoever resumes instead
        of being retried blind.
        """
        require(outcome in RECORD_OUTCOMES, "invalid record operation outcome")
        require(bool(operation.strip()) and bool(target.strip()),
                "a record operation needs a stable logical identity and a target")
        entry = {"operation": operation, "target": target, "outcome": outcome,
                 "provider_id": provider_id, "data_sha256": data_sha256,
                 **self.clock.stamp()}
        with self.transaction() as state:
            state.setdefault("record_journal", []).append(entry)
            self.event(state, "record_operation", operation=operation, outcome=outcome,
                       provider_id=provider_id)
        return entry

    def probe(self, key, expect):
        """Host publication feasibility: did the worker's own bytes survive delivery?

        A feasibility gate has to be able to FAIL. Comparing hashes of the payload the
        child was told to publish against what actually landed distinguishes the three
        outcomes that matter — nothing arrived, a prefix arrived, or something else
        arrived — where a schema test would call all three a valid result object.
        """
        expected = Path(expect).read_bytes()
        with self.transaction() as state:
            worker = self.worker(state, key)
            require(worker["role"] == "probe", "publication probes use the probe role")
            result = worker["result"]
            payload = (result or {}).get("payload")
            if result is None or not isinstance(payload, str):
                finding, received = ("missing" if result is None else "mangled"), b""
            else:
                received = payload.encode("utf-8")
                finding = ("delivered" if received == expected else
                           "truncated" if expected.startswith(received) else "mangled")
            outcome = {"worker": key, "finding": finding, "passed": finding == "delivered",
                       "expected_bytes": len(expected), "received_bytes": len(received),
                       "expected_sha256": digest_bytes(expected),
                       "received_sha256": digest_bytes(received),
                       "delivery_lag_seconds": elapsed(worker["started"], self.clock.stamp())
                       if worker.get("result_ready") else None,
                       "environment": environment_signature()}
            self.event(state, "publication_probed", worker=key, finding=finding)
        return outcome

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
            evidence = {}
            for worker in state["workers"].values():
                if worker["role"] == "completeness" and worker.get("requirements"):
                    counts = Counter(r["applicability"] for r in self.evidence_records(worker))
                    evidence[worker["id"]] = {k: counts[k] for k in
                                              ("current", "stale", "blocked", "unresolved")}
            journal = state.get("record_journal", [])
            # The old ledger's fields are kept verbatim -- they are still the right
            # counters -- but they were printed at the top level where they read as
            # whole-run totals. They only ever covered what this runtime observed:
            # a command run outside `verify`, or an agent never registered as a worker,
            # is absent from every number here. `end_to_end` says so in the output.
            return {"run": state["run"], "stage": state["stage"], "workers": workers,
                    "full_completeness_attempts": sum(w["role"] == "completeness" and not w.get("previous")
                                                       for w in state["workers"].values()),
                    "delta_attempts": sum(bool(w.get("previous")) for w in state["workers"].values()),
                    "stage_spans": spans, "open_stages": list(starts),
                    "verification_runs": len(tests),
                    "repeated_verification_signatures": len(signatures) - len(set(signatures)),
                    "delivery_lags": [e for e in state["events"] if e["kind"] == "worker_result_consumed"],
                    "end_to_end": {
                        "scope": "runtime-observed only: registered workers, measured stages, and "
                                 "commands run through `verify`. Anything else is unknown, not zero.",
                        "schema": state.get("schema"),
                        "workers_by_role": dict(Counter(w["role"] for w in state["workers"].values())),
                        "unaccounted_workers": [w["id"] for w in state["workers"].values()
                                                if not w["terminated"] and not w.get("accepted")],
                        "verification_reuses": sum(e["kind"] == "verification_reused" for e in state["events"]),
                        "evidence_by_worker": evidence,
                        "record_operations": dict(Counter(e["outcome"] for e in journal)),
                        "unconfirmed_record_operations": [e["operation"] for e in journal
                                                          if e["outcome"] != "confirmed"],
                        "correction_causes": (state.get("correction") or {}).get("reasons", []),
                        "stages_measured": [s["stage"] for s in spans]},
                    "model_usage": "unknown until raw telemetry is imported; never inferred from characters"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, help="per-invocation state.json outside disposable worktrees")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("init"); p.add_argument("--run", required=True); p.add_argument("--ticket", required=True)
    p = commands.add_parser("stage"); p.add_argument("name")
    p = commands.add_parser("requirements"); p.add_argument("--source", required=True); p.add_argument("--inventory", required=True)
    commands.add_parser("ready")
    p = commands.add_parser("correction-needed"); p.add_argument("--worktree", required=True)
    p.add_argument("--reason", help="what made this correction necessary; recorded, never inferred")
    p = commands.add_parser("prepare"); p.add_argument("--role", required=True); p.add_argument("--file", action="append", default=[])
    p.add_argument("--worktree"); p.add_argument("--timeout", type=float, default=900)
    p.add_argument("--previous"); p.add_argument("--slot")
    for name in ("attach", "publish", "inspect", "wait", "consume", "accept", "resolve-citations",
                 "evidence", "section", "probe", "end-worker", "yield", "merge-gate"):
        p = commands.add_parser(name); p.add_argument("--worker", required=True)
        if name == "attach": p.add_argument("--agent", required=True)
        if name == "publish": p.add_argument("--result", required=True)
        if name == "resolve-citations": p.add_argument("--citations", required=True)
        if name == "probe": p.add_argument("--expect", required=True)
        if name == "section":
            p.add_argument("--name", required=True); p.add_argument("--page", type=int, default=1)
        if name == "wait": p.add_argument("--seconds", type=float, default=30)
        if name == "end-worker":
            p.add_argument("--reason", required=True); p.add_argument("--confirmed", action="store_true")
            p.add_argument("--host-failed", action="store_true"); p.add_argument("--user-requested", action="store_true")
            p.add_argument("--invalid-result", action="store_true")
        if name == "yield": p.add_argument("--marker", required=True); p.add_argument("--session", required=True)
        if name == "merge-gate": p.add_argument("--worktree", required=True)
    p = commands.add_parser("verify"); p.add_argument("--worktree", required=True); p.add_argument("--shell-command", required=True)
    p.add_argument("--reuse", action="store_true",
                   help="return an applicable existing receipt instead of rerunning; never caches a stale one")
    p = commands.add_parser("verifications"); p.add_argument("--worktree")
    p = commands.add_parser("record-op")
    p.add_argument("--operation", required=True); p.add_argument("--target", required=True)
    p.add_argument("--outcome", required=True, choices=RECORD_OUTCOMES)
    p.add_argument("--provider-id"); p.add_argument("--digest")
    commands.add_parser("summary")
    args = parser.parse_args()
    runtime = Runtime(args.state)
    name = args.command
    if name == "init": result = runtime.init(args.run, args.ticket)
    elif name == "stage": result = runtime.stage(args.name)
    elif name == "requirements": result = runtime.requirements(args.source, read_json(args.inventory))
    elif name == "ready": result = runtime.ready()
    elif name == "correction-needed": result = runtime.correction_needed(args.worktree, args.reason)
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
    elif name == "evidence": result = runtime.evidence(args.worker)
    elif name == "section": result = runtime.section(args.worker, args.name, args.page)
    elif name == "probe": result = runtime.probe(args.worker, args.expect)
    elif name == "end-worker": result = runtime.end_worker(args.worker, args.reason, args.confirmed, args.host_failed, args.user_requested, args.invalid_result)
    elif name == "yield": result = runtime.yield_once(args.worker, args.marker, args.session)
    elif name == "merge-gate": result = runtime.merge_gate(args.worker, args.worktree)
    elif name == "verify": result = runtime.verify(args.worktree, args.shell_command, args.reuse)
    elif name == "verifications": result = runtime.verifications(args.worktree)
    elif name == "record-op":
        result = runtime.record_op(args.operation, args.target, args.outcome, args.provider_id, args.digest)
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
