"""Generic convergence regressions; disposable repositories, no provider writes."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_runtime as fixtures

runtime = fixtures.runtime


class ConvergenceTests(unittest.TestCase):
    # Reuse the offline repository fixture, not its test methods.
    setUp = fixtures.RuntimeTests.setUp
    run_git = fixtures.RuntimeTests.run_git
    prepare = fixtures.RuntimeTests.prepare
    result = fixtures.RuntimeTests.result
    resolve = fixtures.RuntimeTests.resolve

    def baseline(self):
        key = self.prepare()
        self.rt.publish(key, self.result())
        self.rt.consume(key)
        self.resolve(key)
        self.rt.accept(key)
        return key

    def change(self):
        self.code.write_text("original\nclarification\n", encoding="utf-8")
        self.run_git("commit", "-qam", "clarify")

    def delta(self, previous):
        receipt = self.rt.prepare("completeness", {"ticket": self.source}, self.repo,
                                  previous=previous)
        key = receipt["worker"]
        self.rt.attach(key, "agent-" + key)
        packet = runtime.read_json(receipt["packet"])
        manifest = runtime.read_json(packet["delta"]["path"])
        result = self.result()
        result["delta_review"] = {
            "previous": previous, "manifest_sha256": packet["delta"]["sha256"],
            "disposition": "sufficient", "checked_requirement_ids":
            [item["id"] for item in self.inventory["items"]]}
        return key, result, manifest

    def finish(self, key, result):
        self.rt.publish(key, result)
        self.rt.consume(key)
        self.resolve(key)
        self.rt.accept(key)
        return self.rt.merge_gate(key, self.repo)

    def test_prepare_returns_references_not_repeated_inventory(self):
        receipt = self.rt.prepare("scout", {"ticket": self.source})
        self.assertNotIn("requirements", receipt)
        packet = runtime.read_json(receipt["packet"])
        self.assertEqual(runtime.read_json(packet["requirements"]["path"])["items"],
                         self.inventory["items"])
        saved = packet["inputs"]["ticket"]["snapshot"]
        self.assertEqual(runtime.digest(saved), runtime.digest(self.source))
        self.source.write_text("changed", encoding="utf-8")
        self.assertNotEqual(runtime.digest(saved), runtime.digest(self.source))

    def test_delta_checks_changed_code_and_all_requirement_dependencies(self):
        previous = self.baseline()
        self.change()
        self.assertFalse(self.rt.merge_gate(previous, self.repo)["passed"])
        key, result, manifest = self.delta(previous)
        self.assertEqual(manifest["changed_paths"], ["code.txt"])
        self.assertIn("+clarification", Path(manifest["patch"]["path"]).read_text(encoding="utf-8"))
        self.assertEqual(set(manifest["changed_evidence_ids"]),
                         {item["id"] for item in self.inventory["items"]})
        self.assertTrue(self.finish(key, result)["passed"])
        self.code.write_text("original\nlater edit\n", encoding="utf-8")
        self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])

    def test_delta_cannot_waive_unmet_or_missing_requirements(self):
        previous = self.baseline()
        self.change()
        key, result, _ = self.delta(previous)
        result["requirements"][0]["verdict"] = "not-met"
        self.assertFalse(self.finish(key, result)["passed"])

    def test_delta_requires_independent_current_coverage_and_manifest(self):
        previous = self.baseline()
        self.change()
        key, result, _ = self.delta(previous)
        for field, value in (("manifest_sha256", "invented"),
                             ("checked_requirement_ids", ["AC1"]),
                             ("previous", "wrong-worker")):
            invalid = copy.deepcopy(result)
            invalid["delta_review"][field] = value
            with self.subTest(field=field), self.assertRaises(runtime.Invalid):
                self.rt.publish(key, invalid)
        self.assertTrue(self.finish(key, result)["passed"])

    def test_delta_can_escalate_without_hanging_or_passing(self):
        previous = self.baseline()
        key, result, _ = self.delta(previous)
        result["delta_review"]["disposition"] = "full-review-required"
        self.assertFalse(self.finish(key, result)["passed"])
        with self.assertRaisesRegex(runtime.Invalid, "full review"):
            self.delta(key)

    def test_pr_body_correction_preserves_old_claim_and_checks_new_claim(self):
        pr = self.root / "PR body.txt"
        pr.write_text("Old factual claim", encoding="utf-8")
        receipt = self.rt.prepare("completeness", {"ticket": self.source, "pr": pr}, self.repo)
        previous = receipt["worker"]
        self.rt.attach(previous, "agent-baseline")
        self.finish(previous, self.result())
        pr.write_text("Corrected factual claim", encoding="utf-8")
        receipt = self.rt.prepare("completeness", {"ticket": self.source, "pr": pr}, self.repo,
                                  previous=previous)
        packet = runtime.read_json(receipt["packet"])
        manifest = runtime.read_json(packet["delta"]["path"])
        self.assertEqual(manifest["changed_inputs"], ["pr"])
        self.assertEqual(Path(manifest["before_inputs"]["pr"]["snapshot"]).read_text(), "Old factual claim")
        self.assertEqual(Path(manifest["after_inputs"]["pr"]["snapshot"]).read_text(), "Corrected factual claim")

    def test_content_equivalent_new_head_still_needs_delta_receipt(self):
        previous = self.baseline()
        self.run_git("commit", "--allow-empty", "-qm", "new head, same tree")
        self.assertFalse(self.rt.merge_gate(previous, self.repo)["passed"])
        key, result, manifest = self.delta(previous)
        self.assertEqual(manifest["changed_paths"], [])
        self.assertTrue(self.finish(key, result)["passed"])

    def test_snapshot_tampering_is_not_carried_forward(self):
        previous = self.baseline()
        key, result, manifest = self.delta(previous)
        Path(manifest["before_inputs"]["ticket"]["snapshot"]).write_text("corrupted", encoding="utf-8")
        with self.assertRaisesRegex(runtime.Invalid, "snapshot"):
            self.rt.publish(key, result)

    def test_patch_is_a_separate_hashed_artifact_not_inline_context(self):
        previous = self.baseline()
        self.change()
        key, result, manifest = self.delta(previous)
        self.assertEqual(set(manifest["patch"]), {"path", "sha256", "bytes"})
        Path(manifest["patch"]["path"]).write_bytes(b"corrupted")
        with self.assertRaisesRegex(runtime.Invalid, "patch changed"):
            self.rt.publish(key, result)

    def test_requirement_snapshot_cannot_change_between_dispatch_and_merge(self):
        key = self.baseline()
        worker = runtime.read_json(self.state)["workers"][key]
        Path(worker["inventory_snapshot"]["path"]).write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(runtime.Invalid, "snapshot"):
            self.rt.merge_gate(key, self.repo)

    def test_unicode_spaced_paths_and_deleted_files_in_delta(self):
        path = self.repo / "café space.txt"
        path.write_text("source\n", encoding="utf-8")
        self.run_git("add", "--", path.name)
        self.run_git("commit", "-qm", "unicode fixture")
        previous = self.baseline()
        path.unlink()
        self.run_git("commit", "-qam", "remove fixture")
        _, _, manifest = self.delta(previous)
        self.assertEqual(manifest["changed_paths"], [path.name])
        self.assertIn("deleted file mode", Path(manifest["patch"]["path"]).read_text(encoding="utf-8"))

    def test_cli_packet_is_compact_utf8_json_with_lf(self):
        output = subprocess.check_output([sys.executable, str(fixtures.ROOT / "plugins/notion-dev/scripts/runtime.py"),
            "--state", str(self.state), "prepare", "--role", "implementation", "--slot", "task-a",
            "--worktree", str(self.repo), "--file", "ticket=" + str(self.source)])
        receipt = json.loads(output.decode("utf-8"))
        self.assertTrue(Path(receipt["packet"]).is_file())
        self.assertNotIn(b"\r\n", output)
        self.assertNotIn("requirements", receipt)

    def test_delta_requires_accepted_baseline_and_clean_committed_trees(self):
        previous = self.prepare()
        with self.assertRaises(runtime.Invalid):
            self.rt.prepare("completeness", {"ticket": self.source}, self.repo, previous=previous)
        self.rt.publish(previous, self.result())
        self.rt.consume(previous)
        self.rt.accept(previous)
        self.code.write_text("dirty", encoding="utf-8")
        with self.assertRaisesRegex(runtime.Invalid, "clean"):
            self.rt.prepare("completeness", {"ticket": self.source}, self.repo, previous=previous)

    def test_changed_inventory_requires_full_review(self):
        previous = self.baseline()
        self.inventory["items"][0]["evidence"] = "new decision"
        self.rt.requirements(self.source, self.inventory)
        with self.assertRaisesRegex(runtime.Invalid, "requirements"):
            self.rt.prepare("completeness", {"ticket": self.source}, self.repo, previous=previous)

    def test_two_delta_attempts_are_a_hard_bound_not_a_reset(self):
        previous = self.baseline()
        for _ in range(2):
            key, result, _ = self.delta(previous)
            self.assertTrue(self.finish(key, result)["passed"])
            previous = key
        self.assertEqual(self.rt.summary()["delta_attempts"], 2)
        self.assertEqual(self.rt.summary()["full_completeness_attempts"], 1)
        with self.assertRaisesRegex(runtime.Invalid, "delta.*budget"):
            self.rt.prepare("completeness", {"ticket": self.source}, self.repo, previous=previous)

    def test_terminated_delta_attempt_does_not_strand_the_second(self):
        # The budget counts failed attempts, so a dead first attempt must still leave a
        # usable second one. It did not: the spent worker stayed "the latest completeness
        # result", so the accepted baseline was rejected as stale and the dead worker was
        # rejected as unaccepted -- no legal value for --previous existed.
        previous = self.baseline()
        self.change()
        spent, _, _ = self.delta(previous)
        self.rt.end_worker(spent, "host died", confirmed=True, host_failed=True)
        with self.assertRaisesRegex(runtime.Invalid, "accepted"):
            self.rt.prepare("completeness", {"ticket": self.source}, self.repo, previous=spent)
        second, result, _ = self.delta(previous)
        self.assertTrue(self.finish(second, result)["passed"])
        self.assertEqual(self.rt.summary()["delta_attempts"], 2)
        with self.assertRaisesRegex(runtime.Invalid, "delta.*budget"):
            self.rt.prepare("completeness", {"ticket": self.source}, self.repo, previous=second)

    def test_a_live_delta_attempt_still_blocks_a_new_baseline(self):
        # The skip above is scoped to `terminated` precisely so this stays true: an
        # in-flight review is still the latest result and cannot be stepped around.
        previous = self.baseline()
        self.change()
        self.delta(previous)
        with self.assertRaisesRegex(runtime.Invalid, "accepted"):
            self.rt.prepare("completeness", {"ticket": self.source}, self.repo, previous=previous)

    def test_whole_branch_reviewer_blocks_merge_until_accounted_for(self):
        baseline = self.baseline()
        reviewer = self.prepare("branch-review")
        self.assertFalse(self.rt.merge_gate(baseline, self.repo)["passed"])
        self.rt.publish(reviewer, {"report": "No findings"})
        self.rt.consume(reviewer)
        self.assertFalse(self.rt.merge_gate(baseline, self.repo)["passed"])
        self.rt.accept(reviewer)
        self.assertTrue(self.rt.merge_gate(baseline, self.repo)["passed"])

    def test_parallel_implementation_slots_do_not_allow_same_slot_replacement(self):
        self.rt.prepare("implementation", {"ticket": self.source}, self.repo, slot="task-a")
        self.rt.prepare("implementation", {"ticket": self.source}, self.repo, slot="task-b")
        with self.assertRaises(runtime.Invalid):
            self.rt.prepare("implementation", {"ticket": self.source}, self.repo, slot="task-a")
        with self.assertRaises(runtime.Invalid):
            self.rt.prepare("record", {"ticket": self.source}, slot="escape")
        with self.assertRaises(runtime.Invalid):
            self.rt.prepare("implementation", {"ticket": self.source}, self.repo)

    def test_unscoped_writer_blocks_new_scoped_writer(self):
        self.rt.prepare("implementation", {"ticket": self.source}, self.repo)
        with self.assertRaises(runtime.Invalid):
            self.rt.prepare("implementation", {"ticket": self.source}, self.repo, slot="task-a")

    def test_parallel_flow_review_seats_are_distinct_not_replacement_loopholes(self):
        for role in ("scout", "plan", "local-review", "branch-review"):
            self.rt.prepare(role, {"ticket": self.source}, self.repo, slot="seat-a")
            self.rt.prepare(role, {"ticket": self.source}, self.repo, slot="seat-b")
            with self.assertRaises(runtime.Invalid):
                self.rt.prepare(role, {"ticket": self.source}, self.repo, slot="seat-a")
        with self.assertRaises(runtime.Invalid):
            self.rt.prepare("completeness", {"ticket": self.source}, self.repo, slot="escape")

    def test_resume_closes_stopped_span(self):
        self.rt.stage("stopped")
        self.clock.seconds += 10
        self.rt.stage("review")
        self.clock.seconds += 20
        self.rt.stage("merge")
        spans = self.rt.summary()["stage_spans"]
        self.assertEqual([(s["stage"], s["seconds"]) for s in spans],
                         [("stopped", 10), ("review", 20)])

    def test_delta_validator_mutation_is_detected(self):
        # In-memory mutation; never restore source with git checkout.
        previous = self.baseline()
        key, result, _ = self.delta(previous)
        result["delta_review"]["manifest_sha256"] = "invented"
        with patch.object(runtime.Runtime, "validate_delta", return_value=None):
            with self.assertRaises(AssertionError):
                with self.assertRaises(runtime.Invalid):
                    self.rt.publish(key, result)

    def test_prompt_contracts_fail_under_in_memory_mutation(self):
        review = (fixtures.ROOT / "plugins/notion-dev/skills/review-and-merge/SKILL.md").read_text(encoding="utf-8")
        candidate = self.root / "review.md"
        # Python runs natively on Windows; Git Bash needs forward-slash arguments.
        library = (fixtures.ROOT / "scripts/lib/assert.sh").as_posix()
        prefix = 'fails=0; ok() { :; }; bad() { fails=$((fails + 1)); }; . "$1"; '
        for fragment in ("The full verifier runs at most twice.",
                         "require the independent correction review below",
                         "delta attempts per invocation",
                         "exhausted budget or an unmet mandatory",
                         "changed behavior needs independent review"):
            command = prefix + 'assert_has contract "$2" "$3"; test "$fails" -eq 0'
            for text, expected in ((review, 0), (review.replace(fragment, "REMOVED"), 1)):
                candidate.write_text(text, encoding="utf-8")
                actual = subprocess.run([runtime.bash_exe(), "-c", command, "--", library,
                                         candidate.as_posix(), fragment], capture_output=True)
                self.assertEqual(actual.returncode, expected, actual.stderr.decode("utf-8"))
        order = ["**Rebase at the gate.**", "**Caller's pre-merge check**",
                 "4. **Completeness gate**", "gh pr merge <pr>"]
        command = prefix + r'''assert_order order "$2" 1 2000 rebase '^\*\*Rebase at the gate' premerge '^\*\*Caller' completeness '^4\. \*\*Completeness gate' merge '^gh pr merge <pr>'; test "$fails" -eq 0'''
        swapped = review.replace(order[0], "TEMP").replace(order[2], order[0]).replace("TEMP", order[2])
        for text, expected in ((review, 0), (swapped, 1)):
            candidate.write_text(text, encoding="utf-8")
            actual = subprocess.run([runtime.bash_exe(), "-c", command, "--", library,
                                     candidate.as_posix()], capture_output=True)
            self.assertEqual(actual.returncode, expected, actual.stderr.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
