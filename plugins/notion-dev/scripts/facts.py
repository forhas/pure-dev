"""Cross-epic fact routing: the fact-check contract and the routing decision.

A ticket run that established a fact about another epic used to hand it to the user as a
`/notion-dev:new-info` line to paste. This module is what lets the run route it instead,
and it is deliberately the only judge of that: the worker checks each fact, and `decide`
turns its verdicts into routed and handed-off facts by fixed rules. Nothing here trusts
the parent's own reading of its evidence.
"""
import re

VERDICTS = ("supported", "narrowed", "unsupported")
SOURCES = ("reproducible", "human")
# A ticket run is scoped to one ticket. More than this many facts about other epics is a
# sign the run drifted, and every routed fact writes to briefs, Notion and the bundle.
ROUTE_CAP = 3
EPIC_KEY = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]+$")

RULES = (
    "Check every fact yourself, read-only: resolve each evidence pointer against primary state "
    "(git objects and files at a named commit on origin, gh pull-request and merge state, a "
    "read-only command re-run, Notion pages through ticket-system reads). Never write, push, "
    "broadcast or call a mutating API. verdict: supported only when the evidence shows the fact "
    "exactly as worded; narrowed when it shows only a weaker claim, given in narrowed as a "
    "statement the evidence does show; unsupported otherwise. source: reproducible only when "
    "an independent party can re-establish the fact from primary state now; human when it is a "
    "person's decision, commitment, approval, acceptance or statement, or rests on a "
    "conversation, email or meeting. A document committed by this ticket's own pull request "
    "proves only what it mechanically records from a reproducible artefact, never a human "
    "decision it reports. citation names what you checked and what it showed.")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_facts(document):
    """Validate the facts the run hands to the checker, in NEW-INFO order."""
    require(isinstance(document, dict) and isinstance(document.get("facts"), list)
            and document["facts"], "facts.json requires a nonempty facts list")
    seen = set()
    for item in document["facts"]:
        require(isinstance(item, dict), "each fact must be an object")
        for key in ("id", "fact", "evidence"):
            require(isinstance(item.get(key), str) and item[key].strip(), "each fact needs nonempty " + key)
        require(item["id"] not in seen, "fact ids must be unique")
        seen.add(item["id"])
        epics = item.get("epics")
        require(isinstance(epics, list) and epics and all(isinstance(e, str) for e in epics),
                "each fact needs a nonempty epics list (use [\"unknown\"] when unknown)")
        require(all(e == "unknown" or EPIC_KEY.match(e) for e in epics),
                "epics are logical keys like STO-184, or unknown")
    return document["facts"]


def contract(items):
    return {"facts": [{"id": item["id"], "verdict": "|".join(VERDICTS), "source": "|".join(SOURCES),
                       "narrowed": "weaker wording the evidence shows, only when verdict is narrowed; else null",
                       "citation": "nonempty: what was checked and what it showed"} for item in items]}


def draft(items):
    """A deliberately nonpassing skeleton: unchecked facts are unsupported and human."""
    return [{"id": item["id"], "verdict": "unsupported", "source": "human", "narrowed": None, "citation": ""}
            for item in items]


def validate(items, result):
    checks = result.get("facts")
    require(isinstance(checks, list) and all(isinstance(c, dict) for c in checks),
            "facts must be a list of check objects")
    require([c.get("id") for c in checks] == [item["id"] for item in items],
            "facts must cover every fact id exactly once, in order")
    for check in checks:
        require(check.get("verdict") in VERDICTS and check.get("source") in SOURCES,
                "each fact check needs a valid verdict and source")
        require(isinstance(check.get("citation"), str) and check["citation"].strip(),
                "each fact check needs a nonempty citation")
        narrowed = check.get("narrowed")
        if check["verdict"] == "narrowed":
            require(isinstance(narrowed, str) and narrowed.strip(), "a narrowed verdict needs its narrowed wording")
        else:
            require(narrowed is None, "narrowed wording is only for a narrowed verdict")


def render(items, result):
    lines = ["FACT-CHECK: " + str(len(items))]
    for check in result["facts"]:
        lines.append(check["id"] + ": " + check["verdict"] + " / " + check["source"])
    # Re-rendering a rendered report must not stack a second header (publish is idempotent).
    ids = "|".join(re.escape(item["id"]) for item in items)
    narrative = re.sub(r"^(?:FACT-CHECK: [0-9]+|(?:" + ids + r"): (?:" + "|".join(VERDICTS) + r") / (?:"
                       + "|".join(SOURCES) + r"))\r?\n?", "", result["report"], flags=re.M)
    return "\n".join(lines) + "\n" + narrative


def decide(items, result, own_epic, interactive):
    """Every fact is routed or handed off, by these rules and no others."""
    routed, handed = [], []
    checks = {c["id"]: c for c in result["facts"]}
    for item in items:
        check = checks[item["id"]]
        epics = [e for e in item["epics"] if e != own_epic]
        base = {"id": item["id"], "fact": item["fact"], "evidence": item["evidence"],
                "verdict": check["verdict"], "source": check["source"], "citation": check["citation"]}
        reason = None
        if "unknown" in epics or not epics:
            reason = ("no other epic named" if not epics else "epics unknown") + "; route it with --epic yourself"
        elif check["verdict"] == "unsupported":
            reason = "the independent check did not support it: " + check["citation"]
        elif check["source"] == "human" and not interactive:
            reason = "human-sourced, and a non-interactive run cannot ask you to confirm it"
        elif len(routed) == ROUTE_CAP:
            reason = "over the per-run cap of " + str(ROUTE_CAP) + " routed facts"
        if reason:
            handed.append(dict(base, epics=item["epics"], reason=reason))
            continue
        wording = check["narrowed"] if check["verdict"] == "narrowed" else item["fact"]
        # A human-sourced fact is applied only through new-info's per-epic gate, which shows
        # it to the person whose confirmation it needs; a reproducible one needs no gate.
        routed.append(dict(base, fact=wording, original=item["fact"], epics=epics,
                           gate=check["source"] == "human"))
    return {"routed": routed, "handed_off": handed}
