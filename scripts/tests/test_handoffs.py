"""Generic regressions for bounded review, full-source freshness and recording.

No client data, network calls or provider writes. Same suite on Git Bash and WSL.
"""
import copy
import json
import os
import subprocess
import sys
import re
import shutil
from pathlib import Path
import unittest
from unittest.mock import patch

import test_lean_workflow as lean
from test_lean_workflow import runtime, workflow, ROOT


class HandoffTests(unittest.TestCase):
    setUp = lean.LeanTests.setUp
    run_git = lean.LeanTests.run_git
    prepare = lean.LeanTests.prepare
    result = lean.LeanTests.result
    resolve = lean.LeanTests.resolve
    config = lean.LeanTests.config
    facts = lean.LeanTests.facts

    def reviewed(self, correction=False, inputs=None):
        if correction:
            self.rt.correction_needed(self.repo, "independent finding")
            self.code.write_text("original corrected\n", encoding="utf-8")
            self.run_git("add", "code.txt"); self.run_git("commit", "-qm", "fix")
        if inputs:
            prepared = self.rt.prepare("completeness", inputs, self.repo)
            key = prepared["worker"]
            self.rt.attach(key, "agent-" + key)
        else:
            key = self.prepare()
        result = self.result()
        if correction:
            contract = runtime.read_json(runtime.read_json(self.state)["workers"][key]["packet"])["result_contract"]
            result["correction_review"] = {**contract["required"]["correction_review"],
                "verdict": "clean", "report": "VERDICT: CLEAN. Independently checked both source paths.",
                "depends_on": []}
        self.rt.publish(key, result); self.rt.consume(key); self.rt.accept(key)
        return key

    def test_structured_correction_punctuation_and_rendering(self):
        key = self.reviewed(True)
        worker = runtime.read_json(self.state)["workers"][key]
        self.resolve(key)
        self.assertTrue(self.rt.merge_gate(key, self.repo)["passed"])
        self.assertIn("Independently checked both source paths.", worker["result"]["correction_review"]["report"])
        for report in ("VERDICT: CLEAN. prose", "VERDICT: CLEAN\nprose", "Independent review complete"):
            value = copy.deepcopy(worker["result"]); value["correction_review"]["report"] = report
            runtime.validate_result(worker, value)
            self.assertTrue(runtime.Runtime.correction_reviewed(runtime.read_json(self.state), worker, value))
            rendered = runtime.render_result(worker, value)
            self.assertEqual(rendered, runtime.render_result(worker, rendered))
            self.assertTrue(runtime.Runtime.correction_reviewed(runtime.read_json(self.state), worker, rendered))
        for field, wrong in (("id", "foreign"), ("manifest_sha256", "wrong")):
            value = copy.deepcopy(worker["result"]); value["correction_review"][field] = wrong
            with self.assertRaises(runtime.Invalid): runtime.validate_result(worker, value)
        for field, wrong in (("verdict", "findings"), ("verdict", "unverified"), ("blocking_findings", ["unresolved"])):
            value = copy.deepcopy(worker["result"]); value["correction_review"][field] = wrong
            runtime.validate_result(worker, value)
            self.assertFalse(runtime.Runtime.correction_reviewed(runtime.read_json(self.state), worker, value))
        legacy = {**worker, "contract_version": 2}
        value = copy.deepcopy(worker["result"]); value["correction_review"]["report"] = "VERDICT: CLEAN. prose"
        self.assertFalse(runtime.Runtime.correction_reviewed(runtime.read_json(self.state), legacy, value))

    def test_delta_requires_evidence_handoff_and_retains_named_inputs(self):
        claims = self.root / "claims.md"; claims.write_text("old claim", encoding="utf-8")
        log = self.root / "check.log"; log.write_text("passing checks", encoding="utf-8")
        key = self.reviewed(inputs={"ticket": self.source, "pr_body": claims, "checks": log})
        claims.write_text("corrected claim", encoding="utf-8")
        with self.assertRaisesRegex(runtime.Invalid, "resolve available citations"):
            self.rt.prepare("completeness", {"pr_body": claims}, self.repo, previous=key)
        self.assertEqual(len(runtime.read_json(self.state)["workers"]), 1)
        self.resolve(key)
        delta = self.rt.prepare("completeness", {"pr_body": claims}, self.repo, previous=key)
        worker = runtime.read_json(self.state)["workers"][delta["worker"]]
        index = runtime.read_json(worker["delta"]["path"])
        sections = runtime.read_json(runtime.Runtime.ref_path(index, index["sections_file"]))
        self.assertEqual(sections["changed_inputs"], ["pr_body"])
        self.assertEqual(sections["changed_paths"], [])
        self.assertEqual(len(sections["reuse_applicable"]), len(self.inventory["items"]))
        self.assertEqual(set(worker["files"]), {"ticket", "pr_body", "checks"})

    def test_explicit_missing_evidence_is_unknown_not_a_clean_verdict(self):
        key = self.reviewed(); self.rt.resolve_citations(key, [])
        delta = self.rt.prepare("completeness", {}, self.repo, previous=key)
        index = runtime.read_json(runtime.read_json(delta["packet"])["delta"]["path"])
        self.assertEqual(index["evidence"]["unresolved"], len(self.inventory["items"]))

    def test_input_removal_is_explicit_and_new_path_same_bytes_is_not_a_change(self):
        log = self.root / "log"; log.write_text("pass", encoding="utf-8")
        key = self.reviewed(inputs={"ticket": self.source, "log": log}); self.resolve(key)
        moved = self.root / "moved.md"; moved.write_bytes(self.source.read_bytes())
        delta = self.rt.prepare("completeness", {"ticket": moved}, self.repo, previous=key, remove_inputs=["log"])
        index = runtime.read_json(runtime.read_json(delta["packet"])["delta"]["path"])
        sections = runtime.read_json(runtime.Runtime.ref_path(index, index["sections_file"]))
        self.assertEqual(sections["changed_inputs"], ["log"])

    def test_unchanged_correction_is_carried_by_runtime_not_reauthored(self):
        key = self.reviewed(True); self.resolve(key)
        delta = self.rt.prepare("completeness", {}, self.repo, previous=key)
        packet = runtime.read_json(delta["packet"])
        self.assertEqual(packet["correction_reuse"]["worker"], key)
        self.assertNotIn("correction_review", packet["result_contract"]["required"])
        value = self.result()
        value["delta_review"] = {**packet["result_contract"]["required"]["delta_review"], "disposition": "sufficient"}
        self.rt.attach(delta["worker"], "delta-agent")
        self.rt.publish(delta["worker"], value)
        got = self.rt.consume(delta["worker"])["result"]
        self.assertEqual(got["correction_review"], runtime.read_json(self.state)["workers"][key]["result"]["correction_review"])
        self.rt.accept(delta["worker"]); self.resolve(delta["worker"])
        self.assertTrue(self.rt.merge_gate(delta["worker"], self.repo)["passed"])

    def test_changed_code_or_correction_dependency_prevents_reuse(self):
        key = self.reviewed(True); self.resolve(key)
        self.code.write_text("original corrected again", encoding="utf-8")
        self.run_git("add", "code.txt"); self.run_git("commit", "-qm", "second fix")
        delta = self.rt.prepare("completeness", {}, self.repo, previous=key)
        self.assertNotIn("correction_reuse", runtime.read_json(delta["packet"]))
        worker = runtime.read_json(self.state)["workers"][key]
        worker["correction_dependencies"] = [{"path": str(self.code), "sha256": "old"}]
        self.assertFalse(runtime.Runtime.correction_reviewed(runtime.read_json(self.state), worker, worker["result"]))

    def fetch(self, name="fetch.json", body=None, status="Backlog", page="a" * 32):
        content = self.source.read_text(encoding="utf-8") if body is None else body
        url = "https://app.notion.com/p/" + page
        raw = {"metadata": {"type": "page"}, "title": "Generic requirement", "url": url,
               "text": '<page url="' + url + '">\n<properties>\n' + json.dumps({"Status": status, "Project": "Example", "userDefined:ID": "TEST-1"})
                       + '\n</properties>\n<content>\n' + content + '</content>\n</page>'}
        path = self.root / name; runtime.atomic_json(path, raw)
        return path

    def bind(self):
        self.config()
        body = self.source.read_text(encoding="utf-8")
        capture = self.fetch(body=body)
        source = self.rt.ticket_source(capture, self.repo / ".claude/notion-dev.config.json")
        self.source = Path(source["source"])
        self.inventory["source_sha256"] = source["source_sha256"]
        self.rt.requirements(self.source, self.inventory)
        with self.rt.transaction() as state: state["schema"] = 4
        return body

    def refresh(self, key, capture):
        pending = self.rt.refresh_ticket(key)
        # Fixture capture emulates a file saved after the provider call completes.
        os.utime(capture, (self.clock.stamp()["wall"] + 1,) * 2)
        return self.rt.refresh_ticket(key, capture, pending["request"], "tool-" + pending["request"])

    def test_full_ticket_refresh_is_required_and_status_only_changes_are_ignored(self):
        body = self.bind(); key = self.reviewed(); self.resolve(key)
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])
        receipt = self.refresh(key, self.fetch("new.json", body, "In Progress"))
        self.assertTrue(receipt["passed"])
        self.assertTrue(self.rt.merge_gate(key, self.repo)["passed"])
        self.clock.seconds += 301
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])

    def test_new_prerequisite_outside_acceptance_blocks_merge(self):
        body = self.bind(); key = self.reviewed(); self.resolve(key)
        receipt = self.refresh(key, self.fetch("changed.json", "## Prerequisite\nObtain customer approval.\n" + body))
        self.assertFalse(receipt["passed"])
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])

    def test_body_sections_never_hide_new_constraints(self):
        body = self.bind(); key = self.reviewed(); self.resolve(key)
        self.assertFalse(self.refresh(key, self.fetch("changed.json", body + "\n## Implementation\nMust also support offline mode.\n"))["passed"])

    def test_status_projection_failed_read_wrong_page_and_old_capture_are_rejected(self):
        body = self.bind(); key = self.reviewed(); self.resolve(key)
        for value in ({"rows": [{"Status": "In Progress"}]}, {"isError": True, "content": "failed"}):
            capture = self.root / "invalid.json"; runtime.atomic_json(capture, value)
            with self.assertRaises((runtime.Invalid, ValueError)): self.refresh(key, capture)
            self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])
        with self.assertRaisesRegex(runtime.Invalid, "not the reviewed ticket"):
            self.refresh(key, self.fetch("foreign.json", body, page="b" * 32))
        pending = self.rt.refresh_ticket(key)
        with self.assertRaisesRegex(runtime.Invalid, "do not replay"):
            self.rt.refresh_ticket(key, self.root / "fetch.json", pending["request"], "new-call")
        fresh = self.fetch("fresh.json", body)
        with self.assertRaisesRegex(runtime.Invalid, "stale or foreign"):
            self.rt.refresh_ticket(key, fresh, "foreign-request", "new-call")
        self.clock.seconds += 301
        with self.assertRaisesRegex(runtime.Invalid, "expired"):
            self.rt.refresh_ticket(key, fresh, pending["request"], "new-call")

    def test_complete_looking_failed_or_truncated_response_is_never_authoritative(self):
        raw = runtime.read_json(self.fetch())
        for marker in ("isError", "truncated", "has_more"):
            for invalid in ({**raw, marker: True}, {marker: True, "content": [{"type": "text", "text": json.dumps(raw)}]}):
                with self.assertRaisesRegex(runtime.Invalid, "incomplete fetch"):
                    runtime.notion_source(invalid, ["Status"])
        for malformed in ([None], {"metadata": None}, {"metadata": "page"}):
            with self.assertRaises(runtime.Invalid): runtime.notion_source(malformed, [])

    def test_receipt_replay_and_snapshot_tampering_are_rejected(self):
        body = self.bind(); key = self.reviewed(); self.resolve(key)
        capture = self.fetch("new.json", body); receipt = self.refresh(key, capture)["receipt"]
        pending = self.rt.refresh_ticket(key)
        with self.assertRaisesRegex(runtime.Invalid, "new actual provider"):
            self.rt.refresh_ticket(key, capture, pending["request"], receipt["call_id"])
        receipt = self.refresh(key, self.fetch("third.json", body))["receipt"]
        Path(receipt["response"]).write_text("tampered", encoding="utf-8")
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])

    def v3_plan(self, canonical=False):
        facts = self.facts(); data = runtime.read_json(facts)
        data.update(epic="b" * 32, epic_url="https://example.invalid/epic", brief_path="knowledge/epic/TEST-10.md",
                    knowledge_dir="knowledge", project_root=str(self.repo))
        if canonical:
            key = self.prepare(); value = self.result()
            value["report"] = "Long corroborating narrative. " * 1200
            value["recording"] = {"release_obligations": ["Obtain deployment approval after merge."],
                "claim_corrections": ["This is a new regression test, not a previously failing test."],
                "technical_delta": [{"fact": "Only the caller owns retries.", "evidence": "code.txt"}]}
            self.rt.publish(key, value); result = self.rt.consume(key)["result"]; self.rt.accept(key)
            runtime.atomic_json(self.root / "review.json", result)
            data["requirements"] = data["review"] = "review.json"
            data["knowledge_delta"] = [{"fact": "stale author claim", "evidence": "chat"}]
        with self.rt.transaction() as state: state["schema"] = 4
        runtime.atomic_json(facts, data)
        return workflow.record_plan(self.state, facts)

    def child_writes(self, parent):
        manifest = self.root / "writes.json"
        # Complete, scoped inputs; unrelated live content is not a frozen page replacement.
        runtime.atomic_json(manifest, [{"name": "completeness", "target": "https://example.invalid/ticket",
                                      "data": {"append": "verified evidence"}},
                                     {"name": "merged", "target": "https://example.invalid/ticket",
                                      "data": {"upsert": "merge facts"}}])
        return workflow.record_children(self.state, parent, str(manifest))

    def confirm(self, operation):
        current = workflow.record_input(self.state, operation, begin=True)
        self.assertIn(current["action"], {"execute", "reconcile"})
        return workflow.record_outcome(self.state, operation, "confirmed", "provider-readback")

    def test_deduplicated_provider_view_keeps_requirements_and_accepted_claims(self):
        plan = self.v3_plan(canonical=True)
        resolution = next(p for p in plan["operations"] if p["kind"] == "ticket-resolution")
        view = workflow.record_input(self.state, resolution["operation"])["data"]
        self.assertEqual(view["requirements"], view["review"])
        self.assertEqual(len(view["evidence"]), 2)  # review/requirements + verification
        review = view["evidence"][view["review"]["evidence_id"]]
        self.assertNotIn("report", review["data"])
        self.assertEqual(len(review["data"]["requirements"]), len(self.inventory["items"]))
        self.assertIn("Obtain deployment approval after merge.", view["release_obligations"])
        self.assertIn("new regression test", view["accepted_claim_corrections"][0])
        self.assertIn("Long corroborating narrative", Path(review["archive"]).read_text(encoding="utf-8"))
        self.assertLess(len(json.dumps(view)), 10000)
        knowledge = next(p for p in plan["operations"] if p["kind"] == "knowledge-delta")
        self.assertEqual(workflow.record_input(self.state, knowledge["operation"])["data"]["facts"][0]["fact"], "Only the caller owns retries.")
        self.assertEqual(next(p for p in plan["operations"] if p["kind"] == "epic-record")["target"], "https://example.invalid/epic")
        Path(review["archive"]).write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "archive changed"):
            workflow.record_input(self.state, resolution["operation"])

    def test_unknown_provider_fields_and_narrative_are_not_truncated(self):
        full = {"recording": {}, "report": "A requirement mentioned only here", "custom": {"obligation": "keep it"}}
        identity, view = workflow.evidence_view(full, self.root / "archive")
        self.assertEqual(view["data"], full)
        self.assertEqual(runtime.read_json(view["archive"]), full)

    def test_child_recovery_skips_confirmed_writes_and_reconciles_unknown(self):
        plan = self.v3_plan(); parent = next(p for p in plan["operations"] if p["kind"] == "ticket-resolution")["operation"]
        with self.assertRaisesRegex(ValueError, "record-children"):
            workflow.record_input(self.state, parent, begin=True)
        children = self.child_writes(parent)["children"]
        self.assertEqual(workflow.record_input(self.state, parent, begin=True)["action"], "children")
        first, second = [p["operation"] for p in children]
        receipt = self.confirm(first)
        self.assertEqual(receipt["target"], "https://example.invalid/ticket")
        workflow.record_input(self.state, second, begin=True)
        workflow.record_outcome(self.state, second, "unknown-outcome", "connection lost")
        self.assertEqual(workflow.record_input(self.state, first, begin=True)["action"], "skip")
        self.assertEqual(workflow.record_input(self.state, second, begin=True)["action"], "reconcile")
        with self.assertRaisesRegex(ValueError, "every declared write"):
            workflow.record_outcome(self.state, parent, "confirmed", "premature")
        # A live provider edit survives a section-level read/merge. Recovery reads the
        # effect; it never performs the already-confirmed append a second time.
        live = {"human": "new constraint", "completeness": "verified evidence", "merged": "merge facts"}
        self.assertEqual(live["merged"], workflow.record_input(self.state, second)["data"]["upsert"])
        workflow.record_outcome(self.state, second, "confirmed", "readback after disconnect")
        workflow.record_outcome(self.state, parent, "confirmed", "all child receipts")
        self.assertEqual(live["human"], "new constraint")
        self.assertEqual(workflow.record_input(self.state, parent, begin=True)["action"], "skip")
        with self.assertRaisesRegex(ValueError, "terminal"):
            workflow.record_outcome(self.state, first, "failed", "cannot undo confirmation")

    def test_full_child_manifest_is_bound_and_legacy_low_level_cannot_hide_omission(self):
        plan = self.v3_plan(); parent = next(p for p in plan["operations"] if p["kind"] == "ticket-resolution")
        for op in plan["operations"]:
            self.rt.record_op(op["operation"], op["target"], "confirmed", "legacy receipt", op["data_sha256"])
        self.assertFalse(workflow.record_summary(self.state)["passed"])
        self.assertIn(parent["operation"], workflow.record_summary(self.state)["blocking_unresolved"])

    def test_portable_stdin_child_payload_and_cli_confirmation(self):
        plan = workflow.record_plan(self.state, self.facts()); parent = plan["operations"][0]["operation"]
        script = ROOT / "plugins/notion-dev/scripts/workflow.py"
        command = [sys.executable, str(script), "record-child", "--state", str(self.state), "--parent", parent,
                   "--name", "unicode", "--target", "https://example.invalid/ticket", "--payload", "-"]
        result = subprocess.run(command, input='{"fact":"résolu – שלום"}', encoding="utf-8", capture_output=True, check=True)
        child = json.loads(result.stdout)
        self.assertEqual(workflow.record_input(self.state, child["operation"])["data"]["fact"], "résolu – שלום")
        self.confirm(child["operation"])
        self.assertEqual(workflow.record_input(self.state, child["operation"], begin=True)["action"], "skip")
        with self.assertRaisesRegex(ValueError, "real JSON file"):
            workflow.record_child(self.state, parent, "bad", "target", "/dev/fd/63")

    def test_arbitrary_child_evidence_field_is_not_an_internal_archive_pool(self):
        plan = self.v3_plan()
        parent = next(p for p in plan["operations"] if p["kind"] == "knowledge-delta")["operation"]
        for index, evidence in enumerate(("source:commit", {"quote": "verified behavior"})):
            payload = self.root / "child.json"
            runtime.atomic_json(payload, {"fact": "caller owns retries", "evidence": evidence})
            child = workflow.record_child(self.state, parent, "fact-" + str(index), "knowledge", str(payload))
            self.assertEqual(workflow.record_input(self.state, child["operation"], begin=True)["data"]["evidence"], evidence)

    def completion_fixture(self):
        plan = self.v3_plan()
        for op in plan["operations"]:
            if op["requires_children"]:
                for child in self.child_writes(op["operation"])["children"]: self.confirm(child["operation"])
                workflow.record_outcome(self.state, op["operation"], "confirmed", "child receipts")
            else: self.confirm(op["operation"])
        marker = self.root / ".claude/notion-dev/runs/TEST-1.json"
        runtime.atomic_json(marker, {"claude_session": "host", "runtime_state": str(self.state),
                                   "session": "invocation-1", "run": "TEST-1", "state": "running", "phase": "closeout"})
        return marker

    def test_completion_is_validated_and_updates_both_terminal_fields(self):
        marker = self.completion_fixture()
        with self.assertRaisesRegex(ValueError, "ownership"):
            workflow.complete(self.state, marker, "foreign-host")
        with self.assertRaisesRegex(ValueError, "use workflow.py complete"):
            workflow.marker_update(marker, "host", "complete", "complete")
        with self.assertRaisesRegex(ValueError, "phase-only completion"):
            workflow.marker_update(marker, "host", "complete")
        with self.assertRaisesRegex(runtime.Invalid, "validated terminal"):
            self.rt.stage("complete")
        self.rt.stage("closeout")
        self.assertTrue(workflow.complete(self.state, marker, "host")["passed"])
        self.assertEqual(runtime.read_json(marker)["state"], "complete")
        self.assertEqual(runtime.read_json(marker)["phase"], "complete")
        self.assertEqual(runtime.read_json(self.state)["stage"], "complete")
        self.assertTrue(any(e["kind"] == "stage_ended" and e["stage"] == "closeout"
                            for e in runtime.read_json(self.state)["events"]))
        self.assertTrue(workflow.complete(self.state, marker, "host")["passed"])
        with self.assertRaisesRegex(ValueError, "resume explicitly"):
            self.prepare("probe")

    def test_legacy_runtime_retains_its_documented_stage_complete_command(self):
        for schema in (1, 2, 3):
            with self.rt.transaction() as state: state["schema"] = schema
            self.assertEqual(self.rt.stage("complete"), {"stage": "complete"})

    def test_explicit_new_legacy_flow_uses_its_own_contract_without_downgrading_resumes(self):
        path = self.root / "legacy/state.json"
        legacy = runtime.Runtime(path)
        legacy.init("legacy-flow", "TEST-1", legacy=True)
        self.assertEqual(runtime.read_json(path)["schema"], 2)
        packet = legacy.prepare("probe", {"input": self.source})
        self.assertNotIn("result_contract", runtime.read_json(packet["packet"]))
        legacy.init("legacy-flow", "TEST-1")
        self.assertEqual(len(runtime.read_json(path)["workers"]), 1)
        lean_path = self.root / "new-lean/state.json"
        lean_runtime = runtime.Runtime(lean_path)
        lean_runtime.init("lean-flow", "TEST-1")
        lean_runtime.init("lean-flow", "TEST-1", legacy=True)
        self.assertEqual(runtime.read_json(lean_path)["schema"], 5)

    def test_owned_lock_outstanding_worker_and_partial_recording_block_completion(self):
        marker = self.completion_fixture()
        lock = marker.parent.parent / "locks/primary"
        lock.mkdir(parents=True); (lock / "owner").write_text("run: invocation-1\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "writer lock"):
            workflow.complete(self.state, marker, "host")
        # Another run's lock is observed, never released or mistaken for our own.
        (lock / "owner").write_text("run: foreign\n", encoding="utf-8")
        key = self.prepare("probe")
        with self.assertRaisesRegex(ValueError, "workers remain"):
            workflow.complete(self.state, marker, "host")
        self.rt.end_worker(key, "host confirmed stopped", confirmed=True, host_failed=True)
        self.rt.record_op("unknown-extra-operation", "target", "unknown-outcome", "lost response")
        with self.assertRaisesRegex(ValueError, "recording outcomes"):
            workflow.complete(self.state, marker, "host")
        self.assertEqual(runtime.read_json(marker)["state"], "running")
        self.assertTrue(lock.exists())

    def test_operation_routers_resolve_and_bound_the_intake_read_set(self):
        plugin = ROOT / "plugins/notion-dev"
        size = 0
        for name in ("knowledge", "epic-doc", "ticket-system"):
            base = plugin / "skills" / name
            text = (base / "SKILL.md").read_text(encoding="utf-8")
            size += len(text.encode("utf-8"))
            paths = re.findall(r"`((?:references/)?[a-z-]+\.md)`", text)
            self.assertTrue(paths, name)
            for path in paths:
                target = base / path if path.startswith("references/") else base / "references" / path
                self.assertTrue(target.is_file(), str(target))
        self.assertLess(size, 11000)
        mandatory = ["skills/knowledge/SKILL.md", "skills/knowledge/references/common.md",
                     "skills/knowledge/references/retrieve.md", "skills/epic-doc/SKILL.md",
                     "skills/epic-doc/references/schedule.md", "skills/epic-doc/references/parse.md",
                     "skills/ticket-system/SKILL.md", "skills/ticket-system/references/config.md",
                     "skills/ticket-system/references/query.md", "skills/ticket-system/references/fetch-ticket.md",
                     "skills/ticket-system/references/list-children.md"]
        self.assertLess(sum((plugin / p).stat().st_size for p in mandatory), 70000)
        next_task = (plugin / "commands/next-task.md").read_text(encoding="utf-8")
        self.assertIn("schedule(<epic-id>)", next_task)
        self.assertNotIn("retrieve(<epic-id>)", next_task)
        retrieve = (plugin / "skills/knowledge/references/retrieve.md").read_text(encoding="utf-8")
        self.assertIn('skills/epic-doc/references/parse.md', retrieve)
        self.assertIn('--lexical "<ticket title>"', retrieve)
        self.assertNotIn('## `capture', retrieve)
        self.assertNotIn('## `migrate', retrieve)
        schedule = (plugin / "skills/epic-doc/references/schedule.md").read_text(encoding="utf-8")
        self.assertIn("full candidate ticket", schedule)
        self.assertIn("live resolved statuses", schedule)
        self.assertIn("dependency may be outside", schedule)

    @unittest.skipUnless(shutil.which("iwe"), "iwe integration is exercised in both full CI jobs")
    def test_targeted_retrieval_retains_sibling_history_and_release_constraints(self):
        bundle = self.root / "knowledge"
        shutil.copytree(ROOT / "scripts/fixtures/handoffs", bundle)
        shutil.copytree(ROOT / "plugins/notion-dev/skills/knowledge/references/iwe", bundle / ".iwe")
        # npm installs iwe.cmd on Windows; CreateProcess does not resolve a bare
        # "iwe" through PATHEXT. Match knowledge.py's resolved executable path.
        proc = subprocess.run([shutil.which("iwe"), "retrieve", "-k", "epic/TEST-10", "--expand-references", "1",
            "--lexical", "Sanitize the failure response", "--filter", "status: stable", "--max-tokens", "1000", "-f", "markdown"],
            cwd=bundle, capture_output=True, encoding="utf-8", check=True)
        for required in ("sibling failure paths", "Rejected historical approach", "approval before deployment"):
            self.assertIn(required, proc.stdout)
        self.assertIn("[TEST-2] Sanitize the failure response", proc.stdout)
        self.assertNotIn("migration", proc.stdout)

    def test_guards_fail_under_isolated_mutations(self):
        # Isolated functions/fixtures only. No worktree reset/restore, no source edits.
        original_baseline = runtime.Runtime.delta_baseline
        original_prepare = runtime.Runtime.prepare
        original_view = workflow.evidence_view

        def skip_handoff(instance, state, previous, current):
            state["workers"][previous]["citation_resolutions"] = []
            return original_baseline(instance, state, previous, current)

        def forget_inputs(instance, role, files, *args, **kwargs):
            if kwargs.get("previous"):
                old = runtime.read_json(instance.path)["workers"][kwargs["previous"]]["files"]
                kwargs["remove_inputs"] = [name for name in old if name not in files]
            return original_prepare(instance, role, files, *args, **kwargs)

        def confirm_without_children(state, operation, outcome, provider_id=None):
            current = workflow.record_input(state, operation)
            return workflow.Runtime(state).record_op(operation, current["target"], outcome, provider_id, current["data_sha256"])

        # Check each mutation trips the corresponding independent behavioral assertion.
        cases = [
            ("test_full_ticket_refresh_is_required_and_status_only_changes_are_ignored",
             runtime.Runtime, "ticket_freshness", lambda *a: []),
            ("test_delta_requires_evidence_handoff_and_retains_named_inputs",
             runtime.Runtime, "delta_baseline", skip_handoff),
            ("test_delta_requires_evidence_handoff_and_retains_named_inputs",
             runtime.Runtime, "prepare", forget_inputs),
            ("test_deduplicated_provider_view_keeps_requirements_and_accepted_claims",
             workflow, "evidence_view", lambda snapshot, directory, canonical=None: original_view(snapshot, directory)),
            ("test_child_recovery_skips_confirmed_writes_and_reconciles_unknown",
             workflow, "record_outcome", confirm_without_children),
            ("test_completion_is_validated_and_updates_both_terminal_fields",
             workflow, "complete", lambda *a: {"passed": True}),
        ]
        original_correction = runtime.Runtime.correction_reviewed
        cases.append(("test_structured_correction_punctuation_and_rendering", runtime.Runtime, "correction_reviewed",
                      staticmethod(lambda state, worker, result: original_correction(state, {**worker, "contract_version": 2}, result))))
        for test, target, method, replacement in cases:
            with self.subTest(mutation=method):
                case = HandoffTests(test)
                try:
                    case.setUp()
                    with patch.object(target, method, replacement):
                        with self.assertRaises(AssertionError): getattr(case, test)()
                finally: case.doCleanups()

    def test_instruction_guards_reject_their_own_removal(self):
        guards = {
            "skills/epic-doc/references/schedule.md": ["full candidate ticket", "live resolved statuses", "dependency may be outside", "Fetch candidates progressively"],
            "skills/epic-doc/references/record.md": ["dependencies_known: false", "external_statuses"],
            "skills/knowledge/references/capture.md": ["recording.technical_delta", "All touched concepts still receive a validity check"],
            "commands/create-task.md": ["--reviewed-followup", "Every implementation-", "only the missing questions"],
            "skills/knowledge/references/retrieve.md": ['--lexical "<ticket title>"', 'skills/epic-doc/references/parse.md'],
            "skills/ticket-system/references/fetch-ticket.md": ["actual host tool-call ID", "complete original notion-fetch"],
            "skills/review-and-merge/SKILL.md": ["refresh-ticket", "--call-id", "Resolve baseline citations BEFORE"],
            "references/record.md": ["record-children", "record-outcome", "workflow.py complete", "Never pipe provider input through head/tail", "record-reconcile", "--readback-verdict", "Begin before invoking Skill"],
        }
        candidate = self.root / "instructions.md"
        command = 'fails=0; ok() { :; }; bad() { fails=$((fails + 1)); }; . "$1"; assert_has invariant "$2" "$3"; test "$fails" -eq 0'
        for path, fragments in guards.items():
            source = (ROOT / "plugins/notion-dev" / path).read_text(encoding="utf-8")
            for fragment in fragments:
                for text, expected in ((source, 0), (source.replace(fragment, "REMOVED"), 1)):
                    candidate.write_text(text, encoding="utf-8")
                    proc = subprocess.run([runtime.bash_exe(), "-c", command, "--", (ROOT / "scripts/lib/assert.sh").as_posix(),
                                           candidate.as_posix(), fragment], capture_output=True)
                    self.assertEqual(proc.returncode, expected, (path, fragment, proc.stderr.decode("utf-8")))


if __name__ == "__main__":
    unittest.main()
