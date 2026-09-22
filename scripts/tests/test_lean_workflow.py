"""Generic offline regressions for the lean path; no client data or provider writes."""
from contextlib import ExitStack, nullcontext
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
    result = support.RuntimeTests.result
    resolve = support.RuntimeTests.resolve

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
        for field in ("report", "requirements_complete", "requirements", "blocking_findings", "code_review"):
            with self.subTest(field=field):
                value = self.result(); del value[field]
                with self.assertRaises(runtime.Invalid):
                    self.rt.publish(key, value)
                self.assertFalse(self.rt.inspect(key)["result_available"])

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

    def test_record_payload_drift_cannot_replay_under_old_identity(self):
        facts = self.facts(); workflow.record_plan(self.state, facts)
        changed = runtime.read_json(facts); changed["base"] = "other"
        runtime.atomic_json(facts, changed)
        with self.assertRaisesRegex(ValueError, "payload changed"):
            workflow.record_plan(self.state, facts)

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
