#!/usr/bin/env python3
"""Read-only Claude JSONL usage accounting; cache traffic is not window occupancy.

Usage: telemetry.py SESSION.jsonl [--runtime state.json]
Includes SESSION/subagents/*.jsonl. Never executes transcript tools or copies
prompt bodies. Output is a snapshot through each file's last observed request.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys


FIELDS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")


def analyze(path, stages=()):
    raw = Path(path).read_bytes()
    records = []
    incomplete_tail = False
    # Split on the RAW BYTES before decoding anything. The tolerance below is for a live
    # writer caught mid-record, and a writer can equally be caught mid-CHARACTER: decoding
    # the whole buffer would raise UnicodeDecodeError on a truncated multibyte sequence
    # before the tolerance could run, so a snapshot of any transcript containing non-ASCII
    # text failed outright instead of returning the complete records it did have.
    #
    # The delimiter is also the only thing that distinguishes a partial write from a
    # complete corrupt record -- `splitlines()` erases it, landing `{bad}\n` and `{bad`
    # alike at the end. A terminated record is COMPLETE, so a malformed one is corruption
    # and must refuse totals rather than silently lowering them.
    complete, delimiter, tail = raw.rpartition(b"\n")
    lines = (complete + delimiter).decode("utf-8").splitlines() if delimiter else []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            raise ValueError(f"invalid JSONL at line {index + 1}; refusing partial totals")
    # An unterminated tail, decoded on its own. A writer that has finished the record but
    # not the newline still parses and counts; only one that cannot be read is tolerated.
    if tail.strip():
        try:
            # UnicodeDecodeError subclasses ValueError, so one clause covers both a tail
            # truncated mid-character and one truncated mid-record.
            records.append(json.loads(tail.decode("utf-8")))
        except ValueError:
            incomplete_tail = True
    groups = defaultdict(list)
    tools = {}
    compactions = 0
    for record in records:
        message = record.get("message", {})
        if record.get("type") == "assistant" and message.get("usage"):
            if not message.get("id"):
                raise ValueError("usage record missing message ID; cannot deduplicate")
            groups[message["id"]].append(record)
        compactions += record.get("subtype") == "compact_boundary"
        content = message.get("content", [])
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tools[block["id"]] = block["name"]
    totals = Counter({field: 0 for field in FIELDS})
    per_stage = defaultdict(Counter)
    peak = 0
    last = None
    for group in groups.values():
        inputs = {tuple(r["message"]["usage"].get(k, 0) for k in FIELDS[:3]) for r in group}
        if len(inputs) != 1:
            raise ValueError("streamed input counters disagree; refusing ambiguous totals")
        usage = {key: max(r["message"]["usage"].get(key, 0) for r in group) for key in FIELDS}
        if any(type(n) is not int or n < 0 for n in usage.values()):
            raise ValueError("usage counters must be nonnegative integers")
        usage["requests"] = 1
        totals.update(usage)
        peak = max(peak, sum(usage[k] for k in FIELDS[:3]))
        stamp = group[0].get("timestamp")
        last = max(last or "", stamp or "")
        # ISO timestamps are normalized before comparing offsets/Z spellings.
        from datetime import datetime
        parse = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
        label = "unattributed"
        for event in stages:
            if stamp and parse(event["utc"]) <= parse(stamp):
                label = event["stage"]
        per_stage[label].update(usage)
    return {"file": Path(path).name, "sha256": hashlib.sha256(raw).hexdigest(),
            "usage": dict(totals), "peak_input_context_tokens": peak,
            "tool_calls": dict(Counter(tools.values())), "compactions": compactions,
            "last_observed_request": last, "incomplete_tail": incomplete_tail,
            "stages": {k: dict(v) for k, v in per_stage.items()}}


def roster(state):
    """Runtime workers as an attribution table: agent ID -> role, slot, and stage.

    The stage is the one the run was IN when the worker was prepared, read off the
    `worker_prepared` event rather than inferred from timestamps. A child's requests
    overlap the parent's and each other's, so placing them on the parent's stage
    timeline by clock would invent a sequence that never happened.
    """
    prepared = {e["worker"]: e for e in state.get("events", []) if e["kind"] == "worker_prepared"}
    workers = []
    for key, worker in state.get("workers", {}).items():
        workers.append({"worker": key, "role": worker["role"], "slot": worker.get("slot"),
                        "agent_id": worker.get("agent_id"),
                        "stage": prepared.get(key, {}).get("stage"),
                        "accepted": worker.get("accepted", False),
                        "terminated": worker.get("terminated", False)})
    return sorted(workers, key=lambda w: (w["role"], w["worker"]))


def correlate(workers, logs):
    """Match child logs to workers by host agent ID; leave the rest explicitly unknown.

    Both directions are reported. A worker whose log is absent is UNKNOWN cost, not
    zero -- that distinction is the whole reason this returns lists rather than one
    coverage number someone would read as completeness.
    """
    by_agent = {w["agent_id"]: w for w in workers if w["agent_id"]}
    attribution, matched = {}, set()
    for name in logs:
        stem = Path(name).stem
        worker = by_agent.get(stem)
        if worker is None:
            # Some hosts decorate the filename around the agent ID. An unambiguous
            # containment match is still evidence; an ambiguous one is not.
            # This host writes agent-a<name>-<hex>.jsonl for <name>@<session>.
            # Anchor the whole name: "review" must not also match "review-p2".
            candidates = [w for agent, w in by_agent.items() if agent and
                          (agent in stem or re.fullmatch(r"agent-a" + re.escape(agent.split("@", 1)[0])
                                                        + r"-[0-9a-f]+", stem))]
            worker = candidates[0] if len(candidates) == 1 else None
        attribution[name] = worker
        if worker:
            matched.add(worker["worker"])
    attached = [w for w in workers if w["agent_id"]]
    return {"attribution": attribution,
            "summary": {
                "workers": len(workers), "attached_workers": len(attached),
                "child_logs": len(logs), "matched_workers": len(matched),
                "log_coverage_percent": round(100.0 * len(matched) / len(attached), 1)
                if attached else None,
                "missing_logs": [{k: w[k] for k in ("worker", "role", "agent_id")}
                                 for w in attached if w["worker"] not in matched],
                "unattached_workers": [{k: w[k] for k in ("worker", "role")}
                                       for w in workers if not w["agent_id"]],
                "unmatched_logs": [n for n, w in attribution.items() if w is None],
                "note": "A worker with no log is unknown cost, never zero. An unmatched "
                        "log is real cost this run cannot attribute to a role."}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument("--runtime", type=Path)
    args = parser.parse_args()
    stages, workers = [], []
    if args.runtime:
        state = json.loads(args.runtime.read_text(encoding="utf-8"))
        stages = [e for e in state["events"] if e["kind"] == "stage_started"]
        workers = roster(state)
    parent = analyze(args.session, stages)
    # Children are separate scopes; do not pretend their overlapping work is a
    # sequential parent stage. A missing child log is unknown, never zero cost.
    paths = sorted(args.session.with_suffix("").glob("subagents/*.jsonl"))
    agents = [analyze(path) for path in paths]
    links = correlate(workers, [path.name for path in paths])
    by_role = defaultdict(Counter)
    for child in agents:
        worker = links["attribution"].get(child["file"])
        child["worker"] = worker["worker"] if worker else None
        child["role"] = worker["role"] if worker else "unattributed"
        child["slot"] = worker["slot"] if worker else None
        child["runtime_stage"] = worker["stage"] if worker else None
        by_role[child["role"]].update(child["usage"])
    total = Counter(parent["usage"])
    for child in agents:
        total.update(child["usage"])
    print(json.dumps({"parent": parent, "agents": agents, "usage": dict(total),
                      "new_input_plus_output": sum(total[k] for k in FIELDS if k != "cache_read_input_tokens"),
                      "total_token_traffic": sum(total[k] for k in FIELDS),
                      "correlation": links["summary"],
                      "by_role": {role: dict(counts) for role, counts in sorted(by_role.items())},
                      # Peaks are concurrent scopes. Adding them would describe a
                      # context window no single request ever held.
                      "peak_context": {"parent": parent["peak_input_context_tokens"],
                                       "max_child": max([c["peak_input_context_tokens"] for c in agents] or [0]),
                                       "note": "the largest single request in each scope; peaks are never summed"},
                      "coverage": "Only available logs through their last observed request; not a billing invoice. Child roles come from the runtime roster; missing and unmatched logs are reported rather than absorbed. Thinking is included in output."},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", newline="\n")
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        sys.exit(2)
