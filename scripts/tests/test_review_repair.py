"""Lossless review accounting and user-authorized recovery on Windows and WSL.

Synthetic evidence only; no client data, live providers or spawned agents.
"""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_boundaries as boundaries
from test_lean_workflow import runtime, workflow, account_findings
import host_capture


class ReviewRepairTests(unittest.TestCase):
    setUp = boundaries.BoundaryTests.setUp
    config = boundaries.BoundaryTests.config
    fetch = boundaries.BoundaryTests.fetch
    prepare = boundaries.BoundaryTests.prepare
    result = boundaries.BoundaryTests.result
    resolve = boundaries.BoundaryTests.resolve
    run_git = boundaries.BoundaryTests.run_git
    new_schema = boundaries.BoundaryTests.new_schema
    log = boundaries.BoundaryTests.log
    capture = boundaries.BoundaryTests.capture
    reviewed = boundaries.BoundaryTests.reviewed

    @staticmethod
    def finding(obligation="advisory", text="optional naming suggestion", resolved=False):
        return {"finding": text, "rationale": "independent source and test evidence",
                "obligation": obligation, "resolved": resolved, "disposition": "absorb" if resolved else "blocked",
                "blocking": obligation == "unknown" or (obligation == "mandatory" and not resolved)}

    def published(self, value):
        self.new_schema()
        key = self.prepare()
        self.rt.publish(key, value)
        self.rt.consume(key, summary=True)
        return key

    def fresh_gate(self, key, fetched):
        pending = self.rt.refresh_ticket(key)
        self.clock.seconds += 2
        self.rt.capture_ticket(self.log(fetched, "fresh"), "fixture-session", "fresh",
                               worker=key, request=pending["request"])
        return self.rt.merge_gate(key, self.repo)

    def test_hidden_third_finding_cannot_be_lost_in_clipped_summary(self):
        value = self.result()
        value["claims"]["findings"] = [self.finding(text="long evidence " * 300),
                                       self.finding(text="second"), self.finding("mandatory", "hidden defect")]
        key = self.published(value)
        index = self.rt.result_view(key)
        self.assertLess(len(json.dumps(index).encode()), 3000)
        self.assertEqual(index["findings"]["count"], 3)
        self.assertIn("claims:3", index["findings"]["ids"])
        self.assertFalse(index["findings"]["complete"])
        self.assertFalse(index["findings"]["accounted"])
        with self.assertRaisesRegex(runtime.Invalid, "unaccounted"): self.rt.accept(key)
        with self.assertRaisesRegex(runtime.Invalid, "account for every"): self.prepare()
        entries = account_findings(self.rt, key)
        self.assertEqual(entries[2]["evidence"]["finding"], "hidden defect")
        self.rt.accept(key)
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])

    def test_unicode_fragments_are_bounded_lossless_and_paged(self):
        value = self.result()
        value["claims"]["findings"] = [self.finding(text="שלום🙂\\\n" * 600)] * 12
        key = self.published(value)
        index = self.rt.result_view(key)
        self.assertFalse(index["findings"]["ids_complete"])
        for page in range(1, index["findings"]["pages"] + 1):
            self.assertLess(len(json.dumps(self.rt.result_view(key, page=page), ensure_ascii=False).encode()), 4096)
        entries = account_findings(self.rt, key)
        self.assertEqual(len(entries), 12)
        self.assertEqual(entries[0]["evidence"], value["claims"]["findings"][0])
        with self.assertRaisesRegex(runtime.Invalid, "range"): self.rt.result_view(key, page=0)

    def test_judgment_rejects_missing_duplicate_foreign_hash_and_unread_evidence(self):
        value = self.result(); value["claims"]["findings"] = [self.finding()]
        key = self.published(value); index = self.rt.result_view(key)
        judgment = {"result_sha256": index["result_sha256"], "dispositions": [
            {"id": "claims:1", "action": "drop", "rationale": "optional", "evidence": "source"}]}
        with self.assertRaisesRegex(runtime.Invalid, "read every"): self.rt.judge_findings(key, judgment)
        account_findings(self.rt, key)
        for change in ({"result_sha256": "wrong"}, {"dispositions": []},
                       {"dispositions": judgment["dispositions"] * 2},
                       {"dispositions": [{**judgment["dispositions"][0], "id": "invented"}]},
                       {"dispositions": [{**judgment["dispositions"][0], "evidence": ""}]}):
            with self.subTest(change=change), self.assertRaises(runtime.Invalid):
                self.rt.judge_findings(key, {**judgment, **change})
        self.rt.judge_findings(key, judgment); self.rt.accept(key)
        self.rt.consume(key, summary=True)
        self.assertTrue(self.rt.result_view(key)["findings"]["accounted"])

    def test_advisory_only_result_passes_all_gates_after_disposition(self):
        fetched = self.capture()
        value = self.result(); value["code_review"].update(verdict="findings", findings=[self.finding()])
        key = self.published(value)
        account_findings(self.rt, key); self.rt.accept(key); self.resolve(key)
        self.assertTrue(self.fresh_gate(key, fetched)["passed"])

    def test_mandatory_unknown_and_unverified_cannot_be_disposed_away(self):
        self.new_schema(); key = self.prepare()
        worker = runtime.read_json(self.state)["workers"][key]
        for kind in ("mandatory", "unknown"):
            value = self.result(); value["code_review"].update(verdict="findings", findings=[self.finding(kind)])
            runtime.validate_result(worker, value)
            self.assertFalse(runtime.review_pass(worker, value["code_review"]))
            value["code_review"]["findings"][0]["blocking"] = False
            with self.assertRaisesRegex(runtime.Invalid, "nonblocking"): runtime.validate_result(worker, value)
        value = self.result(); value["code_review"]["verdict"] = "unverified"
        self.assertFalse(runtime.review_pass(worker, value["code_review"]))
        value["code_review"]["verdict"] = "findings"
        with self.assertRaisesRegex(runtime.Invalid, "enumerate"): runtime.validate_result(worker, value)

    def test_legacy_prose_findings_remain_unknown_and_nonpassing(self):
        key = self.prepare(); value = self.result()
        value["code_review"] = {"verdict": "findings", "citation": "Three prose-only findings"}
        self.rt.publish(key, value); self.rt.consume(key, summary=True)
        self.assertEqual(self.rt.result_view(key)["findings"]["counts"], {"unknown": 1})
        with self.assertRaises(runtime.Invalid): self.rt.accept(key)
        account_findings(self.rt, key); self.rt.accept(key); self.resolve(key)
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])

    def test_correction_advisories_use_same_gate_and_stale_dependencies_still_fail(self):
        self.new_schema(); self.rt.correction_needed(self.repo, "claim correction")
        key = self.prepare(); worker = runtime.read_json(self.state)["workers"][key]
        value = self.result()
        value["correction_review"] = {"id": worker["correction"]["id"],
            "manifest_sha256": worker["correction_manifest"]["sha256"], "verdict": "findings",
            "findings": [self.finding()], "blocking_findings": [], "report": "optional only", "depends_on": []}
        self.rt.publish(key, value); self.rt.consume(key)
        account_findings(self.rt, key); self.rt.accept(key)
        state = runtime.read_json(self.state); worker = state["workers"][key]
        self.assertTrue(self.rt.correction_reviewed(state, worker, worker["result"]))
        worker["correction_dependencies"] = [{"path": str(self.root / "missing.log"), "sha256": "missing"}]
        self.assertFalse(self.rt.correction_reviewed(state, worker, worker["result"]))

    def delta_finish(self, previous):
        prepared = self.rt.prepare("completeness", {}, self.repo, previous=previous)
        packet = runtime.read_json(prepared["packet"]); key = prepared["worker"]
        value = self.result()
        value["delta_review"] = {**packet["result_contract"]["required"]["delta_review"], "disposition": "sufficient"}
        self.rt.attach(key, "host-" + key); self.rt.publish(key, value); self.rt.consume(key)
        self.rt.accept(key); self.resolve(key)
        return key

    def exhausted(self):
        self.new_schema(); key = self.reviewed(); self.resolve(key)
        key = self.delta_finish(key)
        return self.delta_finish(key)

    def approval(self, request, **changes):
        self.clock.seconds += 1
        row = {"type": "user", "uuid": "human-approval", "sessionId": "fixture-session",
               "timestamp": datetime.fromtimestamp(self.clock.stamp()["wall"], timezone.utc).isoformat(),
               "message": {"role": "user", "content": request["approval_phrase"]}}
        row.update(changes)
        path = self.root / "approval café.jsonl"
        path.write_text(json.dumps(row) + "\n", encoding="utf-8")
        return path

    def test_exhausted_budget_requires_real_user_and_grants_only_one_delta(self):
        key = self.exhausted()
        with self.assertRaisesRegex(runtime.Invalid, "budget exhausted"):
            self.rt.prepare("completeness", {}, self.repo, previous=key)
        request = self.rt.budget_request(key, self.repo, "two coupled corrections", "documentation claim and indirect impact")
        path = self.approval(request)
        self.rt.budget_extend(request["request"], path, "fixture-session", None, self.repo)
        with self.assertRaisesRegex(runtime.Invalid, "already authorized"):
            self.rt.budget_extend(request["request"], path, "fixture-session", "human-approval", self.repo)
        key = self.delta_finish(key)
        self.rt = runtime.Runtime(self.state, self.clock)  # Restart is not a new budget.
        self.assertEqual(self.rt.summary()["delta_attempts"], 3)
        self.assertEqual(self.rt.summary()["full_completeness_attempts"], 1)
        self.assertEqual(self.rt.summary()["review_budget"]["extensions"][0]["worker"], key)
        with self.assertRaisesRegex(runtime.Invalid, "budget exhausted"):
            self.rt.prepare("completeness", {}, self.repo, previous=key)

    def test_approval_rejects_agent_tool_meta_foreign_stale_and_wrong_phrase(self):
        key = self.exhausted(); request = self.rt.budget_request(key, self.repo, "reason", "scope")
        cases = [{"type": "assistant"}, {"isSidechain": True}, {"isMeta": True}, {"isCompactSummary": True},
                 {"sessionId": "foreign"}, {"timestamp": "2020-01-01T00:00:00Z"},
                 {"message": {"role": "user", "content": "go ahead"}},
                 {"message": {"role": "user", "content": [{"type": "tool_result", "content": request["approval_phrase"]}]}}]
        for changes in cases:
            path = self.approval(request, **changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.rt.budget_extend(request["request"], path, "fixture-session", "human-approval", self.repo)
        self.assertFalse(self.rt.summary()["review_budget"]["extensions"][0]["authority"])

    def test_extension_is_bound_to_revision_and_owner(self):
        key = self.exhausted(); request = self.rt.budget_request(key, self.repo, "reason", "scope")
        path = self.approval(request)
        self.code.write_text("changed\n", encoding="utf-8")
        with self.assertRaisesRegex(runtime.Invalid, "changed"):
            self.rt.budget_extend(request["request"], path, "fixture-session", "human-approval", self.repo)
        self.code.write_text("original\n", encoding="utf-8")
        self.rt.budget_extend(request["request"], path, "fixture-session", "human-approval", self.repo)
        with self.rt.transaction() as state: state["host_session"] = "new-owner"
        with self.assertRaisesRegex(runtime.Invalid, "budget exhausted"):
            self.rt.prepare("completeness", {}, self.repo, previous=key)

    def test_exhausted_preparation_does_not_rerun_validation(self):
        key = self.exhausted()
        with patch.object(workflow, "verify_config") as verify:
            with self.assertRaisesRegex(ValueError, "budget exhausted"):
                workflow.review_prepare(self.state, self.repo, self.repo, {}, previous=key)
            verify.assert_not_called()

    def test_grant_cannot_replace_authorized_claims_or_increase_full_budget(self):
        key = self.exhausted(); request = self.rt.budget_request(key, self.repo, "reason", "scope")
        self.rt.budget_extend(request["request"], self.approval(request), "fixture-session", "human-approval", self.repo)
        replacement = self.root / "different.md"; replacement.write_text("different source", encoding="utf-8")
        with self.assertRaisesRegex(runtime.Invalid, "inputs changed"):
            self.rt.prepare("completeness", {"ticket": replacement}, self.repo, previous=key)
        # The original second full allowance can be used, but the grant adds no third.
        extra = self.reviewed(); self.resolve(extra)
        with self.assertRaisesRegex(runtime.Invalid, "full completeness attempt budget"):
            self.prepare()
        with self.assertRaisesRegex(runtime.Invalid, "latest accepted"):
            self.rt.prepare("completeness", {}, self.repo, previous=key)

    def test_compact_advisory_delta_preserves_accounting_and_legacy_clean_upgrade(self):
        self.new_schema(); value = self.result()
        value["code_review"].update(verdict="findings", findings=[self.finding()])
        key = self.published(value); account_findings(self.rt, key); self.rt.accept(key); self.resolve(key)
        prepared = self.rt.prepare("completeness", {}, self.repo, previous=key)
        packet = runtime.read_json(prepared["packet"])
        compact = {"report": "All indirect impacts checked", "requirements_complete": True,
            "delta_review": {**packet["result_contract"]["required"]["delta_review"], "disposition": "sufficient"},
            "delta_result": {"baseline_sha256": packet["delta_publication"]["baseline_sha256"],
                "changed_requirements": [], "reused_requirement_ids": [i["id"] for i in self.inventory["items"]],
                "updated_sections": {}, "reused_sections": ["code_review", "blocking_findings", "claims", "caveats", "triage", "recording"]}}
        delta = prepared["worker"]; self.rt.attach(delta, "host-delta"); self.rt.publish(delta, compact); self.rt.consume(delta)
        with self.assertRaisesRegex(runtime.Invalid, "unaccounted"): self.rt.accept(delta)
        account_findings(self.rt, delta); self.rt.accept(delta)
        self.assertEqual(runtime.read_json(self.state)["workers"][delta]["result"]["code_review"], value["code_review"])

    def test_legacy_clean_delta_needs_no_reviewer_just_to_add_empty_field(self):
        self.new_schema()
        with patch.object(runtime, "RESULT_CONTRACT_VERSION", 4): key = self.prepare()
        value = self.result(); value["code_review"].pop("findings")
        self.rt.publish(key, value); self.rt.consume(key); self.rt.accept(key); self.resolve(key)
        prepared = self.rt.prepare("completeness", {}, self.repo, previous=key)
        packet = runtime.read_json(prepared["packet"])
        compact = {"report": "Indirect effects checked", "requirements_complete": True,
            "delta_review": {**packet["result_contract"]["required"]["delta_review"], "disposition": "sufficient"},
            "delta_result": {"baseline_sha256": packet["delta_publication"]["baseline_sha256"],
                "changed_requirements": [], "reused_requirement_ids": [i["id"] for i in self.inventory["items"]],
                "updated_sections": {}, "reused_sections": ["code_review", "blocking_findings", "claims", "caveats", "triage", "recording"]}}
        delta = prepared["worker"]; self.rt.attach(delta, "host-delta"); self.rt.publish(delta, compact)
        self.assertEqual(self.rt.consume(delta)["result"]["code_review"]["findings"], [])
        self.rt.accept(delta)

    def test_approval_partial_conflicting_and_replayed_transcripts_fail(self):
        key = self.exhausted(); request = self.rt.budget_request(key, self.repo, "reason", "scope")
        path = self.approval(request); raw = path.read_bytes()
        path.write_bytes(raw[:-1])
        with self.assertRaisesRegex(ValueError, "missing"):
            self.rt.budget_extend(request["request"], path, "fixture-session", "human-approval", self.repo)
        row = json.loads(raw); row["message"]["content"] = "not authorized"
        path.write_bytes(raw + (json.dumps(row) + "\n").encode())
        for selector in (None, "human-approval"):
            with self.subTest(selector=selector), self.assertRaises(ValueError):
                self.rt.budget_extend(request["request"], path, "fixture-session", selector, self.repo)
        path.write_bytes(raw)
        second = self.rt.budget_request(key, self.repo, "another request", "different scope")
        with self.assertRaises(ValueError):
            self.rt.budget_extend(second["request"], path, "fixture-session", "human-approval", self.repo)

    def test_regressions_kill_guard_mutations_without_touching_tracked_files(self):
        ledger = runtime.finding_ledger
        binding = runtime.Runtime.budget_binding
        def forget_revision(*args):
            result = binding(*args); result.pop("revision")
            return result
        cases = [
            ("test_hidden_third_finding_cannot_be_lost_in_clipped_summary", runtime, "findings_accounted", lambda w: True),
            ("test_hidden_third_finding_cannot_be_lost_in_clipped_summary", runtime, "finding_ledger", lambda r: ledger(r)[:2]),
            ("test_advisory_only_result_passes_all_gates_after_disposition", runtime, "review_pass", lambda w, r: r.get("verdict") == "clean"),
            ("test_mandatory_unknown_and_unverified_cannot_be_disposed_away", runtime, "validate_findings", lambda r: None),
            ("test_approval_rejects_agent_tool_meta_foreign_stale_and_wrong_phrase", host_capture, "user_approval", lambda *a: {"invented": True}),
            ("test_exhausted_preparation_does_not_rerun_validation", workflow.Runtime, "check_review_budget", lambda *a: None),
            ("test_extension_is_bound_to_revision_and_owner", runtime.Runtime, "budget_binding", staticmethod(forget_revision)),
            ("test_exhausted_budget_requires_real_user_and_grants_only_one_delta", runtime.Runtime, "correction_grant", lambda *a: None),
        ]
        for name, owner, attribute, replacement in cases:
            outcome = unittest.TestResult()
            with self.subTest(guard=attribute), patch.object(owner, attribute, replacement):
                ReviewRepairTests(name).run(outcome)
                self.assertFalse(outcome.wasSuccessful(), "mutation survived: " + attribute)


if __name__ == "__main__":
    unittest.main()
