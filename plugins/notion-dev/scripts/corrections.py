"""Correction preflight over existing findings and current sources, not a new ledger.

Literal occurrence accounting is a completeness aid. Independent review still owns
semantic correctness, mandatory coverage, and indirect-effect judgments.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess

from runtime import digest, finding_ledger, findings_accounted, read_json, require, revision
from execution import json_file


def sources(worktree, files):
    root = Path(worktree).resolve()
    names = subprocess.check_output(["git", "-C", str(root), "ls-files", "--stage", "-z"], encoding="utf-8").split("\0")
    values, excluded = {}, {}
    for entry in names:
        if not entry: continue
        metadata, _, name = entry.partition("\t")
        path = root / name
        if metadata.startswith("160000 "):
            excluded["repo:" + name] = "gitlink: " + metadata
            continue
        if path.is_symlink():  # Before exists(): a dangling link is still reported.
            excluded["repo:" + name] = "symlink: " + os.readlink(str(path))
        elif not path.exists(): continue  # Committed deletions are absent from ls-files.
        elif path.is_dir():
            excluded["repo:" + name] = "non-file tracked path"
        else:
            values["repo:" + name] = path
    for name, filename in files.items():
        if name in {"inventory", "review_inputs", "verification_receipts", "diff"}: continue
        path = Path(filename)
        data = path
        if name == "pr_body":
            parsed = read_json(path)
            require(parsed.get("kind") == "github-pr" and isinstance(parsed.get("body"), str), "typed PR body required")
            data = parsed["body"].encode("utf-8")
        values["input:" + name] = data
    return values, excluded


def batch(state, previous, worktree, inputs, checklist=None):
    from review_inputs import validate
    identity = read_json(state)
    worker = identity["workers"][previous]
    require(worker.get("accepted") and findings_accounted(worker), "account for the accepted baseline's complete findings first")
    files = validate(state, worktree, inputs)
    # Recording obligations are downstream facts, not defects to correct again.
    dispositions = {d["id"]: d["action"] for d in worker.get("finding_judgments", {}).get("dispositions", [])}
    entries = []
    for entry in finding_ledger(worker["result"]):
        if entry["id"].startswith("recording."): continue
        evidence = entry["evidence"]
        if isinstance(evidence, dict):
            if evidence.get("resolved") is True: continue
            if (entry["obligation"] == "advisory" and not evidence.get("blocking")
                    and dispositions.get(entry["id"]) != "absorb"): continue
        entries.append(entry)
    if not entries:
        require(checklist is None, "no corrective findings; omit the obsolete worksheet")
        return {"passed": True, "findings": 0}
    values, excluded = sources(worktree, files)
    binding = {"previous": previous, "result_sha256": hashlib.sha256(
        json.dumps(worker["result"], sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
        "revision": revision(worktree), "inputs_sha256": digest(inputs),
        "sources": {k: digest(v) if isinstance(v, Path) else hashlib.sha256(v).hexdigest() for k, v in values.items()},
        "excluded": excluded}
    token = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
    if checklist is None:
        path = Path(state).resolve().parent / ("correction-batch-" + token + ".json")
        template = {"binding": token, "items": [{"id": e["id"], "finding": e["evidence"],
            "anchors": [], "no_literal_reason": "", "locations": ["input:pr_body"],
            "disposition": "", "evidence": "", "retained": {}} for e in entries]}
        # This is the author's editable worksheet, not accepted review evidence.
        if not path.exists(): json_file(template, path)
        index = path.with_name("correction-sources-" + token + ".json")
        json_file({"sources": list(values), "excluded": excluded}, index)
        return {"passed": not entries, "checklist": str(path), "binding": token, "findings": len(entries),
                "source_index": str(index), "source_count": len(values),
                "inputs": [k for k in values if k.startswith("input:")], "excluded": excluded, "instruction":
                "For EVERY finding list reported locations, retired literal anchors (or explain no literal), "
                "disposition corrected/not-applicable and evidence. Include current PR body. "
                "Scan results identify all remaining occurrences; retain one only with a source-specific explanation. "
                "Pass the completed file as review-prepare --corrections; no new agent or self-approved verdict."}
    supplied = read_json(checklist)
    require(supplied.get("binding") == token, "correction batch is stale; regenerate after source/head/input changes")
    items = supplied.get("items")
    require(isinstance(items, list) and all(isinstance(i, dict) for i in items), "correction items required")
    require(len(items) == len(entries) and {i.get("id") for i in items} == {e["id"] for e in entries},
            "account for every finding exactly once")
    unresolved, occurrences = [], []
    for item in items:
        require(item.get("disposition") in {"corrected", "not-applicable"}
                and isinstance(item.get("evidence"), str) and item["evidence"].strip(),
                "each correction needs disposition and evidence")
        locations = item.get("locations")
        require(isinstance(locations, list) and locations and all(p in values for p in locations)
                and "input:pr_body" in locations, "name affected current sources and include input:pr_body")
        anchors = item.get("anchors")
        require(isinstance(anchors, list) and all(isinstance(a, str) and a.strip() for a in anchors), "anchors must be nonempty literals")
        require(anchors or (isinstance(item.get("no_literal_reason"), str) and item["no_literal_reason"].strip()),
                "retired anchors or an explicit no-literal explanation required")
        retained = item.get("retained", {})
        require(isinstance(retained, dict) and all(k in values and isinstance(v, str) and v.strip() for k, v in retained.items()),
                "retained occurrences require source-specific evidence")
    # One source in memory/read at a time, not an eager copy of the repository per finding.
    for name, source in values.items():
        data = source.read_bytes() if isinstance(source, Path) else source
        for item in items:
            anchors, retained = item["anchors"], item.get("retained", {})
            hits = {a: data.count(a.encode("utf-8")) for a in anchors if a.encode("utf-8") in data}
            if hits:
                occurrence = {"id": item["id"], "source": name, "counts": hits, "retained": retained.get(name)}
                occurrences.append(occurrence)
                if name not in retained: unresolved.append(occurrence)
    return {"passed": not unresolved, "binding": token, "occurrences": occurrences,
            "unresolved": unresolved, "excluded": excluded,
            "checklist": str(Path(checklist).resolve()), "sha256": digest(checklist),
            "instruction": "Literal accounting is not independent approval. Reviewer must inspect retained occurrences, "
                           "location completeness, new claims and indirect effects; all existing gates still apply."}
