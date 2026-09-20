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
import sys


FIELDS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")


def analyze(path, stages=()):
    raw = Path(path).read_bytes()
    records = []
    incomplete_tail = False
    lines = raw.decode("utf-8").splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            if index != len(lines) - 1:
                raise ValueError(f"invalid JSONL at line {index + 1}; refusing partial totals")
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument("--runtime", type=Path)
    args = parser.parse_args()
    stages = []
    if args.runtime:
        state = json.loads(args.runtime.read_text(encoding="utf-8"))
        stages = [e for e in state["events"] if e["kind"] == "stage_started"]
    parent = analyze(args.session, stages)
    # Children are separate scopes; do not pretend their overlapping work is a
    # sequential parent stage. A missing child log is unknown, never zero cost.
    agents = [analyze(path) for path in sorted(args.session.with_suffix("").glob("subagents/*.jsonl"))]
    total = Counter(parent["usage"])
    for child in agents:
        total.update(child["usage"])
    print(json.dumps({"parent": parent, "agents": agents, "usage": dict(total),
                      "new_input_plus_output": sum(total[k] for k in FIELDS if k != "cache_read_input_tokens"),
                      "total_token_traffic": sum(total[k] for k in FIELDS),
                      "coverage": "Only available logs through their last observed request; not a billing invoice. Child stage attribution is unavailable without correlation. Thinking is included in output."},
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
