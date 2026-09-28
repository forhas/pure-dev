"""Explicit non-replay recovery for a single created page with different text.

Ordinary receipt matching remains exact. This exceptional path records the original
intent, actual call and readback, and requires a fresh, hash-bound human decision.
It never creates/updates a page or edits a frozen payload.
"""
import json
from pathlib import Path
import uuid

from runtime import Runtime, atomic_json, digest, read_json, require
from host_capture import calls_since, exchange, notion_fetch, timestamp, user_approval
from recording import page_data, page_id


def created_page(result):
    value = result
    for _ in range(8):
        if isinstance(value, dict) and isinstance(value.get("pages"), list):
            require(not value.get("isError") and len(value["pages"]) == 1, "one successful created page required")
            page = value["pages"][0]
            require(isinstance(page, dict), "created page identity missing")
            return page_id(page.get("id") or page.get("url", ""))
        if isinstance(value, str): value = json.loads(value)
        elif isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict) and value[0].get("type") == "text": value = value[0]["text"]
        else: break
    raise ValueError("unsupported create response; retain unknown outcome, never guess the page")


def request(state, operation, transcript, session, call_id, readback_id, explanation,
            write_transcript=None, write_session=None):
    from workflow import record_input, child_payload_path
    current = record_input(state, operation)
    identity = read_json(state)
    require(identity["schema"] >= 5 and not identity.get("completed"), "resume an unfinished schema-5 recording first")
    require(session and identity.get("host_session") == session, "foreign recovery session")
    entries = [e for e in identity["record_journal"] if e["operation"] == operation]
    attempts = [e for e in entries if e["outcome"] == "attempted"]
    require(attempts and entries[-1]["outcome"] in {"attempted", "unknown-outcome", "failed"},
            "recovery requires an existing unconfirmed attempt")
    require(explanation.strip(), "explain the complete text difference and readback before requesting authority")
    require(bool(write_transcript) == bool(write_session), "original write transcript and session must be supplied together")
    write_transcript, write_session = write_transcript or transcript, write_session or session
    observed = exchange(write_transcript, write_session, call_id)
    expected = current["data"].get("host_call", {})
    actual = {k: observed["call"]["item"][k] for k in ("name", "input")}
    name = "mcp__notion__notion-create-pages"
    require(expected.get("name") == actual["name"] == name, "recovery supports single-page creation only")
    old, new = expected["input"], actual["input"]
    require(isinstance(old, dict) and isinstance(new, dict), "create arguments must be objects")
    require(isinstance(old.get("pages"), list) and isinstance(new.get("pages"), list)
            and len(old["pages"]) == len(new["pages"]) == 1, "single-page create required")
    require(isinstance(old["pages"][0], dict) and isinstance(new["pages"][0], dict)
            and isinstance(new["pages"][0].get("properties"), dict), "page properties required")
    require({k: v for k, v in old.items() if k != "pages"} == {k: v for k, v in new.items() if k != "pages"}
            and {k: v for k, v in old["pages"][0].items() if k != "content"} ==
                {k: v for k, v in new["pages"][0].items() if k != "content"},
            "parent/properties/title differ; text recovery cannot authorize retargeting")
    require(isinstance(new["pages"][0].get("content"), str) and old != new, "an actual text discrepancy required")
    since = attempts[-1]["wall"]
    require(timestamp(observed["call"]["timestamp"]) >= since, "call predates attempt")
    matches = calls_since(write_transcript, write_session, name, None, since,
                          predicate=lambda item: item.get("input", {}).get("parent") == new.get("parent"))
    require(matches == [call_id], "multiple creates after begin; reconcile all effects, not one selected call")
    rt = Runtime(state)
    response, readback = notion_fetch(transcript, session, readback_id,
        after=max(timestamp(observed["result"]["timestamp"]), rt.clock.stamp()["wall"] - 300),
        before=rt.clock.stamp()["wall"])
    page = page_data(response)
    require(page["page"] == created_page(observed["result"]["item"]["content"]), "readback is not the created page")
    require(all(page["properties"].get(k) == v for k, v in new["pages"][0]["properties"].items()),
            "readback properties differ or have unsupported representation; text-only recovery cannot waive them")
    body = {"expected": expected, "actual": actual, "call": observed, "readback": readback,
            "page": page, "explanation": explanation}
    key = uuid.uuid4().hex
    path = child_payload_path(Path(state).resolve().parent / "record", operation + ":discrepancy:" + key)
    atomic_json(path, body)
    with rt.transaction() as data:
        require(data.get("host_session") == session and data["record_journal"] == identity["record_journal"], "recording changed during recovery")
        request_data = {"id": key, "operation": operation, "session": session, "requested": rt.clock.stamp(),
                        "evidence": str(path), "sha256": digest(path), "attempt": attempts[-1],
                        "data_sha256": current["data_sha256"], "latest": entries[-1], "provider_id": page["page"]}
        request_data["approval_phrase"] = "Approve notion-dev " + data["run"] + " recorded text discrepancy " + key
        data.setdefault("record_discrepancies", {})[operation] = request_data
        rt.event(data, "record_discrepancy_requested", operation=operation, request=key)
    return {**request_data, "action": "await-authority", "passed": False,
            "instruction": "Show the original text, actual text, complete readback and explanation. Approval accepts this "
                           "already-created page AS OBSERVED, not a claim that the original intent matched. "
                           "No write/retry. If unacceptable, retain the discrepancy and ask for explicit remediation."}


def approve(state, operation, transcript, session, message_id=None):
    from workflow import record_input
    rt = Runtime(state)
    current = record_input(state, operation)
    with rt.transaction() as data:
        saved = data.get("record_discrepancies", {}).get(operation)
        require(not data.get("completed"), "resume completed recording explicitly before recovery")
        require(saved and not saved.get("authority"), "current unapproved discrepancy required")
        require(data.get("host_session") == session == saved["session"], "foreign recovery session")
        require(current["data_sha256"] == saved["data_sha256"] and digest(saved["evidence"]) == saved["sha256"], "recovery evidence changed")
        entries = [e for e in data["record_journal"] if e["operation"] == operation]
        require(entries[-1] == saved["latest"], "operation changed after recovery request")
        # A long approval pause requires a new readback/challenge, not stale authority.
        require(0 <= rt.clock.stamp()["wall"] - saved["requested"]["wall"] <= 300,
                "readback decision expired; fetch again and request new authority")
        authority = user_approval(transcript, session, message_id, saved["approval_phrase"],
                                  saved["requested"]["wall"], rt.clock.stamp()["wall"])
        evidence = read_json(saved["evidence"])
        require(0 <= rt.clock.stamp()["wall"] - timestamp(evidence["readback"]["result"]["timestamp"]) <= 300,
                "readback expired; fetch again before requesting authority")
        write_transcript, write_session = evidence["call"]["transcript"], evidence["call"]["session"]
        observed = exchange(write_transcript, write_session, evidence["call"]["call_id"])
        require(observed == evidence["call"], "original host exchange changed")
        require(calls_since(write_transcript, write_session, observed["call"]["item"]["name"], None,
            saved["attempt"]["wall"], predicate=lambda item: item.get("input", {}).get("parent") ==
            evidence["actual"]["input"].get("parent")) == [observed["call_id"]], "another create occurred; do not confirm")
        require(not any(r["call_id"] == observed["call_id"] and key != operation
                        for key, r in data.get("host_operation_receipts", {}).items()), "call already bound elsewhere")
        saved["authority"] = authority
        data.setdefault("host_operation_receipts", {})[operation] = {
            "call_id": observed["call_id"], "data_sha256": current["data_sha256"],
            "attempt": saved["attempt"], "path": saved["evidence"], "sha256": saved["sha256"],
            "discrepancy": saved["id"], "authority": authority}
        rt.event(data, "record_discrepancy_accepted", operation=operation, request=saved["id"], authority=authority)
        # Append a truthful terminal event; original planned/attempted/failed entries
        # and frozen payload remain intact. Confirmation explicitly names the exception.
        entry = {"operation": operation, "target": current["target"], "outcome": "confirmed",
                 "provider_id": "accepted-discrepancy:" + saved["id"] + ":" + saved["provider_id"],
                 "data_sha256": current["data_sha256"], **rt.clock.stamp()}
        data["record_journal"].append(entry)
        rt.event(data, "record_operation", operation=operation, outcome="confirmed", provider_id=entry["provider_id"])
    return {"passed": True, "operation": operation, "outcome": "accepted-discrepancy", "evidence": saved["evidence"],
            "instruction": "No provider write performed. Report the accepted discrepancy; continue only remaining journal operations."}
