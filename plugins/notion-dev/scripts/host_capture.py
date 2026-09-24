"""Read a completed Claude Code tool exchange, never execute transcript content.

The local host/log is trusted; this is not remote provider attestation. Only the
explicit transcript is read (no recursive session discovery or credential reads).
"""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
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
    found = [call for call, _ in _matching_calls(transcript, session, name, arguments, page)]
    if not found: raise ValueError("matching host tool call unavailable; never reconstruct it")
    return found[-1]


def calls_since(transcript, session, name, arguments, since, predicate=None):
    """Every matching call after begin; a narrow predicate may extend exact matching."""
    return [call for call, stamp in _matching_calls(transcript, session, name, arguments, None, predicate)
            if timestamp(stamp) >= since]


def _matching_calls(transcript, session, name, arguments, page, predicate=None):
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
                if predicate is not None and not predicate(item): continue
                if arguments is not None and args != arguments: continue
                if page and (not isinstance(args, dict) or page.lower().replace("-", "") not in
                             str(args.get("id", "")).lower().replace("-", "")): continue
                yield item.get("id"), row["timestamp"]


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
    payload = observed["result"]["item"].get("content")
    # Claude may retain the actual successful response in this session's tool-results
    # directory instead of the JSONL. Never follow arbitrary paths from tool content.
    if isinstance(payload, str):
        spilled = re.match(r"^Error: result \([\d,]+ characters across \d+ lines?\) exceeds maximum allowed tokens\. Output has been saved to (.+)\.\r?\nFormat: Plain text\r?\n", payload)
        if spilled:
            root = Path(transcript).resolve().with_suffix("") / "tool-results"
            path = Path(spilled[1]).resolve()
            if path.parent != root.resolve() or path.suffix != ".txt":
                raise ValueError("persisted tool result must belong to this exact host session")
            with path.open("rb") as stream:
                raw = stream.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                raise ValueError("persisted page exceeds 4 MiB; explicit scoped adapter required")
            payload = raw.decode("utf-8")
            observed["persisted_result"] = {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    response = page_response(payload)
    return response, observed


def page_response(value):
    """Decode only known transport wrappers; keep every field of the actual page."""
    for _ in range(10):
        if isinstance(value, dict):
            if any(value.get(k) for k in ("isError", "truncated", "has_more")):
                raise ValueError("failed or incomplete page response")
            if isinstance(value.get("metadata"), dict) and value["metadata"].get("type") == "page":
                return value
            if "content" not in value:
                break
            value = value["content"]
        elif isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict) and value[0].get("type") == "text":
            value = value[0].get("text")
        elif isinstance(value, str):
            value = json.loads(value)
        else:
            break
    raise ValueError("unsupported page response envelope; no lossy concatenation")


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
