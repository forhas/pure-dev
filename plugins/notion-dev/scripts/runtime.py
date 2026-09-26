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
import difflib
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid


SCHEMA = 5
SCHEMAS = (1, 2, 3, 4, SCHEMA)

# A delta index is read by a fresh reviewer as its first act, so it is a table of
# contents, not the material. Lists that do not fit are paged out to a side file and
# marked incomplete rather than silently cut; INDEX_BYTES is the budget that decides.
INDEX_BYTES = 2048
PAGE_ITEMS = 50

RECORD_OUTCOMES = ("planned", "attempted", "confirmed", "unknown-outcome", "failed")
RECORD_FIELDS = ("EPIC-REPORT", "TICKET-RECORD", "CLEANUP", "CLEANUP-STEPS",
                 "HOOKS", "EPIC-DOC-RECORD", "EPIC-DOC-NEXT", "ISSUES")
RESULT_CONTRACT_VERSION = 5
AUDIT_FIELDS = ("claims", "caveats", "triage")


def finding_contract():
    return {"finding": "defect, not an affirmative audit observation", "rationale": "evidence and obligation basis",
            "disposition": "absorb|file|drop|blocked", "obligation": "mandatory|advisory|unknown",
            "resolved": "boolean: independently verified fixed in this revision",
            "blocking": "boolean: unknown, or unresolved mandatory; cannot waive by filing/dropping"}


def review_pass(worker, review):
    if review.get("verdict") == "clean":
        return True
    findings = review.get("findings", [])
    return ((worker.get("contract_version") or 0) >= 5 and review.get("verdict") == "findings"
            and bool(findings) and all(f["obligation"] != "unknown" and
                (f["obligation"] == "advisory" or f["resolved"]) and not f["blocking"] for f in findings))


def validate_findings(review):
    findings = review.get("findings")
    require(isinstance(findings, list), "version 5 review requires explicit findings (empty means none)")
    for f in findings:
        require(isinstance(f, dict) and all(isinstance(f.get(k), str) and f[k].strip()
                for k in ("finding", "rationale")) and f.get("disposition") in {"absorb", "file", "drop", "blocked"}
                and f.get("obligation") in {"mandatory", "advisory", "unknown"}
                and isinstance(f.get("resolved"), bool) and isinstance(f.get("blocking"), bool),
                "every finding needs evidence, obligation, resolution and disposition")
        require(f["blocking"] == (f["obligation"] == "unknown" or
                (f["obligation"] == "mandatory" and not f["resolved"])),
                "mandatory/unknown finding cannot be relabeled nonblocking")
    if review.get("verdict") == "clean":
        require(not any(f["blocking"] for f in findings), "clean verdict contradicts blocking findings")
    if review.get("verdict") == "findings":
        require(bool(findings), "findings verdict must enumerate its findings, not hide them in prose")


def finding_ledger(result):
    """Lossless, deterministic IDs within a hash-bound result, including legacy prose.

    No model inference: old ambiguous narrative stays unknown; accounting cannot
    turn it into a passing independent verdict. Recording facts remain obligations.
    """
    entries = []
    def add(source, value, obligation="unknown"):
        entries.append({"id": source, "obligation": obligation, "evidence": value})
    for name in ("code_review", *AUDIT_FIELDS, "correction_review"):
        section = result.get(name, {})
        for i, finding in enumerate(section.get("findings", []), 1):
            add(name + ":" + str(i), finding, finding.get("obligation", "mandatory" if finding.get("blocking") else "unknown"))
        if section.get("verdict") in {"findings", "unverified"} and not section.get("findings"):
            add(name + ":unclassified", section)
        if section.get("status") == "unverified": add(name + ":unverified", section)
        for i, finding in enumerate(section.get("blocking_findings", []), 1):
            add(name + ":blocking:" + str(i), finding, "mandatory")
    for i, finding in enumerate(result.get("blocking_findings", []), 1):
        add("blocking:" + str(i), finding, "mandatory")
    for i, item in enumerate(result.get("requirements", []), 1):
        if item.get("verdict") != "met": add("requirement:" + str(i), item, "mandatory")
    for name in ("claim_corrections", "release_obligations"):
        for i, fact in enumerate(result.get("recording", {}).get(name, []), 1):
            add("recording." + name + ":" + str(i), fact)
    return entries


def finding_pages(result):
    # A single very long finding is fragmented, never clipped. 400 characters
    # caps even JSON-escaped control characters at 2,400 bytes per fragment.
    pages, current = [], []
    for entry in finding_ledger(result):
        payload = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        parts = [payload[i:i + 400] for i in range(0, len(payload), 400)]
        for i, part in enumerate(parts):
            fragment = {"id": entry["id"], "part": i + 1, "parts": len(parts), "json_fragment": part}
            if current and len(json.dumps(current + [fragment], ensure_ascii=False).encode("utf-8")) > 3500:
                pages.append(current); current = []
            current.append(fragment)
    if current: pages.append(current)
    return pages


def findings_accounted(worker):
    if worker["role"] != "completeness" or not (worker.get("finding_accounting") or
                                               (worker.get("contract_version") or 0) >= 5):
        return True
    entries = finding_ledger(worker["result"] or {})
    if not entries: return True
    judgment = worker.get("finding_judgments", {})
    return (judgment.get("result_sha256") == digest_bytes(json_bytes(worker["result"]))
            and {e["id"] for e in entries} == {d["id"] for d in judgment.get("dispositions", [])})


def audits_pass(result):
    return all(result.get(name, {}).get("status") == "checked"
               and not any(item["blocking"] for item in result[name]["findings"])
               for name in AUDIT_FIELDS)


def result_contract(role, items, version=RESULT_CONTRACT_VERSION):
    """One machine-readable contract, supplied to the worker and checked at publication."""
    contract = {"version": version, "required": {"report": "nonempty summary string; do not duplicate structured fields"}}
    if role == "completeness":
        contract["required"].update(
            requirements_complete="boolean: independently checked the whole authoritative source",
            requirements=[{"id": item["id"], "verdict": "met|not-met|unverified",
                           "citation": "nonempty evidence reference"} for item in items],
            blocking_findings="list of unresolved mandatory findings; empty only if none",
            code_review={"verdict": "clean|findings|unverified", "citation": "code/test evidence"})
        for name in AUDIT_FIELDS:
            contract["required"][name] = {
                "status": "checked|unverified", "evidence": "nonempty audit scope/evidence or reason unverified",
                "findings": [{"finding": "nonempty description", "disposition": "absorb|file|drop|blocked",
                              "rationale": "nonempty decision/evidence", "blocking": "boolean: unresolved merge obligation"}]}
        contract["audit_rules"] = "All three audits required. Checked with findings=[] means NONE. Missing is unknown. Unverified or blocking=true prevents merge. Mandatory work cannot be waived with file/drop."
        if version >= 5:
            for name in ("code_review", *AUDIT_FIELDS):
                contract["required"][name]["findings"] = [finding_contract()]
            contract["finding_rules"] = "Enumerate every defect in its owning section, never only in citation/report. Affirmative observations belong in evidence. Mandatory incorrect claims, missing validation and unknown coverage block; advisory means genuinely optional. Explicitly verified resolved findings may remain as history. findings verdict with only advisory/resolved items can pass; unverified never passes. Parent must account for every indexed item before acceptance."
        if version >= 3:
            contract["required"]["recording"] = {"release_obligations": [], "claim_corrections": [], "technical_delta": []}
            contract["recording_rules"] = "Preserve release obligations and accepted claim corrections as strings; technical_delta items carry fact/evidence. Explicit [] means none. These are the canonical post-merge facts, not another narrative."
    elif role == "record":
        contract["required"]["record"] = {field: "nonempty outcome, including skipped reason" for field in RECORD_FIELDS}
    contract["delivery"] = "Publish this object, repair rejected fields in the same worker, then return only its artifact reference. Never rerun completed work to repair a report."
    return contract


def validate_result(worker, result):
    require(isinstance(result, dict) and isinstance(result.get("report"), str)
            and result["report"].strip(), "result requires a nonempty report, not a launch acknowledgement")
    if not worker.get("contract_version"):
        return  # In-flight pre-0.36 workers keep their original contract and merge gate.
    role = worker["role"]
    if role == "completeness":
        require(isinstance(result.get("requirements_complete"), bool), "requirements_complete must be boolean")
        verdicts = result.get("requirements")
        expected = {item["id"] for item in worker["requirements"]["items"]}
        require(isinstance(verdicts, list) and all(isinstance(v, dict) for v in verdicts),
                "requirements must be a list of verdict objects")
        require(len(verdicts) == len(expected) and {v.get("id") for v in verdicts} == expected,
                "requirements must cover every inventory ID exactly once")
        for verdict in verdicts:
            require(verdict.get("verdict") in {"met", "not-met", "unverified"}
                    and isinstance(verdict.get("citation"), str) and verdict["citation"].strip(),
                    "each verdict needs a valid verdict and nonempty citation")
        require(isinstance(result.get("blocking_findings"), list)
                and all(isinstance(f, str) and f.strip() for f in result["blocking_findings"]),
                "blocking_findings must be a list of nonempty strings")
        review = result.get("code_review")
        require(isinstance(review, dict) and review.get("verdict") in {"clean", "findings", "unverified"}
                and isinstance(review.get("citation"), str) and review["citation"].strip(),
                "code_review requires verdict and evidence citation")
        if worker["contract_version"] >= 2:
            for name in AUDIT_FIELDS:
                audit = result.get(name)
                require(isinstance(audit, dict) and audit.get("status") in {"checked", "unverified"}
                        and isinstance(audit.get("evidence"), str) and audit["evidence"].strip()
                        and isinstance(audit.get("findings"), list),
                        name + " audit requires status, evidence and findings (explicit [] for NONE)")
                for finding in audit["findings"]:
                    require(isinstance(finding, dict)
                            and all(isinstance(finding.get(k), str) and finding[k].strip()
                                    for k in ("finding", "rationale"))
                            and finding.get("disposition") in {"absorb", "file", "drop", "blocked"}
                            and isinstance(finding.get("blocking"), bool),
                            name + " finding requires finding/disposition/rationale/blocking")
        if worker["contract_version"] >= 3:
            recording = result.get("recording")
            require(isinstance(recording, dict), "recording facts required")
            for name in ("release_obligations", "claim_corrections"):
                require(isinstance(recording.get(name), list)
                        and all(isinstance(v, str) and v.strip() for v in recording[name]), name + " must be a list of facts")
            require(isinstance(recording.get("technical_delta"), list)
                    and all(isinstance(v, dict) and all(isinstance(v.get(k), str) and v[k].strip()
                            for k in ("fact", "evidence")) for v in recording["technical_delta"]),
                    "technical_delta must contain fact/evidence objects")
        if worker["contract_version"] >= 5:
            for name in ("code_review", *AUDIT_FIELDS): validate_findings(result[name])
        if worker.get("correction_manifest"):
            correction = result.get("correction_review")
            if worker.get("reused_correction") and correction is None:
                correction = worker["reused_correction"]
            require(isinstance(correction, dict)
                    and correction.get("id") == worker["correction"]["id"]
                    and correction.get("manifest_sha256") == worker["correction_manifest"]["sha256"]
                    and correction.get("verdict") in {"clean", "findings", "unverified"}
                    and isinstance(correction.get("blocking_findings"), list)
                    and isinstance(correction.get("report"), str) and correction["report"].strip(),
                    "correction_review must cover the exact correction manifest with verdict/report/findings")
            if worker.get("reused_correction"):
                require(correction == worker["reused_correction"], "reused correction evidence is immutable")
            elif worker["contract_version"] >= 3:
                require(isinstance(correction.get("depends_on"), list)
                        and all(isinstance(p, str) and Path(p).is_absolute() for p in correction["depends_on"]),
                        "correction_review depends_on must list its external evidence files (explicit [] for code-only)")
            if worker["contract_version"] >= 5 and not worker.get("reused_correction"):
                validate_findings(correction)
    elif role == "record":
        fields = result.get("record")
        require(isinstance(fields, dict) and all(isinstance(fields.get(k), str) and fields[k].strip()
                for k in RECORD_FIELDS), "record must contain all eight named outcome fields")


def render_result(worker, result):
    """The human report is a view of the same result, never a competing chat contract."""
    rendered = dict(result)
    if not worker.get("contract_version"):
        return rendered
    if worker["role"] == "record":
        rendered["report"] = "RECORD:\n" + "\n".join(k + ": " + result["record"][k] for k in RECORD_FIELDS)
    elif worker["role"] == "completeness":
        if worker.get("reused_correction"):
            rendered["correction_review"] = worker["reused_correction"]
        elif worker["contract_version"] >= 3 and result.get("correction_review"):
            correction = dict(result["correction_review"])
            # The structured verdict is authoritative. Narrative punctuation cannot
            # demand another independent investigation of unchanged code.
            narrative = re.sub(r"^VERDICT: (?:CLEAN|FINDINGS|UNVERIFIED)\r?\n", "", correction["report"], count=1)
            narrative = re.sub(r"^VERDICT:", "Review detail:", narrative, flags=re.M)
            correction["report"] = "VERDICT: " + correction["verdict"].upper() + "\n" + narrative
            rendered["correction_review"] = correction
        verdicts = {v["id"]: v["verdict"] for v in result["requirements"]}
        counts = Counter(verdicts[i["id"]] for i in worker["requirements"]["items"] if i["kind"] == "acceptance")
        clean = (result["requirements_complete"] and not result["blocking_findings"]
                 and review_pass(worker, result["code_review"]) and all(v == "met" for v in verdicts.values()))
        if worker["contract_version"] >= 2:
            clean = clean and audits_pass(result)
        header = ["COMPLETENESS: " + ("clean" if clean else "blocked"),
                  "CRITERIA-TOTAL: " + str(sum(counts.values())), "CRITERIA-MET: " + str(counts["met"]),
                  "CRITERIA-NOT-MET: " + str(counts["not-met"]), "CRITERIA-UNVERIFIED: " + str(counts["unverified"])]
        narrative = re.sub(r"^(?:COMPLETENESS|CRITERIA-(?:TOTAL|MET|NOT-MET|UNVERIFIED)):[^\r\n]*\r?\n?",
                           "", result["report"], flags=re.M)
        if worker["contract_version"] >= 2:
            # Render one-line JSON per charge, so repeated publication is idempotent
            # and prose claiming NONE cannot override structured findings.
            narrative = re.sub(r"^(?:CLAIMS|CAVEATS|TRIAGE):[^\r\n]*\r?\n?", "", narrative, flags=re.M)
            if worker["contract_version"] >= 4:
                # Full audits are siblings in this same result. Repeating all their
                # evidence in report doubles transport without adding information.
                header.extend(name.upper() + ": " + result[name]["status"] + "; findings="
                              + str(len(result[name]["findings"])) for name in AUDIT_FIELDS)
            else:
                header.extend(name.upper() + ": " + json.dumps(result[name], ensure_ascii=False, sort_keys=True)
                              for name in AUDIT_FIELDS)
        rendered["report"] = "\n".join(header) + "\n" + narrative
    return rendered


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def notion_source(response, ignored_properties):
    """Canonicalize a complete notion-fetch response, never a query/status projection.

    The MCP's `as of` value describes page editing, not the time of the network read.
    Keep ALL body text and unknown properties. Only configured status/PR properties
    are non-requirement metadata; never strip sections just because of their headings.
    """
    value = response
    for _ in range(5):
        require(not isinstance(value, dict) or not any(value.get(k) for k in ("isError", "truncated", "has_more")),
                "failed or incomplete fetch cannot establish full-source freshness")
        if isinstance(value, str):
            value = json.loads(value)
        elif isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict) and value[0].get("type") == "text":
            value = value[0]["text"]
        elif isinstance(value, dict) and "content" in value and not value.get("isError"):
            value = value["content"]
        else:
            break
    require(isinstance(value, dict) and isinstance(value.get("metadata"), dict) and value["metadata"].get("type") == "page"
            and isinstance(value.get("title"), str) and isinstance(value.get("text"), str),
            "requires the complete raw notion-fetch page response, not rows/status or a summary")
    text = value["text"].replace("\r\n", "\n")
    page = re.search(r'<page\s+url="([^"]+)"[^>]*>', text)
    ids = lambda url: re.findall(r"[0-9a-f]{32}", str(url).lower().replace("-", ""))
    require(page is not None and ids(page[1]) and ids(value.get("url")) == ids(page[1]),
            "full page identity missing or inconsistent")
    properties = re.findall(r"<properties>\s*(.*?)\s*</properties>", text, re.S)
    bodies = re.findall(r"<content>\n?(.*?)</content>\s*</page>", text, re.S)
    require(len(properties) == len(bodies) == 1 and "<truncated" not in text.lower(),
            "full page properties/content required; incomplete fetch is not evidence")
    props = json.loads(properties[0])
    require(isinstance(props, dict), "page properties must be an object")
    source = "# " + value["title"] + "\n\n" + json.dumps(
        {k: v for k, v in props.items() if k not in ignored_properties and k != "url"},
        ensure_ascii=False, sort_keys=True, indent=2) + "\n\n" + bodies[0]
    return ids(page[1])[-1], source.encode("utf-8"), props


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


def json_bytes(value, indent=2):
    """The exact bytes `atomic_json` writes for `value`. One spelling, two callers.

    `bound_index` has to measure the file it is about to produce; measuring a form
    nobody writes is how a budget reports 2005 for a 2409-byte file.
    """
    separators = None if indent is not None else (",", ":")
    body = json.dumps(value, ensure_ascii=False, indent=indent,
                      separators=separators, allow_nan=False)
    return (body + "\n").encode("utf-8")


def atomic_json(path, value, indent=2):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".runtime-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=indent,
                      separators=None if indent is not None else (",", ":"),
                      allow_nan=False)
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
                # Schema 1/2 runs retain their schema: an in-flight invocation is never force-
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

    def init(self, run, ticket, legacy=False):
        with self.transaction(create=True) as state:
            if state:
                require(state["run"] == run and state["ticket"] == ticket,
                        "state belongs to a different invocation")
                return {"state": str(self.path), "run": run, "resumed": True}
            state.update(schema=2 if legacy else SCHEMA, run=run, ticket=ticket, stage=None, events=[],
                         workers={}, requirements=None, awaiting_worker=None,
                         verifications=[], record_journal=[],
                         host_session=os.environ.get("NOTION_DEV_SESSION_ID") or None)
            self.event(state, "run_started")
        return {"state": str(self.path), "run": run, "resumed": False}

    def stage(self, name):
        require(bool(name.strip()), "stage name required")
        with self.transaction() as state:
            require(name != "complete" or state["schema"] < 4,
                    "use workflow.py complete for the validated terminal transition")
            if state["stage"] != name:
                if state["stage"]:
                    self.event(state, "stage_ended")
                state["stage"] = name
                self.event(state, "stage_started")
        return {"stage": name}

    def capture_ticket(self, transcript, session, call_id=None, config=None, worker=None, request=None, page=None):
        """Persist actual host output and bind/refresh without model-transcribed JSON."""
        from host_capture import notion_fetch
        with self.transaction() as state:
            require(not state.get("completed"), "resume before capturing into a completed invocation")
            require(not state.get("host_session") or state["host_session"] == session, "foreign host session")
            pending = state.get("ticket_refresh_request") if worker else None
            require(not worker or (pending and pending["request"] == request and pending["worker"] == worker),
                    "begin the review's refresh challenge first")
            require(bool(worker) == bool(request), "refresh worker and request must be supplied together")
            require(worker or config, "intake capture requires primary config")
            response, observed = notion_fetch(transcript, session, call_id,
                pending["started"]["wall"] if pending else None, self.clock.stamp()["wall"],
                pending["page"] if pending else page)
            call_id = observed["call_id"]
            page, _, _ = notion_source(response, [])
            requested = str(observed["call"]["item"].get("input", {}).get("id", "")).lower().replace("-", "")
            require(page in requested, "fetch request must identify the returned page")
            if pending: require(page == pending["page"], "foreign ticket page")
            saved = self.path.parent / ("host-fetch-" + digest_bytes(call_id.encode("utf-8")) + ".json")
            if saved.exists(): require(read_json(saved) == response, "host capture is immutable")
            else: atomic_json(saved, response)
            binding = {"path": str(saved), "sha256": digest(saved), "session": session,
                       "call_id": call_id, "call_time": observed["call"]["timestamp"],
                       "result_time": observed["result"]["timestamp"],
                       "transcript": observed["transcript"],
                       "call_sha256": observed["call"]["sha256"], "result_sha256": observed["result"]["sha256"]}
            old = state.setdefault("host_captures", {}).get(str(saved))
            require(old is None or old == binding, "capture provenance changed")
            state["host_session"] = session
            state["host_captures"][str(saved)] = binding
        if worker:
            return self.refresh_ticket(worker, saved, request, call_id)
        return self.ticket_source(saved, config)

    @staticmethod
    def captured_response(state, response):
        binding = state.get("host_captures", {}).get(str(Path(response).resolve()))
        require(binding and binding["sha256"] == digest(response)
                and binding["session"] == state.get("host_session"),
                "schema 5 requires capture-ticket from the actual host transcript, not reconstructed JSON")
        return binding

    def ticket_source(self, response, config):
        """Bind a fetched provider page to the local source used by the inventory."""
        settings = read_json(config)["ticketSystem"]
        ignored = [settings.get("statusProperty", "Status"), settings.get("prProperty", "PR")]
        page, content, props = notion_source(read_json(response), ignored)
        source = self.path.parent / "ticket.md"
        with self.transaction() as state:
            if state["schema"] >= 5: self.captured_response(state, response)
            old = state.get("ticket_source")
            require(not state.get("completed"), "resume explicitly before changing a completed invocation")
            id_property = settings.get("idProperty", "ID")
            value = props.get("userDefined:" + id_property, props.get(id_property))
            if isinstance(value, float) and value.is_integer():
                value = int(value)  # Number properties may be encoded as 42.0.
            number = re.fullmatch(r"(?:[A-Za-z][A-Za-z0-9_-]*-)?([0-9]+)", str(value))
            require(number and int(number[1]) == int(state["ticket"].rsplit("-", 1)[-1]),
                    "provider page ID property does not match the invocation ticket")
            for name, expected in settings.get("staticProperties", {}).items():
                require(name not in props or props[name] == expected, "provider page violates configured project scope: " + name)
            require(not old or old["page"] == page, "cannot change the invocation's ticket page")
            require(not any(not w["terminated"] and not w.get("accepted") for w in state["workers"].values()),
                    "account for workers before changing their authoritative source")
            source.write_bytes(content)
            state["ticket_source"] = {"page": page, "ignored_properties": ignored,
                                      "source": str(source), "source_sha256": digest(source),
                                      "response": str(Path(response).resolve())}
            state.pop("ticket_refresh", None)
            self.event(state, "ticket_source_bound", page=page, source_sha256=digest(source))
        return {"source": str(source), "source_sha256": digest(source), "page": page}

    def refresh_ticket(self, key, response=None, request=None, call_id=None):
        """Begin before the host's full fetch; finish with that call's raw response.

        This is an integration receipt, NOT provider attestation. The host must capture
        the real tool response/call ID. Python cannot detect a host forging a new call
        and copying old bytes. Replaying a retained capture/receipt is rejected locally.
        """
        with self.transaction() as state:
            worker = self.worker(state, key)
            require(worker["role"] == "completeness" and worker.get("accepted"),
                    "refresh requires an accepted independent review")
            latest = [w for w in state["workers"].values() if w["role"] == "completeness" and not w["terminated"]]
            require(latest and latest[-1]["id"] == key, "refresh must follow the final independent review")
            binding = state.get("ticket_source")
            require(binding and worker["requirements"] == state["requirements"]
                    and worker["requirements"]["source_sha256"] == binding["source_sha256"],
                    "bind full ticket source and review its current inventory first")
            if response is None:
                state.pop("ticket_refresh", None)
                challenge = {"request": uuid.uuid4().hex, "worker": key, "run": state["run"],
                             "started": self.clock.stamp(), "page": binding["page"],
                             "source_sha256": binding["source_sha256"]}
                state["ticket_refresh_request"] = challenge
                self.event(state, "ticket_refresh_started", worker=key, request=challenge["request"])
                return challenge
            pending = state.get("ticket_refresh_request")
            require(pending and pending["request"] == request and pending["worker"] == key
                    and pending["source_sha256"] == binding["source_sha256"], "refresh request is stale or foreign")
            age = elapsed(pending["started"], self.clock.stamp())
            require(age is not None and 0 <= age <= 300, "refresh expired; begin a new full fetch")
            used = state.setdefault("ticket_fetch_calls", [])
            require(isinstance(call_id, str) and call_id.strip() and call_id not in used,
                    "a new actual provider tool-call ID is required")
            capture = Path(response).resolve()
            if state["schema"] >= 5:
                from host_capture import timestamp
                provenance = self.captured_response(state, capture)
                require(provenance["call_id"] == call_id
                        and timestamp(provenance["call_time"]) >= pending["started"]["wall"],
                        "actual provider call must follow this refresh challenge")
            require(str(capture) != binding["response"] and capture.stat().st_mtime >= pending["started"]["wall"],
                    "capture the new full fetch response after refresh began; do not replay intake")
            fetched = read_json(capture)
            page, content, _ = notion_source(fetched, binding["ignored_properties"])
            require(page == pending["page"], "refreshed page is not the reviewed ticket")
            snapshot = self.path.parent / ("ticket-refresh-" + request + ".json")
            atomic_json(snapshot, fetched)
            used.append(call_id)
            unchanged = digest_bytes(content) == binding["source_sha256"]
            receipt = {**pending, "call_id": call_id, "response": str(snapshot),
                       "response_sha256": digest(snapshot), "finished": self.clock.stamp(),
                       "unchanged": unchanged}
            state["ticket_refresh"] = receipt
            del state["ticket_refresh_request"]
            self.event(state, "ticket_refreshed", worker=key, unchanged=unchanged, call_id=call_id)
        return {"passed": unchanged, "receipt": receipt,
                "action": "merge-gate" if unchanged else "requirements changed: bind refreshed response, inventory and review again"}

    def ticket_freshness(self, state, worker):
        if state["schema"] < 4:
            return []  # Existing invocations keep their original contract.
        receipt = state.get("ticket_refresh") or {}
        age = elapsed(receipt["started"], self.clock.stamp()) if receipt.get("started") else None
        binding = state.get("ticket_source") or {}
        latest = [w for w in state["workers"].values() if w["role"] == "completeness" and not w["terminated"]]
        if (not latest or latest[-1]["id"] != worker["id"]
                or receipt.get("worker") != worker["id"] or receipt.get("run") != state["run"]
                or not receipt.get("unchanged") or receipt.get("page") != binding.get("page")
                or receipt.get("source_sha256") != (worker["requirements"] or {}).get("source_sha256")
                or age is None or not 0 <= age <= 300
                or not Path(receipt.get("response", "")).is_file()
                or digest(receipt["response"]) != receipt["response_sha256"]):
            return ["fresh full authoritative ticket receipt required after final review (refresh-ticket)"]
        return []

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
        source = state.get("ticket_source")
        if state["schema"] >= 5 and source:
            # A takeover transfers host_session but keeps this binding; recapture first.
            capture = state.get("host_captures", {}).get(source["response"])
            if not capture or capture["session"] != state.get("host_session"):
                return ["ticket source predates this host session; capture-ticket again"]
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

    def prepare(self, role, files, worktree=None, timeout=900, previous=None, slot=None, remove_inputs=()):
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
        require(not remove_inputs or previous, "input removal requires a delta baseline")
        require(not set(remove_inputs) & set(files), "cannot supply and remove the same input")
        require(role not in {"plan", "implementation", "branch-review", "local-review", "completeness"} or worktree,
                "review workers require a worktree revision")
        current = revision(worktree) if worktree else None
        with self.transaction() as state:
            require(role != "completeness" or not self.readiness(state), "completeness requires ready requirements")
            require(not state.get("completed"), "resume explicitly before dispatching in a completed invocation")
            if role == "completeness":
                require(all(findings_accounted(w) for w in state["workers"].values()
                            if w["role"] == role and w.get("result") and not w["terminated"]),
                        "account for every finding before another review; use result-view and judge-findings")
            if role == "completeness" and not previous and state["schema"] >= 3:
                require(sum(w["role"] == role and not w.get("previous") for w in state["workers"].values()) < 2,
                        "full completeness attempt budget exhausted; preserve unresolved work and escalate")
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
            grant = self.correction_grant(state, previous, current) if previous else None
            if baseline and state["schema"] >= 3:
                old_files = baseline["worker"]["files"]
                require(set(remove_inputs) <= set(old_files), "cannot remove an unknown input")
                for name, source in old_files.items():
                    if name not in snapshots and name not in remove_inputs:
                        snapshots[name] = {"path": source["path"], "sha256": digest(source["path"])}
            require(bool(snapshots), "at least one input artifact is required")
            if grant:
                logs = {r["log"] for r in state.get("verifications", [])}
                require(not remove_inputs and all(name in snapshots and snapshots[name]["sha256"] == value
                        for name, value in grant["binding"]["inputs"].items() if name != "verification_receipts"
                        and not (baseline["worker"]["files"][name]["path"] in logs
                                 and snapshots.get(name, {}).get("path") in logs)),
                        "authorized correction inputs changed; request authorization for the new scope")
            verification_ids = []
            if role == "completeness" and "verification_receipts" in snapshots:
                verification_ids = read_json(snapshots["verification_receipts"]["path"])["verifications"]
                require(verification_ids and not self.verification_reasons(state, verification_ids, current),
                        "review verification is stale: commit, verify, then prepare review")
                for source in snapshots.values():
                    receipts = [r for r in state.get("verifications", []) if r["log"] == source["path"]]
                    require(not receipts or not self.receipt_reusable(receipts[-1], current, environment_signature()),
                            "named test log is stale; use the current verification receipt")
            correction = state.get("correction") if role == "completeness" else None
            correction_manifest = self.correction_manifest(correction, current) if correction else None
            reused = None
            if (baseline and correction and (baseline["worker"].get("contract_version") or 0) >= 3
                    and baseline["worker"]["revision"] == current
                    and self.correction_reviewed(state, baseline["worker"], baseline["worker"]["result"])):
                reused = baseline["worker"]
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
            if verification_ids:
                packet["verification_evidence"] = {
                    "input": "verification_receipts",
                    "instruction": "Read the verification manifest for current logs and archived outputs. Cite outputs[].path, never the mutable outputs[].source. Use those archives in correction_review.depends_on. Re-run only for a concrete doubt; changed results require rechecking affected claims."}
            contract_version = RESULT_CONTRACT_VERSION if state["schema"] >= 5 else (3 if state["schema"] >= 3 else None)
            if contract_version:
                packet["result_contract"] = result_contract(role, (state["requirements"] or {}).get("items", []), contract_version)
            if baseline is not None:
                delta_path = directory / "delta.json"
                # `indent=None`: this one file is budgeted, and `bound_index` measured
                # the compact form it is about to be written in.
                index = self.delta_index(baseline, current, snapshots, directory)
                atomic_json(delta_path, index, indent=None)
                packet["delta"] = {"path": str(delta_path), "sha256": digest(delta_path),
                                   "bytes": delta_path.stat().st_size}
                if contract_version:
                    packet["result_contract"]["required"]["delta_review"] = {
                        "previous": previous, "manifest_sha256": packet["delta"]["sha256"],
                        "checked_requirement_ids": [i["id"] for i in state["requirements"]["items"]],
                        "disposition": "sufficient|full-review-required"}
                if contract_version and contract_version >= 4:
                    packet["delta_publication"] = self.delta_publication(directory, baseline["worker"])
            if grant:
                packet["authorized_correction"] = {"request": grant["id"], "scope": grant["scope"],
                    "instruction": "One bounded correction review only. Check indirect impact on every requirement; "
                                   "if broader review is needed, return full-review-required, never silently widen scope."}
            if reused:
                packet["correction_manifest"] = reused["correction_manifest"]
                packet["correction_reuse"] = {"worker": reused["id"],
                    "review": reused["result"]["correction_review"],
                    "instruction": "Unchanged code, obligation and declared dependencies: runtime carries this independent verdict. Review only delta impact; do not repeat correction tests by default."}
            elif correction_manifest is not None:
                patch_path = directory / "correction.patch"
                patch_path.write_bytes(correction_manifest.pop("patch"))
                correction_manifest["patch"] = {"path": str(patch_path), "sha256": digest(patch_path),
                                                "bytes": patch_path.stat().st_size}
                manifest_path = directory / "correction.json"
                atomic_json(manifest_path, correction_manifest)
                packet["correction_manifest"] = {"path": str(manifest_path), "sha256": digest(manifest_path)}
                if contract_version:
                    packet["result_contract"]["required"]["correction_review"] = {
                        "id": correction["id"], "manifest_sha256": digest(manifest_path),
                        "verdict": "clean|findings|unverified", "blocking_findings": [],
                        "report": "evidence summary; structured verdict is authoritative"}
                    if contract_version >= 3:
                        packet["result_contract"]["required"]["correction_review"]["depends_on"] = []
                        packet["result_contract"]["correction_rules"] = "depends_on lists absolute paths of ALL external evidence used (logs/config/provider snapshots). Code/requirements are already bound. Explicit [] only for code-only review."
                    if contract_version >= 5:
                        packet["result_contract"]["required"]["correction_review"]["findings"] = [finding_contract()]
            packet_path = directory / "context.json"
            if contract_version and contract_version >= 4:
                packet["publication"] = self.publication_kit(key, directory, packet)
            atomic_json(packet_path, packet)
            worker = {"id": key, "role": role, "status": "pending", "agent_id": None,
                      "started": self.clock.stamp(), "timeout_seconds": timeout,
                      "files": snapshots, "revision": current, "result": None,
                      "terminated": False, "accepted": False,
                      "contract_version": contract_version,
                      "requirements": state["requirements"], "slot": slot,
                      "packet": str(packet_path), "packet_sha256": digest(packet_path),
                      "inventory_snapshot": packet["requirements"], "previous": previous,
                      "delta": packet.get("delta"), "correction": correction,
                      "delta_publication": packet.get("delta_publication"),
                      "correction_manifest": packet.get("correction_manifest"),
                      "reused_correction": reused["result"]["correction_review"] if reused else None,
                      "correction_dependencies": reused.get("correction_dependencies", []) if reused else []}
            worker["verification_ids"] = verification_ids
            if previous:
                grant = self.correction_grant(state, previous, current)
                if grant and sum(bool(w.get("previous")) for w in state["workers"].values()) >= 2:
                    grant["worker"] = key
                    self.event(state, "review_allowance_spent", request=grant["id"], worker=key)
            state["workers"][key] = worker
            self.event(state, "worker_prepared", worker=key, role=role,
                       input_bytes=input_bytes, packet_bytes=packet_path.stat().st_size,
                       delta_bytes=(packet.get("delta") or {}).get("bytes"))
        return {"worker": key, "state": str(self.path), "role": role,
                "timeout_seconds": timeout, "revision": current, "packet": str(packet_path)}

    def publication_kit(self, key, directory, packet):
        """An editable, deliberately nonpassing submission and exact Git Bash/WSL command."""
        draft = {"report": "", "requirements_complete": False}
        if packet["role"] == "completeness":
            draft.update(requirements=[{"id": i["id"], "verdict": "unverified", "citation": ""}
                         for i in read_json(packet["requirements"]["path"])["items"]],
                         blocking_findings=[], code_review={"verdict": "unverified", "citation": ""},
                         recording={"release_obligations": [], "claim_corrections": [], "technical_delta": []})
            if packet["result_contract"]["version"] >= 5:
                draft["code_review"]["findings"] = []
            for name in AUDIT_FIELDS:
                draft[name] = {"status": "unverified", "evidence": "", "findings": []}
            if packet.get("delta_publication"):
                for name in ("requirements", "blocking_findings", "code_review", "recording") + AUDIT_FIELDS:
                    draft.pop(name)
                draft["delta_result"] = {"baseline_sha256": packet["delta_publication"]["baseline_sha256"],
                    "changed_requirements": [], "reused_requirement_ids": [], "updated_sections": {}, "reused_sections": []}
            for name in ("delta_review", "correction_review"):
                if name in packet["result_contract"]["required"]:
                    draft[name] = dict(packet["result_contract"]["required"][name])
                    if name == "delta_review": draft[name]["disposition"] = "full-review-required"
                    else: draft[name].update(verdict="unverified", report="")
        elif packet["role"] == "record":
            draft = {"report": "", "record": {name: "" for name in RECORD_FIELDS}}
        else:
            draft = {"report": ""}
        submission = directory / "submission.json"
        atomic_json(submission, draft)
        argv = [sys.executable, str(Path(__file__).resolve()), "--state", str(self.path),
                "publish", "--worker", key, "--result", str(submission)]
        return {"submission": str(submission), "result_directory": str(directory / "published"),
                "argv": argv, "command": " ".join(shlex.quote(a) for a in argv),
                "instruction": "Edit submission.json using the host's permitted structured-file tool, then run command. Skeleton is NOT a verdict. Return findings/evidence once, not another narrative report. Do not read global state.json or load legacy formatting manuals.",
                "host_return": "If the host forbids report writes, do not try another writing tool. Return the complete contract JSON as your final response. After host completion, the parent saves that unchanged object to submission and publishes for this SAME worker; normal consume/accept checks still apply. This route waits for host delivery, not publication polling."}

    @staticmethod
    def result_artifact(worker):
        """Materialize the canonical value, not an assumed caller submission filename."""
        if not worker.get("packet"):
            return None
        # Do not collide with an older worker's freely chosen submission filename.
        path = Path(worker["packet"]).parent / "published" / (digest_bytes(json_bytes(worker["result"])) + ".json")
        if path.exists():
            require(read_json(path) == worker["result"], "canonical result artifact changed")
        else:
            atomic_json(path, worker["result"])
        return {"path": str(path), "sha256": digest(path)}

    def result_view(self, key, section=None, page=None):
        """A parent/reviewer never needs the global worker roster to find one result."""
        with self.transaction() as state:
            worker = self.worker(state, key)
            require(worker["result"] is not None, "result not available")
            artifact = self.result_artifact(worker)
            result = worker["result"]
            if page is not None:
                require(section is None and worker["role"] == "completeness", "finding pages require a review result")
                pages = finding_pages(result)
                require(1 <= page <= len(pages), "finding page out of range")
                worker["finding_accounting"] = True
                seen = worker.setdefault("finding_pages_read", [])
                if page not in seen: seen.append(page)
                return {"worker": key, "result_sha256": digest_bytes(json_bytes(result)),
                        "page": page, "pages": len(pages), "complete": len(seen) == len(pages),
                        "fragments": pages[page - 1]}
            if section is not None:
                require(section in result, "unknown result section")
                return {"worker": key, "artifact": artifact, "section": section, "data": result[section]}
            if worker["role"] == "completeness":
                worker["finding_accounting"] = True
            entries = finding_ledger(result)
            return {"worker": key, "artifact": artifact, "result_sha256": digest_bytes(json_bytes(result)),
                    "accepted": worker.get("accepted", False),
                    "sections": list(result), "requirements_complete": result.get("requirements_complete"),
                    "verdict_counts": dict(Counter(v["verdict"] for v in result.get("requirements", []))),
                    "code_review": {"verdict": result.get("code_review", {}).get("verdict")},
                    "audits": {name: {"status": result[name]["status"], "count": len(result[name]["findings"])}
                               for name in AUDIT_FIELDS if name in result},
                    "findings": {"count": len(entries), "counts": dict(Counter(e["obligation"] for e in entries)),
                                 "ids": [e["id"] for e in entries[:10]], "ids_complete": len(entries) <= 10,
                                 "pages": len(finding_pages(result)), "complete": not entries,
                                 "accounted": findings_accounted(worker)}}

    def judge_findings(self, key, judgment):
        with self.transaction() as state:
            worker = self.worker(state, key)
            require(worker["role"] == "completeness" and worker["status"] == "consumed" and not worker["terminated"],
                    "consume a completed review before judging findings")
            result = worker["result"]
            require(isinstance(judgment, dict) and judgment.get("result_sha256") == digest_bytes(json_bytes(result)),
                    "judgment must bind the exact result hash")
            require(set(worker.get("finding_pages_read", [])) == set(range(1, len(finding_pages(result)) + 1)),
                    "read every finding page before judging; a clipped summary is not full evidence")
            dispositions = judgment.get("dispositions")
            require(isinstance(dispositions, list) and all(isinstance(d, dict) and isinstance(d.get("id"), str)
                    for d in dispositions), "dispositions must be a list of finding judgments")
            ids = [d["id"] for d in dispositions]
            require(len(ids) == len(set(ids)) and set(ids) == {e["id"] for e in finding_ledger(result)},
                    "judge every finding ID exactly once")
            for d in dispositions:
                require(d.get("action") in {"absorb", "file", "drop", "blocked", "record"}
                        and all(isinstance(d.get(k), str) and d[k].strip() for k in ("rationale", "evidence")),
                        "judgment needs action, rationale and evidence; it never overrides the independent verdict")
            worker["finding_accounting"] = True
            worker["finding_judgments"] = judgment
            self.event(state, "findings_judged", worker=key, count=len(ids), result_sha256=judgment["result_sha256"])
        return {"worker": key, "accounted": True, "count": len(ids)}

    def question(self, key, text):
        require(isinstance(text, str) and text.strip(), "question text required")
        with self.transaction() as state:
            worker = self.worker(state, key)
            require(worker["status"] in {"pending", "running"} and not worker["terminated"],
                    "only a live worker can ask a question")
            require(not worker.get("question") or worker["question"].get("answer"),
                    "answer the outstanding question before asking another")
            worker["question"] = {"id": uuid.uuid4().hex, "text": text, "asked": self.clock.stamp(), "answer": None}
            self.event(state, "worker_question", worker=key, question=worker["question"]["id"])
            return worker["question"]

    def answer(self, key, question, text):
        require(isinstance(text, str) and text.strip(), "answer text required")
        with self.transaction() as state:
            worker = self.worker(state, key)
            pending = worker.get("question")
            require(pending and pending["id"] == question, "answer must name the current question")
            require(not worker["terminated"] and worker["result"] is None, "worker already finished")
            if pending.get("answer"):
                require(pending["answer"] == text, "answer is immutable")
                return pending
            duration = elapsed(pending["asked"], self.clock.stamp())
            require(duration is not None, "clock changed while awaiting answer; reconcile before resuming")
            worker["paused_seconds"] = worker.get("paused_seconds", 0) + duration
            pending["answer"] = text
            self.event(state, "worker_answer", worker=key, question=question, paused_seconds=duration)
            return pending

    def check_review_budget(self, previous, worktree):
        """Fail before expensive verification; prepare checks again under its own lock."""
        current = revision(worktree)
        with self.transaction() as state:
            require(all(findings_accounted(w) for w in state["workers"].values()
                        if w["role"] == "completeness" and w.get("result") and not w["terminated"]),
                    "account for every finding before another review")
            reviews = [w for w in state["workers"].values() if w["role"] == "completeness"]
            if previous:
                require(sum(bool(w.get("previous")) for w in reviews) < 2
                        or self.correction_grant(state, previous, current),
                        "delta attempt budget exhausted; finalize preserves it. Use result-view and budget-request")
            elif state["schema"] >= 3:
                require(sum(not w.get("previous") for w in reviews) < 2,
                        "full completeness attempt budget exhausted; preserve unresolved work and escalate")

    @staticmethod
    def budget_binding(state, previous, current):
        baseline = state["workers"][previous]
        return {"previous": previous, "revision": current, "requirements": state["requirements"],
                "inputs": {n: digest(s["path"]) for n, s in baseline["files"].items()},
                "attempts": sum(bool(w.get("previous")) for w in state["workers"].values())}

    def correction_grant(self, state, previous, current):
        requests = state.get("review_allowances", [])
        for request in reversed(requests):
            if (request.get("authority") and not request.get("worker")
                    and request["session"] == state.get("host_session")
                    and request["binding"] == self.budget_binding(state, previous, current)):
                return request
        return None

    def budget_request(self, previous, worktree, reason, scope):
        require(reason.strip() and scope.strip(), "reason and bounded correction scope required")
        current = revision(worktree)
        require(current["clean"], "commit all coupled corrections before requesting their review")
        with self.transaction() as state:
            require(state.get("host_session"), "bind the actual host session through workflow resume first")
            # One authorized correction review per invocation; a second grant would chain extra deltas.
            require(not any(r.get("authority") for r in state.get("review_allowances", [])),
                    "this invocation already used its one authorized correction review")
            baseline = self.worker(state, previous)
            reviews = [w for w in state["workers"].values() if w["role"] == "completeness" and not w["terminated"]]
            require(reviews and reviews[-1]["id"] == previous and baseline.get("accepted")
                    and baseline["status"] == "consumed" and findings_accounted(baseline),
                    "extension requires latest accepted, accounted completeness result")
            require(baseline["requirements"] == state["requirements"], "changed requirements require full review, not an extension")
            require(not any(not w["terminated"] and not w.get("accepted") for w in state["workers"].values()),
                    "account for outstanding workers before requesting allowance")
            binding = self.budget_binding(state, previous, current)
            require(binding["attempts"] >= 2, "use remaining default delta allowance first")
            request = {"id": uuid.uuid4().hex, "session": state["host_session"], "binding": binding,
                       "reason": reason, "scope": scope, "count": 1, "kind": "delta", "requested": self.clock.stamp()}
            request["approval_phrase"] = "Approve notion-dev " + state["run"] + " correction review " + request["id"]
            state.setdefault("review_allowances", []).append(request)
            self.event(state, "review_allowance_requested", request=request["id"], previous=previous)
        return {"request": request["id"], "kind": "delta", "count": 1, "scope": scope, "reason": reason,
                "head": current["head"], "approval_phrase": request["approval_phrase"],
                "instruction": "Ask the user to send this exact phrase only if they authorize this scope. "
                               "Then budget-extend captures that actual user message. No automatic approval or budget reset."}

    def budget_extend(self, request_id, transcript, session, message_id, worktree):
        from host_capture import user_approval
        current = revision(worktree)
        with self.transaction() as state:
            matches = [r for r in state.get("review_allowances", []) if r["id"] == request_id]
            require(len(matches) == 1, "unknown allowance request")
            request = matches[0]
            require(not request.get("authority") and not request.get("worker"), "allowance already authorized or spent")
            require(session == state.get("host_session") == request["session"], "approval belongs to a different owner")
            require(request["binding"] == self.budget_binding(state, request["binding"]["previous"], current),
                    "review scope/head/inputs/counts changed; request new authorization")
            request["authority"] = user_approval(transcript, session, message_id, request["approval_phrase"],
                                                 request["requested"]["wall"], self.clock.stamp()["wall"])
            self.event(state, "review_allowance_authorized", request=request_id, authority=request["authority"])
        return {"request": request_id, "authorized": True, "kind": "delta", "count": 1,
                "previous": request["binding"]["previous"], "scope": request["scope"]}

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
        require(sum(bool(w.get("previous")) for w in reviews) < 2 or self.correction_grant(state, previous, current),
                "delta attempt budget exhausted; finalize preserves it. Inspect result-view finding IDs; "
                "use budget-request for explicit user authorization of ONE bounded correction review")
        require(baseline["requirements"] == state["requirements"],
                "changed requirements require a full review")
        if (baseline.get("contract_version") or 0) >= 3:
            require("citation_resolutions" in baseline,
                    "resolve available citations before preparing a delta (explicit [] records genuinely missing evidence)")
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
        # THE BYTES `atomic_json` WILL ACTUALLY WRITE for this file. Measuring a form
        # nobody writes was exact about the wrong quantity — on a wide-delta fixture it
        # reported 2005 against a 2048 budget while `delta.json` landed at 2409, 18% over,
        # on precisely the wide changes the bound exists for.
        #
        # So the index is written COMPACTLY and measured compactly, and `prepare` passes
        # `indent=None` for it alone. Indentation is 20% of this file — an ordinary index
        # measures 1700 bytes compact and 2060 indented, over budget before any wide
        # change has been paged — and it buys an agent parsing JSON nothing at all. The
        # budget exists to bound a reviewer's read, so the cheaper serialization is the
        # one that should be read. Its sibling artifacts stay indented: they are not
        # budgeted, and they are the ones a person opens when a receipt is disputed.
        def size():
            return len(json_bytes(index, indent=None))

        def shrink():
            # Shrink the LARGEST inlined list, repeatedly, so one wide change does not
            # cost every small section its detail. First cut is to one page; after that
            # it halves, because a fixed page can still exceed the budget on its own. The
            # inlined list stays a PREFIX of page 1, and `incomplete` names every list
            # that was cut, so a short preview is never mistakable for the whole section.
            while size() > budget:
                name = max(sections, key=lambda n: (len(index[n]), n))
                length = len(index[name])
                if length == 0:
                    return
                index[name] = index[name][:min(page, length // 2)]
                if len(index[name]) != len(sections[name]) and name not in incomplete:
                    incomplete.append(name)

        # One counts map and one list of truncated names, not a metadata object per
        # section: at six sections that ceremony cost more of the budget than the
        # content it described. `pages` is ceil(count / page_items); `section` returns it.
        incomplete = []
        index["sections"] = {"page_items": page, "incomplete": incomplete,
                             "counts": {name: len(items) for name, items in sections.items()}}
        for name, items in sections.items():
            index[name] = list(items)
        # The three self-describing keys are present for every measurement, because
        # writing them changes the size they describe. Their values then reach a fixed
        # point — only one integer's digit width and two booleans' spellings vary, so it
        # settles in a pass or two — and shrinking runs again inside the loop, in case a
        # value that grew pushed the file back over. On exit `index_bytes` equals the
        # file's real size, rather than being exact about a quantity nobody reads.
        index["index_bytes"], index["within_budget"], index["complete"] = 0, False, False
        for _ in range(8):
            shrink()
            index["complete"] = not incomplete
            measured = size()
            if measured == index["index_bytes"] and index["within_budget"] == (measured <= budget):
                break
            index["index_bytes"] = measured
            index["within_budget"] = measured <= budget
        return index

    @staticmethod
    def delta_publication(directory, baseline):
        """Small prior-fact index; the complete result remains available on demand."""
        result = baseline["result"]
        sections = {}
        for name in ("code_review", "blocking_findings", "claims", "caveats", "triage", "recording"):
            path = directory / ("prior-" + name + ".json")
            atomic_json(path, result.get(name))
            sections[name] = {"path": str(path), "sha256": digest(path)}
        prior = directory / "prior-judgments.json"
        atomic_json(prior, {"requirements": result["requirements"], "sections": sections})
        return {"version": 1, "baseline": baseline["id"],
                "baseline_sha256": digest_bytes(json_bytes(result)),
                "prior": {"path": str(prior), "sha256": digest(prior)},
                "rules": "Read delta.json and prior judgments first; retrieve prior sections only when needed. Supply report, requirements_complete, delta_review and any required correction_review. Under delta_result supply baseline_sha256, changed_requirements, reused_requirement_ids, updated_sections and reused_sections. Partition EVERY requirement and section exactly once. Reuse requirements only with current evidence and independently checked indirect effects. Replace affected sections in full; never clear findings implicitly. Runtime assembles the complete result; no duplicate narrative. Full result publication remains supported."}

    def expand_delta(self, state, worker, submitted):
        publication = worker.get("delta_publication")
        require(publication and worker.get("contract_version", 0) >= 4, "compact delta not supported by this packet")
        require(set(submitted) <= {"report", "requirements_complete", "delta_review", "correction_review", "delta_result"},
                "do not mix compact and complete result fields")
        delta = submitted["delta_result"]
        baseline = self.worker(state, worker["previous"])
        require(baseline.get("accepted") and not baseline["terminated"], "accepted baseline required")
        previous = baseline["result"]
        require(set(previous) <= {"report", "requirements_complete", "requirements", "blocking_findings",
                "code_review", "claims", "caveats", "triage", "recording", "correction_review", "delta_review"},
                "unknown baseline fields require complete publication, not implicit dropping")
        require(isinstance(delta, dict) and delta.get("baseline_sha256") == publication["baseline_sha256"]
                == digest_bytes(json_bytes(previous)), "compact delta baseline changed")
        prior = publication["prior"]
        require(digest(prior["path"]) == prior["sha256"], "prior judgments changed")
        for reference in read_json(prior["path"])["sections"].values():
            require(digest(reference["path"]) == reference["sha256"], "prior section changed")
        changed = delta.get("changed_requirements")
        reused = delta.get("reused_requirement_ids")
        require(isinstance(changed, list) and all(isinstance(v, dict) for v in changed)
                and isinstance(reused, list) and all(isinstance(v, str) for v in reused),
                "compact delta needs explicit changed and reused requirements")
        ids = [v.get("id") for v in changed] + reused
        expected = [v["id"] for v in worker["requirements"]["items"]]
        require(all(isinstance(v, str) for v in ids) and len(ids) == len(set(ids))
                and set(ids) == set(expected), "compact delta must partition every requirement exactly once")
        index = read_json(worker["delta"]["path"])
        sections = read_json(self.ref_path(index, index["sections_file"]))
        current = {r["id"]: r["applicability"] for r in self.evidence_records(baseline, sections["changed_paths"])}
        require(all(current.get(i) == "current" for i in reused), "stale/unknown evidence cannot be inherited")
        updates, carry = delta.get("updated_sections"), delta.get("reused_sections")
        names = {"code_review", "blocking_findings", "claims", "caveats", "triage", "recording"}
        require(isinstance(updates, dict) and isinstance(carry, list) and all(isinstance(n, str) for n in carry)
                and len(carry) == len(set(carry)) and not set(updates) & set(carry)
                and set(updates) | set(carry) == names, "compact delta must partition all audit/recording sections")
        for name in carry:
            old = previous.get(name)
            require(old is not None, "missing baseline section cannot be inherited")
            if name in AUDIT_FIELDS:
                require(old["status"] == "checked" and not any(f["blocking"] for f in old["findings"]),
                        "unverified/blocking audit must be rechecked")
            if name == "code_review": require(review_pass(baseline, old), "nonclean code review must be rechecked")
            if name == "blocking_findings": require(not old, "unresolved findings cannot be inherited as clean")
        result = {name: previous[name] if name in carry else updates[name] for name in names}
        # A legacy clean verdict already asserts no code finding; preserve it without
        # another review just to add an empty field. Ambiguous legacy findings/audits
        # require explicit reviewer updates, never inferred advisory classifications.
        if worker.get("contract_version", 0) >= 5 and "code_review" in carry:
            result["code_review"] = {"findings": [], **result["code_review"]}
        old_verdicts = {v["id"]: v for v in previous["requirements"]}
        verdicts = {v["id"]: v for v in changed}
        verdicts.update({i: old_verdicts[i] for i in reused})
        result.update({k: v for k, v in submitted.items() if k != "delta_result"})
        result["requirements"] = [verdicts[i] for i in expected]
        if worker["result"] is None:
            worker["inherited_requirements"] = reused
            worker["citation_resolutions"] = [c for c in baseline.get("citation_resolutions", []) if c["id"] in reused]
        return result

    def delta_index(self, baseline, current, snapshots, directory):
        """The compact change/reuse index a delta reviewer reads first."""
        worker = baseline["worker"]
        old_inputs = worker["files"]
        changed_inputs = [name for name in sorted(set(old_inputs) | set(snapshots))
                          if old_inputs.get(name, {}).get("sha256") != snapshots.get(name, {}).get("sha256")]
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
        # Only changed inputs, read from owned frozen snapshots, never the overwritten
        # author's path. This keeps PR-only review from rediscovering its own diff.
        changes = []
        for name in changed_inputs:
            before, after = old_inputs.get(name), snapshots.get(name)
            row = {"name": name, "before": before, "after": after}
            try:
                def frozen(source):
                    if not source: return ""
                    path = source.get("snapshot", source["path"])
                    require(digest(path) == source["sha256"], "changed input snapshot no longer matches")
                    return Path(path).read_text(encoding="utf-8")
                old, new = frozen(before), frozen(after)
                lines = difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                    fromfile="before/" + name, tofile="after/" + name)
                # An unterminated last line would fuse with the next record, as in `-old+new`.
                row["diff"] = "".join(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
                                      for line in lines)
                if old != new and not row["diff"]:
                    row["instruction"] = "Compare complete snapshots; text representation differs."
            except UnicodeError:
                row["instruction"] = "Non-UTF-8 input: inspect both complete binary snapshots."
            changes.append(row)
        # Add to the existing side index, not the bounded top-level manifest.
        index["inputs"] = side("delta-inputs.json", {"changes": changes, "before": old_inputs, "after": snapshots})
        return self.bound_index(index, sections)

    @staticmethod
    def unread_delta_sections(worker):
        """Sections the index shortened that this reviewer never paged in full.

        `references/runtime.md` says a truncated section and an unread page are not
        complete input — and until this existed that was prose with a recorded event and
        no gate, so a reviewer could read a 50-item preview of a 141-item change, declare
        the scope `sufficient`, and pass the merge gate having never seen the rest. This
        repo's own standard is that a claim is worth what re-checks it; this is the check.

        Only pages are required, never a judgement: reading them all is the floor, and
        what the reviewer concludes from them remains its own independent call.
        """
        reference = worker.get("delta")
        if not reference or not Path(reference["path"]).is_file():
            return []
        index = read_json(reference["path"])
        sections = index.get("sections") or {}
        size = sections.get("page_items") or PAGE_ITEMS
        read = worker.get("sections_read") or {}
        missing = []
        for name in sections.get("incomplete", []):
            count = (sections.get("counts") or {}).get(name, 0)
            pages = max(1, -(-count // size))
            if not set(range(1, pages + 1)) <= set(read.get(name, [])):
                missing.append(name)
        return sorted(missing)

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
            # Recorded on the WORKER, not only as an event, so the merge gate can decide
            # from the worker alone -- the same place every other delta receipt lives.
            read = worker.setdefault("sections_read", {}).setdefault(name, [])
            if page not in read:
                read.append(page)
                read.sort()
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
        if worker.get("contract_version", 0) and worker["contract_version"] >= 3:
            if any(not Path(d["path"]).is_file() or digest(d["path"]) != d["sha256"]
                   for d in worker.get("correction_dependencies", [])):
                return False
            verdicts = ["CLEAN"]  # One authority for new contracts; prose is only a view.
        return (review.get("id") == worker["correction"]["id"]
                and review.get("manifest_sha256") == worker["correction_manifest"]["sha256"]
                and review_pass(worker, review) and review.get("blocking_findings") == []
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
        if worker.get("delta_publication"):
            prior = worker["delta_publication"]["prior"]
            require(digest(prior["path"]) == prior["sha256"], "prior judgments changed")
            for reference in read_json(prior["path"])["sections"].values():
                require(digest(reference["path"]) == reference["sha256"], "prior section changed")
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
            require(not worker.get("question") or worker["question"].get("answer"),
                    "answer the outstanding question before publication")
            if "delta_result" in result:
                result = self.expand_delta(state, worker, result)
            validate_result(worker, result)
            result = render_result(worker, result)
            self.validate_packet(worker)
            self.validate_delta(worker, result)
            if worker["result"] is not None:
                require(worker["result"] == result, "result is immutable; create a new attempt for a revision")
                return {"worker": key, "status": worker["status"], "artifact": self.result_artifact(worker)}
            require(worker["status"] in {"pending", "running", "timed_out", "cancellation_requested"},
                    "worker cannot publish in its current state")
            if worker.get("contract_version", 0) and worker["contract_version"] >= 3 and not worker.get("reused_correction"):
                worker["correction_dependencies"] = [{"path": str(Path(p).resolve()), "sha256": digest(p)}
                    for p in result.get("correction_review", {}).get("depends_on", [])]
            worker.update(result=result, status="result_ready", result_ready=self.clock.stamp())
            artifact = self.result_artifact(worker)
            # Sizes, not bodies. Knowing a report arrived at 40KB is what identifies
            # prose duplicated into both `report` and the per-criterion records; copying
            # the prose here to measure it would be the same mistake one layer down.
            self.event(state, "worker_result_ready", worker=key, role=worker["role"],
                       result_bytes=len(json.dumps(result, ensure_ascii=False).encode("utf-8")),
                       report_bytes=len(result["report"].encode("utf-8")))
        return {"worker": key, "status": "result_ready", "artifact": artifact}

    def inspect(self, key):
        with self.transaction() as state:
            worker = self.worker(state, key)
            duration = elapsed(worker["started"], self.clock.stamp())
            if duration is not None:
                duration = max(0, duration - worker.get("paused_seconds", 0))
            question = worker.get("question")
            needs_input = question and not question.get("answer")
            if not needs_input and worker["status"] in {"pending", "running"} and duration is not None and duration >= worker["timeout_seconds"]:
                worker["status"] = "timed_out"
                self.event(state, "worker_timed_out", worker=key)
            return {"worker": key, "status": "needs_input" if needs_input and not worker["terminated"] else worker["status"], "elapsed_seconds": duration,
                    "question": question,
                    "clock_uncertain": duration is None, "terminated": worker["terminated"],
                    "accepted": worker.get("accepted", False),
                    "result_available": worker["result"] is not None}

    def wait(self, key, seconds=30):
        require(math.isfinite(seconds) and 0 <= seconds <= 60, "one wait must be between 0 and 60 seconds")
        # A second shell waiter fails quickly instead of multiplying background jobs.
        with self.transaction() as state:
            self.worker(state, key)
        with state_lock(self.path.parent / ("worker-" + key + ".wait.lock"), 0.05):
            with self.transaction() as state:
                self.event(state, "worker_wait", worker=key, seconds=seconds)
            deadline = time.monotonic() + seconds
            while True:
                result = self.inspect(key)
                if result["clock_uncertain"] or result["status"] not in {"pending", "running"} or time.monotonic() >= deadline:
                    return result
                time.sleep(min(0.25, max(0, deadline - time.monotonic())))

    def consume(self, key, summary=False):
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
            artifact = self.result_artifact(worker)
        if summary:
            return {"status": "consumed", **self.result_view(key)}
        return {"worker": key, "status": "consumed", "result": worker["result"], "artifact": artifact}

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
            validate_result(worker, worker["result"])
            require(findings_accounted(worker), "unaccounted findings: read result-view pages and judge-findings before accept")
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
        # `or []`, not `.get(…, [])`: a present-but-null `requirements` returns None from
        # the latter, and iterating it raised a TypeError out of `summary()` — breaking
        # the report on exactly the invalid-result path the report exists to record. Any
        # non-list value normalizes to no verdicts, which the strict check below then
        # reads as `blocked` for every requirement. Fail closed and keep reporting.
        recorded = (worker.get("result") or {}).get("requirements")
        verdicts = {v.get("id"): v.get("verdict")
                    for v in (recorded if isinstance(recorded, list) else [])
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
            # Fail closed on anything that is not exactly `met`, INCLUDING an absent or
            # null verdict. A contract-invalid report is deliberately publishable so the
            # parent can judge it, so "the ID is missing from the verdict list" is a case
            # that really occurs — and treating a verdict nobody gave as a verdict of
            # `met` advertised it to the next delta reviewer as reuse-applicable. The
            # merge gate catches missing coverage separately; this is the reuse path,
            # which is the one that decides what gets re-derived.
            verdict = verdicts.get(item)
            if verdict != "met":
                reasons.append("baseline verdict is %s, not 'met'"
                               % ("absent" if verdict is None else "'%s'" % verdict))
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
            reasons = self.readiness(state) + self.ticket_freshness(state, worker)
            verification_reasons = self.verification_reasons(state, worker.get("verification_ids", []), current)
            reasons.extend(verification_reasons)
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
            if worker.get("contract_version"):
                if not worker.get("accepted"):
                    reasons.append("parent has not accepted the independent result")
                validate_result(worker, result) if result else None
                if not review_pass(worker, result.get("code_review", {})):
                    reasons.append("independent code-quality review is not clean")
                if worker["contract_version"] >= 2 and result and not audits_pass(result):
                    reasons.append("claims/caveats/triage audits are unverified or have blocking findings")
            if not findings_accounted(worker):
                reasons.append("unaccounted findings: use result-view and judge-findings")
            if not self.correction_reviewed(state, worker, result):
                reasons.append("corrective code needs an independent clean correction review of the exact manifest")
            if worker.get("previous"):
                self.validate_delta(worker, result)
                if result["delta_review"]["disposition"] != "sufficient":
                    reasons.append("delta reviewer requires full review")
                else:
                    # Only `sufficient` makes this claim. An honest escalation says the
                    # scope was NOT bounded, which needs no complete input to say.
                    for name in self.unread_delta_sections(worker):
                        reasons.append(f"delta section was never retrieved in full: {name}")
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
        invalidations = [{"kind": "external-review-evidence", "path": d["path"],
                          "recovery": "Recover the verified immutable artifact or review affected evidence/claims; do not automatically restart full review."}
                         for d in worker.get("correction_dependencies", [])
                         if not Path(d["path"]).is_file() or digest(d["path"]) != d["sha256"]]
        return {"passed": not reasons, "reasons": reasons, "head": current["head"], "invalidations": invalidations}

    @staticmethod
    def declared_inputs(paths):
        """Hash the non-Git inputs a caller says its command reads."""
        records = []
        for item in paths or ():
            source = Path(item).resolve()
            require(source.is_file(),
                    "declared verification input must be an existing file: " + str(source))
            records.append({"path": str(source), "sha256": digest(source)})
        records.sort(key=lambda record: record["path"])
        return records

    @staticmethod
    def receipt_applicable(receipt, revision_now, signature, declared=None):
        """Why a stored receipt may or may not stand in for running the command again.

        Byte equality of a log establishes that the receipt is intact, never that it
        still describes the current tree — so the revision fingerprint, which includes
        dirty and untracked content, and the toolchain signature are both part of the
        answer. A receipt whose command modified the tree is not reusable at all: it
        never described a state that survived its own run.

        **What the fingerprint and the signature cover is the whole warranty, and it is
        narrower than "the command's inputs".** `revision` builds its fingerprint with
        `--exclude-standard`, so ignored files are outside it; the signature is four
        toolchain facts and no environment values. A `--shell-command` is arbitrary and
        may read either. So a caller declares the rest with `--depends`, exactly as a
        citation declares `depends_on`, and those are hashed into the receipt and
        rechecked here. A command with an input that CANNOT be declared — an env value,
        a clock, a network service — must simply not be given `--reuse`: omitting the
        flag always runs the command, and that is the honest answer for that case.
        """
        reasons = []
        recorded = receipt.get("inputs", [])
        reasons.extend(receipt.get("output_errors", []))
        for artifact in receipt.get("outputs", []):
            if not Path(artifact["path"]).is_file() or digest(artifact["path"]) != artifact["sha256"]:
                reasons.append("verification archive missing or changed: " + artifact["path"])
        for entry in recorded:
            source = Path(entry["path"])
            if not source.is_file():
                reasons.append("declared input is missing: " + entry["path"])
            elif digest(source) != entry["sha256"]:
                reasons.append("declared input changed: " + entry["path"])
        # Declaring MORE than the receipt did is not a match: the extra input was never
        # covered when that receipt was earned, so reusing it would answer a narrower
        # question than the caller asked.
        if declared is not None and \
                [e["path"] for e in declared] != [e["path"] for e in recorded]:
            reasons.append("this call declares a different input set than the receipt")
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

    @classmethod
    def receipt_reusable(cls, receipt, revision_now, signature, declared=None):
        """Applicable AND passing. One predicate, so the index cannot contradict the path.

        `applicable` and `reusable` are different questions and the index reports both:
        a failed receipt is perfectly applicable evidence — it says this command fails on
        this tree — it is simply not reusable as a pass. Collapsing them would lose that;
        letting the reuse path apply its own extra condition, which is what it did, let
        the index advertise a failed receipt as reusable while `verify --reuse` correctly
        skipped it.
        """
        reasons = list(cls.receipt_applicable(receipt, revision_now, signature, declared))
        if receipt.get("exit_code") != 0:
            reasons.append("the command failed when this receipt was produced")
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
                reuse_reasons = self.verification_reasons(state, [receipt["verification"]], current) if current else \
                    list(reasons)
                # `{**a, **b}`, not `a | b`: the merge operator is 3.9 and this plugin
                # supports 3.8. verify-python-floor.sh is a smoke filter that does not
                # see this form, so the floor job is what would have caught it.
                items.append({**{k: receipt.get(k) for k in
                                 ("verification", "command_sha256", "exit_code",
                                  "duration_seconds", "log", "log_sha256", "outputs", "output_errors")},
                              "revision": receipt["revision"]["fingerprint"],
                              "environment": receipt.get("environment", {}).get("signature"),
                              "started": receipt.get("started", {}).get("utc"),
                              "declared_inputs": [e["path"] for e in receipt.get("inputs", [])],
                              "applicable": not reasons, "reasons": reasons,
                              "reusable": not reuse_reasons, "reuse_reasons": reuse_reasons})
            self.event(state, "verification_indexed", count=len(items))
        return {"verifications": items, "count": len(items),
                "environment": signature,
                "coverage": "receipts recorded by this runtime only; a command run outside it "
                            "leaves no receipt and is unknown, never passed"}

    @classmethod
    def verification_reasons(cls, state, keys, current):
        reasons = []
        receipts = state.get("verifications", [])
        signature = environment_signature()
        for key in keys:
            receipt = next((r for r in receipts if r["verification"] == key), None)
            if not receipt:
                reasons.append("verification receipt missing: " + key)
                continue
            reasons.extend(cls.receipt_reusable(receipt, current, signature))
            # A later failure on this same source/command cannot hide behind an old pass.
            later = [r for r in receipts[receipts.index(receipt) + 1:]
                     if r["command_sha256"] == receipt["command_sha256"]
                     and r["revision"] == current]
            if any(r["exit_code"] != 0 or r["changed_during_verification"] or r.get("output_errors") for r in later):
                reasons.append("later verification contradicted reviewed evidence: " + key)
            if any(r.get("outputs") and r["outputs"] != receipt.get("outputs", []) for r in later):
                reasons.append("generated evidence changed; recheck affected claims: " + key)
        return reasons

    def verify(self, worktree, command, reuse=False, depends=(), outputs=()):
        before = revision(worktree)
        signature = environment_signature()
        declared = self.declared_inputs(depends)
        output_paths = sorted({str(Path(worktree, p).resolve()) for p in outputs})
        command_hash = digest_bytes(command.encode("utf-8"))
        if reuse:
            with self.transaction() as state:
                for receipt in reversed(state.get("verifications", [])):
                    if receipt["command_sha256"] != command_hash:
                        continue
                    if (receipt["revision"] == before and receipt.get("environment") == signature
                            and (receipt["exit_code"] != 0 or receipt.get("output_errors") or receipt.get("changed_during_verification"))):
                        break  # Do not skip a newer failed run to resurrect an older pass.
                    if self.receipt_reusable(receipt, before, signature, declared):
                        continue
                    if self.verification_reasons(state, [receipt["verification"]], before):
                        continue
                    if [o["source"] for o in receipt.get("outputs", [])] != output_paths:
                        continue
                    self.event(state, "verification_reused", verification=receipt["verification"],
                               command_sha256=command_hash)
                    return {**receipt, "reused": True}
        key = uuid.uuid4().hex
        log = self.path.parent / f"verify-{key}.log"
        started = self.clock.stamp()
        output_before = {p: Path(p).stat().st_mtime_ns if Path(p).is_file() else None for p in output_paths}
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
                   "environment": signature, "started": started, "inputs": declared,
                   "changed_during_verification": revision(worktree) != before}
        receipt["outputs"] = []
        receipt["output_errors"] = []
        for source in output_paths:
            path = Path(source)
            if not path.is_file() or path.stat().st_mtime_ns == output_before[source]:
                receipt["output_errors"].append("declared output was not regenerated: " + source)
                continue
            raw = path.read_bytes()
            sha = digest_bytes(raw)
            saved = self.path.parent / "verification-evidence" / sha
            saved.parent.mkdir(parents=True, exist_ok=True)
            if saved.exists(): require(digest(saved) == sha, "verification archive changed")
            else: saved.write_bytes(raw)
            receipt["outputs"].append({"source": source, "path": str(saved), "sha256": sha})
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
            require(not state.get("completed"), "resume explicitly before recording in a completed invocation")
            if state["schema"] >= 3:
                previous = [e for e in state["record_journal"] if e["operation"] == operation]
                if previous:
                    latest = previous[-1]
                    require(latest["target"] == target and latest.get("data_sha256") == data_sha256,
                            "record outcome must preserve planned target and payload digest")
                    require(latest["outcome"] != "confirmed" or outcome == "confirmed",
                            "confirmed operation is terminal; do not reset it to replay side effects")
                    require(outcome != "planned" or latest["outcome"] == "planned",
                            "an executed operation cannot be reset to planned; reconcile its outcome")
                    if outcome == "attempted":
                        require(latest["outcome"] in {"planned", "failed"},
                                "completed or uncertain operation cannot be blindly retried; reconcile first")
            state.setdefault("record_journal", []).append(entry)
            self.event(state, "record_operation", operation=operation, outcome=outcome,
                       provider_id=provider_id)
        return entry

    def record_check(self, operation, target, payload):
        """Plan a stable operation or report the reconciliation needed before a retry."""
        require(operation.strip() and target.strip(), "operation and target required")
        payload_hash = digest(payload)
        with self.transaction() as state:
            previous = [e for e in state["record_journal"] if e["operation"] == operation]
            if previous:
                latest = previous[-1]
                require(latest["target"] == target and latest.get("data_sha256") == payload_hash,
                        "record operation identity changed; reconcile, then use a new explicit operation revision")
                action = ("skip" if latest["outcome"] == "confirmed" else "reconcile"
                          if latest["outcome"] in {"attempted", "unknown-outcome"} else "execute")
            else:
                require(not state.get("completed"), "resume explicitly before planning new recording")
                latest = {"operation": operation, "target": target, "data_sha256": payload_hash,
                          "provider_id": None, "outcome": "planned", **self.clock.stamp()}
                state["record_journal"].append(latest)
                self.event(state, "record_operation", operation=operation, outcome="planned")
                action = "execute"
            return {"operation": operation, "action": action, "data_sha256": payload_hash,
                    "provider_id": latest.get("provider_id"), "target": target}

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
                       # From `result_ready`, not from `started` — the same baseline
                       # `consume` uses for the identically named field. Measuring from
                       # worker start folds the agent's whole execution into the number,
                       # so a worker that thought for 30 seconds and was read instantly
                       # reported 30 seconds of "delivery lag": the one quantity this
                       # probe exists to measure, distorted by the one thing it is not.
                       "delivery_lag_seconds": elapsed(worker["result_ready"], self.clock.stamp())
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
            # An operation's CURRENT outcome is its latest entry, not every entry it ever
            # had. The journal is append-only, so the ordinary lifecycle — `attempted`,
            # then `confirmed` — left the operation permanently listed as unconfirmed, and
            # a run that reconciled everything still reported itself incompletely recorded.
            # A gate that cries wolf on a clean run is one people learn to skip, which is
            # the opposite of what this list is for. Later entries override earlier ones,
            # so a retry after a confirmation correctly puts the operation back on the list.
            current_outcome = {}
            for entry in journal:
                current_outcome[entry["operation"]] = entry["outcome"]
            # The old ledger's fields are kept verbatim -- they are still the right
            # counters -- but they were printed at the top level where they read as
            # whole-run totals. They only ever covered what this runtime observed:
            # a command run outside `verify`, or an agent never registered as a worker,
            # is absent from every number here. `end_to_end` says so in the output.
            return {"run": state["run"], "stage": state["stage"], "workers": workers,
                    "review_budget": {"defaults": {"full": 2, "delta": 2},
                        "extensions": [{k: r.get(k) for k in ("id", "kind", "count", "reason", "scope", "authority", "worker")}
                                       for r in state.get("review_allowances", [])],
                        "cost": "Cumulative attempts, events and stage times retained; model tokens require telemetry, not inferred here."},
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
                        "worker_waits": sum(e["kind"] == "worker_wait" for e in state["events"]),
                        "worker_questions": sum(e["kind"] == "worker_question" for e in state["events"]),
                        "question_wait_seconds": sum(e.get("paused_seconds", 0) for e in state["events"]
                                                     if e["kind"] == "worker_answer"),
                        "evidence_by_worker": evidence,
                        # Attempt counts stay per entry: how many attempts an operation
                        # took is exactly what a journal is for. Only the unconfirmed
                        # LIST collapses, because that one answers "what is still open".
                        "record_operations": dict(Counter(e["outcome"] for e in journal)),
                        "unconfirmed_record_operations": sorted(
                            name for name, outcome in current_outcome.items()
                            if outcome != "confirmed"),
                        "correction_causes": (state.get("correction") or {}).get("reasons", []),
                        "stages_measured": [s["stage"] for s in spans]},
                    "model_usage": "unknown until raw telemetry is imported; never inferred from characters"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, help="per-invocation state.json outside disposable worktrees")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("init"); p.add_argument("--run", required=True); p.add_argument("--ticket", required=True)
    p.add_argument("--legacy", action="store_true", help="only for an explicitly selected legacy build flow; never changes an existing invocation")
    p = commands.add_parser("stage"); p.add_argument("name")
    p = commands.add_parser("requirements"); p.add_argument("--source", required=True); p.add_argument("--inventory", required=True)
    p = commands.add_parser("ticket-source"); p.add_argument("--response", required=True); p.add_argument("--config", required=True)
    p = commands.add_parser("capture-ticket"); p.add_argument("--transcript", default=os.environ.get("NOTION_DEV_TRANSCRIPT"))
    p.add_argument("--session", default=os.environ.get("NOTION_DEV_SESSION_ID", "")); p.add_argument("--call-id"); p.add_argument("--page")
    p.add_argument("--config"); p.add_argument("--worker"); p.add_argument("--request")
    p = commands.add_parser("refresh-ticket"); p.add_argument("--worker", required=True)
    p.add_argument("--response"); p.add_argument("--request"); p.add_argument("--call-id")
    commands.add_parser("ready")
    p = commands.add_parser("correction-needed"); p.add_argument("--worktree", required=True)
    p.add_argument("--reason", help="what made this correction necessary; recorded, never inferred")
    p = commands.add_parser("prepare"); p.add_argument("--role", required=True); p.add_argument("--file", action="append", default=[])
    p.add_argument("--worktree"); p.add_argument("--timeout", type=float, default=900)
    p.add_argument("--previous"); p.add_argument("--slot")
    p.add_argument("--remove-input", action="append", default=[])
    p = commands.add_parser("budget-request")
    p.add_argument("--previous", required=True); p.add_argument("--worktree", required=True)
    p.add_argument("--reason", required=True); p.add_argument("--scope", required=True)
    p = commands.add_parser("budget-extend")
    p.add_argument("--request", required=True); p.add_argument("--worktree", required=True)
    p.add_argument("--transcript", required=True); p.add_argument("--session", required=True)
    p.add_argument("--message-id", help="optional actual user UUID; otherwise select the exact approval phrase")
    for name in ("attach", "publish", "inspect", "wait", "consume", "accept", "resolve-citations",
                 "evidence", "section", "result-view", "judge-findings", "probe", "end-worker", "yield", "merge-gate", "question", "answer"):
        p = commands.add_parser(name); p.add_argument("--worker", required=True)
        if name == "attach": p.add_argument("--agent", required=True)
        if name == "publish": p.add_argument("--result", required=True)
        if name == "consume": p.add_argument("--summary", action="store_true")
        if name == "result-view":
            p.add_argument("--section"); p.add_argument("--page", type=int)
        if name == "judge-findings": p.add_argument("--judgments", required=True)
        if name in {"question", "answer"}: p.add_argument("--text", required=True)
        if name == "answer": p.add_argument("--question", required=True)
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
    p.add_argument("--output", action="append", default=[], help="generated report path to archive after execution")
    p.add_argument("--reuse", action="store_true",
                   help="return an applicable existing receipt instead of rerunning; never caches a stale one")
    p.add_argument("--depends", action="append", default=[],
                   help="a non-Git input this command reads (ignored file, generated artifact); "
                        "hashed into the receipt and rechecked before any reuse. Repeatable.")
    p = commands.add_parser("verifications"); p.add_argument("--worktree")
    p = commands.add_parser("record-op")
    p.add_argument("--operation", required=True); p.add_argument("--target", required=True)
    p.add_argument("--outcome", required=True, choices=RECORD_OUTCOMES)
    p.add_argument("--provider-id"); p.add_argument("--digest")
    p = commands.add_parser("record-check")
    p.add_argument("--operation", required=True); p.add_argument("--target", required=True)
    p.add_argument("--payload", required=True)
    commands.add_parser("summary")
    args = parser.parse_args()
    runtime = Runtime(args.state)
    name = args.command
    if name == "init": result = runtime.init(args.run, args.ticket, args.legacy)
    elif name == "stage": result = runtime.stage(args.name)
    elif name == "requirements": result = runtime.requirements(args.source, read_json(args.inventory))
    elif name == "ticket-source": result = runtime.ticket_source(args.response, args.config)
    elif name == "capture-ticket": result = runtime.capture_ticket(args.transcript, args.session, args.call_id, args.config, args.worker, args.request, args.page)
    elif name == "refresh-ticket": result = runtime.refresh_ticket(args.worker, args.response, args.request, args.call_id)
    elif name == "ready": result = runtime.ready()
    elif name == "correction-needed": result = runtime.correction_needed(args.worktree, args.reason)
    elif name == "budget-request": result = runtime.budget_request(args.previous, args.worktree, args.reason, args.scope)
    elif name == "budget-extend": result = runtime.budget_extend(args.request, args.transcript, args.session, args.message_id, args.worktree)
    elif name == "prepare":
        files = {}
        for item in args.file:
            require("=" in item, "--file must be name=path")
            key, path = item.split("=", 1)
            require(key and key not in files, "unique artifact name required")
            files[key] = path
        result = runtime.prepare(args.role, files, args.worktree, args.timeout, args.previous, args.slot, args.remove_input)
    elif name == "attach": result = runtime.attach(args.worker, args.agent)
    elif name == "publish": result = runtime.publish(args.worker, read_json(args.result))
    elif name == "question": result = runtime.question(args.worker, args.text)
    elif name == "answer": result = runtime.answer(args.worker, args.question, args.text)
    elif name == "inspect": result = runtime.inspect(args.worker)
    elif name == "wait": result = runtime.wait(args.worker, args.seconds)
    elif name == "consume": result = runtime.consume(args.worker, args.summary)
    elif name == "result-view": result = runtime.result_view(args.worker, args.section, args.page)
    elif name == "judge-findings": result = runtime.judge_findings(args.worker, read_json(args.judgments))
    elif name == "accept": result = runtime.accept(args.worker)
    elif name == "resolve-citations": result = runtime.resolve_citations(args.worker, read_json(args.citations))
    elif name == "evidence": result = runtime.evidence(args.worker)
    elif name == "section": result = runtime.section(args.worker, args.name, args.page)
    elif name == "probe": result = runtime.probe(args.worker, args.expect)
    elif name == "end-worker": result = runtime.end_worker(args.worker, args.reason, args.confirmed, args.host_failed, args.user_requested, args.invalid_result)
    elif name == "yield": result = runtime.yield_once(args.worker, args.marker, args.session)
    elif name == "merge-gate": result = runtime.merge_gate(args.worker, args.worktree)
    elif name == "verify": result = runtime.verify(args.worktree, args.shell_command, args.reuse, args.depends, args.output)
    elif name == "verifications": result = runtime.verifications(args.worktree)
    elif name == "record-op":
        result = runtime.record_op(args.operation, args.target, args.outcome, args.provider_id, args.digest)
    elif name == "record-check": result = runtime.record_check(args.operation, args.target, args.payload)
    else: result = runtime.summary()
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    if result.get("passed") is False or (name == "wait" and result["status"] not in {"result_ready", "consumed"}):
        return 1
    if name == "verify" and (result["exit_code"] != 0 or result["changed_during_verification"] or result.get("output_errors")):
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
