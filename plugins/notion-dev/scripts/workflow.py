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


RECORD_PAYLOAD_VERSION = 2
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


def save_record_payload(path, kind, data):
    payload = {"record_payload_version": RECORD_PAYLOAD_VERSION, "kind": kind, "data": data}
    if path.exists():
        require(read_json(path) == payload,
                "record payload changed or legacy payload: reconcile before an explicit operation revision")
    else:
        atomic_json(path, payload)


def child_payload_path(directory, operation):
    return directory / ("child-" + hashlib.sha256(operation.encode("utf-8")).hexdigest() + ".json")


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
        atomic_json(marker, body)
        pending_path.unlink()
    return {"marker": str(marker), "runtime": str(runtime_path), "worktree": str(worktree), "branch": branch}


def verify_config(state, project, worktree, depends=()):
    root = primary(project)
    config = read_json(root / ".claude/notion-dev.config.json")
    steps = config.get("verify", {}).get("steps", [])
    require(isinstance(steps, list) and all(isinstance(s, dict) and isinstance(s.get("cmd"), str)
            and s["cmd"].strip() and isinstance(s.get("name"), str) for s in steps),
            "verify.steps must contain name/cmd objects")
    require(steps, "no verification configured; establish task-appropriate checks before completion")
    runtime = Runtime(state)
    receipts = []
    for step in steps:
        command = step["cmd"]
        receipt = runtime.verify(worktree, command, reuse=True, depends=depends)
        receipts.append({"name": step["name"], **{k: receipt[k] for k in ("verification", "exit_code", "duration_seconds", "log", "reused", "changed_during_verification")}})
        if receipt["exit_code"] != 0 or receipt["changed_during_verification"]:
            return {"passed": False, "receipts": receipts}
    return {"passed": True, "receipts": receipts}


def record_plan(state, facts_file):
    """Prepare immutable payloads; execute with provider tools, then journal readback."""
    facts = read_json(facts_file)
    required = ("ticket", "ticket_url", "pr_url", "merge_sha", "base", "merged_at", "strategy", "requirements", "verification", "review")
    require(all(facts.get(k) for k in required), "record facts are incomplete")
    require(re.fullmatch(r"[0-9a-f]{40}", facts["merge_sha"]), "full verified merge SHA required")
    facts = {**facts, **{name: snapshot_evidence(facts[name], name, Path(facts_file).resolve().parent)
                         for name in ("requirements", "verification", "review")}}
    output = Path(state).resolve().parent / "record"
    output.mkdir(exist_ok=True)
    payloads = {
        "ticket-status": {"status": "implemented"},
        "ticket-resolution": {k: facts[k] for k in required if k != "ticket"},
        "epic-record": {"ticket": facts["ticket"], "epic": facts.get("epic"), "followups": facts.get("followups", [])},
        "cleanup": {"merge_sha": facts["merge_sha"], "worktree": facts.get("worktree"), "branch": facts.get("branch"), "base": facts["base"]},
        "knowledge-delta": {"merge_sha": facts["merge_sha"], "facts": facts.get("knowledge_delta", [])},
        "post-merge-hooks": {"merge_sha": facts["merge_sha"], "hooks": facts.get("hooks", [])},
        "epic-brief": {"epic": facts.get("epic"), "ticket": facts["ticket"], "pr_url": facts["pr_url"], "merge_sha": facts["merge_sha"]},
    }
    runtime = Runtime(state)
    operations = []
    for name, payload in payloads.items():
        path = output / (name + ".json")
        save_record_payload(path, name, payload)
        operation = facts["ticket"] + ":" + facts["merge_sha"] + ":" + name
        check = runtime.record_check(operation, facts["ticket_url"], path)
        operations.append({**check, "kind": name, "payload": str(path)})
    atomic_json(output / "plan.json", operations)
    return {"plan": str(output / "plan.json"), "operations": operations}


def record_child(state, parent, name, target, payload_file):
    """One level of stable, explicitly registered child operations per planned parent."""
    directory = Path(state).resolve().parent / "record"
    plan = read_json(directory / "plan.json")
    kinds = {op["operation"]: op["kind"] for op in plan}
    require(parent in kinds, "child parent must be a planned operation")
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", name), "invalid child name")
    operation = parent + CHILD_SEPARATOR + name
    path = child_payload_path(directory, operation)
    data = read_json(payload_file)
    require(isinstance(data, dict), "child payload must be a self-contained object, not a live file reference")
    save_record_payload(path, kinds[parent], data)
    check = Runtime(state).record_check(operation, target, path)
    return {**check, "payload": str(path), "parent": parent, "kind": kinds[parent]}


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
    require(isinstance(payload, dict) and payload.get("record_payload_version") == RECORD_PAYLOAD_VERSION and payload.get("kind") == kind
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
    if field is not None:
        require(field in content, "requested payload field does not exist")
        content = {field: content[field]}
    action = ("skip" if latest["outcome"] == "confirmed" else "reconcile"
              if latest["outcome"] in {"attempted", "unknown-outcome"} else "execute")
    if begin and action == "execute":
        # record_op rechecks the latest journal state under its own lock, so a
        # concurrent begin cannot dispatch the same provider mutation twice.
        rt.record_op(operation, latest["target"], "attempted", data_sha256=payload_hash)
    return {"operation": operation, "action": action, "target": latest["target"],
            "data_sha256": payload_hash, "data": content if action != "skip" or field is not None else None}


# Named best-effort by `references/record.md`; every other operation is required.
BEST_EFFORT_RECORD = frozenset({"knowledge-delta", "epic-brief"})


def record_summary(state):
    path = Path(state).resolve()
    plan = read_json(path.parent / "record/plan.json")
    require(isinstance(plan, list) and plan, "record operation plan missing")
    with Runtime(path).transaction() as data:
        latest = {entry["operation"]: entry for entry in data["record_journal"]}
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
    blocking = [k for k in unresolved if record_kind(k, kinds) not in BEST_EFFORT_RECORD]
    fields["ISSUES"] = ", ".join(unresolved) if unresolved else "none"
    result = {"record": fields, "passed": not blocking, "unresolved": unresolved,
              "blocking_unresolved": blocking,
              "best_effort_unresolved": [k for k in unresolved if k not in blocking],
              "report": "RECORD:\n" + "\n".join(k + ": " + v for k, v in fields.items())}
    atomic_json(path.parent / "record-result.json", result)
    return result


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
    p = commands.add_parser("record-plan"); p.add_argument("--state", required=True); p.add_argument("--facts", required=True)
    p = commands.add_parser("record-child"); p.add_argument("--state", required=True); p.add_argument("--parent", required=True)
    p.add_argument("--name", required=True); p.add_argument("--target", required=True); p.add_argument("--payload", required=True)
    p = commands.add_parser("record-input"); p.add_argument("--state", required=True); p.add_argument("--operation", required=True)
    p.add_argument("--begin", action="store_true"); p.add_argument("--field")
    p = commands.add_parser("record-summary"); p.add_argument("--state", required=True)
    args = parser.parse_args()
    if args.command == "preflight": result = preflight(args.project, args.session, args.non_interactive)
    elif args.command == "marker": result = marker_update(args.path, args.session, args.phase, args.status, args.cause)
    elif args.command == "claim": result = claim(args.project, args.preflight, args.ticket, args.title, args.state, args.resume)
    elif args.command == "resume-pr": result = resume_pr(args.project, args.preflight, args.ticket, args.state, args.worktree, args.branch, args.merged)
    elif args.command == "verify": result = verify_config(args.state, args.project, args.worktree, args.depends)
    elif args.command == "record-plan": result = record_plan(args.state, args.facts)
    elif args.command == "record-child": result = record_child(args.state, args.parent, args.name, args.target, args.payload)
    elif args.command == "record-input": result = record_input(args.state, args.operation, args.begin, args.field)
    else: result = record_summary(args.state)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result.get("passed") is False else 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", newline="\n")
    try:
        sys.exit(main())
    except (Invalid, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        sys.exit(2)
