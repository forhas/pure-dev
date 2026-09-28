"""Epic convergence: goal-based closure, filing rules, verified follow-ups, artifact-bound
PR claims, premise checks, the prose correction cap and the follow-up circuit breaker.

Synthetic epics and tickets only; no client data, live providers or spawned agents.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import test_review_repair as repair
from test_lean_workflow import runtime, workflow, ROOT, account_findings
import corrections
import recording
import scope

KNOWLEDGE = ROOT / "plugins/notion-dev/scripts/knowledge.py"
FIXTURE = ROOT / "scripts/fixtures/evaluation"


def write_lf(path, text):
    """UTF-8/LF on both platforms; `Path.write_text(newline=)` needs Python 3.10."""
    with open(str(path), "w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)

BRIEF = """---
type: Epic
title: "[EX-1] Example epic"
description: "Stop the reported failure"
status: stable
epic: EX-1
---
# [EX-1] Example epic
Epic: https://example.invalid/ex-1 · Status: open · Updated: 2026-09-01 after refresh

## Why
A customer-reported failure.

## Goal
Close the reported failure and record a build-or-drop verdict.
Done when:
- [EX-2] resolved
- [EX-3] resolved
- [EX-4] verdict recorded

## Where we stand
Work started.

## Open threads

## Decisions & constraints

## Release obligations
- [EX-2] wire error code 4012 added — sign-off: yes — gate: none — released: no
- [EX-5] DTO field renamed — sign-off: yes — gate: contract test — released: no
- commitment: fixed retry for the customer — for: next release — ticket: [EX-2] — released: no

## Next
1. **[EX-5] Connection audit** — first in phase order
2. [EX-6] Stale JSDoc — ready
"""


def child(key, status, title=None):
    number = int(key.split("-")[1])
    return {"key": key, "id": number, "title": title or "Task " + key, "status_class": status,
            "blocked_by": [], "phase": None, "step": None, "dependencies_known": True}


def live_state(open_goal=False):
    children = [child("EX-2", "resolved"), child("EX-3", "open" if open_goal else "resolved"),
                child("EX-4", "resolved"), child("EX-5", "open", "Connection audit"),
                child("EX-6", "open", "Stale JSDoc")]
    return {"epic": {"key": "EX-1", "status_class": "open"}, "children": children, "thread_blocked": []}


def resolution_log(entries):
    """entries: (key, goal follow-ups, outside follow-ups); legacy when outside is None."""
    out = ["## Resolution Log", ""]
    for key, goal, outside in entries:
        out.append("### [%s] resolved — 2026-09-01 10:00 UTC" % key)
        out.append("**Summary** — work landed.")
        if goal:
            out.append("**Follow-ups filed** — " + ", ".join("[%s] t · https://x.invalid/%s" % (k, k) for k in goal))
        if outside:
            out.append("**Follow-ups filed outside the goal** — " + ", ".join("[%s] t · backlog" % k for k in outside))
        out.append("**Epic status** — open")
        out.append("")
    return "\n".join(out) + "\n"


class KnowledgeGoalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="decomposition-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, value):
        path = self.root / name
        data = value if isinstance(value, str) else json.dumps(value)
        write_lf(path, data)
        return path

    def knowledge(self, *args):
        return subprocess.run([sys.executable, str(KNOWLEDGE), *args], capture_output=True, encoding="utf-8")

    def goal(self, brief=BRIEF, state=None, log=None, *extra):
        args = ["epic-goal", "--brief", str(self.write("brief.md", brief)),
                "--state", str(self.write("state.json", state or live_state()))]
        if log is not None: args += ["--log", str(self.write("log.md", log))]
        proc = self.knowledge(*args, *extra)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_goal_met_while_other_children_open_proposes_close_and_rehome(self):
        result = self.goal()
        self.assertEqual(result["goal"], "met")
        self.assertEqual(result["recommendation"], "close")
        self.assertEqual([c["key"] for c in result["rehome"]], ["EX-5", "EX-6"])

    def test_open_goal_item_and_unknown_key_are_never_met(self):
        self.assertEqual(self.goal(state=live_state(open_goal=True))["goal"], "open")
        unknown = BRIEF.replace("- [EX-4] verdict recorded", "- [EX-9] resolved")
        result = self.goal(brief=unknown)
        self.assertEqual(result["goal"], "open")
        self.assertEqual(result["done_when"][-1]["status"], "unknown")
        outside = {**live_state(), "external_statuses": {"EX-9": "resolved"}}
        self.assertEqual(self.goal(brief=unknown, state=outside)["goal"], "open",
                         "a resolved dependency outside the epic is not a child goal item")
        external = BRIEF.replace("- [EX-4] verdict recorded", "- external: customer confirms the fix — open")
        self.assertEqual(self.goal(brief=external)["goal"], "open")
        self.assertEqual(self.goal(brief=external.replace("— open", "— met"))["goal"], "met")

    def test_epic_without_done_when_keeps_the_all_children_rule(self):
        brief = BRIEF.replace("Done when:\n- [EX-2] resolved\n- [EX-3] resolved\n- [EX-4] verdict recorded\n", "")
        result = self.goal(brief=brief)
        self.assertEqual(result["goal"], "undefined")
        self.assertEqual(result["recommendation"], "continue")
        self.assertEqual(result["rehome"], [])

    def test_malformed_done_when_is_invalid_not_met(self):
        result = self.goal(brief=BRIEF.replace("- [EX-3] resolved", "- EX-3 is done"))
        self.assertEqual(result["goal"], "invalid")
        self.assertEqual(result["recommendation"], "repair-goal")

    def test_three_resolutions_filing_two_each_trigger_rescope(self):
        log = resolution_log([("EX-2", ["EX-7", "EX-8"], None), ("EX-7", ["EX-9", "EX-10"], []),
                              ("EX-9", ["EX-11", "EX-12"], [])])
        result = self.goal(BRIEF, live_state(open_goal=True), log)
        self.assertEqual(result["followups"]["rate"], 2.0)
        self.assertTrue(result["followups"]["rescope"])
        self.assertEqual(result["recommendation"], "rescope")
        self.assertEqual(result["followups"]["generation"]["max"], 3)
        self.assertEqual(result["followups"]["generation"]["by_key"]["EX-11"], 3)

    def test_a_retry_entry_for_the_same_ticket_counts_its_followups_once(self):
        log = resolution_log([("EX-2", ["EX-7"], None), ("EX-2", ["EX-7", "EX-8"], None)])
        result = self.goal(BRIEF, live_state(open_goal=True), log, "--window", "1")
        self.assertEqual(result["followups"]["resolutions"], 1)
        self.assertEqual(result["followups"]["filed_goal"], 2)

    def test_the_breaker_compares_the_exact_rate_not_its_rounding(self):
        log = resolution_log([("EX-2", ["EX-7"], None), ("EX-3", ["EX-8"], None), ("EX-4", [], None)])
        result = self.goal(BRIEF, live_state(open_goal=True), log, "--threshold", "0.6668")
        self.assertEqual(result["followups"]["rate"], 0.667)
        self.assertFalse(result["followups"]["rescope"])

    def test_non_goal_followups_do_not_count_toward_the_rate(self):
        log = resolution_log([("EX-2", [], ["EX-7", "EX-8"]), ("EX-3", ["EX-9"], ["EX-10"]),
                              ("EX-4", [], ["EX-11"])])
        result = self.goal(BRIEF, live_state(open_goal=True), log)
        self.assertEqual(result["followups"]["filed_goal"], 1)
        self.assertEqual(result["followups"]["filed_outside"], 4)
        self.assertFalse(result["followups"]["rescope"])
        partial = self.goal(BRIEF, live_state(open_goal=True), resolution_log([("EX-2", ["EX-7", "EX-8", "EX-9"], None)]))
        self.assertFalse(partial["followups"]["rescope"], "one resolution is not a full window")

    def test_release_ledger_warns_about_a_committed_deliverable_held_behind_new_obligations(self):
        release = self.goal()["release"]
        self.assertEqual(release["unreleased"], 2)
        self.assertEqual(release["signoff_pending"], 2)
        self.assertEqual(len(release["warnings"]), 1)
        self.assertIn("EX-5", release["warnings"][0])
        released = BRIEF.replace("gate: contract test — released: no", "gate: contract test — released: yes")
        self.assertEqual(self.goal(brief=released)["release"]["warnings"], [])

    def test_bookkeeping_counts_brief_commits_per_resolution(self):
        repo = self.root / "repo"
        (repo / "knowledge" / "epic").mkdir(parents=True)
        git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)
        git("init", "-q"); git("config", "user.email", "t@example.invalid"); git("config", "user.name", "t")
        brief = repo / "knowledge" / "epic" / "EX-1-example.md"
        for n in range(3):
            write_lf(brief, BRIEF + "\n" * n)
            git("add", "."); git("commit", "-qm", "docs(epic): EX-1 %d" % n)
        log = resolution_log([("EX-2", [], None), ("EX-3", [], None)])
        proc = self.knowledge("epic-goal", "--brief", str(brief), "--state", str(self.write("s.json", live_state())),
                              "--log", str(self.write("log.md", log)), "--repo", str(repo))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["bookkeeping"],
                         {"brief_commits": 3, "resolutions": 2, "per_resolution": 1.5})

    def test_brief_budget_is_reported(self):
        result = self.goal(BRIEF, None, None, "--budget", "20")
        self.assertTrue(result["brief"]["over_budget"])
        self.assertFalse(self.goal()["brief"]["over_budget"])

    def test_next_renders_goal_met_instead_of_recommending_children(self):
        brief = self.write("brief.md", BRIEF)
        state = self.write("state.json", live_state())
        first = self.knowledge("next", "--brief", str(brief), "--state", str(state), "--today", "2026-09-02")
        self.assertEqual(first.returncode, 1, first.stderr)
        self.assertIn("drift: goal met, ## Next not in goal-met form", first.stderr)
        region = first.stdout.split("## Next\n", 1)[1]
        self.assertTrue(region.startswith("goal met — propose closing the epic"))
        self.assertIn("Re-home:\n- [EX-5] Connection audit\n- [EX-6] Stale JSDoc\n", region)
        self.assertNotRegex(region, r"(?m)^1\. ")
        write_lf(brief, first.stdout)
        again = self.knowledge("next", "--brief", str(brief), "--state", str(state), "--today", "2026-09-02")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("DRIFT: 0", again.stderr)
        reopened = self.knowledge("next", "--brief", str(brief), "--state",
                                  str(self.write("open.json", live_state(open_goal=True))), "--today", "2026-09-02")
        self.assertEqual(reopened.returncode, 1)
        self.assertIn("drift: goal open, ## Next still in goal-met form", reopened.stderr)
        self.assertIn("1. **[EX-3]", reopened.stdout)

    def test_goal_met_rehome_line_matches_the_close_batch_including_claimed_children(self):
        state = live_state()
        state["children"][4]["status_class"] = "in_progress"
        batch = [c["key"] for c in self.goal(state=state)["rehome"]]
        proc = self.knowledge("next", "--brief", str(self.write("brief.md", BRIEF)),
                              "--state", str(self.write("state.json", state)), "--today", "2026-09-02")
        region = proc.stdout.split("## Next\n", 1)[1]
        self.assertEqual(batch, ["EX-5", "EX-6"])
        self.assertIn("Re-home:\n- [EX-5] Connection audit\n- [EX-6] Stale JSDoc\n", region)
        self.assertNotIn("In progress:", region)
        brief = self.write("brief.md", proc.stdout)
        again = self.knowledge("next", "--brief", str(brief), "--state", str(self.write("state.json", state)),
                               "--today", "2026-09-02")
        self.assertEqual(again.returncode, 0, again.stderr)

    def test_a_title_carrying_a_ticket_reference_round_trips_without_drift(self):
        state = live_state()
        state["children"][3]["title"] = "Audit, [EX-99] compatible mode"
        args = ["--state", str(self.write("state.json", state)), "--today", "2026-09-02"]
        first = self.knowledge("next", "--brief", str(self.write("brief.md", BRIEF)), *args)
        again = self.knowledge("next", "--brief", str(self.write("brief.md", first.stdout)), *args)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("DRIFT: 0", again.stderr)

    def test_next_without_done_when_is_unchanged(self):
        brief = BRIEF.replace("Done when:\n- [EX-2] resolved\n- [EX-3] resolved\n- [EX-4] verdict recorded\n", "")
        proc = self.knowledge("next", "--brief", str(self.write("brief.md", brief)),
                              "--state", str(self.write("state.json", live_state())), "--today", "2026-09-01")
        self.assertIn("1. **[EX-5] Connection audit**", proc.stdout)
        self.assertNotIn("goal met", proc.stdout)

    def test_a_claim_only_start_defers_its_commit(self):
        brief = BRIEF.replace("Done when:\n- [EX-2] resolved\n- [EX-3] resolved\n- [EX-4] verdict recorded\n", "")
        state = live_state()
        state["children"][3]["status_class"] = "in_progress"
        args = ["--state", str(self.write("state.json", state)), "--today", "2026-09-02"]
        start = self.knowledge("next", "--brief", str(self.write("brief.md", brief)), "--reason", "start", "EX-5", *args)
        self.assertEqual(start.returncode, 1, start.stderr)
        self.assertIn("COMMIT: deferred", start.stderr)
        drift = self.knowledge("next", "--brief", str(self.write("brief.md", brief)), *args)
        self.assertIn("COMMIT: deferred", drift.stderr)
        # A claim plus a real scheduling change (a dependency now resolved) must commit.
        waiting = brief.replace("2. [EX-6] Stale JSDoc — ready", "2. [EX-6] Stale JSDoc — after EX-2")
        waited = self.knowledge("next", "--brief", str(self.write("brief.md", waiting)), *args)
        self.assertIn("COMMIT: needed", waited.stderr)
        stopped = brief.replace("## Open threads\n", "## Open threads\n- **[EX-5] stopped at validation** — "
                                "tests; worktree at ../w. Unblocked by: /notion-dev:ticket EX-5 (resumes).\n")
        resumed = self.knowledge("next", "--brief", str(self.write("brief.md", stopped)), "--reason", "start", "EX-5", *args)
        self.assertIn("COMMIT: needed", resumed.stderr)
        state["children"][3]["status_class"] = "resolved"
        resolve = self.knowledge("next", "--brief", str(self.write("brief.md", brief)), "--reason", "resolve", "EX-5",
                                 "--state", str(self.write("state.json", state)), "--today", "2026-09-02")
        self.assertIn("COMMIT: needed", resolve.stderr)

    def test_selection_plan_stops_when_the_goal_is_met(self):
        state = {**live_state(), "goal_met": True}
        proc = self.knowledge("retrieval-plan", "--purpose", "select", "--state", str(self.write("s.json", state)))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertIsNone(result["candidate"])
        self.assertTrue(result["goal_met"])


class FilingRuleTests(unittest.TestCase):
    base = {"id": "code:1", "action": "file", "rationale": "separate work", "evidence": "finding text",
            "criterion": 2, "absorb_class": "none", "blocks_goal": "no", "blocks_goal_reason": "unrelated debt"}

    def test_a_complete_file_disposition_is_allowed(self):
        self.assertEqual(scope.disposition_problems(self.base), [])

    def test_mandatory_absorb_cases_cannot_be_filed(self):
        for name in scope.ABSORB_CLASSES:
            with self.subTest(absorb_class=name):
                problems = scope.disposition_problems({**self.base, "absorb_class": name})
                self.assertTrue(any(p.startswith("mandatory absorb") for p in problems), problems)

    def test_file_requires_criterion_absorb_check_and_goal_judgment(self):
        for missing in ("criterion", "absorb_class", "blocks_goal", "blocks_goal_reason"):
            value = dict(self.base); value.pop(missing)
            with self.subTest(missing=missing):
                self.assertTrue(scope.disposition_problems(value))

    def test_size_criterion_needs_the_threshold_or_a_second_design_question(self):
        size = {**self.base, "criterion": "3", "changed_lines": 150}
        self.assertTrue(scope.disposition_problems(size))
        self.assertEqual(scope.disposition_problems({**size, "changed_lines": 900}), [])
        self.assertEqual(scope.disposition_problems(size, threshold=100), [])
        self.assertEqual(scope.disposition_problems({**size, "second_design_question": "which queue owns retries"}), [])

    def test_no_consumer_drop_records_its_reopen_trigger(self):
        drop = {"id": "code:2", "action": "drop", "no_consumer": True}
        self.assertTrue(scope.disposition_problems(drop))
        self.assertEqual(scope.disposition_problems({**drop, "reopen_trigger": "customer re-enables path"}), [])

    def test_destination_routes_non_goal_work_off_the_epic(self):
        self.assertEqual(scope.destination_problems("yes", "epic"), [])
        self.assertTrue(scope.destination_problems("yes", "backlog"))
        for good in ("backlog", "related", "epic:EX-90"):
            self.assertEqual(scope.destination_problems("no", good, "EX-1"), [])
        self.assertTrue(scope.destination_problems("no", "epic:EX-1", "EX-1"))
        self.assertTrue(scope.destination_problems("no", "epic"))
        self.assertTrue(scope.destination_problems("no", "epic:EX-1"), "an unknown source epic cannot be excluded")


class JudgmentTests(unittest.TestCase):
    setUp = repair.ReviewRepairTests.setUp
    config = repair.ReviewRepairTests.config
    fetch = repair.ReviewRepairTests.fetch
    prepare = repair.ReviewRepairTests.prepare
    result = repair.ReviewRepairTests.result
    resolve = repair.ReviewRepairTests.resolve
    run_git = repair.ReviewRepairTests.run_git
    new_schema = repair.ReviewRepairTests.new_schema
    log = repair.ReviewRepairTests.log
    capture = repair.ReviewRepairTests.capture
    reviewed = repair.ReviewRepairTests.reviewed
    finding = staticmethod(repair.ReviewRepairTests.finding)
    published = repair.ReviewRepairTests.published

    def test_runtime_refuses_filing_the_tickets_own_gap_and_counts_goal_judgments(self):
        value = self.result(); value["claims"]["findings"] = [self.finding()]
        key = self.published(value)
        index = self.rt.result_view(key)
        for page in range(1, index["findings"]["pages"] + 1): self.rt.result_view(key, page=page)
        filed = {"id": "claims:1", "action": "file", "rationale": "known limitation", "evidence": "finding",
                 "criterion": 1, "absorb_class": "own-feature", "blocks_goal": "no", "blocks_goal_reason": "later"}
        judgment = {"result_sha256": index["result_sha256"], "dispositions": [filed]}
        with self.assertRaisesRegex(runtime.Invalid, "mandatory absorb"): self.rt.judge_findings(key, judgment)
        filed["absorb_class"] = "none"
        self.rt.judge_findings(key, judgment)
        metrics = self.rt.summary()["scope"]
        self.assertEqual(metrics["dispositions"], {"file": 1})
        self.assertEqual(metrics["filed_by_blocks_goal"], {"no": 1})

    def test_configured_threshold_governs_the_size_criterion(self):
        value = self.result(); value["claims"]["findings"] = [self.finding()]
        key = self.published(value)
        index = self.rt.result_view(key)
        for page in range(1, index["findings"]["pages"] + 1): self.rt.result_view(key, page=page)
        judgment = {"result_sha256": index["result_sha256"], "dispositions": [
            {"id": "claims:1", "action": "file", "rationale": "large", "evidence": "finding", "criterion": 3,
             "changed_lines": 300, "absorb_class": "none", "blocks_goal": "yes", "blocks_goal_reason": "EX-3 needs it"}]}
        with self.assertRaisesRegex(runtime.Invalid, "criterion 3"): self.rt.judge_findings(key, judgment)
        config = self.root / "convergence.json"
        runtime.atomic_json(config, {"convergence": {"fileThresholdLines": 200}})
        self.rt.judge_findings(key, judgment, str(config))


class FollowupPacketTests(unittest.TestCase):
    def packet(self, **changes):
        value = {"title": "Bound retry", "goal": "Keep failures bounded", "scope": "Worker retry only",
                 "evidence": "Accepted finding", "provenance": "Follow-up-of: EX-2 · finding-hash: abc",
                 "source": "https://example.invalid/pr/7", "decision": "file",
                 "verified_facts": [{"fact": "A transient failure is not retried", "citation": "worker.py:42"}],
                 "requirements": [{"text": "Retry a transient failure once", "facts": [1]}],
                 "premises_to_verify": ["The server returns 503 for transient failures"],
                 "hypothesis": ["Wrap the call in the existing retry helper"],
                 "blocks_goal": {"value": "no", "reason": "hardening outside the epic goal"},
                 "destination": "backlog", "source_epic": "EX-1",
                 "acceptance": ["test_transient_retry passes"], "edge_cases": [], "dependencies": [],
                 "open_questions": []}
        value.update(changes)
        return value

    def test_body_separates_verified_facts_premises_and_hypothesis(self):
        body = recording.followup_body(self.packet())["body"]
        order = [body.index(h) for h in ("## Requirements", "## Verified facts", "## Premises to verify",
                                         "## Hypothesis — verify before implementing", "## Context")]
        self.assertEqual(order, sorted(order))
        self.assertIn("(verified: fact 1)", body)
        self.assertIn("1. A transient failure is not retried — worker.py:42", body)
        requirements = body.split("## Acceptance Criteria")[0]
        self.assertNotIn("retry helper", requirements, "a hypothesis never becomes a requirement")
        self.assertIn("Blocks epic goal: no — hardening outside the epic goal", body)

    def test_uncited_requirement_and_missing_goal_judgment_are_refused(self):
        for changes in ({"requirements": ["Retry once"]}, {"requirements": [{"text": "Retry", "facts": []}]},
                        {"requirements": [{"text": "Retry", "facts": [2]}]},
                        {"verified_facts": [{"fact": "x", "citation": ""}]}, {"verified_facts": []},
                        {"blocks_goal": {"value": "maybe", "reason": "x"}},
                        {"destination": "epic"}, {"destination": "epic:EX-1"},
                        {"blocks_goal": {"value": "yes", "reason": "EX-3"}, "destination": "backlog"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                recording.followup_body(self.packet(**changes))
        recording.followup_body(self.packet(blocks_goal={"value": "yes", "reason": "EX-3 needs it"}, destination="epic"))


class PrClaimTests(unittest.TestCase):
    facts = {"requirement": "Bound retries", "behavior": ["Retries once"], "validation": ["Suite passed"],
             "risks": [], "mandatory": []}

    def test_the_fixture_false_quantitative_claim_fails_rendering(self):
        body = (FIXTURE / "pr-body.md").read_text(encoding="utf-8")
        claim = next(line for line in body.splitlines() if "registry lookups" in line)
        with self.assertRaisesRegex(ValueError, "artifact"):
            recording.pr_body({**self.facts, "behavior": [claim]})

    def test_artifact_references_and_measured_facts_pass(self):
        referenced = "Memoization removes 50% of registry lookups (artifact: test_lookup_reduction_claim)"
        recording.pr_body({**self.facts, "behavior": [referenced]})
        measured = {"kind": "ratio", "numerator": 3, "denominator": 6, "unit": "lookups",
                    "population": "fixture workload", "source": "oracle/test_scheduler.py"}
        recording.pr_body({**self.facts, "behavior": {"lookups": measured}})
        for harmless in ("Fixes EX-12 and HTTP 404 handling in v2.3", "Adds retries to worker 2"):
            recording.pr_body({**self.facts, "behavior": [harmless]})
        for figure in ("3x faster", "cuts 120 ms", "saves 4 KB", "removes 2 round-trips"):
            with self.subTest(figure=figure), self.assertRaises(ValueError):
                recording.pr_body({**self.facts, "validation": [figure]})

    def test_body_budget_warns_without_failing(self):
        with tempfile.TemporaryDirectory() as temp:
            facts = Path(temp) / "facts.json"
            runtime.atomic_json(facts, {**self.facts, "behavior": ["Retries once. " * 400]})
            config = Path(temp) / "config.json"
            runtime.atomic_json(config, {"convergence": {"prBodyBudget": 500}})
            result = workflow.render_pr_body(str(facts), str(Path(temp) / "body.md"), str(config))
            self.assertIn("warning", result)
            small = workflow.render_pr_body(str(facts), str(Path(temp) / "body2.md"))
            self.assertIn("warning", small)
            runtime.atomic_json(config, {"convergence": {"prBodyBudget": 100000}})
            self.assertNotIn("warning", workflow.render_pr_body(str(facts), str(Path(temp) / "body3.md"), str(config)))


class PremiseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="premises-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.ticket = root / "ticket.md"
        write_lf(self.ticket, "## Requirements\n\n- Retry once\n\n## Premises to verify\n\n"
                               "- The server returns 503 for transient failures\n- The helper is unused\n\n"
                               "## Hypothesis — verify before implementing\n\n- Wrap the call\n")
        self.rt = runtime.Runtime(root / "state.json")
        self.rt.init("premises", "EX-2")
        self.rt.requirements(self.ticket, {
            "source_sha256": hashlib.sha256(self.ticket.read_bytes()).hexdigest(), "reviewed_whole_ticket": True,
            "items": [{"id": "R1", "kind": "requirement", "text": "Retry once", "readiness": "ready"}]})

    def check(self, verdict="holds", **extra):
        return [{"text": "The server returns 503 for transient failures", "verdict": "holds", "evidence": "api.py:10"},
                {"text": "The helper is unused", "verdict": verdict, "evidence": "grep shows 2 callers", **extra}]

    def test_readiness_waits_for_every_premise(self):
        self.assertIn("check every premise", " ".join(self.rt.ready()["reasons"]))
        with self.assertRaisesRegex(runtime.Invalid, "unchecked premise"): self.rt.premises(self.check()[:1])
        with self.assertRaisesRegex(runtime.Invalid, "correction"): self.rt.premises(self.check("false"))
        result = self.rt.premises(self.check("false", correction="comment posted: the helper has 2 callers"))
        self.assertEqual(result["false"], 1)
        self.assertTrue(self.rt.ready()["passed"])
        self.assertEqual(self.rt.summary()["scope"]["premises"], {"holds": 1, "false": 1})

    def test_a_moot_ticket_stops_with_a_drop_recommendation(self):
        result = self.rt.premises(self.check("moot"))
        self.assertEqual(result["action"], "stop and recommend drop")
        self.assertIn("recommend drop", " ".join(self.rt.ready()["reasons"]))

    def test_tickets_without_premises_are_unaffected(self):
        self.assertEqual(scope.premise_items("## Requirements\n\n- x\n"), [])
        self.assertEqual(scope.premise_items("## Premises to verify\n\nNone.\n"), [])


class ProseCapTests(unittest.TestCase):
    def test_third_prose_rewrite_of_one_claim_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            state = str(Path(temp) / "state.json")
            item = {"claim": "lookups", "method": "rewrite"}
            corrections.prose_cap(state, "review-1", [item])
            corrections.prose_cap(state, "review-2", [item])
            corrections.prose_cap(state, "review-2", [item])  # the same round again is idempotent
            with self.assertRaisesRegex(ValueError, "artifact reference or remove"):
                corrections.prose_cap(state, "review-3", [item])
            corrections.prose_cap(state, "review-3", [{"claim": "lookups", "method": "artifact"}])
            corrections.prose_cap(state, "review-3", [{"claim": "other", "method": "rewrite"}])
            with self.assertRaises(ValueError):
                corrections.prose_cap(state, "review-4", [{"claim": "x", "method": "reword"}])
            with self.assertRaisesRegex(ValueError, "claims finding names its claim"):
                corrections.prose_cap(state, "review-4", [{"id": "claims:1", "claim": None, "method": ""}])
            corrections.prose_cap(state, "review-4", [{"id": "code_review:1", "claim": None, "method": ""}])


if __name__ == "__main__":
    unittest.main()
