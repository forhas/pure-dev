"""Pure rendering/building of authorized writes. No network, credentials or execution.

The adapter still establishes live scope/schema/authority. Exact old_str edits let
the provider reject changed anchors; this is not a transactional page revision API.
"""
import re

from host_capture import page_response
from runtime import notion_source, require


def page_id(value):
    ids = re.findall(r"[0-9a-f]{32}", str(value).lower().replace("-", ""))
    require(len(ids) == 1, "expected one exact Notion page UUID or URL")
    return ids[0]


def page_data(response):
    response = page_response(response)
    identity, _, props = notion_source(response, [])
    body = re.findall(r"<content>\n?(.*?)</content>\s*</page>", response["text"].replace("\r\n", "\n"), re.S)[0]
    return {"page": identity, "url": response["url"], "properties": props, "content": body}


def pr_body(facts):
    """Stable implementation facts only; review status is a separate runtime view."""
    fields = ("requirement", "behavior", "validation", "risks", "mandatory")
    require(isinstance(facts, dict) and set(facts) == set(fields),
            "PR facts require requirement/behavior/validation/risks/mandatory; no review-history field")
    require(isinstance(facts["requirement"], str) and facts["requirement"].strip(), "requirement must be nonempty")
    for name in fields[1:]:
        require(isinstance(facts[name], list) and all(isinstance(v, str) and v.strip() for v in facts[name]),
                name + " must be an explicit list of facts; preserve required wording")
    require(facts["behavior"] and facts["validation"], "behavior and actual validation evidence required")
    parts = ["## Requirement\n\n" + facts["requirement"]]
    for name, title in (("behavior", "Behavior"), ("validation", "Validation"), ("risks", "Known risks"), ("mandatory", "Required disclosures")):
        if facts[name]: parts.append("## " + title + "\n\n" + "\n\n".join(facts[name]))
    return "\n\n".join(parts) + "\n"


def section_edits(body, sections):
    """Preserve existing human content/heading attributes, append only owned facts.

    One update_content batch for existing sections and one append for missing ones.
    Unknown block structures must use the existing adapter, not a guessed replacement.
    """
    require(isinstance(sections, dict) and sections, "sections must be a nonempty heading/content object")
    headings = section_headings(body)
    updates, additions = [], []
    for name, content in sections.items():
        require(isinstance(name, str) and name.strip() and not any(c in name for c in "\r\n{}"), "invalid heading")
        require(isinstance(content, str) and content.strip(), "section content must be nonempty")
        require(not re.search(r"^#{1,2} ", content, re.M), "section content cannot introduce peer headings")
        matches = [(i, h) for i, h in enumerate(headings)
                   if re.sub(r"\s*\{[^{}]*\}\s*$", "", h[1]).strip().casefold() == name.casefold()]
        require(len(matches) <= 1, "ambiguous duplicate heading; reconcile with adapter")
        if matches:
            i, h = matches[0]
            old = body[h.start():headings[i + 1].start() if i + 1 < len(headings) else len(body)]
            require(body.count(old) == 1, "section anchor is not unique")
            require(content.strip() not in old, "section content already present; reconcile instead of appending again")
            updates.append({"old_str": old, "new_str": old.rstrip() + "\n\n" + content.rstrip() + "\n\n"})
        else:
            color = {"Implementation": "blue", "Merged": "green", "Resolution Log": "purple", "Tasks": "blue"}.get(name)
            heading = "## " + name + (' {color="' + color + '"}' if color else "")
            additions.append(("---\n\n" if name in {"Implementation", "Merged"} else "") + heading + "\n\n" + content.rstrip())
    calls = []
    if updates: calls.append({"command": "update_content", "content_updates": updates})
    if additions: calls.append({"command": "insert_content", "position": {"type": "end"}, "content": "\n\n" + "\n\n".join(additions) + "\n"})
    return calls


def section_headings(body):
    """A heading quoted in a fenced example is not a page section."""
    require(not re.search(r"<code\b", body, re.I), "HTML code blocks require adapter parsing")
    headings, fence = [], None
    for line in re.finditer(r"^.*(?:\n|$)", body, re.M):
        marker = re.match(r"[ \t]*(`{3,}|~{3,})", line[0])
        if marker:
            token = marker[1]
            if fence is None: fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not line[0][marker.end():].strip(): fence = None
            continue
        if fence is None:
            h = re.compile(r"## ([^\n]+)\n?").match(body, line.start())
            if h: headings.append(h)
    require(fence is None, "unclosed code fence; reconcile content before writing")
    return headings


def ticket_sections(facts, inventory, review):
    """Derive resolution facts once from the accepted result, never an author recap."""
    require(isinstance(review, dict) and isinstance(review.get("recording"), dict),
            "canonical recording unavailable; use explicit unknown-coverage recovery through the adapter")
    recording = review["recording"]
    verdicts = {v["id"]: v for v in review["requirements"]}
    coverage = []
    for item in inventory["items"]:
        v = verdicts[item["id"]]
        coverage.append("- " + item["id"] + " — " + v["verdict"] + ": " + item["text"] + "\n  Evidence: " + v["citation"])
    details = ["**PR:** " + facts["pr_url"], "**Completeness**\n\n" + "\n".join(coverage)]
    for name in ("claims", "caveats", "triage"):
        audit = review[name]
        if audit["status"] != "checked" or audit["findings"]:
            details.append("**" + name.title() + " — " + audit["status"] + "**\n\n" + audit["evidence"] + "\n" +
                "\n".join("- " + f["finding"] + " — " + f["disposition"] + ": " + f["rationale"] for f in audit["findings"]))
    if review["blocking_findings"]:
        details.append("**Unresolved mandatory findings**\n\n" + "\n".join("- " + f for f in review["blocking_findings"]))
    for field, title in (("technical_delta", "Implementation"), ("claim_corrections", "Accepted corrections"), ("release_obligations", "Release obligations")):
        entries = recording[field]
        if entries:
            values = [e["fact"] + "\n  Evidence: " + e["evidence"] if isinstance(e, dict) else e for e in entries]
            details.append("**" + title + "**\n\n" + "\n".join("- " + v for v in values))
    # Compact generated merge facts, not a second narration of the implementation.
    def cell(value):
        return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    rows = [("PR", facts["pr_url"]), ("Merge commit", facts["merge_sha"]),
            ("Merge strategy", facts["strategy"]), ("Base branch", facts["base"]), ("Merged at", facts["merged_at"])]
    merged = '<callout icon="✅" color="green_bg">Merged; release obligations remain as recorded above.</callout>\n\n'
    merged += '<table header-row="true">\n<tr><td>Field</td><td>Value</td></tr>\n'
    merged += "\n".join("<tr><td>" + name + "</td><td>" + cell(value) + "</td></tr>" for name, value in rows) + "\n</table>"
    return {"Implementation": '<callout icon="🔨" color="blue_bg">Merged implementation record.</callout>\n\n' + "\n\n".join(details), "Merged": merged}


def acceptance_edits(body, inventory, review):
    """Tick exact existing criterion text, never reconstruct/rewrite the definition of done."""
    headings = section_headings(body)
    matches = [(i, h) for i, h in enumerate(headings)
               if re.sub(r"\s*\{[^{}]*\}\s*$", "", h[1]).strip().casefold() == "acceptance criteria"]
    require(len(matches) <= 1, "ambiguous Acceptance Criteria section")
    if not matches: return []
    i, h = matches[0]
    section = body[h.end():headings[i + 1].start() if i + 1 < len(headings) else len(body)]
    verdicts = {v["id"]: v["verdict"] for v in review["requirements"]}
    edits = []
    for item in inventory["items"]:
        if item["kind"] != "acceptance": continue
        pattern = r"(?m)^- \[([ xX])\] " + re.escape(item["text"]) + r"$"
        lines = list(re.finditer(pattern, section))
        require(len(lines) == 1, "criterion not an exact unique checkbox; use adapter without paraphrasing")
        old = lines[0][0]
        new = "- [" + ("x" if verdicts[item["id"]] == "met" else " ") + "] " + item["text"]
        require(body.count(old) == 1, "criterion anchor is not unique on page")
        if old != new: edits.append({"old_str": old, "new_str": new})
    return edits


def build_writes(kind, target, data, config, page, spec, inventory=None, review=None):
    """Return exact host_call objects for the existing journal's child protocol."""
    require(isinstance(spec, dict), "builder spec must be an object")
    require(page["page"] == page_id(target), "recording snapshot belongs to another target")
    for prop, expected in config.get("ticketSystem", {}).get("staticProperties", {}).items():
        require(prop not in page["properties"] or page["properties"][prop] == expected, "recording page violates project scope")
    calls = []
    if kind == "ticket-status":
        require(not spec, "ticket-status derives its configured mapping, not a caller override")
        cfg = config.get("ticketSystem", {})
        prop = cfg.get("statusProperty", "Status")
        require(prop in page["properties"], "configured status property missing; revalidate live schema")
        status = cfg.get("statusMap", {}).get("implemented", "Implemented")
        require(isinstance(status, str) and status.strip(), "invalid implemented status mapping")
        live = page["properties"][prop]
        protected = [cfg.get("statusMap", {}).get(k, default) for k, default in (("done", "Done"), ("cancelled", "Cancelled"))]
        require(not isinstance(live, str) or live.casefold() == status.casefold()
                or all(not isinstance(v, str) or live.casefold() != v.casefold() for v in protected),
                "live ticket is done/cancelled; reconcile authority, never regress its status")
        calls = [{"command": "update_properties", "properties": {prop: status}}]
    elif kind == "ticket-resolution":
        require(not spec, "ticket-resolution derives accepted facts, not a caller narrative")
        calls = section_edits(page["content"], ticket_sections(data, inventory, review))
        edits = acceptance_edits(page["content"], inventory, review)
        if edits:
            update = next((c for c in calls if c["command"] == "update_content"), None)
            if update: update["content_updates"] = edits + update["content_updates"]
            else: calls.insert(0, {"command": "update_content", "content_updates": edits})
    else:
        raise ValueError("no provider builder for " + kind + "; retain its existing executor")
    return [{"name": "write-" + str(i + 1), "target": page["url"],
             "data": {"host_call": {"name": "mcp__notion__notion-update-page", "input": {"page_id": page["page"], **call}}}}
            for i, call in enumerate(calls)]
