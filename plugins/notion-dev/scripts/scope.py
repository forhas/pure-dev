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
    labels = d.get("labels", [])
    if not (isinstance(labels, list) and all(text(l) for l in labels)):
        problems.append("labels must be a list of nonempty strings (they drive convergence.destinations)")
    if action == "drop" and d.get("no_consumer") is True and not text(d.get("reopen_trigger")):
        problems.append("a no-consumer drop records its reopen_trigger")
    return problems


def destination_problems(blocks_goal, destination, source_epic=None, routed=False):
    """Where a filed follow-up is created: goal work stays under the epic, other work leaves it."""
    if routed:
        # A project routing rule chose it; only the shape is checked here.
        if destination in ("epic",) + DESTINATIONS or re.fullmatch(r"epic:[A-Z][A-Z0-9]{1,9}-\d+", str(destination)):
            return []
        return ["routed destination must be epic, backlog, related or epic:<KEY>-<n>"]
    if blocks_goal == "yes":
        return [] if destination == "epic" else ["a goal-blocking follow-up is a child of its epic"]
    if blocks_goal != "no":
        return ["blocks_goal must be yes or no"]
    if destination in DESTINATIONS:
        return []
    match = re.fullmatch(r"epic:([A-Z][A-Z0-9]{1,9}-\d+)", str(destination))
    if not match:
        return ["non-goal destination must be backlog, related or epic:<KEY>-<n>"]
    if not source_epic:
        return ["an epic:<KEY>-<n> destination needs source_epic to prove it is not the source epic"]
    if match.group(1) == source_epic:
        return ["a non-goal follow-up cannot be filed under the epic whose goal it does not block"]
    return []


# A figure is a number with a unit, a percentage or a multiplier. Ticket keys, versions,
# HTTP codes and bare counts in identifiers are not quantitative claims. The built-in units
# are generic measurement units; a project adds its own domain units (a currency, `gas`,
# `bps`, or a counted noun such as `tests`) through `convergence.figureUnits`.
BUILTIN_UNITS = (r"%", r"percent\b", r"[x×](?![\w])", r"-?fold\b", r"ms\b", r"milliseconds?\b",
                 r"s\b", r"secs?\b", r"seconds?\b", r"min\b", r"minutes?\b", r"h\b", r"hours?\b",
                 r"days?\b", r"[KMGT]i?B\b", r"kB\b", r"bytes?\b", r"tokens?\b", r"lines?\b",
                 r"requests?\b", r"calls?\b", r"lookups?\b", r"queries\b", r"round-?trips?\b")
# A figure cites what produced it: an artifact (test, receipt, export, generated diff), or,
# for a parameter the spec defines rather than a measurement, the spec section.
ARTIFACT_RE = re.compile(r"[\[(](?:artifact|spec):\s*[^\])\s][^\])]*[\])]")


def figure_regex(extra_units=()):
    extra = [re.escape(u) + (r"\b" if re.match(r".*\w$", u) else "") for u in extra_units]
    return re.compile(r"(?<![\w.-])\d+(?:[.,]\d+)?\s*(?:" + "|".join(list(BUILTIN_UNITS) + extra) + ")", re.I)


FIGURE_RE = figure_regex()


def unreferenced_figures(value, extra_units=()):
    """Figures in a PR fact that carry neither an artifact nor a spec citation."""
    if ARTIFACT_RE.search(value):
        return []
    pattern = figure_regex(extra_units) if extra_units else FIGURE_RE
    return [m.group(0) for m in pattern.finditer(value)]


# A neutral fallback, used only when the project names none. Projects list their own classes
# (`convergence.failureModeClasses`) or point at a file in their repo that does
# (`convergence.failureModeReference`), so no project type's threat model lives here.
NEUTRAL_FAILURE_MODES = (
    "correctness of every decision a consumer acts on",
    "authorization: who may invoke it, and who acts first",
    "input and parameter bounds",
    "irreversible or one-shot state transitions",
    "resource bounds: time, concurrency, size, cost",
    "lifetime and cleanup of acquired resources",
    "behaviour when a dependency fails or is slow",
    "compatibility of the published surface for existing consumers",
)


def failure_mode_classes(convergence, project_root):
    """(classes, source): the project's list, its reference file, or the neutral fallback."""
    import os
    classes = convergence.get("failureModeClasses")
    if classes:
        return list(classes), "convergence.failureModeClasses"
    reference = convergence.get("failureModeReference")
    if reference:
        path = os.path.join(project_root, reference)
        with open(path, encoding="utf-8") as stream:
            items = [re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", line).strip() for line in stream
                     if re.match(r"^\s*(?:[-*]|\d+\.)\s+\S", line)]
        if not items:
            raise ValueError("failureModeReference lists no classes (one bullet per class): " + reference)
        return items, reference
    return list(NEUTRAL_FAILURE_MODES), "neutral fallback"


def is_generated(path, globs):
    """A path the project declares generated (lockfiles, codegen, exported specs)."""
    import fnmatch
    return any(fnmatch.fnmatchcase(path, g) or fnmatch.fnmatchcase(path, g.rstrip("/") + "/*")
               or path.startswith(g.rstrip("/") + "/") for g in globs)


def route_followup(blocks_goal, labels, convergence):
    """(destination, reason). Project routing rules win, then meta-work, then the goal judgment.

    The plugin never knows what a label means: `convergence.destinations` maps a label
    pattern (e.g. a severity) to a destination, so a finding the project must not lose
    (one that gates its launch or release) is not quietly sent to the backlog.
    """
    labels = [str(l) for l in labels or []]
    for i, rule in enumerate(convergence.get("destinations") or []):
        if any(re.fullmatch(rule["match"], l, re.I) for l in labels):
            return rule["to"], "convergence.destinations[%d] (%s)" % (i, rule["match"])
    if "meta" in labels:
        return convergence.get("metaDestination", "backlog"), "meta-work (tooling, knowledge, plugin) stays off product epics"
    if blocks_goal == "yes":
        return "epic", "blocks the epic goal"
    return convergence.get("nonGoalDestination", "backlog"), "does not block the epic goal"


FOLD_RE = re.compile(r"\b(?:fold(?:ed|s)?\s+into|land(?:s|ed)?\s+(?:with|before|alongside)|"
                     r"merge(?:d|s)?\s+into|absorb(?:ed)?\s+(?:into|by))\s*:?\s+\[?%s\]?(?![\d])", re.I)


def fold_declarations(target, pages):
    """Open siblings whose own text declares they belong in `target`'s change."""
    pattern = re.compile(FOLD_RE.pattern % re.escape(target), re.I)
    return [{"key": p["key"], "excerpt": m.group(0)} for p in pages
            if p.get("key") != target for m in [pattern.search(p.get("text", ""))] if m]


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
