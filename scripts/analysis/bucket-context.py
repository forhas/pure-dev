#!/usr/bin/env python3
"""Bucket a Claude Code session transcript's message volume by source.

Usage:  python3 bucket-context.py <session.jsonl>

Find the transcript with:
  ls -lt ~/.claude/projects/*BTC*/*.jsonl | head
(Windows: %USERPROFILE%\\.claude\\projects\\...)

Prints chars and approximate tokens (chars/4) per bucket, largest first.
Emits no file content -- only names, counts and sizes.
"""
import json, sys, os
from collections import defaultdict

path = sys.argv[1]
by_bucket = defaultdict(int)
by_bucket_n = defaultdict(int)
tool_of = {}          # tool_use_id -> tool name
skill_hits = defaultdict(int)

def size(x):
    if isinstance(x, str):
        return len(x)
    return len(json.dumps(x, ensure_ascii=False))

with open(path, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        msg = rec.get("message") or {}
        content = msg.get("content")
        if isinstance(content, str):
            by_bucket["assistant text" if rec.get("type") == "assistant" else "user text"] += len(content)
            by_bucket_n["assistant text" if rec.get("type") == "assistant" else "user text"] += 1
            continue
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if kind == "text":
                b = "assistant text" if rec.get("type") == "assistant" else "user text"
                by_bucket[b] += size(block.get("text", ""))
                by_bucket_n[b] += 1
            elif kind == "thinking":
                by_bucket["thinking"] += size(block.get("thinking", ""))
                by_bucket_n["thinking"] += 1
            elif kind == "tool_use":
                name = block.get("name", "?")
                tool_of[block.get("id")] = name
                inp = block.get("input") or {}
                by_bucket[f"call:{name}"] += size(inp)
                by_bucket_n[f"call:{name}"] += 1
                # Skill invocations tell us which SKILL.md bodies got loaded
                if name == "Skill":
                    skill_hits[str(inp.get("skill", "?"))] += 1
                # Bash commands: bucket by the leading word too
                if name == "Bash":
                    cmd = str(inp.get("command", "")).strip().split() or ["?"]
                    by_bucket[f"  bash-cmd:{cmd[0]}"] += 0
            elif kind == "tool_result":
                name = tool_of.get(block.get("tool_use_id"), "unknown-tool")
                by_bucket[f"result:{name}"] += size(block.get("content", ""))
                by_bucket_n[f"result:{name}"] += 1

total = sum(v for k, v in by_bucket.items() if not k.startswith("  "))
print(f"transcript: {os.path.basename(path)}")
print(f"total message chars: {total:,}  (~{total//4:,} tokens)\n")
print(f"{'bucket':<48}{'n':>6}{'chars':>12}{'~tokens':>10}{'%':>7}")
print("-" * 83)
for k, v in sorted(by_bucket.items(), key=lambda kv: -kv[1]):
    if v == 0:
        continue
    print(f"{k:<48}{by_bucket_n[k]:>6}{v:>12,}{v//4:>10,}{100*v/total:>6.1f}%")

if skill_hits:
    print("\nSkill invocations (each loads that SKILL.md into this context):")
    for k, n in sorted(skill_hits.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<44}{n:>4}x")
