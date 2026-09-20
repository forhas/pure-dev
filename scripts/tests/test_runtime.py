"""Offline lifecycle/telemetry regressions. No network, agents, or live providers."""
import copy
from datetime import datetime, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    path = ROOT / "plugins/notion-dev/scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


runtime = module("runtime")
telemetry = module("telemetry")
FIXTURE = json.loads((ROOT / "scripts/fixtures/runtime/sto153.json").read_text(encoding="utf-8"))


class Clock:
    def __init__(self):
        self.seconds = 0
        self.wall_adjustment = 0

    def stamp(self):
        wall = 1790000000 + self.seconds + self.wall_adjustment
        return {"wall": wall, "mono": 100000 + self.seconds,
                "utc": datetime.fromtimestamp(wall, timezone.utc).isoformat()}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="notion-runtime-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo with space"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.run_git("config", "user.email", "fixture@example.invalid")
        self.run_git("config", "user.name", "Fixture")
        self.code = self.repo / "code.txt"
        self.code.write_text("original\n", encoding="utf-8")
        self.run_git("add", "code.txt")
        self.run_git("commit", "-qm", "fixture")
        self.clock = Clock()
        self.state = self.root / "runtime" / "state.json"
        self.rt = runtime.Runtime(self.state, self.clock)
        self.rt.init("invocation-1", "STO-153")
        self.source = self.root / "ticket.md"
        with self.source.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(FIXTURE["ticket"])
        lines = FIXTURE["ticket"].splitlines()
        self.inventory = {"source_sha256": runtime.digest(self.source), "reviewed_whole_ticket": True,
                          "items": [{"id": "P1", "kind": "prerequisite", "text": lines[1],
                                     "readiness": "ready", "evidence": "fixture customer decision"}] +
                          [{"id": f"AC{i}", "kind": "acceptance", "text": text, "readiness": "ready"}
                           for i, text in enumerate(lines[3:], 1)]}
        self.rt.requirements(self.source, self.inventory)

    def run_git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True)

    def prepare(self, role="completeness"):
        result = self.rt.prepare(role, {"ticket": self.source}, self.repo)
        self.rt.attach(result["worker"], "agent-" + result["worker"])
        return result["worker"]

    def result(self):
        return {"report": "COMPLETENESS: clean\nCRITERIA-TOTAL: 4\nCRITERIA-MET: 4\nCRITERIA-NOT-MET: 0\nCRITERIA-UNVERIFIED: 0\n",
                "requirements": [{"id": item["id"], "verdict": "met", "citation": "fixture evidence"}
                                 for item in self.inventory["items"]], "blocking_findings": [],
                "requirements_complete": True}

    def complete(self):
        key = self.prepare()
        self.rt.publish(key, self.result())
        self.rt.consume(key)
        self.resolve(key)
        return key

    def resolve(self, key):
        self.rt.resolve_citations(key, [{"id": item["id"], "artifact": str(self.code), "quote": "original"}
                                       for item in self.inventory["items"]])

    def test_active_plan_not_cancelled_after_three_minutes(self):
        key = self.prepare("plan")
        self.clock.seconds = FIXTURE["plan_cancel_after_seconds"]
        self.assertEqual(self.rt.inspect(key)["status"], "running")
        with self.assertRaisesRegex(runtime.Invalid, "deadline has not elapsed"):
            self.rt.end_worker(key, "relative agent age looked stuck")

    def test_launch_ack_is_not_completed_result(self):
        key = self.prepare()
        with self.assertRaisesRegex(runtime.Invalid, "no completed result"):
            self.rt.consume(key)
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])

    def test_sto153_result_ready_before_delayed_mailbox(self):
        key = self.prepare()
        self.clock.seconds = FIXTURE["completeness_result_after_seconds"]
        self.rt.publish(key, self.result())
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])
        self.clock.seconds = FIXTURE["completeness_delivery_after_seconds"]
        # Real result beats both a delayed notification and elapsed timeout.
        self.assertEqual(self.rt.inspect(key)["status"], "result_ready")
        self.rt.consume(key)
        self.resolve(key)
        self.assertTrue(self.rt.merge_gate(key, self.repo)["passed"])
        lag = self.rt.summary()["delivery_lags"][0]["delivery_lag_seconds"]
        self.assertAlmostEqual(lag, 829.502, places=3)

    def test_result_may_precede_attach_acknowledgement(self):
        key = self.rt.prepare("plan", {"ticket": self.source}, self.repo)["worker"]
        self.rt.publish(key, {"report": "ready"})
        with self.assertRaises(runtime.Invalid):
            self.rt.consume(key)
        self.rt.attach(key, "real-host-agent")
        self.assertEqual(self.rt.inspect(key)["status"], "result_ready")
        self.rt.consume(key)

    def test_deadline_is_not_confirmation_of_cancellation(self):
        key = self.prepare("record")
        self.clock.seconds = 901
        self.assertEqual(self.rt.inspect(key)["status"], "timed_out")
        self.assertFalse(self.rt.end_worker(key, "deadline elapsed")["safe_to_replace"])
        with self.assertRaisesRegex(runtime.Invalid, "before replacement"):
            self.prepare("record")
        self.assertTrue(self.rt.end_worker(key, "host confirmed stop", confirmed=True)["safe_to_replace"])
        with self.assertRaises(runtime.Invalid):
            self.rt.publish(key, {"report": "late side effects"})

    def test_late_result_can_be_consumed_before_cancellation(self):
        key = self.prepare()
        self.clock.seconds = 901
        self.rt.inspect(key)
        self.rt.publish(key, self.result())
        self.rt.consume(key)
        self.resolve(key)
        self.assertTrue(self.rt.merge_gate(key, self.repo)["passed"])

    def test_clock_change_does_not_kill_work(self):
        key = self.prepare()
        self.clock.wall_adjustment = 3600
        observed = self.rt.inspect(key)
        self.assertTrue(observed["clock_uncertain"])
        self.assertEqual(observed["status"], "running")
        self.assertTrue(self.rt.wait(key, 60)["clock_uncertain"])

    def test_non_ac_prerequisite_blocks_readiness(self):
        self.inventory["items"][0].update(readiness="blocked", evidence="customer has not answered")
        self.rt.requirements(self.source, self.inventory)
        self.assertFalse(self.rt.ready()["passed"])
        with self.assertRaisesRegex(runtime.Invalid, "ready requirements"):
            self.prepare()

    def test_prerequisite_cannot_be_self_waived_without_evidence(self):
        self.inventory["items"][0]["evidence"] = ""
        with self.assertRaisesRegex(runtime.Invalid, "evidence"):
            self.rt.requirements(self.source, self.inventory)

    def test_source_change_same_criterion_count_invalidates_gate(self):
        key = self.complete()
        self.source.write_text(FIXTURE["ticket"].replace("stated bound", "measured bound"), encoding="utf-8")
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])

    def test_changed_prerequisite_evidence_requires_new_review(self):
        key = self.complete()
        self.inventory["items"][0]["evidence"] = "a different customer decision"
        self.rt.requirements(self.source, self.inventory)
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])

    def test_omitted_prerequisite_verdict_blocks_even_with_all_acs_met(self):
        key = self.prepare()
        result = self.result()
        result["requirements"] = result["requirements"][1:]
        self.rt.publish(key, result)
        self.rt.consume(key)
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])

    def test_unverified_and_filed_are_not_met(self):
        for verdict in ("unverified", "file", "drop", "blocked", "not-met"):
            key = self.prepare()
            result = self.result()
            result["requirements"][0]["verdict"] = verdict
            self.rt.publish(key, result)
            self.rt.consume(key)
            self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"], verdict)

    def test_degraded_or_missing_claim_check_blocks(self):
        key = self.prepare()
        result = self.result()
        result["report"] = result["report"].replace("clean", "degraded")
        del result["blocking_findings"]
        self.rt.publish(key, result)
        self.rt.consume(key)
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])

    def test_duplicate_verdict_or_null_citation_blocks(self):
        key = self.prepare()
        result = self.result()
        result["requirements"][1] = result["requirements"][0]
        result["requirements"][0]["citation"] = None
        self.rt.publish(key, result)
        self.rt.consume(key)
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])

    def test_contradictory_duplicate_report_headers_block(self):
        key = self.prepare()
        result = self.result()
        result["report"] += "CRITERIA-UNVERIFIED: 4\n"
        self.rt.publish(key, result)
        self.rt.consume(key)
        self.resolve(key)
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])

    def test_dirty_and_untracked_changes_invalidate_review(self):
        key = self.complete()
        self.code.write_text("changed\n", encoding="utf-8")
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])
        self.code.write_text("original\n", encoding="utf-8")
        (self.repo / "new-test.txt").write_text("new\n", encoding="utf-8")
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])

    def test_untracked_path_and_content_boundaries_are_unambiguous(self):
        first = self.repo / "a"
        first.write_text("bc", encoding="utf-8")
        before = runtime.revision(self.repo)
        first.unlink()
        (self.repo / "ab").write_text("c", encoding="utf-8")
        self.assertNotEqual(before, runtime.revision(self.repo))

    def test_other_pending_worker_blocks_merge(self):
        key = self.complete()
        self.prepare("plan")
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])

    def test_second_pass_requires_complete_current_head_verdicts(self):
        old = self.complete()
        self.code.write_text("original\nrepaired\n", encoding="utf-8")
        self.run_git("add", "code.txt")
        self.run_git("commit", "-qm", "repair")
        self.assertFalse(self.rt.merge_gate(old, self.repo)["passed"])
        current = self.complete()
        self.assertTrue(self.rt.merge_gate(current, self.repo)["passed"])

    def test_results_are_immutable_and_consumption_idempotent(self):
        key = self.complete()
        self.rt.publish(key, self.result())
        self.rt.consume(key)
        self.assertEqual(len(self.rt.summary()["delivery_lags"]), 1)
        with self.assertRaises(runtime.Invalid):
            self.rt.publish(key, {"report": "different"})

    def test_invalid_consumed_record_still_requires_confirmed_termination(self):
        key = self.prepare("record")
        self.rt.publish(key, {"report": "RECORD: missing mandatory keys"})
        self.rt.consume(key)
        self.assertFalse(self.rt.end_worker(key, "contract invalid", invalid_result=True)["safe_to_replace"])
        self.assertTrue(self.rt.end_worker(key, "host confirmed stop", confirmed=True, invalid_result=True)["safe_to_replace"])

    def test_parent_must_resolve_citations_not_just_consume_verdict(self):
        key = self.prepare()
        self.rt.publish(key, self.result())
        self.rt.consume(key)
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])
        with self.assertRaisesRegex(runtime.Invalid, "quote must resolve"):
            self.rt.resolve_citations(key, [{"id": "P1", "artifact": str(self.code), "quote": "invented evidence"}])

    def test_state_survives_parent_restart(self):
        key = self.prepare()
        self.rt.publish(key, self.result())
        restored = runtime.Runtime(self.state, self.clock)
        restored.init("invocation-1", "STO-153")
        restored.consume(key)
        self.resolve(key)
        self.assertTrue(restored.merge_gate(key, self.repo)["passed"])
        with self.assertRaises(runtime.Invalid):
            restored.init("different-invocation", "STO-153")

    def test_stage_clock_and_repeated_validation_are_measured(self):
        self.rt.stage("implementation")
        self.clock.seconds += 12
        self.rt.stage("review")
        self.rt.verify(self.repo, "printf 'ok\\n'")
        self.rt.verify(self.repo, "printf 'ok\\n'")
        summary = self.rt.summary()
        self.assertEqual(summary["stage_spans"], [{"stage": "implementation", "seconds": 12}])
        self.assertEqual(summary["verification_runs"], 2)
        self.assertEqual(summary["repeated_verification_signatures"], 1)

    def test_pipe_failure_is_not_reported_as_success(self):
        result = self.rt.verify(self.repo, "(exit 7) | cat")
        self.assertEqual(result["exit_code"], 7)
        self.assertTrue(Path(result["log"]).exists())
        sequence = self.rt.verify(self.repo, "(exit 9); printf 'misleading success'")
        self.assertEqual(sequence["exit_code"], 9)

    def test_yield_is_owned_one_shot_and_does_not_complete_run(self):
        key = self.prepare()
        marker = self.root / "STO-153.json"
        runtime.atomic_json(marker, {"claude_session": "session-1", "state": "running"})
        with self.assertRaises(runtime.Invalid):
            self.rt.yield_once(key, marker, "someone-else")
        result = self.rt.yield_once(key, marker, "session-1")
        self.assertTrue(Path(result["permit"]).exists())
        self.assertFalse(result["complete"])

    def test_cli_returns_nonzero_for_closed_gate(self):
        path = ROOT / "plugins/notion-dev/scripts/runtime.py"
        self.inventory["items"][0]["readiness"] = "unknown"
        self.rt.requirements(self.source, self.inventory)
        process = subprocess.run([sys.executable, str(path), "--state", str(self.state), "ready"],
                                 capture_output=True, encoding="utf-8")
        self.assertEqual(process.returncode, 1)
        self.assertFalse(json.loads(process.stdout)["passed"])
        self.assertNotIn("\r\n", process.stdout)

    def test_stop_hook_yield_does_not_spend_or_reset_counter(self):
        key = self.prepare()
        marker = self.repo / ".claude/notion-dev/runs/STO-153.json"
        runtime.atomic_json(marker, {"run": "STO-153", "phase": "review", "state": "running",
                                    "non_interactive": True, "claude_session": "session-1"})
        env = {**os.environ, "NOTION_DEV_PRIMARY_ROOT": str(self.repo), "CLAUDE_PROJECT_DIR": str(self.repo)}
        hook = ROOT / "plugins/notion-dev/hooks/stop-guard.sh"
        def stop():
            process = subprocess.run(["bash", str(hook)], input=json.dumps({"session_id": "session-1", "cwd": str(self.repo)}),
                                     capture_output=True, encoding="utf-8", env=env, check=True)
            return json.loads(process.stdout) if process.stdout.strip() else {}
        self.assertIn("Block 1 of 3", stop()["reason"])
        self.rt.yield_once(key, marker, "session-1")
        self.assertEqual(stop(), {})
        self.assertIn("Block 2 of 3", stop()["reason"])

    def test_omitted_requirement_detected_by_independent_source_check_blocks(self):
        self.inventory["items"] = self.inventory["items"][1:]
        self.rt.requirements(self.source, self.inventory)
        key = self.prepare()
        result = self.result()
        result["requirements_complete"] = False
        result["blocking_findings"] = ["HMAC-first prerequisite omitted from inventory"]
        self.rt.publish(key, result)
        self.rt.consume(key)
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="notion-telemetry-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "session.jsonl"

    def record(self, key="message-1", output=10):
        return {"type": "assistant", "timestamp": "2026-09-20T11:30:00Z",
                "message": {"id": key, "content": [], "usage": {
                    "input_tokens": 2, "cache_creation_input_tokens": 100,
                    "cache_read_input_tokens": 900, "output_tokens": output,
                    "output_tokens_details": {"thinking_tokens": 5},
                    "iterations": [{"output_tokens": output}]}}}

    def save(self, records, tail=""):
        self.path.write_text("".join(json.dumps(r) + "\n" for r in records) + tail, encoding="utf-8")

    def test_stream_records_and_thinking_not_double_counted(self):
        self.save([self.record(output=10), self.record(output=30),
                   {"type": "attachment", "attachment": {"type": "prompt_snapshot"}}])
        result = telemetry.analyze(self.path)
        self.assertEqual(result["usage"]["requests"], 1)
        self.assertEqual(result["usage"]["output_tokens"], 30)
        self.assertEqual(result["peak_input_context_tokens"], 1002)
        self.assertEqual(result["compactions"], 0)

    def test_real_compaction_and_partial_live_tail_are_explicit(self):
        self.save([self.record(), {"type": "system", "subtype": "compact_boundary"}], '{"type":')
        result = telemetry.analyze(self.path)
        self.assertEqual(result["compactions"], 1)
        self.assertTrue(result["incomplete_tail"])

    def test_disagreeing_inputs_fail_instead_of_inventing_totals(self):
        changed = copy.deepcopy(self.record())
        changed["message"]["usage"]["input_tokens"] = 3
        self.save([self.record(), changed])
        with self.assertRaisesRegex(ValueError, "disagree"):
            telemetry.analyze(self.path)

    def test_cli_includes_child_cost_once(self):
        self.save([self.record()])
        children = self.path.with_suffix("") / "subagents"
        children.mkdir(parents=True)
        (children / "agent-1.jsonl").write_text(json.dumps(self.record("child")) + "\n", encoding="utf-8")
        process = subprocess.run([sys.executable, str(ROOT / "plugins/notion-dev/scripts/telemetry.py"), str(self.path)],
                                 check=True, capture_output=True, encoding="utf-8")
        result = json.loads(process.stdout)
        self.assertEqual(result["usage"]["requests"], 2)
        self.assertEqual(result["new_input_plus_output"], 224)
        self.assertEqual(result["usage"]["cache_read_input_tokens"], 1800)


class MutationProofTests(unittest.TestCase):
    """Mutations are in-memory, never edits/resets to the user's worktree."""
    def test_false_pass_gate_is_detected(self):
        test = RuntimeTests("test_omitted_prerequisite_verdict_blocks_even_with_all_acs_met")
        with patch.object(runtime.Runtime, "merge_gate", return_value={"passed": True}):
            result = unittest.TextTestRunner(stream=io.StringIO()).run(test)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(len(result.errors), 0)

    def test_premature_cancellation_is_detected(self):
        test = RuntimeTests("test_active_plan_not_cancelled_after_three_minutes")
        with patch.object(runtime.Runtime, "end_worker", return_value={"safe_to_replace": True}):
            result = unittest.TextTestRunner(stream=io.StringIO()).run(test)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(len(result.errors), 0)

    def test_stream_double_counting_is_detected(self):
        original = telemetry.analyze
        def broken(*args, **kwargs):
            value = original(*args, **kwargs)
            value["usage"]["requests"] += 1
            return value
        with patch.object(telemetry, "analyze", side_effect=broken):
            result = unittest.TextTestRunner(stream=io.StringIO()).run(
                TelemetryTests("test_stream_records_and_thinking_not_double_counted"))
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(len(result.errors), 0)


if __name__ == "__main__":
    unittest.main()
