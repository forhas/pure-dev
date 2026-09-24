#!/usr/bin/env python3
"""Small local workflow operations. No Notion/GitHub calls, credentials or merge authority.

Run with knowledge.python. Provider writes remain with the host's authorized tools.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

from runtime import Runtime, Invalid, atomic_json, git, read_json, require, state_lock


RECORD_PAYLOAD_VERSION = 3
MAX_EVIDENCE_BYTES = 4 * 1024 * 1024
CHILD_SEPARATOR = ":child:"


def snapshot_evidence(value, field, facts_dir):
    """Embed the named evidence, not a reference a later write would dereference.

    No recursive file crawling: nested references in a receipt are provenance, not
    instructions to copy project files/secrets. Large material stays out of plan stdout.
    """
    if isinstance(value, (dict, list)):
        return value
    require(isinstance(value, str) and value.strip(), field + " requires evidence or an existing file")
    if field == "requirements" and value == "unknown":
        return {"status": "unknown"}
    source = Path(value)
    if not source.is_absolute():
        source = facts_dir / source
    require(source.is_file(), field + " evidence path is missing: " + str(source))
    with source.open("rb") as stream:
        data = stream.read(MAX_EVIDENCE_BYTES + 1)
    require(len(data) <= MAX_EVIDENCE_BYTES, field + " evidence exceeds 4 MiB; supply scoped evidence, never truncate")
    return {"format": "utf-8", "content": data.decode("utf-8"), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def record_kind(operation, kinds):
    if operation in kinds:
        return kinds[operation]
    parent, separator, name = operation.rpartition(CHILD_SEPARATOR)
    if separator and parent in kinds and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", name):
        return kinds[parent]
    return None  # Unknown/legacy ids remain required; never guess ancestry.


def save_record_payload(path, kind, data, version=2):
    payload = {"record_payload_version": version, "kind": kind, "data": data}
    if path.exists():
        require(read_json(path) == payload,
                "record payload changed or legacy payload: reconcile before an explicit operation revision")
    else:
        atomic_json(path, payload)


def child_payload_path(directory, operation):
    return directory / ("child-" + hashlib.sha256(operation.encode("utf-8")).hexdigest() + ".json")


def json_input(path):
    """A real UTF-8 file or stdin works with native Windows Python; /dev/fd does not."""
    if path == "-":
        return json.load(sys.stdin)
    require(not str(path).startswith(("/dev/fd/", "/proc/")), "use a real JSON file or --payload - with stdin, not process substitution")
    return read_json(path)


def evidence_view(snapshot, directory, canonical_review=None):
    """One content-addressed full archive and one complete provider-facing value.

    Only a version-3 structured review has canonical recording facts that replace
    narrative. Unknown fields/formats are retained, never silently summarized/cut.
    """
    raw = json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode("utf-8")
    identity = hashlib.sha256(raw).hexdigest()
    path = directory / "evidence" / (identity + ".json")
    if not path.exists(): atomic_json(path, snapshot)
    require(read_json(path) == snapshot, "frozen evidence archive changed")
    data = snapshot
    if isinstance(snapshot, dict) and snapshot.get("format") == "utf-8":
        try: data = json.loads(snapshot["content"])
        except ValueError: pass
    if canonical_review is not None and data == canonical_review:
        data = {k: v for k, v in data.items() if k != "report"}
    return identity, {"archive": str(path), "archive_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "data": data}


def primary(project):
    lines = git(project, "worktree", "list", "--porcelain").splitlines()
    require(lines and lines[0].startswith("worktree "), "primary worktree unavailable")
    return Path(lines[0][9:]).resolve()


def local_dir(root):
    path = root / ".claude/notion-dev"
    path.mkdir(parents=True, exist_ok=True)
    ignore = path / ".gitignore"
    if not ignore.exists():
        with ignore.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write("*\n")
    return path


def now():
    return datetime.now(timezone.utc).isoformat()


def preflight(project, session, non_interactive=False):
    root = primary(project)
    directory = local_dir(root)
    invocation = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    marker = directory / "runs" / ("preflight-" + re.sub(r"[^A-Za-z0-9._-]", "_", session or "unowned") + "-" + invocation + ".json")
    body = {"run": "preflight", "session": invocation, "phase": "preflight", "heartbeat": now(),
            "state": "running", "non_interactive": non_interactive,
            "claude_session": session, "cause": None, "flow": "lean"}
    atomic_json(marker, body)
    try:
        config = read_json(root / ".claude/notion-dev.config.json")
        require(isinstance(config, dict) and config.get("ticketSystem", {}).get("databaseId"),
                "Notion database config missing; run /notion-dev:init")
        status = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all", "-z"], encoding="utf-8")
        exempt = {".claude/notion-dev.config.json", ".mcp.json", ".claude/settings.local.json"}
        dirty = [row for row in status.split("\0") if row and row[3:] not in exempt]
        require(not dirty, "primary checkout is dirty; preserve changes and ask the user: " + repr(dirty))
        return {"root": str(root), "marker": str(marker), "invocation": invocation,
                "config": str(root / ".claude/notion-dev.config.json"),
                "runtime": str(directory / "runtime" / invocation / "state.json"),
                "preexisting_status": status, "stop_protection": bool(session) and non_interactive}
    except Exception as error:
        body.update(state="stopped", cause=str(error), heartbeat=now())
        atomic_json(marker, body)
        raise


def marker_update(path, session, phase, state="running", cause=None):
    path = Path(path).resolve()
    require(state in {"running", "stopped", "complete"}, "invalid marker state")
    with state_lock(path.with_suffix(".claim.lock"), 5):
        marker = read_json(path)
        require(marker.get("claude_session") == session, "marker belongs to another host session")
        require(marker.get("state") != "complete", "terminal marker: resume-pr is required for explicit recovery")
        require(phase != "complete" or state == "complete", "phase-only completion is invalid; use workflow.py complete")
        require(state != "complete" or not marker.get("runtime_state"), "use workflow.py complete to validate a ticket's terminal transition")
        marker.update(phase=phase, state=state, cause=cause, heartbeat=now())
        atomic_json(path, marker)
    return marker


def claim(project, preflight_marker, ticket, title, runtime_path, resume=False):
    """Serialize ownership and Git worktree creation with a process-death-safe lock."""
    root = primary(project)
    directory = local_dir(root)
    config = read_json(root / ".claude/notion-dev.config.json")
    key = config["project"]["key"]
    require(re.fullmatch(r"[A-Za-z0-9_-]+", key) and re.fullmatch(re.escape(key) + r"-[0-9]+", ticket),
            "ticket must match the configured project key and numeric id")
    number = ticket[len(key) + 1:]
    prefix = config.get("worktree", {}).get("prefix", "{name}-{key}-{id}").format(name=config["project"]["name"], key=key, id=number)
    require(prefix not in {"", ".", ".."} and not any(c in prefix for c in "/\\:\x00"), "unsafe worktree prefix")
    worktree = root.parent / (root.name + "-worktrees") / prefix
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40].rstrip("-") or "ticket"
    branch = "ticket/" + ticket + "-" + slug
    marker = directory / "runs" / (ticket + ".json")
    preflight_marker = Path(preflight_marker).resolve()
    require(preflight_marker.parent == marker.parent and preflight_marker.name.startswith("preflight-"),
            "preflight marker must belong to this primary checkout")
    pending = read_json(preflight_marker)
    require(pending.get("state") == "running", "preflight has already stopped")
    with state_lock(marker.with_suffix(".claim.lock"), 5):
        old = read_json(marker) if marker.exists() else None
        if old:
            require(resume, "existing run; use explicit resume, never replace its runtime")
            require(old.get("flow") == "lean", "legacy run: resume with references/legacy/ticket.md")
            require(old.get("state") != "running" or old.get("session") == pending["session"],
                    "run is owned by a live or unconfirmed session; obtain explicit takeover and stop its workers first")
            runtime_path = old["runtime_state"]
            require(not Runtime(runtime_path).summary()["end_to_end"]["unaccounted_workers"],
                    "resolve outstanding workers before taking over the run")
            worktree, branch = Path(old["worktree"]), old["branch"]
        identity = read_json(runtime_path)
        require(identity["ticket"] == ticket, "runtime belongs to another ticket")
        require(not old or identity["schema"] < 5 or pending.get("claude_session"),
                "schema-5 takeover needs the actual host session in preflight --session")
        require(Runtime(runtime_path).ready()["passed"], "requirements/readiness must pass before claiming")
        if not old:
            require(not worktree.exists(), "existing unowned worktree; inspect rather than overwrite")
            # The branch the PR will actually target, which is what the implementation
            # must be written and tested against. Every other consumer in this plugin
            # already reads it this way -- `commands/ticket.md`, `epic-doc`, `knowledge`,
            # `create-task` -- and the legacy flow states the reason outright: with the
            # two differing, `baseBranch` alone "would misstate the PR's contents". The
            # lean flow has no unconditional pre-implementation sync to catch it later.
            base = config["git"].get("prTargetBranch") or config["git"]["baseBranch"]
            git(root, "fetch", "origin")
            git(root, "worktree", "add", str(worktree), "origin/" + base, "-b", branch)
        else:
            require(worktree.exists() and git(worktree, "branch", "--show-current") == branch,
                    "resume worktree missing or on another branch; use finalize if a PR exists")
        body = {**pending, "run": ticket, "session": identity["run"], "worktree": str(worktree), "branch": branch,
                "phase": "implementation", "heartbeat": now(), "runtime_state": str(runtime_path)}
        with Runtime(runtime_path).transaction() as state:
            if state["schema"] >= 5:
                state["host_session"] = pending.get("claude_session") or state.get("host_session")
                state.pop("ticket_refresh", None)
                state.pop("ticket_refresh_request", None)
                state.pop("record_recovery", None)
        atomic_json(marker, body)
        preflight_marker.unlink()
    return {"marker": str(marker), "worktree": str(worktree), "branch": branch,
            "runtime": str(runtime_path), "resumed": bool(old)}


def resume_pr(project, preflight_marker, ticket, runtime_path, worktree, branch, merged=False):
    """Bind a verified PR to its original invocation, including post-cleanup recovery.

    The host verifies PR state/head with GitHub first. This helper neither merges nor
    infers provider state from a missing worktree. A running foreign owner is never stolen.
    """
    root = primary(project)
    marker = local_dir(root) / "runs" / (ticket + ".json")
    require(re.fullmatch(r"[A-Za-z0-9_-]+-[0-9]+", ticket), "invalid ticket key")
    pending_path = Path(preflight_marker).resolve()
    require(pending_path.parent == marker.parent and pending_path.name.startswith("preflight-"),
            "preflight marker must belong to this primary checkout")
    pending = read_json(pending_path)
    require(pending.get("state") == "running", "preflight has already stopped")
    runtime_path = Path(runtime_path).resolve()
    identity = read_json(runtime_path)
    require(identity["ticket"] == ticket and identity["schema"] >= 3, "runtime ticket/schema mismatch")
    require(identity["schema"] < 5 or pending.get("claude_session"),
            "schema-5 recovery needs the actual host session in preflight --session")
    with state_lock(marker.with_suffix(".claim.lock"), 5):
        old = read_json(marker) if marker.exists() else None
        if old:
            require(old.get("flow") == "lean" and Path(old["runtime_state"]).resolve() == runtime_path,
                    "resume must retain the original lean runtime")
            same_host = bool(pending.get("claude_session")) and old.get("claude_session") == pending["claude_session"]
            require(old.get("state") != "running" or same_host,
                    "another session owns this run; resolve ownership before resume")
        require(not Runtime(runtime_path).summary()["end_to_end"]["unaccounted_workers"],
                "resolve outstanding workers before resuming")
        worktree = Path(worktree).resolve()
        if not merged:
            require(worktree != root and worktree.is_dir(), "OPEN PR requires its own worktree")
            require(git(worktree, "branch", "--show-current") == branch, "PR worktree branch mismatch")
            require(Runtime(runtime_path).ready()["passed"], "requirements/readiness must pass before review")
        body = {**pending, "run": ticket, "session": identity["run"], "runtime_state": str(runtime_path),
                "worktree": str(worktree), "branch": branch, "phase": "record" if merged else "review"}
        with Runtime(runtime_path).transaction() as state:
            state.pop("completed", None)  # Explicit verified PR recovery; budgets/journal unchanged.
            if state["schema"] >= 5:
                state["host_session"] = pending.get("claude_session") or None
                state.pop("ticket_refresh", None)
                state.pop("ticket_refresh_request", None)
                state["record_recovery"] = merged
        atomic_json(marker, body)
        pending_path.unlink()
    return {"marker": str(marker), "runtime": str(runtime_path), "worktree": str(worktree), "branch": branch}


def verify_config(state, project, worktree, depends=(), outputs=()):
    root = primary(project)
    config = read_json(root / ".claude/notion-dev.config.json")
    steps = config.get("verify", {}).get("steps", [])
    require(isinstance(steps, list) and all(isinstance(s, dict) and isinstance(s.get("cmd"), str)
            and s["cmd"].strip() and isinstance(s.get("name"), str) for s in steps),
            "verify.steps must contain name/cmd objects")
    require(steps, "no verification configured; establish task-appropriate checks before completion")
    extra = {}
    for entry in outputs:
        name, sep, path = entry.partition("=")
        require(sep and path and name in {s["name"] for s in steps}, "output must be STEP=PATH for a configured step")
        extra.setdefault(name, []).append(path)
    runtime = Runtime(state)
    receipts = []
    for step in steps:
        command = step["cmd"]
        paths = step.get("outputs", [])
        require(isinstance(paths, list) and all(isinstance(p, str) and p for p in paths), "step outputs must be path strings")
        receipt = runtime.verify(worktree, command, reuse=True, depends=depends, outputs=paths + extra.get(step["name"], []))
        receipts.append({"name": step["name"], **{k: receipt.get(k, []) for k in ("verification", "exit_code", "duration_seconds", "log", "reused", "changed_during_verification", "outputs", "output_errors")}})
        if receipt["exit_code"] != 0 or receipt["changed_during_verification"] or receipt.get("output_errors"):
            return {"passed": False, "receipts": receipts}
    return {"passed": True, "receipts": receipts}


def review_prepare(state, project, worktree, files, previous=None, depends=(), outputs=(), remove_inputs=()):
    """One final-revision verification boundary, shared by full and delta reviews."""
    from runtime import revision, digest
    require(revision(worktree)["clean"], "commit preparation/corrections before review verification")
    verified = verify_config(state, project, worktree, depends, outputs)
    if not verified["passed"]: return verified
    keys = [r["verification"] for r in verified["receipts"]]
    manifest = Path(state).resolve().parent / "verification-evidence" / ("review-" + hashlib.sha256(json.dumps(keys).encode()).hexdigest() + ".json")
    data = {"verifications": keys, "receipts": [{k: v for k, v in r.items() if k != "reused"} for r in verified["receipts"]]}
    if manifest.exists():
        # `reused` describes this call, not the evidence itself.
        require(read_json(manifest) == data, "verification manifest changed")
    else: atomic_json(manifest, data)
    inputs = dict(files)
    require("verification_receipts" not in inputs, "verification_receipts is runtime-owned")
    if previous:
        identity = read_json(state)
        prior = identity["workers"][previous]
        receipts = {r["log"]: r for r in identity.get("verifications", [])}
        fresh = {receipts[r["log"]]["command_sha256"]: r["log"] for r in verified["receipts"]}
        for name, source in prior["files"].items():
            old = receipts.get(source["path"])
            if name not in inputs and name not in remove_inputs and old and old["command_sha256"] in fresh:
                inputs[name] = fresh[old["command_sha256"]]
    inputs["verification_receipts"] = str(manifest)
    result = Runtime(state).prepare("completeness", inputs, worktree, previous=previous, remove_inputs=remove_inputs)
    return {"passed": True, **result, "verification": str(manifest), "verification_sha256": digest(manifest)}


def record_plan(state, facts_file, review_worker=None):
    """Prepare immutable payloads; execute with provider tools, then journal readback."""
    facts = json_input(facts_file)
    identity = read_json(state)
    source = identity.get("ticket_source")
    if identity["schema"] >= 5 and source:
        # A takeover clears refresh receipts but not this binding; never write from it.
        capture = identity.get("host_captures", {}).get(source["response"])
        require(capture and capture["session"] == identity.get("host_session"),
                "ticket source predates this host session; capture-ticket again before recording")
    if identity["schema"] >= 5 or review_worker:
        reviews = [w for w in identity["workers"].values() if w["role"] == "completeness" and not w["terminated"]]
        require(not any(k in facts for k in ("requirements", "review", "verification")),
                "worker-bound recording derives requirements/review/verification; do not copy them into facts")
        if not reviews and not review_worker and identity.get("record_recovery"):
            # Verified MERGED recovery may have no runtime history. Do not invent
            # an accepted verdict, or require a pre-merge worker after the merge.
            facts.update(requirements=identity.get("requirements") or {"status": "unknown"},
                         review={"status": "unknown", "evidence": "No accepted runtime review survives; merge does not establish coverage."},
                         release_obligations=["Unknown: independent review evidence unavailable; verify release readiness explicitly."])
        else:
            require(reviews and reviews[-1]["id"] == review_worker and reviews[-1].get("accepted"),
                    "record-plan requires the final accepted --review-worker, not a consume envelope")
            accepted = reviews[-1]
            require(accepted.get("contract_version", 0) >= 3, "canonical recording facts unavailable on this legacy worker")
            facts.update(requirements=accepted["requirements"], review=accepted["result"])
        facts["verification"] = {"receipts": identity.get("verifications", []),
                                 "status": "recorded" if identity.get("verifications") else "unknown"}
    required = ("ticket", "ticket_url", "pr_url", "merge_sha", "base", "merged_at", "strategy", "requirements", "verification", "review")
    require(all(facts.get(k) for k in required), "record facts are incomplete")
    require(re.fullmatch(r"[0-9a-f]{40}", facts["merge_sha"]), "full verified merge SHA required")
    facts = {**facts, **{name: snapshot_evidence(facts[name], name, Path(facts_file).resolve().parent)
                         for name in ("requirements", "verification", "review")}}
    output = Path(state).resolve().parent / "record"
    output.mkdir(exist_ok=True)
    version = RECORD_PAYLOAD_VERSION if identity["schema"] >= 4 else 2
    pool = {}
    if version >= 3:
        reviews = [w for w in identity["workers"].values() if w["role"] == "completeness" and w.get("accepted") and not w["terminated"]]
        canonical = reviews[-1]["result"] if reviews and (reviews[-1].get("contract_version") or 0) >= 3 else None
        for name in ("requirements", "verification", "review"):
            key, view = evidence_view(facts[name], output, canonical)
            pool[key] = view
            facts[name] = {"evidence_id": key}
        if reviews:
            accepted = reviews[-1]["result"].get("recording")
            require(accepted is not None, "accepted review lacks canonical recording facts; preserve legacy recovery explicitly")
            facts["knowledge_delta"] = accepted["technical_delta"]
            facts["accepted_claim_corrections"] = accepted["claim_corrections"]
            facts["release_obligations"] = accepted["release_obligations"]
    payloads = {
        "ticket-status": {"status": "implemented"},
        "ticket-resolution": {k: facts[k] for k in required if k != "ticket"},
        "epic-record": {"ticket": facts["ticket"], "epic": facts.get("epic"), "followups": facts.get("followups", [])},
        "cleanup": {"merge_sha": facts["merge_sha"], "worktree": facts.get("worktree"), "branch": facts.get("branch"), "base": facts["base"]},
        "knowledge-delta": {"merge_sha": facts["merge_sha"], "facts": facts.get("knowledge_delta", [])},
        "post-merge-hooks": {"merge_sha": facts["merge_sha"], "hooks": facts.get("hooks", [])},
        "epic-brief": {"epic": facts.get("epic"), "ticket": facts["ticket"], "pr_url": facts["pr_url"], "merge_sha": facts["merge_sha"]},
    }
    if version >= 3:
        payloads["ticket-resolution"].update(evidence=pool, release_obligations=facts.get("release_obligations", []),
                                              accepted_claim_corrections=facts.get("accepted_claim_corrections", []))
        payloads["knowledge-delta"].update(accepted_claim_corrections=facts.get("accepted_claim_corrections", []),
                                             release_obligations=facts.get("release_obligations", []))
    targets = {"epic-record": facts.get("epic_url") or facts.get("epic") or "none:epic",
               "epic-brief": facts.get("brief_path") or facts.get("epic_url") or facts.get("epic") or "none:epic",
               "cleanup": facts.get("worktree") or "none:worktree",
               "knowledge-delta": facts.get("knowledge_dir") or "none:knowledge",
               "post-merge-hooks": facts.get("project_root") or "none:hooks"}
    runtime = Runtime(state)
    operations = []
    for name, payload in payloads.items():
        path = output / (name + ".json")
        save_record_payload(path, name, payload, version)
        operation = facts["ticket"] + ":" + facts["merge_sha"] + ":" + name
        check = runtime.record_check(operation, targets.get(name, facts["ticket_url"]) if version >= 3 else facts["ticket_url"], path)
        operations.append({**check, "kind": name, "payload": str(path),
                           "requires_children": (identity["schema"] >= 5 and (name == "ticket-status" or
                                (name == "epic-record" and bool(facts.get("epic") or facts.get("followups"))))) or version >= 3 and (name == "ticket-resolution" or
                                (name == "post-merge-hooks" and bool(facts.get("hooks"))))})
    atomic_json(output / "plan.json", operations)
    return {"plan": str(output / "plan.json"), "operations": operations}


def record_view(state, name, field=None):
    """Complete scoped evidence, selected mechanically from the frozen parent pool."""
    plan = read_json(Path(state).resolve().parent / "record/plan.json")
    operation = next(p["operation"] for p in plan if p["kind"] == "ticket-resolution")
    data = record_input(state, operation, field=name)["data"][name]
    if isinstance(data, dict) and set(data) == {"evidence_id"}:
        pool = record_input(state, operation, field="evidence")["data"]["evidence"]
        data = pool[data["evidence_id"]]["data"]
    if field is not None:
        require(isinstance(data, dict) and field in data, "unknown evidence field")
        data = data[field]
    return {"operation": operation, "section": name, "field": field, "data": data}


def record_next(state, begin=False):
    """One pending operation, in the existing plan order; no new scheduler/state."""
    plan = read_json(Path(state).resolve().parent / "record/plan.json")
    for parent in plan:
        current = record_input(state, parent["operation"])
        if current["action"] == "skip": continue
        if parent.get("requires_children"):
            binding = read_json(state).get("record_child_sets", {}).get(parent["operation"])
            if not binding:
                scoped = current["data"]
                if parent["kind"] == "ticket-resolution":
                    # The builder consumes the full canonical evidence in code. The host
                    # needs facts/obligations, not a dumped archive pool or opaque IDs.
                    scoped = {k: v for k, v in scoped.items() if k not in {"evidence", "review", "requirements", "verification"}}
                    review = record_view(state, "review")["data"]
                    scoped["recording"] = (review.get("recording") if isinstance(review, dict) else None) or {
                        "status": "unknown", "instruction": "Use record-view --name review for the complete legacy evidence; do not infer coverage."}
                return {"operation": parent["operation"], "target": parent["target"], "action": "plan-children",
                        "kind": parent["kind"], "data": scoped,
                        "builder": "record-build" if parent["kind"] in {"ticket-status", "ticket-resolution"} else None,
                        "instruction": "For ticket-status/resolution: live fetch, record-capture, record-build. Other kinds declare the COMPLETE write set with record-children. record-view retrieves specific additional evidence; never dump/truncate the archive pool."}
            require(hashlib.sha256(Path(binding["path"]).read_bytes()).hexdigest() == binding["sha256"], "child write set changed")
            for child in read_json(binding["path"]):
                operation = parent["operation"] + CHILD_SEPARATOR + child["name"]
                pending = record_input(state, operation)
                if pending["action"] != "skip":
                    # Local commands are begun inside record-run, never here.
                    local = "local_command" in pending["data"]
                    return {**record_input(state, operation, begin=begin and not local),
                            "executor": "record-run" if local else "host"}
            return {"operation": parent["operation"], "action": "confirm-children",
                    "provider_id": "confirmed-child-set:" + binding["sha256"]}
        return record_input(state, parent["operation"], begin=begin)
    return {"action": "complete", "instruction": "Run record-summary and validated completion."}


def record_capture(state, transcript, session, page, call_id=None):
    """Capture a live recording page without changing the frozen ticket requirements."""
    from host_capture import notion_fetch, timestamp
    from recording import page_data
    rt = Runtime(state)
    identity = read_json(state)
    require(identity.get("host_session") == session and session, "foreign recording capture session")
    response, observed = notion_fetch(transcript, session, call_id, page=page,
                                      after=rt.clock.stamp()["wall"] - 300, before=rt.clock.stamp()["wall"])
    decoded = page_data(response)
    from recording import page_id
    require(decoded["page"] == page_id(page), "recording fetch returned a foreign page")
    # Each capture is immutable; a later fetch cannot silently change a planned write.
    directory = Path(state).resolve().parent / "record" / "captures"
    path = directory / (hashlib.sha256(observed["call_id"].encode()).hexdigest() + ".json")
    payload = {"page": decoded, "response": response, "host": observed}
    if path.exists(): require(read_json(path) == payload, "recording capture changed")
    else: atomic_json(path, payload)
    binding = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "session": session,
               "fetched_at": timestamp(observed["result"]["timestamp"])}
    with rt.transaction() as data:
        require(data.get("host_session") == session, "recording session changed")
        data.setdefault("record_captures", {})[str(path)] = binding
    return {"snapshot": str(path), "page": decoded["page"], "fetched_at": binding["fetched_at"],
            "instruction": "Pass snapshot to record-build; no manual envelope decoding."}


def record_build(state, parent, config_file, snapshot, spec_file=None):
    """Freeze exact common ticket writes using canonical facts and actual host capture."""
    from recording import build_writes
    current = record_input(state, parent)
    require(current["action"] == "execute", "builder only plans new writes; reconcile existing attempts")
    path = Path(snapshot).resolve()
    identity = read_json(state)
    binding = identity.get("record_captures", {}).get(str(path))
    require(binding and binding["session"] == identity.get("host_session")
            and hashlib.sha256(path.read_bytes()).hexdigest() == binding["sha256"], "actual unchanged host recording capture required")
    age = Runtime(state).clock.stamp()["wall"] - binding["fetched_at"]
    require(0 <= age <= 300, "recording capture stale; fetch current content before planning")
    plan = read_json(Path(state).resolve().parent / "record/plan.json")
    operation = next((p for p in plan if p["operation"] == parent), None)
    require(operation is not None, "builder requires a planned parent")
    require(operation["kind"] in {"ticket-status", "ticket-resolution"},
            "common builder handles ticket writes; other complete write sets use record-children")
    inventory = record_view(state, "requirements")["data"] if operation["kind"] == "ticket-resolution" else None
    review = record_view(state, "review")["data"] if operation["kind"] == "ticket-resolution" else None
    writes = build_writes(operation["kind"], current["target"], current["data"], read_json(config_file),
                          read_json(path)["page"], json_input(spec_file) if spec_file else {}, inventory, review)
    source = Path(state).resolve().parent / "record" / (operation["kind"] + "-writes.json")
    if source.exists(): require(read_json(source) == writes, "builder intent changed; reconcile existing plan")
    else: atomic_json(source, writes)
    planned = record_children(state, parent, source)
    return {**planned, "writes": str(source), "instruction": "record-next --begin returns exact host_call; dispatch it unchanged, capture receipt and verify effect."}


def record_page(state, snapshot, heading=None):
    """Scoped read of a real page capture; never claim an absent heading is its content."""
    from recording import section_headings
    path = Path(snapshot).resolve()
    identity = read_json(state)
    binding = identity.get("record_captures", {}).get(str(path))
    require(binding and binding["session"] == identity.get("host_session")
            and hashlib.sha256(path.read_bytes()).hexdigest() == binding["sha256"], "actual unchanged host recording capture required")
    page = read_json(path)["page"]
    headings = section_headings(page["content"])
    labels = [re.sub(r"\s*\{[^{}]*\}\s*$", "", h[1]).strip() for h in headings]
    result = {"page": page["page"], "fetched_at": binding["fetched_at"], "snapshot": str(path)}
    if heading is None:
        return {**result, "properties": page["properties"], "headings": labels,
                "instruction": "Use --heading for a complete section. This index is not the whole page or a live ownership check."}
    indices = [i for i, label in enumerate(labels) if label.casefold() == heading.casefold()]
    require(len(indices) <= 1, "ambiguous duplicate heading")
    if not indices: return {**result, "heading": heading, "present": False, "content": None}
    i = indices[0]
    return {**result, "heading": heading, "present": True,
            "content": page["content"][headings[i].start():headings[i + 1].start() if i + 1 < len(headings) else len(page["content"])]}


def render_pr_body(facts_file, output):
    from recording import pr_body
    body = pr_body(json_input(facts_file))
    target = Path(output)
    # Never overwrite a hand-edited body by accident; corrections use a new file.
    if target.exists(): require(target.read_text(encoding="utf-8") == body, "PR output exists with different content; use a new output path")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8", newline="\n") as stream: stream.write(body)
    return {"body": str(target.resolve()), "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "instruction": "Review actual facts and mandatory disclosures. Rendering is not verification. Freeze this exact body as pr_body; do not append a review-history narrative."}


def record_run(state, operation):
    """Run an explicitly planned local hook after durable begin. No shell interpolation."""
    current = record_input(state, operation)
    if current["action"] != "execute": return current
    plan = read_json(Path(state).resolve().parent / "record/plan.json")
    kinds = {p["operation"]: p["kind"] for p in plan}
    require(operation not in kinds and record_kind(operation, kinds) == "post-merge-hooks",
            "record-run is only for declared local hook children")
    command = current["data"].get("local_command")
    require(isinstance(command, dict) and isinstance(command.get("argv"), list) and command["argv"]
            and all(isinstance(v, str) and v for v in command["argv"])
            and isinstance(command.get("cwd"), str) and Path(command["cwd"]).is_dir(),
            "local hook requires argv strings and an existing cwd; Claude skills use the host instead")
    log = child_payload_path(Path(state).resolve().parent / "record", operation + ":execution").with_suffix(".log")
    # A concurrent dispatcher that began first leaves this begin at reconcile: never launch.
    require(record_input(state, operation, begin=True)["action"] == "execute",
            "another dispatcher began this hook; reconcile it instead of launching")
    try:
        with log.open("wb") as output:
            proc = subprocess.run(command["argv"], cwd=command["cwd"], stdout=output,
                                  stderr=subprocess.STDOUT, timeout=900,
                                  env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        receipt = {"operation": operation, "exit_code": proc.returncode, "log": str(log),
                   "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest()}
        if proc.returncode:
            record_outcome(state, operation, "unknown-outcome", "local hook failed; inspect effects before retry")
        else:
            record_outcome(state, operation, "confirmed", "local-exit-0:" + receipt["log_sha256"])
        return {**receipt, "passed": proc.returncode == 0}
    except BaseException:
        record_outcome(state, operation, "unknown-outcome", "local execution interrupted; reconcile before retry")
        raise


def record_observed(state, operation, receipt):
    """Do not invent a historical begin for an effect discovered after dispatch."""
    current = record_input(state, operation)
    # After begin, an effect must bind to its actual host receipt; an "unjournaled"
    # observation there would let confirmation skip that check.
    require(current["action"] == "execute", "record-observed is only for an effect found before begin")
    require(isinstance(receipt, str) and receipt.strip(), "observed effect requires readback evidence")
    rt = Runtime(state)
    entry = rt.record_op(operation, current["target"], "unknown-outcome",
                         "unjournaled effect; reconcile: " + receipt, current["data_sha256"])
    # Provenance, not the caller-settable provider_id text, marks this reconciliation.
    with rt.transaction() as data:
        data.setdefault("unjournaled_observations", {})[operation] = entry
    return entry


def record_receipt(state, operation, transcript, session, call_id=None, readback_call_id=None, readback_verdict=None):
    """Bind a host-mediated attempt to its real tool exchange, not a guessed ID.

    A successful tool transport is not proof that a provider write had its intended
    effect. The host still checks the response/readback before record-outcome.
    """
    from host_capture import exchange, timestamp, latest_call, calls_since
    from recording import equivalent_write, write_effect_present, page_data
    current = record_input(state, operation)
    require(current["action"] == "reconcile", "begin the operation before host dispatch")
    identity = read_json(state)
    require(identity.get("host_session") == session, "foreign host session")
    expected = current["data"].get("host_call")
    require(isinstance(expected, dict) and set(expected) == {"name", "input"}, "planned host_call missing")
    attempts = [e for e in read_json(state)["record_journal"] if e["operation"] == operation and e["outcome"] == "attempted"]
    # Two identical writes after one begin may both have taken effect; never keep only one.
    candidates = calls_since(transcript, session, expected["name"], None, attempts[-1]["wall"],
        predicate=lambda item: equivalent_write(expected, {"name": item.get("name"), "input": item.get("input")})) if attempts else []
    require(len(candidates) <= 1,
            "multiple matching host calls after begin; reconcile, never select one")
    call_id = call_id or (candidates[0] if readback_call_id and candidates else
                         latest_call(transcript, session, expected["name"], arguments=expected["input"]))
    observed = exchange(transcript, session, call_id)
    call = observed["call"]["item"]
    actual = {"name": call.get("name"), "input": call.get("input")}
    if readback_call_id:
        from host_capture import notion_fetch
        require(equivalent_write(expected, actual), "host arguments materially differ; no automatic reconciliation")
        require(attempts and timestamp(observed["call"]["timestamp"]) >= attempts[-1]["wall"], "provider call predates durable begin")
        now = Runtime(state).clock.stamp()["wall"]
        require(timestamp(observed["result"]["timestamp"]) <= now, "future host receipt")
        response, readback = notion_fetch(transcript, session, readback_call_id,
            after=max(timestamp(observed["result"]["timestamp"]), now - 300), before=now)
        from recording import page_id
        page = page_data(response)
        require(page["page"] == page_id(expected["input"]["page_id"]), "readback belongs to another target")
        observed["reconciliation"] = {"version": 1, "readback": readback, "response": response,
                                      "expected": expected, "actual": actual}
        if not write_effect_present(expected["input"], page):
            # Notion rewrites presentation (links/callouts/indentation). Do not strip
            # arbitrary whitespace/code to manufacture equality. The existing host
            # adapter must judge the complete effect against these immutable objects.
            binding = {"intent_sha256": current["data_sha256"],
                       "readback_sha256": hashlib.sha256(json.dumps(response, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
                       "call_sha256": observed["call"]["sha256"]}
            if readback_verdict is None:
                path = child_payload_path(Path(state).resolve().parent / "record", operation + ":reconciliation-evidence")
                atomic_json(path, observed)
                return {"operation": operation, "action": "judge-effect", "evidence": str(path), **binding,
                        "instruction": "Adapter must compare ALL intended effects to this fresh readback, including uniqueness for append and preservation of unrelated content. Supply JSON with these three hashes, verdict=matched and nonempty evidence explaining the comparison via --readback-verdict, or leave unknown. Never undo/replay or claim unmatched/partial effects succeeded."}
            verdict = read_json(readback_verdict)
            require(all(verdict.get(k) == v for k, v in binding.items()) and verdict.get("verdict") == "matched"
                    and isinstance(verdict.get("evidence"), str) and verdict["evidence"].strip(),
                    "adapter verdict must bind this exact intent/call/readback and explain the complete matched effect")
            observed["reconciliation"]["adapter_verdict"] = verdict
    else:
        require(actual == expected, "host tool/arguments differ from frozen operation; use record-reconcile with fresh readback, never undo/replay")
    rt = Runtime(state)
    with rt.transaction() as data:
        require(data.get("host_session") == session, "foreign host session")
        entries = [e for e in data["record_journal"] if e["operation"] == operation]
        require(entries[-1]["outcome"] in {"attempted", "unknown-outcome"}, "operation changed during receipt capture")
        attempts = [e for e in entries if e["outcome"] == "attempted"]
        require(attempts and timestamp(observed["call"]["timestamp"]) >= attempts[-1]["wall"],
                "provider call predates durable begin; it cannot confirm this attempt, never retroactively begin")
        require(timestamp(observed["result"]["timestamp"]) <= rt.clock.stamp()["wall"], "future host receipt")
        receipts = data.setdefault("host_operation_receipts", {})
        require(not any(r["call_id"] == call_id and key != operation for key, r in receipts.items()), "host call already belongs to another operation")
        binding = {"call_id": call_id, "data_sha256": current["data_sha256"],
                   "attempt": attempts[-1],
                   "result_sha256": observed["result"]["sha256"], "call_sha256": observed["call"]["sha256"]}
        saved = child_payload_path(Path(state).resolve().parent / "record", operation + ":host-receipt")
        atomic_json(saved, observed)
        receipts[operation] = {**binding, "path": str(saved), "sha256": hashlib.sha256(saved.read_bytes()).hexdigest()}
    return {"operation": operation, "action": "verify-effect", "receipt": str(saved),
            "instruction": "Inspect provider response or read back its actual effect before confirming. Tool transport success is not write success."}


def record_child(state, parent, name, target, payload_file):
    """One level of stable, explicitly registered child operations per planned parent."""
    directory = Path(state).resolve().parent / "record"
    plan = read_json(directory / "plan.json")
    kinds = {op["operation"]: op["kind"] for op in plan}
    require(parent in kinds, "child parent must be a planned operation")
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", name), "invalid child name")
    operation = parent + CHILD_SEPARATOR + name
    path = child_payload_path(directory, operation)
    data = json_input(payload_file)
    require(isinstance(data, dict), "child payload must be a self-contained object, not a live file reference")
    version = read_json(next(p["payload"] for p in plan if p["operation"] == parent))["record_payload_version"]
    save_record_payload(path, kinds[parent], data, version)
    check = Runtime(state).record_check(operation, target, path)
    return {**check, "payload": str(path), "parent": parent, "kind": kinds[parent]}


def record_children(state, parent, manifest_file):
    """Freeze the complete provider-write set BEFORE any child dispatch.

    A caller may declare one atomic batch, or separately recoverable writes. Unknown
    outcomes then stop only the affected child, not replay a completed sibling.
    """
    writes = json_input(manifest_file)
    # Compact host-tool recipes use the exact input object the host already needs.
    # Normalize into the original protocol before freezing; no second journal or API.
    if isinstance(writes, list):
        normalized = []
        for write in writes:
            if isinstance(write, dict) and "tool" in write:
                require(set(write) == {"name", "target", "tool", "input"},
                        "host recipe requires name/target/tool/input, not mixed payload formats")
                write = {"name": write["name"], "target": write["target"],
                         "data": {"host_call": {"name": write["tool"], "input": write["input"]}}}
            normalized.append(write)
        writes = normalized
    require(isinstance(writes, list) and writes and all(isinstance(w, dict) and
            all(k in w for k in ("name", "target", "data")) for w in writes), "writes must list name/target/data objects")
    require(all(isinstance(w["name"], str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", w["name"])
                and isinstance(w["target"], str) and w["target"].strip() and isinstance(w["data"], dict)
                for w in writes), "each write requires a valid child name, actual target and self-contained data")
    require(len({w["name"] for w in writes}) == len(writes), "duplicate child name")
    if read_json(state)["schema"] >= 5:
        for write in writes:
            body = write["data"]
            require(("host_call" in body) != ("local_command" in body), "declare exactly one host_call or local_command per write")
            if "host_call" in body:
                call = body["host_call"]
                require(isinstance(call, dict) and set(call) == {"name", "input"}
                        and isinstance(call["name"], str) and call["name"].strip() and isinstance(call["input"], dict),
                        "host_call needs exact tool name and input object")
            else:
                command = body["local_command"]
                require(isinstance(command, dict) and isinstance(command.get("argv"), list) and command["argv"]
                        and all(isinstance(v, str) and v for v in command["argv"])
                        and isinstance(command.get("cwd"), str) and Path(command["cwd"]).is_dir(),
                        "local_command needs argv strings and an existing cwd before freezing its write set")
    directory = Path(state).resolve().parent / "record"
    plan = read_json(directory / "plan.json")
    require(any(p["operation"] == parent for p in plan), "unknown parent operation")
    if any("local_command" in w["data"] for w in writes):
        require(any(p["operation"] == parent and p["kind"] == "post-merge-hooks" for p in plan),
                "local_command is only supported for configured post-merge hook children")
    manifest = child_payload_path(directory, parent + ":manifest")
    if manifest.exists(): require(read_json(manifest) == writes, "child write set changed; reconcile explicitly")
    else:
        require(record_input(state, parent)["action"] == "execute", "declare children before parent execution")
        atomic_json(manifest, writes)
    binding = {"path": str(manifest), "sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()}
    with Runtime(state).transaction() as data:
        old = data.setdefault("record_child_sets", {}).get(parent)
        require(old is None or old == binding, "declared child write set changed")
        data["record_child_sets"][parent] = binding
    children = []
    for write in writes:
        source = child_payload_path(directory, parent + ":input:" + write["name"])
        atomic_json(source, write["data"])
        children.append(record_child(state, parent, write["name"], write["target"], source))
    return {"parent": parent, "children": children}


def record_input(state, operation, begin=False, field=None):
    """Read/hash ONCE, then return those exact bytes as data for the authorized host.

    The provider must consume this result, not reopen original evidence paths. A
    source file changing after planning therefore cannot change the provider input.
    """
    require(not (begin and field is not None), "--field is inspection-only; --begin returns the full operation input")
    directory = Path(state).resolve().parent / "record"
    plan = read_json(directory / "plan.json")
    parents = {op["operation"]: op for op in plan}
    kind = record_kind(operation, {key: op["kind"] for key, op in parents.items()})
    require(kind is not None, "unknown recording operation")
    path = directory / (kind + ".json") if operation in parents else child_payload_path(directory, operation)
    raw = path.read_bytes()
    payload_hash = hashlib.sha256(raw).hexdigest()
    payload = json.loads(raw.decode("utf-8"))
    require(isinstance(payload, dict) and payload.get("record_payload_version") in {2, RECORD_PAYLOAD_VERSION} and payload.get("kind") == kind
            and isinstance(payload.get("data"), dict), "legacy/invalid payload; reconcile before recording")
    if operation in parents:
        require(parents[operation]["data_sha256"] == payload_hash, "planned payload changed")
    rt = Runtime(state)
    with rt.transaction() as data:
        entries = [entry for entry in data["record_journal"] if entry["operation"] == operation]
        require(entries, "record operation must be planned first")
        latest = entries[-1]
        require(latest.get("data_sha256") == payload_hash, "journal payload changed")
        if operation in parents:
            require(latest["target"] == parents[operation]["target"], "planned target changed")
    content = payload["data"]
    # `evidence` is an ordinary provider field in arbitrary child/legacy payloads.
    # Only our version-3 parent ticket-resolution owns the archive-pool shape.
    pool = content.get("evidence", {}) if (operation in parents and kind == "ticket-resolution"
            and payload["record_payload_version"] >= 3) else {}
    for view in pool.values():
        require(hashlib.sha256(Path(view["archive"]).read_bytes()).hexdigest() == view["archive_sha256"],
                "frozen evidence archive changed")
    if field is not None:
        require(field in content, "requested payload field does not exist")
        content = {field: content[field]}
    action = ("skip" if latest["outcome"] == "confirmed" else "reconcile"
              if latest["outcome"] in {"attempted", "unknown-outcome"} else "execute")
    if begin and action == "execute":
        if operation in parents and parents[operation].get("requires_children"):
            manifest = child_payload_path(directory, operation + ":manifest")
            require(manifest.exists(), "plan independently recoverable writes with record-children before execution")
            return {"operation": operation, "action": "children", "children": [
                operation + CHILD_SEPARATOR + w["name"] for w in read_json(manifest)]}
        # record_op rechecks the latest journal state under its own lock, so a
        # concurrent begin cannot dispatch the same provider mutation twice.
        rt.record_op(operation, latest["target"], "attempted", data_sha256=payload_hash)
    return {"operation": operation, "action": action, "target": latest["target"],
            "data_sha256": payload_hash, "data": content if action != "skip" or field is not None else None}


def record_outcome(state, operation, outcome, provider_id=None):
    require(outcome in {"confirmed", "failed", "unknown-outcome"}, "invalid recording outcome")
    current = record_input(state, operation)
    require(outcome != "confirmed" or (isinstance(provider_id, str) and provider_id.strip()),
            "confirmation requires an actual response/readback receipt")
    directory = Path(state).resolve().parent / "record"
    plan = read_json(directory / "plan.json")
    parent = next((p for p in plan if p["operation"] == operation), None)
    identity = read_json(state)
    if identity["schema"] >= 5 and outcome == "confirmed" and current["action"] != "skip" and not parent:
        if "host_call" in current["data"]:
            receipt = identity.get("host_operation_receipts", {}).get(operation)
            entries = [e for e in identity["record_journal"] if e["operation"] == operation]
            attempts = [e for e in entries if e["outcome"] == "attempted"]
            reconciled = (entries[-1]["outcome"] == "unknown-outcome"
                          and identity.get("unjournaled_observations", {}).get(operation) == entries[-1])
            require(reconciled or (receipt and receipt["data_sha256"] == current["data_sha256"]
                    and attempts and receipt.get("attempt") == attempts[-1]
                    and hashlib.sha256(Path(receipt["path"]).read_bytes()).hexdigest() == receipt["sha256"]),
                    "capture the actual host receipt or explicitly reconcile an unjournaled effect")
    require(outcome != "confirmed" or current["action"] != "execute" or (parent and parent.get("requires_children")),
            "begin the operation before confirming its provider effect")
    if outcome == "confirmed" and parent and parent.get("requires_children"):
        manifest = child_payload_path(directory, operation + ":manifest")
        require(manifest.exists(), "required child write plan missing")
        binding = read_json(state).get("record_child_sets", {}).get(operation)
        require(binding and hashlib.sha256(manifest.read_bytes()).hexdigest() == binding["sha256"], "child write set changed")
        for write in read_json(manifest):
            require(record_input(state, operation + CHILD_SEPARATOR + write["name"])["action"] == "skip",
                    "confirm parent only after every declared write is confirmed")
    return Runtime(state).record_op(operation, current["target"], outcome, provider_id, current["data_sha256"])


# Named best-effort by `references/record.md`; every other operation is required.
BEST_EFFORT_RECORD = frozenset({"knowledge-delta", "epic-brief"})


def record_summary(state):
    path = Path(state).resolve()
    plan = read_json(path.parent / "record/plan.json")
    require(isinstance(plan, list) and plan, "record operation plan missing")
    with Runtime(path).transaction() as data:
        latest = {entry["operation"]: entry for entry in data["record_journal"]}
        child_sets = data.get("record_child_sets", {})
    outcomes = {}
    for operation in plan:
        receipt = latest.get(operation["operation"], {})
        require(receipt.get("target") == operation["target"]
                and receipt.get("data_sha256") == operation["data_sha256"], "record receipt identity mismatch")
        outcomes[operation["kind"]] = receipt.get("outcome", "unknown-outcome") + (
            ": " + str(receipt["provider_id"]) if receipt.get("provider_id") else "")
    fields = {"EPIC-REPORT": outcomes["epic-record"], "TICKET-RECORD":
              outcomes["ticket-status"] + "; " + outcomes["ticket-resolution"],
              "CLEANUP": outcomes["cleanup"], "CLEANUP-STEPS": outcomes["cleanup"],
              "HOOKS": outcomes["post-merge-hooks"], "EPIC-DOC-RECORD": outcomes["epic-brief"],
              "EPIC-DOC-NEXT": outcomes["epic-brief"], "ISSUES": "see unresolved operations"}
    # `references/record.md`: "Only fully reconciled REQUIRED record operations permit
    # `OUTCOME: resolved`; best-effort knowledge/brief failures remain explicit in their
    # outcome fields, never hidden by that label." Counting every operation uniformly made
    # a persistent optional-hook failure exit 1 forever, blocking the ticket and the
    # next-task loop over work the contract calls best-effort. Visible, not blocking --
    # both halves matter, so they stay in `unresolved` and in ISSUES and only lose their
    # vote on `passed`. Only explicitly named parents and their well-formed children
    # inherit policy; unknown identities remain REQUIRED.
    kinds = {operation["operation"]: operation["kind"] for operation in plan}
    unresolved = sorted(k for k, entry in latest.items() if entry["outcome"] != "confirmed")
    for operation in plan:
        if not operation.get("requires_children"): continue
        binding = child_sets.get(operation["operation"])
        complete = bool(binding and Path(binding["path"]).is_file()
                        and hashlib.sha256(Path(binding["path"]).read_bytes()).hexdigest() == binding["sha256"])
        if complete:
            complete = all(latest.get(operation["operation"] + CHILD_SEPARATOR + w["name"], {}).get("outcome") == "confirmed"
                           for w in read_json(binding["path"]))
        if not complete and operation["operation"] not in unresolved:
            unresolved.append(operation["operation"])
    blocking = [k for k in unresolved if record_kind(k, kinds) not in BEST_EFFORT_RECORD]
    fields["ISSUES"] = ", ".join(unresolved) if unresolved else "none"
    result = {"record": fields, "passed": not blocking, "unresolved": unresolved,
              "blocking_unresolved": blocking,
              "best_effort_unresolved": [k for k in unresolved if k not in blocking],
              "report": "RECORD:\n" + "\n".join(k + ": " + v for k, v in fields.items())}
    atomic_json(path.parent / "record-result.json", result)
    return result


def complete(state, marker_path, session):
    """Validate recording/ownership once, then set phase AND terminal state together."""
    path = Path(state).resolve()
    marker_path = Path(marker_path).resolve()
    snapshot = read_json(path)["record_journal"]
    summary = record_summary(path)
    require(summary["passed"], "required recording outcomes remain unresolved")
    with state_lock(marker_path.with_suffix(".claim.lock"), 5):
        marker = read_json(marker_path)
        require(marker.get("claude_session") == session and
                Path(marker.get("runtime_state", "")).resolve() == path, "completion marker/runtime ownership mismatch")
        require(marker.get("state") in {"running", "complete"}, "resume a stopped run before completion")
        lock = marker_path.parent.parent / "locks/primary"
        if lock.exists():
            owner = (lock / "owner").read_text(encoding="utf-8") if (lock / "owner").is_file() else ""
            owners = re.findall(r"^run: (.+)$", owner, re.M)
            require(len(owners) == 1 and owners[0] not in {marker.get("session"), marker.get("run")},
                    "release the owned primary writer lock before completion; unknown lock ownership requires reconciliation")
        rt = Runtime(path)
        with rt.transaction() as data:
            require(marker.get("session") == data["run"] and marker.get("run") == data["ticket"], "completion invocation mismatch")
            require(data["record_journal"] == snapshot, "recording changed during completion; check again")
            require(not any(not w["terminated"] and not w.get("accepted") for w in data["workers"].values()),
                    "workers remain outstanding; completion is not cancellation")
            if not data.get("completed") and data.get("stage"):
                rt.event(data, "stage_ended")
            data["completed"] = True
            data["stage"] = "complete"
            marker.update(phase="complete", state="complete", heartbeat=now(), cause=None)
            rt.event(data, "run_completed")
        # If this second atomic write fails, Stop still sees running. Retrying complete
        # repairs only the marker, never repeats provider work. Never the inverse order.
        atomic_json(marker_path, marker)
    return {"passed": True, "phase": "complete", "state": "complete", "record": summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("preflight"); p.add_argument("--project", default=".")
    p.add_argument("--session", default=os.environ.get("NOTION_DEV_SESSION_ID", "")); p.add_argument("--non-interactive", action="store_true")
    p = commands.add_parser("marker"); p.add_argument("--path", required=True); p.add_argument("--phase", required=True)
    p.add_argument("--session", default=os.environ.get("NOTION_DEV_SESSION_ID", "")); p.add_argument("--status", default="running"); p.add_argument("--cause")
    p = commands.add_parser("claim"); p.add_argument("--project", required=True); p.add_argument("--preflight", required=True)
    p.add_argument("--ticket", required=True); p.add_argument("--title", required=True); p.add_argument("--state", required=True); p.add_argument("--resume", action="store_true")
    p = commands.add_parser("resume-pr"); p.add_argument("--project", required=True); p.add_argument("--preflight", required=True)
    p.add_argument("--ticket", required=True); p.add_argument("--state", required=True)
    p.add_argument("--worktree", required=True); p.add_argument("--branch", required=True); p.add_argument("--merged", action="store_true")
    p = commands.add_parser("verify"); p.add_argument("--project", required=True); p.add_argument("--state", required=True)
    p.add_argument("--worktree", required=True); p.add_argument("--depends", action="append", default=[])
    p.add_argument("--output", action="append", default=[], help="STEP=PATH generated evidence to archive")
    p = commands.add_parser("review-prepare"); p.add_argument("--project", required=True); p.add_argument("--state", required=True)
    p.add_argument("--remove-input", action="append", default=[])
    p.add_argument("--worktree", required=True); p.add_argument("--previous")
    p.add_argument("--file", action="append", default=[]); p.add_argument("--depends", action="append", default=[])
    p.add_argument("--output", action="append", default=[])
    p = commands.add_parser("pr-body"); p.add_argument("--facts", required=True); p.add_argument("--output", required=True)
    p = commands.add_parser("record-capture"); p.add_argument("--state", required=True); p.add_argument("--page", required=True)
    p.add_argument("--transcript", default=os.environ.get("NOTION_DEV_TRANSCRIPT")); p.add_argument("--call-id")
    p.add_argument("--session", default=os.environ.get("NOTION_DEV_SESSION_ID", ""))
    p = commands.add_parser("record-build"); p.add_argument("--state", required=True); p.add_argument("--parent", required=True)
    p.add_argument("--config", required=True); p.add_argument("--snapshot", required=True); p.add_argument("--spec")
    p = commands.add_parser("record-page"); p.add_argument("--state", required=True); p.add_argument("--snapshot", required=True); p.add_argument("--heading")
    p = commands.add_parser("record-plan"); p.add_argument("--state", required=True); p.add_argument("--facts", required=True)
    p.add_argument("--review-worker")
    p = commands.add_parser("record-view"); p.add_argument("--state", required=True); p.add_argument("--name", required=True); p.add_argument("--field")
    p = commands.add_parser("record-next"); p.add_argument("--state", required=True); p.add_argument("--begin", action="store_true")
    p = commands.add_parser("record-run"); p.add_argument("--state", required=True); p.add_argument("--operation", required=True)
    p = commands.add_parser("record-observed"); p.add_argument("--state", required=True); p.add_argument("--operation", required=True); p.add_argument("--receipt", required=True)
    p = commands.add_parser("record-receipt"); p.add_argument("--state", required=True); p.add_argument("--operation", required=True)
    p.add_argument("--transcript", default=os.environ.get("NOTION_DEV_TRANSCRIPT")); p.add_argument("--call-id")
    p.add_argument("--session", default=os.environ.get("NOTION_DEV_SESSION_ID", ""))
    p = commands.add_parser("record-reconcile"); p.add_argument("--state", required=True); p.add_argument("--operation", required=True)
    p.add_argument("--transcript", default=os.environ.get("NOTION_DEV_TRANSCRIPT")); p.add_argument("--call-id")
    p.add_argument("--readback-call-id", required=True)
    p.add_argument("--readback-verdict", help="adapter judgment bound to returned intent/call/readback hashes")
    p.add_argument("--session", default=os.environ.get("NOTION_DEV_SESSION_ID", ""))
    p = commands.add_parser("record-child"); p.add_argument("--state", required=True); p.add_argument("--parent", required=True)
    p.add_argument("--name", required=True); p.add_argument("--target", required=True); p.add_argument("--payload", required=True)
    p = commands.add_parser("record-input"); p.add_argument("--state", required=True); p.add_argument("--operation", required=True)
    p.add_argument("--begin", action="store_true"); p.add_argument("--field")
    p = commands.add_parser("record-children"); p.add_argument("--state", required=True); p.add_argument("--parent", required=True)
    p.add_argument("--writes", required=True)
    p = commands.add_parser("record-outcome"); p.add_argument("--state", required=True); p.add_argument("--operation", required=True)
    p.add_argument("--outcome", required=True, choices=("confirmed", "failed", "unknown-outcome")); p.add_argument("--provider-id")
    p = commands.add_parser("complete"); p.add_argument("--state", required=True); p.add_argument("--marker", required=True)
    p.add_argument("--session", default=os.environ.get("NOTION_DEV_SESSION_ID", ""))
    p = commands.add_parser("record-summary"); p.add_argument("--state", required=True)
    args = parser.parse_args()
    if args.command == "preflight": result = preflight(args.project, args.session, args.non_interactive)
    elif args.command == "marker": result = marker_update(args.path, args.session, args.phase, args.status, args.cause)
    elif args.command == "claim": result = claim(args.project, args.preflight, args.ticket, args.title, args.state, args.resume)
    elif args.command == "resume-pr": result = resume_pr(args.project, args.preflight, args.ticket, args.state, args.worktree, args.branch, args.merged)
    elif args.command == "verify": result = verify_config(args.state, args.project, args.worktree, args.depends, args.output)
    elif args.command == "review-prepare":
        files = {}
        for item in args.file:
            key, sep, path = item.partition("=")
            require(sep and key and path and key not in files, "--file requires unique name=path")
            files[key] = path
        result = review_prepare(args.state, args.project, args.worktree, files, args.previous, args.depends, args.output, args.remove_input)
    elif args.command == "pr-body": result = render_pr_body(args.facts, args.output)
    elif args.command == "record-capture": result = record_capture(args.state, args.transcript, args.session, args.page, args.call_id)
    elif args.command == "record-build": result = record_build(args.state, args.parent, args.config, args.snapshot, args.spec)
    elif args.command == "record-page": result = record_page(args.state, args.snapshot, args.heading)
    elif args.command == "record-plan": result = record_plan(args.state, args.facts, args.review_worker)
    elif args.command == "record-view": result = record_view(args.state, args.name, args.field)
    elif args.command == "record-next": result = record_next(args.state, args.begin)
    elif args.command == "record-run": result = record_run(args.state, args.operation)
    elif args.command == "record-observed": result = record_observed(args.state, args.operation, args.receipt)
    elif args.command == "record-receipt": result = record_receipt(args.state, args.operation, args.transcript, args.session, args.call_id)
    elif args.command == "record-reconcile": result = record_receipt(args.state, args.operation, args.transcript, args.session, args.call_id, args.readback_call_id, args.readback_verdict)
    elif args.command == "record-child": result = record_child(args.state, args.parent, args.name, args.target, args.payload)
    elif args.command == "record-children": result = record_children(args.state, args.parent, args.writes)
    elif args.command == "record-outcome": result = record_outcome(args.state, args.operation, args.outcome, args.provider_id)
    elif args.command == "complete": result = complete(args.state, args.marker, args.session)
    elif args.command == "record-input": result = record_input(args.state, args.operation, args.begin, args.field)
    else: result = record_summary(args.state)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result.get("passed") is False else 0


if __name__ == "__main__":
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", newline="\n")
    try:
        sys.exit(main())
    except (Invalid, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        sys.exit(2)
