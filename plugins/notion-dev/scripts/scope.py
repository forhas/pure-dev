"""Scope rules that keep an epic converging. Pure functions: callers own the errors.

Each check returns the list of violated rules (empty means allowed), so runtime,
workflow and recording can refuse through their own `require` without a cycle.
Nothing here decides a disposition; it only refuses the ones the rules forbid.
"""
import re

# Mandatory-absorb classes: a finding in one of these is fixed in the PR that owns it.
ABSORB_CLASSES = {
    "own-feature": "a defect in, or known gap of, the feature or guarantee this ticket introduces",
    "sibling": "a sibling instance of the defect class this ticket fixes",
    "changed-code-docs": "docs, comments, generated specs or tests describing code this PR changes",
    "same-epic-rework": "a correction to text or wording this same epic introduced earlier",
}
FILE_CRITERIA = {"1", "2", "3"}
DEFAULT_FILE_THRESHOLD_LINES = 800
DESTINATIONS = ("backlog", "related")


def text(value):
    return isinstance(value, str) and bool(value.strip())


def disposition_problems(d, threshold=DEFAULT_FILE_THRESHOLD_LINES):
    """Filing and drop rules for one judged finding (review-findings.md)."""
    problems = []
    action = d.get("action")
    absorb_class = d.get("absorb_class", "none")
    if absorb_class != "none" and absorb_class not in ABSORB_CLASSES:
        problems.append("absorb_class must be none or one of " + ", ".join(sorted(ABSORB_CLASSES)))
    if action == "file":
        criterion = str(d.get("criterion", ""))
        if criterion not in FILE_CRITERIA:
            problems.append("file needs criterion 1, 2 or 3")
        if "absorb_class" not in d:
            problems.append("file must state absorb_class none after checking the mandatory-absorb cases")
        elif absorb_class != "none":
            problems.append("mandatory absorb: " + ABSORB_CLASSES.get(absorb_class, absorb_class) + " cannot be filed")
        if d.get("blocks_goal") not in {"yes", "no"} or not text(d.get("blocks_goal_reason")):
            problems.append("file needs blocks_goal yes|no and a one-line blocks_goal_reason")
        if criterion == "3":
            size = d.get("changed_lines")
            large = isinstance(size, int) and not isinstance(size, bool) and size > threshold
            if not large and not text(d.get("second_design_question")):
                problems.append("criterion 3 needs changed_lines above %d or a second_design_question" % threshold)
    if action == "drop" and d.get("no_consumer") is True and not text(d.get("reopen_trigger")):
        problems.append("a no-consumer drop records its reopen_trigger")
    return problems


def destination_problems(blocks_goal, destination, source_epic=None):
    """Where a filed follow-up is created: goal work stays under the epic, other work leaves it."""
    if blocks_goal == "yes":
        return [] if destination == "epic" else ["a goal-blocking follow-up is a child of its epic"]
    if blocks_goal != "no":
        return ["blocks_goal must be yes or no"]
    if destination in DESTINATIONS:
        return []
    match = re.fullmatch(r"epic:([A-Z][A-Z0-9]{1,9}-\d+)", str(destination))
    if not match:
        return ["non-goal destination must be backlog, related or epic:<KEY>-<n>"]
    if source_epic and match.group(1) == source_epic:
        return ["a non-goal follow-up cannot be filed under the epic whose goal it does not block"]
    return []


# A figure is a number with a unit, a percentage or a multiplier. Ticket keys, versions,
# HTTP codes and bare counts in identifiers are not quantitative claims.
FIGURE_RE = re.compile(
    r"(?<![\w.-])\d+(?:[.,]\d+)?\s*(?:%|percent\b|[x×](?![\w])|-?fold\b|ms\b|milliseconds?\b|"
    r"s\b|secs?\b|seconds?\b|min\b|minutes?\b|h\b|hours?\b|days?\b|[KMGT]i?B\b|kB\b|bytes?\b|"
    r"tokens?\b|lines?\b|requests?\b|calls?\b|lookups?\b|queries\b|round-?trips?\b)", re.I)
ARTIFACT_RE = re.compile(r"[\[(]artifact:\s*[^\])\s][^\])]*[\])]")


def unreferenced_figures(value):
    """Figures in a PR fact that carries no artifact reference."""
    if ARTIFACT_RE.search(value):
        return []
    return [m.group(0) for m in FIGURE_RE.finditer(value)]


PREMISES_HEADING_RE = re.compile(r"^#{1,4}\s+Premises to verify\b", re.I)


def premise_items(ticket_text):
    """Bullets under a ticket's `Premises to verify` heading, verbatim."""
    items, inside = [], False
    for line in ticket_text.replace("\r\n", "\n").split("\n"):
        if re.match(r"^#{1,6}\s", line):
            inside = bool(PREMISES_HEADING_RE.match(line))
            continue
        if inside:
            match = re.match(r"^\s*(?:[-*]|\d+\.)\s+(?:\[[ xX]\]\s+)?(.+?)\s*$", line)
            if match and match.group(1).lower() not in {"none", "none."}:
                items.append(match.group(1))
    return items


def premise_problems(ticket_text, checks):
    """Every premise is checked against the code before planning; a moot ticket stops."""
    wanted = premise_items(ticket_text)
    if not wanted:
        return []
    if not isinstance(checks, list):
        return ["check every premise to verify against the code before planning"]
    problems, seen = [], set()
    for check in checks:
        if not isinstance(check, dict) or check.get("text") not in wanted:
            problems.append("premise check must quote a listed premise verbatim")
            continue
        seen.add(check["text"])
        if check.get("verdict") not in {"holds", "false", "moot"} or not text(check.get("evidence")):
            problems.append("premise check needs verdict holds|false|moot and evidence")
        elif check["verdict"] == "false" and not text(check.get("correction")):
            problems.append("a false premise records its correction (ticket comment and PR)")
        elif check["verdict"] == "moot":
            problems.append("a false premise makes the ticket moot: stop and recommend drop")
    missing = [p for p in wanted if p not in seen]
    if missing:
        problems.append("unchecked premise: " + missing[0][:80])
    return problems
