#!/usr/bin/env python3
"""Bucket a Claude Code session transcript by what actually occupies the context window.

Usage:  python3 bucket-context.py <session.jsonl>

Find the transcript with:
  ls -lt ~/.claude/projects/*/*.jsonl | head
(Windows: %USERPROFILE%\\.claude\\projects\\...)

Counts three record classes that reach the model -- assistant turns, user turns, and
`attachment` records (hook output, skill listings, style reminders, file snapshots).
Transcript bookkeeping (mode, ai-title, pr-link, queue-operation, file-history-*) is
excluded. Subagent turns are reported separately when the transcript carries them.

Emits no file content -- only names, counts and sizes.
"""
import json, sys, os
from collections import defaultdict

BOOKKEEPING = {
    "mode", "ai-title", "pr-link", "atis-latch", "bridge-session", "last-prompt",
    "queue-operation", "file-history-delta", "file-history-snapshot",
}

def size(x):
    return len(x) if isinstance(x, str) else len(json.dumps(x, ensure_ascii=False))

def main(path):
    tok = defaultdict(int)
    num = defaultdict(int)
    tool_of = {}
    skills = defaultdict(int)
    sidechain = 0

    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            kind = rec.get("type")
            if kind in BOOKKEEPING:
                continue
            if rec.get("isSidechain"):
                sidechain += 1

            # Attachments: hook output, listings, reminders. Named by their own subtype.
            if kind == "attachment":
                att = rec.get("attachment") or {}
                sub = att.get("type", "?")
                if sub in ("hook_success", "hook_additional_context"):
                    hook = att.get("hookName") or att.get("hookEvent") or "?"
                    label = f"hook:{hook}"
                else:
                    label = f"attach:{sub}"
                tok[label] += size(att)
                num[label] += 1
                continue

            msg = rec.get("message") or {}
            content = msg.get("content")
            role = "assistant" if kind == "assistant" else "user"
            if isinstance(content, str):
                tok[f"{role} text"] += len(content)
                num[f"{role} text"] += 1
                continue
            if not isinstance(content, list):
                continue
            for b in content:
                if not isinstance(b, dict):
                    continue
                t = b.get("type")
                if t == "text":
                    tok[f"{role} text"] += size(b.get("text", ""))
                    num[f"{role} text"] += 1
                elif t == "thinking":
                    tok["thinking"] += size(b.get("thinking", ""))
                    num["thinking"] += 1
                elif t == "tool_use":
                    name = b.get("name", "?")
                    tool_of[b.get("id")] = name
                    tok[f"call:{name}"] += size(b.get("input") or {})
                    num[f"call:{name}"] += 1
                    if name == "Skill":
                        skills[str((b.get("input") or {}).get("skill", "?"))] += 1
                elif t == "tool_result":
                    name = tool_of.get(b.get("tool_use_id"), "unknown-tool")
                    tok[f"result:{name}"] += size(b.get("content", ""))
                    num[f"result:{name}"] += 1

    total = sum(tok.values())
    print(f"transcript: {os.path.basename(path)}")
    print(f"context-bearing chars: {total:,}  (~{total//4:,} tokens)")
    if sidechain:
        print(f"note: {sidechain} sidechain (subagent) records included -- not orchestrator-only")
    print()
    print(f"{'bucket':<46}{'n':>6}{'chars':>12}{'~tokens':>10}{'%':>7}")
    print("-" * 81)
    for k, v in sorted(tok.items(), key=lambda kv: -kv[1]):
        if v:
            print(f"{k:<46}{num[k]:>6}{v:>12,}{v//4:>10,}{100*v/total:>6.1f}%")
    if skills:
        print("\nSkill invocations (each loads that SKILL.md body into this context):")
        for k, n in sorted(skills.items(), key=lambda kv: -kv[1]):
            print(f"  {k:<42}{n:>4}x")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
