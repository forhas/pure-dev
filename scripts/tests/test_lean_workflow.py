"""Generic offline regressions for the lean path; no client data or provider writes."""
from contextlib import ExitStack, nullcontext
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_runtime as support
from test_runtime import runtime, telemetry, ROOT

sys.path.insert(0, str(ROOT / "plugins/notion-dev/scripts"))
import workflow
import dependencies


class LeanTests(unittest.TestCase):
    run_git = support.RuntimeTests.run_git
    prepare = support.RuntimeTests.prepare
    resolve = support.RuntimeTests.resolve

    def result(self):
        value = support.RuntimeTests.result(self)
        value.update({name: {"status": "checked", "evidence": "fixture audit: source, diff and PR body",
                             "findings": []} for name in runtime.AUDIT_FIELDS})
        return value

    def setUp(self):
        support.RuntimeTests.setUp(self)
        with self.rt.transaction() as state:
            state["schema"] = 3
            state["ticket"] = "TEST-1"

    def config(self):
        directory = self.repo / ".claude"
        directory.mkdir(exist_ok=True)
        value = {"project": {"key": "TEST", "name": "Example"},
                 "ticketSystem": {"databaseId": "fixture-db"}, "git": {"baseBranch": "main"},
                 "verify": {"steps": [{"name": "check", "cmd": "printf checked"}]}}
        runtime.atomic_json(directory / "notion-dev.config.json", value)
        return value

    def test_new_run_uses_schema_three(self):
        state = self.root / "new/state.json"
        runtime.Runtime(state).init("new", "TEST-1")
        self.assertEqual(runtime.read_json(state)["schema"], 3)

    def test_generated_contract_covers_whole_inventory_and_code_review(self):
        key = self.prepare()
        worker = runtime.read_json(self.state)["workers"][key]
        packet = runtime.read_json(worker["packet"])
        contract = packet["result_contract"]["required"]
        self.assertEqual({v["id"] for v in contract["requirements"]},
                         {v["id"] for v in self.inventory["items"]})
        self.assertIn("code_review", contract)
        self.assertIn("blocking_findings", contract)
        self.assertEqual(packet["result_contract"]["version"], 2)
        for name in runtime.AUDIT_FIELDS:
            self.assertEqual(set(contract[name]), {"status", "evidence", "findings"})

    def test_report_only_result_repairs_in_same_worker_without_redispatch(self):
        key = self.prepare()
        with self.assertRaisesRegex(runtime.Invalid, "requirements_complete"):
            self.rt.publish(key, {"report": "all done"})
        self.assertEqual(self.rt.inspect(key)["status"], "running")
        self.rt.publish(key, self.result())
        self.rt.consume(key)
        self.rt.accept(key)
        self.resolve(key)
        self.assertTrue(self.rt.merge_gate(key, self.repo)["passed"])
        self.assertEqual(len(runtime.read_json(self.state)["workers"]), 1)

    def test_each_required_field_is_checked_at_publication(self):
        key = self.prepare()
        worker = runtime.read_json(self.state)["workers"][key]
        for field in ("report", "requirements_complete", "requirements", "blocking_findings", "code_review",
                      "claims", "caveats", "triage"):
            with self.subTest(field=field):
                value = self.result(); del value[field]
                with self.assertRaises(runtime.Invalid):
                    runtime.validate_result(worker, value)
                with self.assertRaises(runtime.Invalid):
                    self.rt.publish(key, value)
                self.assertFalse(self.rt.inspect(key)["result_available"])

    def test_malformed_audits_repair_in_same_worker(self):
        key = self.prepare()
        invalid = [None, {}, {"status": "checked", "findings": [], "evidence": ""},
                   {"status": "NONE", "findings": [], "evidence": "scope"},
                   {"status": "checked", "findings": None, "evidence": "scope"},
                   {"status": "checked", "findings": [{}], "evidence": "scope"}]
        finding = {"finding": "unsupported claim", "disposition": "file", "rationale": "issue link",
                   "blocking": False}
        for field, value in (("finding", ""), ("disposition", "waive"), ("rationale", None), ("blocking", "false")):
            invalid.append({"status": "checked", "evidence": "scope", "findings": [{**finding, field: value}]})
        for name in runtime.AUDIT_FIELDS:
            for audit in invalid:
                value = self.result(); value[name] = audit
                with self.subTest(audit=name, value=audit), self.assertRaises(runtime.Invalid):
                    self.rt.publish(key, value)
        self.rt.publish(key, self.result())
        self.assertTrue(self.rt.inspect(key)["result_available"])
        self.assertEqual(len(runtime.read_json(self.state)["workers"]), 1)

    def test_unverified_and_blocking_audits_are_honest_nonpassing_results(self):
        # Publication/acceptance can succeed without licensing merge; filing isn't a waiver.
        for name in runtime.AUDIT_FIELDS:
            for disposition in (None, "file", "drop", "absorb", "blocked"):
                case = LeanTests()
                try:
                    case.setUp(); key = case.prepare(); value = case.result()
                    if disposition is None:
                        value[name]["status"] = "unverified"
                    else:
                        value[name]["findings"] = [{"finding": "mandatory claim unresolved",
                            "disposition": disposition, "rationale": "still outstanding", "blocking": True}]
                    value["report"] += name.upper() + ": NONE\n"
                    case.rt.publish(key, value)
                    report = case.rt.consume(key)["result"]["report"]
                    self.assertIn("COMPLETENESS: blocked", report)
                    self.assertNotIn(name.upper() + ": NONE", report)
                    self.assertIn(name.upper() + ": " + json.dumps(value[name], sort_keys=True), report)
                    case.rt.accept(key); case.resolve(key)
                    self.assertFalse(case.rt.merge_gate(key, case.repo)["passed"])
                finally:
                    case.doCleanups()

    def test_nonblocking_audit_is_preserved_and_rendering_is_idempotent(self):
        key = self.prepare(); value = self.result()
        value["caveats"]["findings"] = [{"finding": "release requires deployment",
            "disposition": "drop", "rationale": "release-only, not a merge prerequisite", "blocking": False}]
        worker = runtime.read_json(self.state)["workers"][key]
        rendered = runtime.render_result(worker, value)
        self.assertEqual(runtime.render_result(worker, rendered), rendered)
        self.rt.publish(key, rendered); self.rt.consume(key); self.rt.accept(key); self.resolve(key)
        self.assertTrue(self.rt.merge_gate(key, self.repo)["passed"])

    def test_version_one_in_flight_worker_retains_contract_and_next_worker_upgrades(self):
        contract = runtime.result_contract("completeness", self.inventory["items"])
        contract["version"] = 1
        del contract["audit_rules"]
        for name in runtime.AUDIT_FIELDS: del contract["required"][name]
        with patch.object(runtime, "RESULT_CONTRACT_VERSION", 1), patch.object(runtime, "result_contract", return_value=contract):
            key = self.prepare()
        worker = runtime.read_json(self.state)["workers"][key]
        packet_hash = runtime.digest(worker["packet"])
        self.rt.publish(key, support.RuntimeTests.result(self))
        self.rt.consume(key); self.rt.accept(key); self.resolve(key)
        self.assertTrue(self.rt.merge_gate(key, self.repo)["passed"])
        self.assertEqual(runtime.digest(worker["packet"]), packet_hash)
        delta = self.rt.prepare("completeness", {"ticket": self.source}, self.repo, previous=key)
        packet = runtime.read_json(delta["packet"])
        self.assertEqual(packet["result_contract"]["version"], 2)
        self.assertIn("triage", packet["result_contract"]["required"])
        self.assertIn("delta_review", packet["result_contract"]["required"])

    def test_missing_duplicate_and_null_requirement_verdicts_are_rejected(self):
        key = self.prepare()
        for change in (lambda r: r["requirements"].pop(),
                       lambda r: r["requirements"].append(r["requirements"][0]),
                       lambda r: r["requirements"][0].update(citation=None)):
            value = self.result(); change(value)
            with self.assertRaises(runtime.Invalid): self.rt.publish(key, value)

    def test_code_findings_are_valid_but_do_not_merge(self):
        key = self.prepare()
        value = self.result(); value["code_review"]["verdict"] = "findings"
        self.rt.publish(key, value); self.rt.consume(key); self.rt.accept(key); self.resolve(key)
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])

    def test_correction_contract_is_generated_and_repaired_before_publication(self):
        self.rt.correction_needed(self.repo, "fix a review finding")
        self.code.write_text("corrected\n", encoding="utf-8")
        self.run_git("add", "code.txt"); self.run_git("commit", "-qm", "correction")
        key = self.prepare(); worker = runtime.read_json(self.state)["workers"][key]
        packet = runtime.read_json(worker["packet"])
        contract = packet["result_contract"]["required"]["correction_review"]
        value = self.result()
        with self.assertRaisesRegex(runtime.Invalid, "correction_review"):
            self.rt.publish(key, value)
        value["correction_review"] = {**contract, "verdict": "clean", "report": "VERDICT: CLEAN"}
        self.rt.publish(key, value)
        self.assertTrue(self.rt.inspect(key)["result_available"])

    def test_new_gate_requires_parent_acceptance_and_rejects_source_drift(self):
        key = self.prepare(); self.rt.publish(key, self.result()); self.rt.consume(key); self.resolve(key)
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])
        self.rt.accept(key)
        self.assertTrue(self.rt.merge_gate(key, self.repo)["passed"])
        self.code.write_text("changed after review\n", encoding="utf-8")
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])

    def test_rendered_counts_follow_verdicts_not_prose(self):
        key = self.prepare(); value = self.result()
        value["requirements"][1]["verdict"] = "unverified"
        self.rt.publish(key, value)
        result = self.rt.consume(key)["result"]
        self.assertIn("CRITERIA-UNVERIFIED: 1", result["report"])
        self.assertIn("COMPLETENESS: blocked", result["report"])
        self.resolve(key)
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])

    def test_record_result_cannot_hide_six_fields_in_chat(self):
        key = self.prepare("record")
        with self.assertRaisesRegex(runtime.Invalid, "eight"):
            self.rt.publish(key, {"report": "ok; complete report will arrive in chat"})
        fields = {k: "confirmed: durable receipt" for k in runtime.RECORD_FIELDS}
        self.rt.publish(key, {"report": "short summary", "record": fields})
        result = self.rt.consume(key)["result"]
        for field in fields: self.assertIn(field + ": confirmed", result["report"])
        self.rt.accept(key)

    def test_question_visible_without_chat_and_answer_excludes_wait_time(self):
        key = self.prepare("implementation")
        self.clock.seconds = 100
        question = self.rt.question(key, "Can this test setup use the existing fixture?")
        self.clock.seconds = 2000
        self.assertEqual(self.rt.wait(key, 0)["status"], "needs_input")
        with self.assertRaises(runtime.Invalid): self.rt.publish(key, {"report": "finished"})
        self.rt.answer(key, question["id"], "Yes; preserve the behavior requirement.")
        self.assertEqual(self.rt.inspect(key)["status"], "running")
        self.assertEqual(self.rt.inspect(key)["elapsed_seconds"], 100)
        measured = self.rt.summary()["end_to_end"]
        self.assertEqual(measured["worker_waits"], 1)
        self.assertEqual(measured["worker_questions"], 1)
        self.assertEqual(measured["question_wait_seconds"], 1900)
        self.rt.publish(key, {"report": "implemented and tested"})

    def test_wrong_or_changed_answer_is_rejected(self):
        key = self.prepare("plan"); question = self.rt.question(key, "Which contract governs?")
        with self.assertRaises(runtime.Invalid): self.rt.answer(key, "wrong", "answer")
        self.rt.answer(key, question["id"], "source ticket")
        self.rt.answer(key, question["id"], "source ticket")
        with self.assertRaises(runtime.Invalid): self.rt.answer(key, question["id"], "different")

    def test_second_waiter_is_refused(self):
        key = self.prepare("plan")
        lock = self.state.parent / ("worker-" + key + ".wait.lock")
        with runtime.state_lock(lock, 1):
            with self.assertRaisesRegex(runtime.Invalid, "held by another process"):
                self.rt.wait(key, 0)
        self.assertEqual(self.rt.wait(key, 0)["status"], "running")

    def test_full_attempt_budget_is_enforced(self):
        for _ in range(2):
            key = self.prepare(); self.rt.publish(key, self.result()); self.rt.consume(key); self.rt.accept(key)
        with self.assertRaisesRegex(runtime.Invalid, "full completeness attempt budget"):
            self.prepare()

    def test_legacy_in_flight_worker_keeps_original_contract(self):
        with self.rt.transaction() as state: state["schema"] = 2
        key = self.prepare()
        self.rt.publish(key, {"report": "legacy diagnostic report"})
        self.rt.consume(key)
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])

    def test_config_verification_reuses_receipts_and_invalidates_changed_code(self):
        self.config()
        first = workflow.verify_config(self.state, self.repo, self.repo)
        second = workflow.verify_config(self.state, self.repo, self.repo)
        self.assertTrue(first["passed"] and second["passed"])
        self.assertFalse(first["receipts"][0]["reused"])
        self.assertTrue(second["receipts"][0]["reused"])
        self.code.write_text("changed\n", encoding="utf-8")
        self.assertFalse(workflow.verify_config(self.state, self.repo, self.repo)["receipts"][0]["reused"])

    def test_failed_pipeline_is_not_a_passing_receipt(self):
        config = self.config(); config["verify"]["steps"][0]["cmd"] = "false | cat"
        runtime.atomic_json(self.repo / ".claude/notion-dev.config.json", config)
        self.assertFalse(workflow.verify_config(self.state, self.repo, self.repo)["passed"])

    def test_lean_dependencies_do_not_require_external_frameworks(self):
        self.config()
        self.assertTrue(dependencies.check(self.repo, [], "lean")["passed"])
        self.assertFalse(dependencies.check(self.repo, [], "ticket")["passed"])

    def test_preflight_self_ignores_and_stops_its_marker_on_dirty_checkout(self):
        self.config()
        result = workflow.preflight(self.repo, "host:session", True)
        marker = runtime.read_json(result["marker"])
        self.assertEqual(marker["claude_session"], "host:session")
        self.assertTrue(result["stop_protection"])
        self.assertEqual(self.run_git("status", "--porcelain").stdout.decode(), "?? .claude/\n")
        self.code.write_text("user changes\n", encoding="utf-8")
        with self.assertRaises(ValueError): workflow.preflight(self.repo, "different-host", True)
        markers = [runtime.read_json(p) for p in (self.repo / ".claude/notion-dev/runs").glob("*.json")]
        self.assertTrue(any(m["state"] == "stopped" and m["claude_session"] == "different-host" for m in markers))
        self.assertEqual(self.code.read_text(), "user changes\n")

    def test_marker_updates_require_ownership(self):
        self.config(); result = workflow.preflight(self.repo, "owner", True)
        with self.assertRaises(ValueError): workflow.marker_update(result["marker"], "other", "complete")
        self.assertEqual(workflow.marker_update(result["marker"], "owner", "done", "complete")["state"], "complete")

    def test_claim_and_stopped_resume_keep_identity_and_do_not_steal_live_runs(self):
        self.config(); self.run_git("branch", "-M", "main")
        remote = self.root / "origin.git"
        subprocess.run(["git", "clone", "--bare", str(self.repo), str(remote)], check=True, capture_output=True)
        self.run_git("remote", "add", "origin", str(remote))
        pending = workflow.preflight(self.repo, "first-host", True)
        claimed = workflow.claim(self.repo, pending["marker"], "TEST-1", "A generic feature", self.state)
        self.assertTrue(Path(claimed["worktree"]).is_dir())
        self.assertFalse(Path(pending["marker"]).exists())
        self.assertEqual(runtime.read_json(claimed["marker"])["session"], "invocation-1")
        other = workflow.preflight(self.repo, "second-host", True)
        with self.assertRaisesRegex(ValueError, "owned"):
            workflow.claim(self.repo, other["marker"], "TEST-1", "different title", self.state, True)
        workflow.marker_update(claimed["marker"], "first-host", "implementation", "stopped", "explicit handoff")
        resumed = workflow.claim(self.repo, other["marker"], "TEST-1", "different title", self.state, True)
        self.assertEqual(resumed["branch"], claimed["branch"])
        marker = runtime.read_json(resumed["marker"])
        self.assertEqual(marker["session"], "invocation-1")
        self.assertEqual(marker["claude_session"], "second-host")

    def test_merged_resume_after_cleanup_rejects_live_owner_and_outstanding_worker(self):
        self.config(); pending = workflow.preflight(self.repo, "first-host", True)
        missing = self.root / "already-cleaned"
        with self.assertRaisesRegex(ValueError, "own worktree"):
            workflow.resume_pr(self.repo, pending["marker"], "TEST-1", self.state, missing, "ticket/TEST-1")
        bound = workflow.resume_pr(self.repo, pending["marker"], "TEST-1", self.state, missing, "ticket/TEST-1", True)
        other = workflow.preflight(self.repo, "second-host", True)
        with self.assertRaisesRegex(ValueError, "another session"):
            workflow.resume_pr(self.repo, other["marker"], "TEST-1", self.state, missing, "ticket/TEST-1", True)
        workflow.marker_update(bound["marker"], "first-host", "record", "stopped", "handoff")
        key = self.prepare("record")
        with self.assertRaisesRegex(ValueError, "outstanding"):
            workflow.resume_pr(self.repo, other["marker"], "TEST-1", self.state, missing, "ticket/TEST-1", True)
        self.rt.end_worker(key, "host confirmed stop", confirmed=True, user_requested=True)
        resumed = workflow.resume_pr(self.repo, other["marker"], "TEST-1", self.state, missing, "ticket/TEST-1", True)
        self.assertEqual(resumed["runtime"], str(self.state))
        self.assertEqual(runtime.read_json(resumed["marker"])["phase"], "record")

    def test_a_fresh_worktree_branches_from_the_configured_pr_target(self):
        """`prTargetBranch` is what the PR targets, so it is what work is built on."""
        value = self.config()
        value["git"]["prTargetBranch"] = "epic/TEST"
        runtime.atomic_json(self.repo / ".claude/notion-dev.config.json", value)
        self.run_git("branch", "-M", "main")
        # A commit that exists on the PR target and NOT on baseBranch: branching from
        # the wrong one is then visible as a missing file rather than as a subtle diff.
        self.run_git("checkout", "-q", "-b", "epic/TEST")
        (self.repo / "target-only.txt").write_text("only on the PR target\n", encoding="utf-8")
        self.run_git("add", "target-only.txt")
        self.run_git("commit", "-qm", "target-only change")
        self.run_git("checkout", "-q", "main")
        remote = self.root / "target-origin.git"
        subprocess.run(["git", "clone", "--bare", str(self.repo), str(remote)],
                       check=True, capture_output=True)
        self.run_git("remote", "add", "origin", str(remote))
        pending = workflow.preflight(self.repo, "host", True)
        claimed = workflow.claim(self.repo, pending["marker"], "TEST-1", "TEST-1", self.state)
        self.assertTrue((Path(claimed["worktree"]) / "target-only.txt").is_file())

    def test_claim_rejects_wrong_ticket_before_git_side_effects(self):
        self.config(); pending = workflow.preflight(self.repo, "host", True)
        with self.assertRaisesRegex(ValueError, "another ticket"):
            workflow.claim(self.repo, pending["marker"], "TEST-2", "another ticket", self.state)
        self.assertFalse((self.repo.parent / (self.repo.name + "-worktrees")).exists())

    def facts(self):
        facts = {"ticket": "TEST-1", "ticket_url": "https://example.invalid/ticket",
                 "pr_url": "https://example.invalid/pr/1", "merge_sha": "a" * 40,
                 "base": "main", "merged_at": "2026-01-01T00:00:00Z", "strategy": "squash",
                 "requirements": "requirements.json", "verification": "verification.json", "review": "review.json"}
        for name in ("requirements", "verification", "review"):
            runtime.atomic_json(self.root / facts[name], {"evidence": name})
        path = self.root / "facts.json"; runtime.atomic_json(path, facts)
        return path

    def test_record_plan_skips_confirmed_and_reconciles_unknown_without_side_effects(self):
        facts = self.facts(); first = workflow.record_plan(self.state, facts)
        op = first["operations"][0]
        self.rt.record_op(op["operation"], op["target"], "attempted", data_sha256=op["data_sha256"])
        self.assertEqual(workflow.record_plan(self.state, facts)["operations"][0]["action"], "reconcile")
        with self.assertRaisesRegex(runtime.Invalid, "blindly retried"):
            self.rt.record_op(op["operation"], op["target"], "attempted", data_sha256=op["data_sha256"])
        with self.assertRaisesRegex(runtime.Invalid, "reset to planned"):
            self.rt.record_op(op["operation"], op["target"], "planned", data_sha256=op["data_sha256"])
        self.rt.record_op(op["operation"], op["target"], "confirmed", "readback", op["data_sha256"])
        with self.assertRaisesRegex(runtime.Invalid, "terminal"):
            self.rt.record_op(op["operation"], op["target"], "failed", data_sha256=op["data_sha256"])
        self.assertEqual(workflow.record_plan(self.state, facts)["operations"][0]["action"], "skip")
        self.assertFalse(workflow.record_summary(self.state)["passed"])
        for item in first["operations"][1:]:
            self.rt.record_op(item["operation"], item["target"], "confirmed", "readback", item["data_sha256"])
        summary = workflow.record_summary(self.state)
        self.assertTrue(summary["passed"])
        self.assertEqual(set(summary["record"]), set(runtime.RECORD_FIELDS))

    def test_a_best_effort_failure_stays_visible_without_blocking_the_gate(self):
        """`record.md`: only REQUIRED operations gate `OUTCOME: resolved`."""
        facts = self.facts()
        planned = workflow.record_plan(self.state, facts)
        kinds = {item["kind"]: item for item in planned["operations"]}
        for kind, item in kinds.items():
            outcome = {"knowledge-delta": "failed", "ticket-status": "unknown-outcome"}.get(kind, "confirmed")
            self.rt.record_op(item["operation"], item["target"], outcome,
                              "readback" if outcome == "confirmed" else None, item["data_sha256"])
        summary = workflow.record_summary(self.state)
        # A REQUIRED operation left unconfirmed still blocks, so this is no blanket
        # relaxation: `ticket-status` is journalled `unknown-outcome` above.
        self.assertEqual(summary["blocking_unresolved"], [kinds["ticket-status"]["operation"]])
        self.assertFalse(summary["passed"])
        # Reconcile the required one; only the best-effort failure is left.
        self.rt.record_op(kinds["ticket-status"]["operation"], kinds["ticket-status"]["target"],
                          "confirmed", "readback", kinds["ticket-status"]["data_sha256"])
        summary = workflow.record_summary(self.state)
        # Visible in the structured field AND the human ISSUES line...
        self.assertEqual(summary["best_effort_unresolved"], [kinds["knowledge-delta"]["operation"]])
        self.assertIn(kinds["knowledge-delta"]["operation"], summary["unresolved"])
        self.assertIn(kinds["knowledge-delta"]["operation"], summary["record"]["ISSUES"])
        # ...never hidden, and it does not block the ticket or the next-task loop.
        self.assertEqual(summary["blocking_unresolved"], [])
        self.assertTrue(summary["passed"])

    def test_record_payload_drift_cannot_replay_under_old_identity(self):
        facts = self.facts(); workflow.record_plan(self.state, facts)
        changed = runtime.read_json(facts); changed["base"] = "other"
        runtime.atomic_json(facts, changed)
        with self.assertRaisesRegex(ValueError, "payload changed"):
            workflow.record_plan(self.state, facts)

    def test_record_input_uses_exact_snapshot_after_source_changes_or_disappears(self):
        facts = self.facts()
        source = self.root / "review.json"
        raw = '{"evidence":"résolu"}\r\n'.encode("utf-8")
        source.write_bytes(raw)
        plan = workflow.record_plan(self.state, facts)
        self.assertNotIn("résolu", json.dumps(plan, ensure_ascii=False))
        op = next(v for v in plan["operations"] if v["kind"] == "ticket-resolution")
        source.write_text("different evidence", encoding="utf-8")
        data = workflow.record_input(self.state, op["operation"], begin=True)
        self.assertEqual(data["data"]["review"], {"format": "utf-8", "content": raw.decode("utf-8"),
                         "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        self.assertEqual(data["action"], "execute")
        source.unlink()
        self.assertEqual(workflow.record_input(self.state, op["operation"])["data"], data["data"])
        self.assertEqual(workflow.record_input(self.state, op["operation"], begin=True)["action"], "reconcile")
        self.rt.record_op(op["operation"], op["target"], "confirmed", "readback", op["data_sha256"])
        self.assertEqual(workflow.record_input(self.state, op["operation"])["action"], "skip")
        self.assertIsNone(workflow.record_input(self.state, op["operation"])["data"])
        self.assertEqual(workflow.record_input(self.state, op["operation"], field="review")["data"],
                         {"review": data["data"]["review"]})
        source.write_bytes(b"changed after confirmation")
        with self.assertRaisesRegex(ValueError, "payload changed"):
            workflow.record_plan(self.state, facts)

    def test_payload_change_after_begin_cannot_change_the_returned_provider_data(self):
        plan = workflow.record_plan(self.state, self.facts())
        op = next(v for v in plan["operations"] if v["kind"] == "ticket-resolution")
        original = workflow.Runtime.record_op

        def mutate_after_attempt(instance, *args, **kwargs):
            result = original(instance, *args, **kwargs)
            Path(op["payload"]).write_bytes(b"{}")
            return result

        with patch.object(workflow.Runtime, "record_op", mutate_after_attempt):
            data = workflow.record_input(self.state, op["operation"], begin=True)
        self.assertEqual(json.loads(data["data"]["review"]["content"]), {"evidence": "review"})
        with self.assertRaises(ValueError): workflow.record_input(self.state, op["operation"])

    def test_missing_oversized_or_legacy_evidence_fails_closed(self):
        facts = self.facts(); value = runtime.read_json(facts)
        for field in ("requirements", "verification", "review"):
            runtime.atomic_json(facts, {**value, field: "missing.json"})
            with self.assertRaisesRegex(ValueError, "missing"):
                workflow.record_plan(self.state, facts)
        self.assertEqual(runtime.read_json(self.state)["record_journal"], [])
        source = self.root / "review.json"
        source.write_bytes(b"x" * (workflow.MAX_EVIDENCE_BYTES + 1))
        runtime.atomic_json(facts, value)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            workflow.record_plan(self.state, facts)
        self.facts()
        plan = workflow.record_plan(self.state, facts); op = plan["operations"][0]
        # Tampering cannot create an attempted entry.
        runtime.atomic_json(op["payload"], {"status": "implemented"})
        with self.assertRaisesRegex(ValueError, "legacy/invalid"):
            workflow.record_input(self.state, op["operation"], begin=True)
        self.assertFalse(any(v["outcome"] == "attempted" for v in runtime.read_json(self.state)["record_journal"]))
        with self.assertRaisesRegex(ValueError, "legacy payload"):
            workflow.record_plan(self.state, facts)

    def test_record_payload_hash_drift_is_rejected_before_attempt(self):
        plan = workflow.record_plan(self.state, self.facts()); op = plan["operations"][0]
        value = runtime.read_json(op["payload"]); value["data"]["status"] = "released"
        runtime.atomic_json(op["payload"], value)
        with self.assertRaisesRegex(ValueError, "payload changed"):
            workflow.record_input(self.state, op["operation"], begin=True)
        self.assertFalse(any(v["outcome"] == "attempted" for v in runtime.read_json(self.state)["record_journal"]))

    def test_explicit_unknown_and_embedded_evidence_do_not_crawl_nested_paths(self):
        facts = self.facts(); value = runtime.read_json(facts)
        value.update(requirements="unknown", review={"status": "unknown", "reason": "recovery"},
                     verification={"log": "missing-private-log-path", "exit_code": 0})
        runtime.atomic_json(facts, value)
        plan = workflow.record_plan(self.state, facts)
        op = next(v for v in plan["operations"] if v["kind"] == "ticket-resolution")
        data = workflow.record_input(self.state, op["operation"], field="requirements")["data"]
        self.assertEqual(data, {"requirements": {"status": "unknown"}})
        with self.assertRaisesRegex(ValueError, "inspection-only"):
            workflow.record_input(self.state, op["operation"], begin=True, field="requirements")
        self.assertEqual(workflow.record_input(self.state, op["operation"])["data"]["verification"], value["verification"])

    def test_children_inherit_only_known_parent_policy_and_stay_visible(self):
        plan = workflow.record_plan(self.state, self.facts())
        payload = self.root / "child.json"; runtime.atomic_json(payload, {"literal": "frozen input"})
        children = []
        for op in plan["operations"]:
            self.rt.record_op(op["operation"], op["target"], "confirmed", "readback", op["data_sha256"])
            child = workflow.record_child(self.state, op["operation"], "hook-01", "actual child target", payload)
            self.assertEqual(child["operation"], op["operation"] + ":child:hook-01")
            self.assertNotIn(":", Path(child["payload"]).name)
            self.rt.record_op(child["operation"], child["target"], "failed", data_sha256=child["data_sha256"])
            children.append(child)
        summary = workflow.record_summary(self.state)
        self.assertEqual(len(summary["best_effort_unresolved"]), 2)
        self.assertEqual(len(summary["blocking_unresolved"]), 5)
        for child in children:
            self.assertIn(child["operation"], summary["record"]["ISSUES"])
            if child["kind"] not in workflow.BEST_EFFORT_RECORD:
                self.rt.record_op(child["operation"], child["target"], "confirmed", "readback", child["data_sha256"])
        self.assertTrue(workflow.record_summary(self.state)["passed"])
        unknown = plan["operations"][-1]["operation"] + ":child:invalid:name"
        self.rt.record_op(unknown, "target", "failed", data_sha256="a" * 64)
        self.assertEqual(workflow.record_summary(self.state)["blocking_unresolved"], [unknown])

    def test_children_reject_ambiguous_identity_and_payload_rebinding(self):
        plan = workflow.record_plan(self.state, self.facts()); parent = plan["operations"][0]["operation"]
        payload = self.root / "child.json"; runtime.atomic_json(payload, {"literal": "intent"})
        for name in ("", "../escape", "nested:child:one", "a" * 81):
            with self.assertRaises(ValueError): workflow.record_child(self.state, parent, name, "target", payload)
        with self.assertRaises(ValueError): workflow.record_child(self.state, "unknown", "one", "target", payload)
        child = workflow.record_child(self.state, parent, "one", "target", payload)
        self.assertEqual(workflow.record_child(self.state, parent, "one", "target", payload)["operation"], child["operation"])
        self.rt.record_op(child["operation"], "target", "confirmed", "readback", child["data_sha256"])
        self.assertEqual(workflow.record_child(self.state, parent, "one", "target", payload)["action"], "skip")
        with self.assertRaises(ValueError): workflow.record_child(self.state, child["operation"], "nested", "target", payload)
        runtime.atomic_json(payload, {"literal": "new intent"})
        with self.assertRaisesRegex(ValueError, "payload changed"):
            workflow.record_child(self.state, parent, "one", "target", payload)

    def test_aggregate_runner_never_announces_success_after_failure_or_empty_suite(self):
        scripts = self.root / "runner with space" / "scripts"; scripts.mkdir(parents=True)
        runner = scripts / "run-verifications.sh"
        runner.write_bytes((ROOT / "scripts/run-verifications.sh").read_bytes())

        def run():
            return subprocess.run([runtime.bash_exe(), runner.as_posix()], capture_output=True, encoding="utf-8")

        self.assertNotEqual(run().returncode, 0)
        first = scripts / "verify-a.sh"; last = scripts / "verify-z.sh"
        first.write_bytes(b'echo first-ran\nexit 1\n')
        last.write_bytes(b'echo last-ran\nexit 0\n')
        failed = run()
        self.assertNotEqual(failed.returncode, 0)
        self.assertNotIn("harness(es) passed", failed.stdout)
        self.assertIn("first-ran", failed.stdout); self.assertIn("last-ran", failed.stdout)
        first.write_bytes(b'exit 0\n')
        passed = run()
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertIn("All 2 harness(es) passed", passed.stdout)

    def test_record_cli_freezes_and_consumes_parent_and_child_inputs(self):
        def command(*args):
            completed = subprocess.run([sys.executable, str(ROOT / "plugins/notion-dev/scripts/workflow.py"),
                *args, "--state", str(self.state)], capture_output=True, encoding="utf-8")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            return json.loads(completed.stdout)

        plan = command("record-plan", "--facts", str(self.facts()))
        parent = plan["operations"][0]["operation"]
        payload = self.root / "child.json"; runtime.atomic_json(payload, {"literal": "résolu"})
        child = command("record-child", "--parent", parent, "--name", "one", "--target", "target", "--payload", str(payload))
        value = command("record-input", "--operation", child["operation"], "--begin")
        self.assertEqual(value["data"], {"literal": "résolu"})
        self.assertEqual(value["action"], "execute")
        self.assertEqual(command("record-input", "--operation", child["operation"], "--begin")["action"], "reconcile")

    def test_decorated_agent_names_are_mapped_without_prefix_collisions(self):
        workers = [{"agent_id": name + "@session-a", "worker": name, "role": "completeness"}
                   for name in ("review", "review-p2")]
        logs = ["agent-areview-0123abcd.jsonl", "agent-areview-p2-abcd0123.jsonl"]
        result = telemetry.correlate(workers, logs)
        self.assertEqual(result["summary"]["matched_workers"], 2)
        self.assertEqual(result["attribution"][logs[0]]["worker"], "review")
        workers.append({"agent_id": "review@session-b", "worker": "other", "role": "completeness"})
        self.assertIsNone(telemetry.correlate(workers, logs)["attribution"][logs[0]])

    def test_default_entrypoints_are_small_and_route_to_shared_owners(self):
        base = ROOT / "plugins/notion-dev"
        files = [base / "commands" / (n + ".md") for n in ("ticket", "next-task", "finalize")]
        files.append(base / "skills/review-and-merge/SKILL.md")
        self.assertLess(sum(p.stat().st_size for p in files), 30000)
        ticket, next_task, finalize, review = [p.read_text(encoding="utf-8") for p in files]
        self.assertIn("Default flow: **lean**", ticket)
        self.assertNotIn("disable-model-invocation: true", ticket)
        self.assertIn("references/record.md", ticket); self.assertIn("references/record.md", finalize)
        self.assertNotIn("### 3.1 Update status", finalize)
        self.assertIn("role `completeness`", review)
        self.assertIn("next-task", next_task)
        for p in files:
            self.assertNotIn("run_in_background", p.read_text(encoding="utf-8"))

    def test_default_safety_contracts_fail_when_removed(self):
        # The old harnesses cover opt-in compatibility flows. These guard the actual
        # default, and prove each check rejects its own missing mechanism in a copy.
        contracts = {
            "commands/ticket.md": ["workflow.py\" verify", "references/record.md", "combined"],
            "commands/next-task.md": ["OUTCOME: resolved", "## Blocked by", "A stop/failure stops this loop too"],
            "commands/finalize.md": ["resume-pr", "--merged", "Missing verdicts remain unknown", "references/record.md"],
            "references/lean-intake.md": ["requirements` and `ready", "live status and ownership", "knowledge.py lock", "Never reset a resumed branch"],
            "skills/review-and-merge/SKILL.md": ["--match-head-commit", "merge-gate", "code_review", "correction-needed", "ALL GraphQL thread pages", "required checks pass", "review-findings.md", "reviewer-recovery.md"],
            "references/record.md": ["record-plan", "record-summary", "--outcome attempted", "EACH configured hook", "pull --ff-only", "LOCK_HELD: true"],
            "skills/epic-update/SKILL.md": ["references/with-followups.md", "CHILDREN", "already-complete matching entry", "query error", "Omit empty"],
            "references/review-findings.md": ["workflow.py verify", "correction-needed", "No second sweep", "A label never waives"],
            "references/reviewer-recovery.md": ["pre-call baseline", "15 minutes", "never licenses ignoring late review", "required provider approval"],
            "references/runtime.md": ["question --worker", "answer --worker", "--seconds 60", "accept --worker", "confirm termination", "--depends"]}
        # Match stable mechanisms rather than whole lines of narrative.
        candidate = self.root / "contract.md"
        command = 'fails=0; ok() { :; }; bad() { fails=$((fails + 1)); }; . "$1"; assert_has invariant "$2" "$3"; test "$fails" -eq 0'
        for name, fragments in contracts.items():
            source = (ROOT / "plugins/notion-dev" / name).read_text(encoding="utf-8")
            for fragment in fragments:
                for content, expected in ((source, 0), (source.replace(fragment, "REMOVED"), 1)):
                    candidate.write_text(content, encoding="utf-8")
                    actual = subprocess.run([runtime.bash_exe(), "-c", command, "--",
                        (ROOT / "scripts/lib/assert.sh").as_posix(), candidate.as_posix(), fragment], capture_output=True)
                    self.assertEqual(actual.returncode, expected, (name, fragment, actual.stderr.decode("utf-8")))

    def test_runtime_guards_fail_under_isolated_mutation(self):
        # Mutate in memory, in independent temporary fixtures; never restore source
        # with checkout/reset over someone's working changes.
        original_record = runtime.Runtime.record_op
        original_verify = workflow.Runtime.verify

        def unchecked_record(instance, *args, **kwargs):
            with instance.transaction() as state:
                state["schema"] = 2  # bypass new-run replay guards deliberately
            return original_record(instance, *args, **kwargs)

        def no_reuse(instance, *args, **kwargs):
            kwargs["reuse"] = False
            return original_verify(instance, *args, **kwargs)

        cases = [
            ("test_each_required_field_is_checked_at_publication",
             [patch.object(runtime, "validate_result", return_value=None)]),
            ("test_unverified_and_blocking_audits_are_honest_nonpassing_results",
             [patch.object(runtime, "audits_pass", return_value=True)]),
            ("test_record_input_uses_exact_snapshot_after_source_changes_or_disappears",
             [patch.object(workflow, "snapshot_evidence", side_effect=lambda value, field, directory: value)]),
            ("test_children_inherit_only_known_parent_policy_and_stay_visible",
             [patch.object(workflow, "record_kind", side_effect=lambda operation, kinds: kinds.get(operation))]),
            ("test_report_only_result_repairs_in_same_worker_without_redispatch",
             [patch.object(runtime, "validate_result", return_value=None),
              patch.object(runtime, "render_result", side_effect=lambda worker, result: result)]),
            ("test_second_waiter_is_refused", [patch.object(runtime, "state_lock", side_effect=lambda *args: nullcontext())]),
            ("test_record_plan_skips_confirmed_and_reconciles_unknown_without_side_effects",
             [patch.object(runtime.Runtime, "record_op", unchecked_record)]),
            ("test_config_verification_reuses_receipts_and_invalidates_changed_code",
             [patch.object(workflow.Runtime, "verify", no_reuse)]),
            ("test_new_gate_requires_parent_acceptance_and_rejects_source_drift",
             [patch.object(runtime.Runtime, "merge_gate", return_value={"passed": True})])]
        for name, mutations in cases:
            with self.subTest(mutation=name):
                case = LeanTests(name)
                try:
                    case.setUp()
                    with ExitStack() as stack:
                        for mutation in mutations: stack.enter_context(mutation)
                        with self.assertRaises(AssertionError): getattr(case, name)()
                finally:
                    case.doCleanups()


if __name__ == "__main__":
    unittest.main()
