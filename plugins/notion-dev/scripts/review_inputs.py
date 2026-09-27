"""Typed review inputs, generated from git and read-only provider observations.

No provider writes. GitHub is queried through gh in the host's configured environment;
Notion source snapshots come from the existing actual-host capture boundary.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

from runtime import Runtime, atomic_json, digest, git, read_json, require, revision


def github(pr):
    match = re.fullmatch(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#([1-9][0-9]*)", pr)
    require(match is not None, "PR must be owner/repository#number")
    process = subprocess.run(["gh", "pr", "view", match[2], "--repo", match[1], "--json",
                              "number,url,state,headRefOid,baseRefOid,body"],
                             capture_output=True, encoding="utf-8", timeout=60)
    require(process.returncode == 0, "cannot read PR: " + process.stderr)
    value = json.loads(process.stdout)
    require(value.get("number") == int(match[2]) and isinstance(value.get("body"), str)
            and value.get("url", "").lower() == ("https://github.com/" + match[1] + "/pull/" + match[2]).lower(),
            "PR identity/body mismatch")
    for name in ("headRefOid", "baseRefOid"):
        require(re.fullmatch(r"[0-9a-f]{40}", value.get(name, "")), "invalid PR revision")
    return value


def save(directory, value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    path = directory / (hashlib.sha256(raw).hexdigest() + ".json")
    if path.exists(): require(read_json(path) == value, "review input archive changed")
    else: atomic_json(path, value)
    return str(path)


def prepare(state, worktree, pr, sources=None):
    identity = read_json(state)
    current = revision(worktree)
    require(current["clean"], "commit changes before preparing review inputs")
    observed = github(pr)
    require(observed["state"] == "OPEN" and observed["headRefOid"] == current["head"], "PR HEAD/state differs from worktree")
    # Fetching refs remains with the host; an unavailable base fails rather than guessing.
    base = git(worktree, "merge-base", observed["baseRefOid"], current["head"])
    diff = git(worktree, "diff", "--no-ext-diff", "--no-textconv", "--binary", base, current["head"], "--")
    directory = Path(state).resolve().parent / "review-inputs"
    files = {"diff": save(directory, {"kind": "git-diff", "base": base, "head": current["head"], "diff": diff}),
             "pr_body": save(directory, {"kind": "github-pr", "pr": pr, **observed})}
    provenance, captures = {}, {}
    for label, source in (sources or {}).items():
        require(re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", label) and label not in {"diff", "pr_body", "review_inputs", "verification_receipts", "ticket", "inventory"}, "reserved/invalid source label")
        path = str(Path(source).resolve())
        binding = identity.get("record_captures", {}).get(path)
        require(binding and binding["session"] == identity.get("host_session") and digest(path) == binding["sha256"],
                "source must be an unchanged actual host page capture, not a relabelled log")
        age = Runtime(state).clock.stamp()["wall"] - binding["fetched_at"]
        require(0 <= age <= 300, "source capture stale; fetch the current source")
        page = read_json(path)["page"]
        # Provider exchange timestamps are provenance, not changed requirements.
        # Equal page content keeps the same review input even after a fresh fetch.
        files[label] = save(directory, {"kind": "notion-page", **page})
        provenance[label] = {"kind": "notion-page", "page": page["page"], "url": page["url"]}
        captures[label] = {"path": path, "sha256": binding["sha256"]}
    ticket = identity.get("ticket_source")
    require(ticket and digest(ticket["source"]) == ticket["source_sha256"], "capture authoritative ticket before preparing review inputs")
    files["ticket"] = ticket["source"]
    files["inventory"] = save(directory, identity["requirements"])
    manifest = {"version": 1, "pr": pr, "revision": current, "base": base,
                "sources": provenance, "files": {k: {"path": v, "sha256": digest(v)} for k, v in files.items()}}
    path = save(directory, manifest)
    with Runtime(state).transaction() as data:
        require(data.get("host_session") == identity.get("host_session") and data["requirements"] == identity["requirements"], "owner/requirements changed during input capture")
        data["review_inputs"] = {"path": path, "sha256": digest(path), "revision": current,
                                 "session": data.get("host_session"), "captures": captures}
        data.pop("review_input_check", None)
    return {"inputs": path, "files": sorted(files), "head": current["head"],
            "instruction": "Pass --inputs to review-prepare. Before any extra-review approval, prepare these inputs first; authorization binds this exact scope."}


def validate(state, worktree, path, live=False):
    identity = read_json(state)
    manifest = read_json(path)
    binding = identity.get("review_inputs")
    require(binding and binding["path"] == str(Path(path).resolve()) and binding["sha256"] == digest(path)
            and binding["session"] == identity.get("host_session"), "review inputs not bound to this session")
    require(manifest["revision"] == revision(worktree), "review inputs describe a stale revision")
    for value in binding.get("captures", {}).values():
        require(digest(value["path"]) == value["sha256"], "review source changed")
    for value in manifest["files"].values():
        require(digest(value["path"]) == value["sha256"], "review source changed")
    require(read_json(manifest["files"]["inventory"]["path"]) == identity["requirements"], "review inventory changed")
    if live:
        require(github(manifest["pr"]) == {k: v for k, v in read_json(manifest["files"]["pr_body"]["path"]).items() if k not in {"kind", "pr"}},
                "live PR changed; regenerate inputs and review affected changes")
    return {**{k: v["path"] for k, v in manifest["files"].items()}, "review_inputs": str(Path(path).resolve())}


def check(state, worktree, worker):
    identity = read_json(state)
    reviewed = identity["workers"][worker]
    require(reviewed.get("accepted") and not reviewed["terminated"], "check requires accepted review")
    source = reviewed["files"].get("review_inputs")
    require(source and digest(source["path"]) == source["sha256"], "reviewed typed input manifest required")
    validate(state, worktree, source["path"], live=True)
    with Runtime(state).transaction() as data:
        require(data.get("host_session") == identity.get("host_session")
                and data.get("review_inputs") == identity.get("review_inputs"), "owner/inputs changed during PR check")
        data["review_input_check"] = {"worker": worker, "head": revision(worktree)["head"],
                                      "session": data.get("host_session"), "sha256": source["sha256"],
                                      "wall": Runtime(state).clock.stamp()["wall"]}
    return {"passed": True, "worker": worker}
