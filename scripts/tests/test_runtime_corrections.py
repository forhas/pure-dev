"""Pre-completeness corrective code receives an explicit independent code verdict."""
from pathlib import Path
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_runtime as fixtures
import test_runtime_convergence as convergence

runtime = fixtures.runtime


class CorrectionTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp
    run_git = fixtures.RuntimeTests.run_git
    prepare = fixtures.RuntimeTests.prepare
    result = fixtures.RuntimeTests.result
    resolve = fixtures.RuntimeTests.resolve

    def register_and_fix(self):
        obligation = self.rt.correction_needed(self.repo)
        self.code.write_text("original\nterminal fix\n", encoding="utf-8")
        self.run_git("commit", "-qam", "terminal correction")
        return obligation

    def corrected_result(self, key):
        worker = runtime.read_json(self.state)["workers"][key]
        manifest = runtime.read_json(worker["correction_manifest"]["path"])
        self.assertIn("+terminal fix", Path(manifest["patch"]["path"]).read_text(encoding="utf-8"))
        result = self.result()
        result["correction_review"] = {"id": worker["correction"]["id"],
            "manifest_sha256": worker["correction_manifest"]["sha256"],
            "verdict": "clean", "blocking_findings": [], "report": "VERDICT: CLEAN"}
        return result

    def finish(self, key, result):
        self.rt.publish(key, result)
        self.rt.consume(key)
        self.resolve(key)
        self.rt.accept(key)
        return self.rt.merge_gate(key, self.repo)

    def test_first_full_verifier_can_review_sweep_without_prior_receipt(self):
        self.register_and_fix()
        key = self.prepare()
        self.assertTrue(self.finish(key, self.corrected_result(key))["passed"])
        self.assertEqual(self.rt.summary()["full_completeness_attempts"], 1)
        self.assertEqual(self.rt.summary()["delta_attempts"], 0)

    def test_reading_full_diff_is_not_implicitly_a_code_review(self):
        self.register_and_fix()
        key = self.prepare()
        self.assertFalse(self.finish(key, self.result())["passed"])

    def test_not_clean_code_review_blocks_despite_all_requirements_met(self):
        self.register_and_fix()
        key = self.prepare()
        result = self.corrected_result(key)
        result["correction_review"].update(verdict="not-clean", blocking_findings=["regression"],
                                           report="VERDICT: NOT-CLEAN")
        self.assertFalse(self.finish(key, result)["passed"])

    def test_wrong_manifest_is_rejected(self):
        self.register_and_fix()
        key = self.prepare()
        result = self.corrected_result(key)
        result["correction_review"]["manifest_sha256"] = "wrong"
        self.assertFalse(self.finish(key, result)["passed"])

    def test_duplicate_verdict_is_rejected(self):
        self.register_and_fix()
        key = self.prepare()
        result = self.corrected_result(key)
        result["correction_review"]["report"] = "VERDICT: CLEAN\nVERDICT: NOT-CLEAN"
        self.assertFalse(self.finish(key, result)["passed"])

    def test_wrong_obligation_is_rejected(self):
        self.register_and_fix()
        key = self.prepare()
        result = self.corrected_result(key)
        result["correction_review"]["id"] = "different-obligation"
        self.assertFalse(self.finish(key, result)["passed"])

    def test_reregister_never_moves_baseline_past_fix(self):
        first = self.register_and_fix()
        self.assertEqual(self.rt.correction_needed(self.repo), first)
        key = self.prepare()
        self.assertTrue(self.finish(key, self.corrected_result(key))["passed"])

    def test_register_requires_clean_baseline(self):
        self.code.write_text("already modified", encoding="utf-8")
        with self.assertRaisesRegex(runtime.Invalid, "before.*clean"):
            self.rt.correction_needed(self.repo)

    def test_review_requires_clean_committed_correction(self):
        self.rt.correction_needed(self.repo)
        self.code.write_text("dirty correction", encoding="utf-8")
        with self.assertRaisesRegex(runtime.Invalid, "clean committed"):
            self.prepare()

    def test_new_obligation_invalidates_old_receipt_even_without_code_change(self):
        key = self.prepare()
        self.assertTrue(self.finish(key, self.result())["passed"])
        self.rt.correction_needed(self.repo)
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])

    def test_obligation_persists_on_resume(self):
        obligation = self.register_and_fix()
        self.rt = runtime.Runtime(self.state)
        state = runtime.read_json(self.state)
        self.rt.init(state["run"], state["ticket"])
        self.assertEqual(runtime.read_json(self.state)["correction"], obligation)
        key = self.prepare()
        self.assertFalse(self.finish(key, self.result())["passed"])

    def test_clean_code_verdict_never_waives_requirement_failure(self):
        self.register_and_fix()
        key = self.prepare()
        result = self.corrected_result(key)
        result["requirements"][0]["verdict"] = "not-met"
        self.assertFalse(self.finish(key, result)["passed"])

    def test_later_delta_keeps_earliest_obligation_and_both_review_contracts(self):
        obligation = self.register_and_fix()
        first = self.prepare()
        self.assertTrue(self.finish(first, self.corrected_result(first))["passed"])
        self.code.write_text("original\nterminal fix\nsecond correction\n", encoding="utf-8")
        self.run_git("commit", "-qam", "second correction")
        key, result, _ = convergence.ConvergenceTests.delta(self, first)
        result.update(correction_review=self.corrected_result(key)["correction_review"])
        worker = runtime.read_json(self.state)["workers"][key]
        self.assertEqual(worker["correction"], obligation)
        manifest = runtime.read_json(worker["correction_manifest"]["path"])
        self.assertIn("+second correction", Path(manifest["patch"]["path"]).read_text(encoding="utf-8"))
        self.assertTrue(self.finish(key, result)["passed"])
        self.assertEqual(self.rt.summary()["delta_attempts"], 1)

    def test_cli_registers_original_revision(self):
        command = [sys.executable, str(fixtures.ROOT / "plugins/notion-dev/scripts/runtime.py"),
                   "--state", str(self.state), "correction-needed", "--worktree", str(self.repo)]
        result = subprocess.run(command, check=True, capture_output=True)
        recorded = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(recorded, runtime.read_json(self.state)["correction"])
        self.assertEqual(recorded["before"], runtime.revision(self.repo))

    def test_correction_after_existing_review_invalidates_old_receipt(self):
        key = self.prepare()
        self.assertTrue(self.finish(key, self.result())["passed"])
        self.register_and_fix()
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])

    def test_correction_patch_cannot_be_altered_after_review(self):
        self.register_and_fix()
        key = self.prepare()
        self.assertTrue(self.finish(key, self.corrected_result(key))["passed"])
        worker = runtime.read_json(self.state)["workers"][key]
        manifest = runtime.read_json(worker["correction_manifest"]["path"])
        Path(manifest["patch"]["path"]).write_bytes(b"changed")
        with self.assertRaisesRegex(runtime.Invalid, "correction patch"):
            self.rt.merge_gate(key, self.repo)

    def test_false_pass_mutation_is_detected(self):
        with patch.object(runtime.Runtime, "merge_gate", return_value={"passed": True}):
            result = unittest.TestResult()
            CorrectionTests("test_reading_full_diff_is_not_implicitly_a_code_review").run(result)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(len(result.errors), 0)


if __name__ == "__main__":
    unittest.main()
