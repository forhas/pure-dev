"""Read a completed Claude Code tool exchange, never execute transcript content.

The local host/log is trusted; this is not remote provider attestation. Only the
explicit transcript is read (no recursive session discovery or credential reads).
"""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("host timestamps must include a timezone")
    return parsed.timestamp()


def latest_call(transcript, session, name, arguments=None, page=None):
    """Select identity mechanically; a missing/failed latest result never falls back.

    Claude need not see its internal tool IDs. Use the exact frozen write arguments
    or requested page, not a broad 'last tool call' heuristic.
    """
    if not transcript or not session or (arguments is None and not page):
        raise ValueError("actual host transcript, session and exact call selector required")
    if page:
        normalized = page.lower().replace("-", "")
        if len(normalized) != 32 or any(c not in "0123456789abcdef" for c in normalized):
            raise ValueError("capture page selector must be the actual Notion page UUID")
    found = None
    with Path(transcript).open("rb") as stream:
        for raw in stream:
            # A partial tail may be the newer matching call; never return an older one.
            if not raw.endswith(b"\n"): raise ValueError("host transcript tail is incomplete; retry after delivery")
            if not raw.strip(): continue
            row = json.loads(raw.decode("utf-8"))
            if not isinstance(row, dict) or row.get("sessionId") != session or row.get("isSidechain"): continue
            message = row.get("message")
            if row.get("type") != "assistant" or not isinstance(message, dict) or message.get("role") != "assistant": continue
            content = message.get("content", [])
            if not isinstance(content, list): continue
            for item in content:
                if not isinstance(item, dict) or item.get("type") != "tool_use" or item.get("name") != name: continue
                args = item.get("input")
                if arguments is not None and args != arguments: continue
                if page and (not isinstance(args, dict) or page.lower().replace("-", "") not in
                             str(args.get("id", "")).lower().replace("-", "")): continue
                found = item.get("id")
    if not found: raise ValueError("matching host tool call unavailable; never reconstruct it")
    return found


def exchange(transcript, session, call_id):
    if not transcript or not session or not call_id:
        raise ValueError("actual host transcript, session and tool-call ID required; restart for SessionStart or supply its real log path")
    call, result = None, None
    path = Path(transcript).resolve()
    with path.open("rb") as stream:
        for line_number, raw in enumerate(stream, 1):
            # A live writer may not have finished the last record. Never interpret
            # a prefix as a successful provider response; retry after host delivery.
            if not raw.endswith(b"\n"):
                break
            if not raw.strip():
                continue
            row = json.loads(raw.decode("utf-8"))
            if not isinstance(row, dict):
                continue
            message = row.get("message", {})
            if not isinstance(message, dict):
                continue
            content = message.get("content", [])
            if not isinstance(content, list):
                continue
            for item in content:
                if not isinstance(item, dict):
                    continue
                is_call = item.get("type") == "tool_use" and item.get("id") == call_id
                is_result = item.get("type") == "tool_result" and item.get("tool_use_id") == call_id
                if not (is_call or is_result):
                    continue
                if row.get("sessionId") != session or row.get("isSidechain"):
                    raise ValueError("tool exchange belongs to a foreign/child host session")
                expected_role = "assistant" if is_call else "user"
                if row.get("type") != expected_role or message.get("role") != expected_role:
                    raise ValueError("unsupported host tool record role")
                observed = {"item": item, "timestamp": row["timestamp"], "line": line_number,
                            "sha256": hashlib.sha256(raw).hexdigest()}
                timestamp(observed["timestamp"])
                previous = call if is_call else result
                if previous and previous["item"] != item:
                    raise ValueError("conflicting records for one tool-call ID")
                if is_call and call is None:
                    call = observed
                elif is_result and result is None:
                    result = observed
    if call is None or result is None:
        raise ValueError("completed tool exchange not in host transcript yet; wait for delivery, never reconstruct it")
    if result["line"] <= call["line"] or timestamp(result["timestamp"]) < timestamp(call["timestamp"]):
        raise ValueError("tool response predates its request")
    if result["item"].get("is_error"):
        raise ValueError("failed host tool response cannot establish success")
    return {"session": session, "call_id": call_id, "transcript": str(path),
            "call": call, "result": result}


def notion_fetch(transcript, session, call_id=None, after=None, before=None, page=None):
    call_id = call_id or latest_call(transcript, session, "mcp__notion__notion-fetch", page=page)
    observed = exchange(transcript, session, call_id)
    call = observed["call"]["item"]
    if call.get("name") != "mcp__notion__notion-fetch":
        raise ValueError("full notion-fetch required; status queries are not ticket captures")
    started = timestamp(observed["call"]["timestamp"])
    finished = timestamp(observed["result"]["timestamp"])
    if (after is not None and started < after) or (before is not None and finished > before):
        raise ValueError("provider fetch is outside the capture challenge window")
    response = observed["result"]["item"].get("content")
    # Keep the real provider object, including all unknown fields. Decode only the
    # host transport envelope; runtime.notion_source validates page completeness.
    if isinstance(response, list):
        if len(response) != 1 or response[0].get("type") != "text":
            raise ValueError("unsupported host result envelope; no lossy concatenation")
        response = response[0]["text"]
    if isinstance(response, str):
        response = json.loads(response)
    if not isinstance(response, dict):
        raise ValueError("provider page response must be an object")
    return response, observed


def session_env():
    """Optional SessionStart bridge: JSON-decode paths, then shell-quote as data."""
    row = json.load(sys.stdin)
    path = row.get("transcript_path")
    target = os.environ.get("CLAUDE_ENV_FILE")
    if not target or not isinstance(path, str) or not path or any(c in path for c in "\r\n\0"):
        return
    with open(target, "a", encoding="utf-8", newline="\n") as stream:
        stream.write("export NOTION_DEV_TRANSCRIPT=" + shlex.quote(path) + "\n")


if __name__ == "__main__":
    try:
        if sys.argv[1:] != ["session-env"]:
            raise ValueError("only the SessionStart session-env bridge is a standalone command")
        session_env()
    except (OSError, ValueError, TypeError):
        sys.exit(1)  # The hook is optional; capture-ticket itself fails closed.
