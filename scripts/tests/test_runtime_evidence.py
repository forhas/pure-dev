"""Evidence reuse, bounded delta indexes, verification receipts, publication probes.

Offline and generic: disposable git repositories, no provider calls, no agents, and
no edits outside the temporary directory each test owns.
"""
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_runtime as fixtures

runtime = fixtures.runtime


class EvidenceTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp
    run_git = fixtures.RuntimeTests.run_git
    prepare = fixtures.RuntimeTests.prepare
    result = fixtures.RuntimeTests.result

    def ids(self):
        return [item["id"] for item in self.inventory["items"]]

    def log(self, name="verify.log", text="all checks passed\n"):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def consumed(self):
        key = self.prepare()
        self.rt.publish(key, self.result())
        self.rt.consume(key)
        return key

    def cite(self, key, ids, artifact, quote="all checks passed", depends_on=None):
        return self.rt.resolve_citations(key, [
            {"id": item, "artifact": str(artifact), "quote": quote,
             "depends_on": [str(p) for p in (depends_on or [])]} for item in ids])

    # -- partial ingestion -------------------------------------------------

    def test_partial_evidence_is_recorded_and_what_is_missing_is_named(self):
        """The whole point: eight of ten citations used to persist as none of them."""
        key = self.consumed()
        evidence = self.log()
        partial = self.cite(key, self.ids()[:2], evidence)
        self.assertEqual(partial["resolved"], 2)
        self.assertEqual(partial["unresolved"], self.ids()[2:])
        self.assertFalse(partial["complete"])
        self.assertFalse(partial["passed"])
        gate = self.rt.merge_gate(key, self.repo)
        self.assertFalse(gate["passed"])
        self.assertIn("parent citation resolution is incomplete", gate["reasons"])
        # Durable across a parent restart: the second call only has to add the rest.
        restored = runtime.Runtime(self.state, self.clock)
        rest = restored.resolve_citations(key, [
            {"id": item, "artifact": str(evidence), "quote": "all checks passed"}
            for item in self.ids()[2:]])
        self.assertTrue(rest["complete"])
        self.assertEqual(rest["resolved"], len(self.ids()))
        self.assertTrue(restored.merge_gate(key, self.repo)["passed"])

    def test_re_resolution_replaces_rather_than_duplicating(self):
        key = self.consumed()
        first, second = self.log(), self.log("second.log", "a later run passed\n")
        self.cite(key, self.ids(), first)
        again = self.cite(key, self.ids()[:1], second, quote="a later run passed")
        self.assertEqual(again["replaced"], self.ids()[:1])
        self.assertEqual(again["resolved"], len(self.ids()))
        stored = runtime.read_json(self.state)["workers"][key]["citation_resolutions"]
        self.assertEqual([c["id"] for c in stored], self.ids())
        # Compare RESOLVED to RESOLVED. Windows hands `tempfile` the 8.3 short form
        # (`C:\Users\RUNNER~1\...`) while `Path.resolve()` returns the long one, so a
        # raw `str(second)` here failed on the Windows leg alone against correct code.
        self.assertEqual(stored[0]["artifact"], str(Path(second).resolve()))

    def test_citations_cannot_invent_or_repeat_a_requirement(self):
        key = self.consumed()
        evidence = self.log()
        with self.assertRaisesRegex(runtime.Invalid, "unknown requirement"):
            self.cite(key, ["AC-INVENTED"], evidence)
        with self.assertRaisesRegex(runtime.Invalid, "at most once per call"):
            self.cite(key, ["AC1", "AC1"], evidence)

    # -- dependencies ------------------------------------------------------

    def test_unchanged_log_does_not_survive_a_changed_dependency(self):
        """Byte equality of a receipt is not applicability of what it describes."""
        key = self.consumed()
        evidence = self.log()
        self.cite(key, self.ids(), evidence, depends_on=[self.code])
        self.assertTrue(self.rt.merge_gate(key, self.repo)["passed"])
        self.code.write_text("original\nchanged helper\n", encoding="utf-8")
        self.run_git("commit", "-qam", "change the helper the log exercised")
        gate = self.rt.merge_gate(key, self.repo)
        self.assertFalse(gate["passed"])
        self.assertIn("evidence dependency changed: P1", gate["reasons"])
        self.assertEqual(runtime.digest(evidence),
                         runtime.read_json(self.state)["workers"][key]["citation_resolutions"][0]["sha256"])

    def test_a_dependency_must_exist_when_it_is_declared(self):
        key = self.consumed()
        with self.assertRaisesRegex(runtime.Invalid, "dependency must be an existing file"):
            self.cite(key, self.ids()[:1], self.log(), depends_on=[self.root / "absent.txt"])

    def test_deleted_evidence_blocks_the_gate_rather_than_vanishing(self):
        key = self.consumed()
        evidence = self.log()
        self.cite(key, self.ids(), evidence)
        evidence.unlink()
        gate = self.rt.merge_gate(key, self.repo)
        self.assertFalse(gate["passed"])
        self.assertIn("resolved evidence is missing: P1", gate["reasons"])

    # -- the evidence index ------------------------------------------------

    def test_an_absent_or_null_verdict_is_blocked_not_reusable(self):
        """A verdict nobody gave is not a verdict of `met`."""
        for mutate in (lambda r: r["requirements"].pop(0),
                       lambda r: r["requirements"][0].update(verdict=None)):
            key = self.prepare()
            outcome = self.result()
            mutate(outcome)
            self.rt.publish(key, outcome)
            self.rt.consume(key)
            self.cite(key, self.ids(), self.log())
            index = self.rt.evidence(key)
            self.assertEqual(index["blocked"], [self.ids()[0]])
            self.assertNotIn(self.ids()[0], index["reuse_applicable"])
            self.assertFalse(self.rt.merge_gate(key, self.repo)["passed"])
            self.rt.end_worker(key, "contract invalid", confirmed=True, invalid_result=True)

    def test_evidence_index_separates_current_stale_blocked_and_unresolved(self):
        key = self.prepare()
        outcome = self.result()
        outcome["requirements"][1]["verdict"] = "unverified"
        self.rt.publish(key, outcome)
        self.rt.consume(key)
        stable, volatile = self.log(), self.log("volatile.log", "all checks passed\n")
        self.cite(key, self.ids()[:1], stable)
        self.cite(key, self.ids()[1:2], volatile)
        self.cite(key, self.ids()[2:3], volatile, depends_on=[self.code])
        self.code.write_text("original\nedited\n", encoding="utf-8")
        index = self.rt.evidence(key)
        self.assertEqual(index["reuse_applicable"], [self.ids()[0]])
        self.assertEqual(index["blocked"], [self.ids()[1]])
        self.assertEqual(index["recheck_needed"], [self.ids()[2]])
        self.assertEqual(index["unresolved"], self.ids()[3:])
        self.assertFalse(index["complete"])
        self.assertEqual(index["count"], len(self.ids()))


class DeltaIndexTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp
    run_git = fixtures.RuntimeTests.run_git
    prepare = fixtures.RuntimeTests.prepare
    result = fixtures.RuntimeTests.result

    def ids(self):
        return [item["id"] for item in self.inventory["items"]]

    def baseline(self, artifact=None, depends_on=None):
        key = self.prepare()
        self.rt.publish(key, self.result())
        self.rt.consume(key)
        artifact = artifact or self.code
        self.rt.resolve_citations(key, [
            {"id": item, "artifact": str(artifact), "quote": "original",
             "depends_on": [str(p) for p in (depends_on or [])]} for item in self.ids()])
        self.rt.accept(key)
        return key

    def delta(self, previous):
        receipt = self.rt.prepare("completeness", {"ticket": self.source}, self.repo,
                                  previous=previous)
        packet = runtime.read_json(receipt["packet"])
        return receipt["worker"], runtime.read_json(packet["delta"]["path"])

    def written_bytes(self, worker):
        """Size of `delta.json` as it was actually written — the reviewer's read cost."""
        return Path(runtime.read_json(self.state)["workers"][worker]["delta"]["path"]).stat().st_size

    def test_the_index_references_the_previous_report_instead_of_inlining_it(self):
        """A 'delta' that starts by re-reading the whole prior report is a full review."""
        long_report = self.result()
        long_report["report"] += "EVIDENCE: " + ("x" * 40000) + "\n"
        key = self.prepare()
        self.rt.publish(key, long_report)
        self.rt.consume(key)
        self.rt.resolve_citations(key, [{"id": i, "artifact": str(self.code), "quote": "original"}
                                        for i in self.ids()])
        self.rt.accept(key)
        self.code.write_text("original\nrepair\n", encoding="utf-8")
        self.run_git("commit", "-qam", "repair")
        delta_worker, manifest = self.delta(key)
        self.assertNotIn("previous_result", manifest)
        self.assertNotIn("previous_citations", manifest)
        self.assertLessEqual(manifest["index_bytes"], runtime.INDEX_BYTES)
        self.assertTrue(manifest["within_budget"])
        self.assertTrue(manifest["complete"])
        self.assertEqual(self.written_bytes(delta_worker), manifest["index_bytes"])
        self.assertGreater(manifest["previous_report"]["bytes"], 40000)
        self.assertEqual(runtime.digest(runtime.Runtime.ref_path(manifest, manifest["previous_report"])),
                         manifest["previous_report"]["sha256"])

    def test_the_index_classifies_evidence_for_reuse_instead_of_dumping_it(self):
        evidence = self.root / "verify.log"
        evidence.write_text("original\n", encoding="utf-8")
        key = self.prepare()
        self.rt.publish(key, self.result())
        self.rt.consume(key)
        # One requirement's evidence depends on the code this change touches; the rest
        # cite a log outside the worktree that the change cannot have affected.
        self.rt.resolve_citations(key, [
            {"id": item, "artifact": str(evidence), "quote": "original",
             "depends_on": [str(self.code)] if item == "AC1" else []} for item in self.ids()])
        self.rt.accept(key)
        self.code.write_text("original\nrepair\n", encoding="utf-8")
        self.run_git("commit", "-qam", "repair")
        _, manifest = self.delta(key)
        self.assertEqual(manifest["recheck_needed"], ["AC1"])
        self.assertEqual(sorted(manifest["reuse_applicable"]),
                         sorted(i for i in self.ids() if i != "AC1"))
        self.assertEqual(manifest["evidence"]["reuse_applicable"], len(self.ids()) - 1)
        self.assertEqual(manifest["changed_paths"], ["code.txt"])

    def test_evidence_recorded_against_the_new_tree_is_not_a_baseline_receipt(self):
        """The cited bytes match the CURRENT tree, so only the diff exposes the reuse."""
        key = self.baseline()
        self.code.write_text("original\nrepair\n", encoding="utf-8")
        self.run_git("commit", "-qam", "repair")
        # Re-cited after the change: hashes now agree with the post-change tree.
        self.rt.resolve_citations(key, [{"id": i, "artifact": str(self.code), "quote": "repair"}
                                        for i in self.ids()])
        _, manifest = self.delta(key)
        self.assertEqual(manifest["reuse_applicable"], [])
        self.assertEqual(sorted(manifest["recheck_needed"]), sorted(self.ids()))
        records = runtime.read_json(
            runtime.Runtime.ref_path(manifest, manifest["evidence"]["index"]))
        self.assertIn("inside this change's diff", " ".join(records[0]["reasons"]))

    def test_unresolved_baseline_items_are_carried_forward_not_silently_dropped(self):
        key = self.prepare()
        self.rt.publish(key, self.result())
        self.rt.consume(key)
        self.rt.resolve_citations(key, [{"id": self.ids()[0], "artifact": str(self.code),
                                         "quote": "original"}])
        self.rt.accept(key)
        _, manifest = self.delta(key)
        self.assertEqual(manifest["unresolved"], self.ids()[1:])
        self.assertEqual(manifest["evidence"]["unresolved"], len(self.ids()) - 1)

    def test_an_oversized_section_is_paged_out_and_says_so(self):
        for index in range(120):
            (self.repo / ("file-%03d.txt" % index)).write_text("x\n", encoding="utf-8")
        self.run_git("add", "-A")
        self.run_git("commit", "-qm", "wide change")
        key = self.baseline()
        (self.repo / "file-000.txt").write_text("y\n", encoding="utf-8")
        for index in range(120, 260):
            (self.repo / ("file-%03d.txt" % index)).write_text("x\n", encoding="utf-8")
        self.run_git("add", "-A")
        self.run_git("commit", "-qm", "wider change")
        worker, manifest = self.delta(key)
        sections = manifest["sections"]
        self.assertEqual(sections["counts"]["changed_paths"], 141)
        self.assertEqual(sections["incomplete"], ["changed_paths"])
        self.assertLessEqual(len(manifest["changed_paths"]), runtime.PAGE_ITEMS)
        self.assertGreater(len(manifest["changed_paths"]), 0)
        self.assertFalse(manifest["complete"])
        # The file on disk, not a compact form nobody writes: the number the budget
        # reported and the bytes a reviewer actually reads must be the same number.
        self.assertLessEqual(manifest["index_bytes"], runtime.INDEX_BYTES)
        self.assertEqual(self.written_bytes(worker), manifest["index_bytes"])
        self.assertLessEqual(self.written_bytes(worker), runtime.INDEX_BYTES)
        # The small sections keep their full detail; only the oversized one is paged.
        self.assertEqual(manifest["changed_inputs"], [])
        pages = -(-141 // sections["page_items"])
        last = self.rt.section(worker, "changed_paths", page=pages)
        self.assertTrue(last["complete"])
        self.assertEqual((last["count"], last["pages"]), (141, pages))
        whole = []
        for page in range(1, pages + 1):
            whole += self.rt.section(worker, "changed_paths", page=page)["items"]
        self.assertEqual(len(whole), 141)
        # The inlined preview is a prefix of page 1, never a sample from the middle.
        self.assertEqual(whole[:len(manifest["changed_paths"])], manifest["changed_paths"])
        with self.assertRaisesRegex(runtime.Invalid, "past the end"):
            self.rt.section(worker, "changed_paths", page=pages + 1)
        with self.assertRaisesRegex(runtime.Invalid, "unknown delta section"):
            self.rt.section(worker, "invented", page=1)

    def wide_delta(self):
        """A baseline plus a change wide enough that the index must page a section."""
        for index in range(120):
            (self.repo / ("file-%03d.txt" % index)).write_text("x\n", encoding="utf-8")
        self.run_git("add", "-A")
        self.run_git("commit", "-qm", "wide change")
        previous = self.baseline()
        (self.repo / "file-000.txt").write_text("y\n", encoding="utf-8")
        for index in range(120, 260):
            (self.repo / ("file-%03d.txt" % index)).write_text("x\n", encoding="utf-8")
        self.run_git("add", "-A")
        self.run_git("commit", "-qm", "wider change")
        worker, manifest = self.delta(previous)
        self.rt.attach(worker, "agent-delta")
        outcome = self.result()
        packet = runtime.read_json(runtime.read_json(self.state)["workers"][worker]["packet"])
        outcome["delta_review"] = {"previous": previous, "manifest_sha256": packet["delta"]["sha256"],
                                   "disposition": "sufficient", "checked_requirement_ids": self.ids()}
        return worker, manifest, outcome

    def test_a_sufficient_delta_cannot_pass_on_a_section_it_never_paged(self):
        """The protocol's unread-page rule was prose with an event and no gate."""
        worker, manifest, outcome = self.wide_delta()
        self.assertEqual(manifest["sections"]["incomplete"], ["changed_paths"])
        self.rt.publish(worker, outcome)
        self.rt.consume(worker)
        self.rt.resolve_citations(worker, [{"id": i, "artifact": str(self.code), "quote": "original"}
                                           for i in self.ids()])
        self.rt.accept(worker)
        gate = self.rt.merge_gate(worker, self.repo)
        self.assertFalse(gate["passed"])
        self.assertIn("delta section was never retrieved in full: changed_paths", gate["reasons"])
        # A partial read is still not a read.
        pages = -(-manifest["sections"]["counts"]["changed_paths"] //
                  manifest["sections"]["page_items"])
        self.rt.section(worker, "changed_paths", page=1)
        self.assertFalse(self.rt.merge_gate(worker, self.repo)["passed"])
        for page in range(2, pages + 1):
            self.rt.section(worker, "changed_paths", page=page)
        self.assertTrue(self.rt.merge_gate(worker, self.repo)["passed"])

    def test_an_honest_escalation_needs_no_complete_input(self):
        """`full-review-required` says the scope was NOT bounded; it claims nothing."""
        worker, _, outcome = self.wide_delta()
        outcome["delta_review"]["disposition"] = "full-review-required"
        self.rt.publish(worker, outcome)
        self.rt.consume(worker)
        gate = self.rt.merge_gate(worker, self.repo)
        self.assertIn("delta reviewer requires full review", gate["reasons"])
        self.assertEqual([r for r in gate["reasons"] if "never retrieved in full" in r], [])

    def test_a_complete_index_requires_no_paging_at_all(self):
        previous = self.baseline()
        self.code.write_text("original\nrepair\n", encoding="utf-8")
        self.run_git("commit", "-qam", "repair")
        worker, manifest = self.delta(previous)
        self.assertTrue(manifest["complete"])
        self.assertEqual(runtime.Runtime.unread_delta_sections(
            runtime.read_json(self.state)["workers"][worker]), [])

    def test_every_referenced_artifact_is_hash_bound_at_publication(self):
        key = self.baseline()
        self.code.write_text("original\nrepair\n", encoding="utf-8")
        self.run_git("commit", "-qam", "repair")
        worker, manifest = self.delta(key)
        self.rt.attach(worker, "agent-delta")
        outcome = self.result()
        packet = runtime.read_json(runtime.read_json(self.state)["workers"][worker]["packet"])
        outcome["delta_review"] = {"previous": key, "manifest_sha256": packet["delta"]["sha256"],
                                   "disposition": "sufficient", "checked_requirement_ids": self.ids()}
        for reference, message in (("patch", "delta patch changed"),
                                   ("inputs", "delta input index changed"),
                                   ("sections_file", "delta sections changed"),
                                   ("previous_report", "previous report changed")):
            path = Path(runtime.Runtime.ref_path(manifest, manifest[reference]))
            original = path.read_bytes()
            path.write_bytes(b"corrupted")
            with self.subTest(reference=reference), \
                    self.assertRaisesRegex(runtime.Invalid, message):
                self.rt.publish(worker, outcome)
            path.write_bytes(original)
        index = Path(runtime.Runtime.ref_path(manifest, manifest["evidence"]["index"]))
        original = index.read_bytes()
        index.write_bytes(b"[]")
        with self.assertRaisesRegex(runtime.Invalid, "evidence index changed"):
            self.rt.publish(worker, outcome)
        index.write_bytes(original)
        self.assertEqual(self.rt.publish(worker, outcome)["status"], "result_ready")


class VerificationIndexTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp
    run_git = fixtures.RuntimeTests.run_git

    def test_receipts_are_indexed_with_why_each_is_or_is_not_reusable(self):
        first = self.rt.verify(self.repo, "printf 'ok\\n'")
        self.assertFalse(first["reused"])
        self.assertEqual(runtime.digest(first["log"]), first["log_sha256"])
        index = self.rt.verifications(self.repo)
        self.assertEqual(index["count"], 1)
        self.assertTrue(index["verifications"][0]["applicable"])
        self.assertEqual(index["verifications"][0]["reasons"], [])
        self.code.write_text("original\nmoved on\n", encoding="utf-8")
        stale = self.rt.verifications(self.repo)["verifications"][0]
        self.assertFalse(stale["applicable"])
        self.assertIn("revision changed since this receipt", stale["reasons"])

    def test_reuse_returns_the_receipt_only_while_it_still_applies(self):
        first = self.rt.verify(self.repo, "printf 'ok\\n'", reuse=True)
        second = self.rt.verify(self.repo, "printf 'ok\\n'", reuse=True)
        self.assertTrue(second["reused"])
        self.assertEqual(second["verification"], first["verification"])
        self.assertEqual(self.rt.summary()["end_to_end"]["verification_reuses"], 1)
        self.code.write_text("original\nmoved on\n", encoding="utf-8")
        third = self.rt.verify(self.repo, "printf 'ok\\n'", reuse=True)
        self.assertFalse(third["reused"])
        self.assertNotEqual(third["verification"], first["verification"])

    def test_a_failure_and_a_tampered_log_are_never_reused(self):
        failed = self.rt.verify(self.repo, "exit 3", reuse=True)
        self.assertEqual(failed["exit_code"], 3)
        self.assertFalse(self.rt.verify(self.repo, "exit 3", reuse=True)["reused"])
        passing = self.rt.verify(self.repo, "printf 'ok\\n'", reuse=True)
        Path(passing["log"]).write_text("invented success\n", encoding="utf-8")
        self.assertFalse(self.rt.verify(self.repo, "printf 'ok\\n'", reuse=True)["reused"])
        tampered = [v for v in self.rt.verifications(self.repo)["verifications"]
                    if v["verification"] == passing["verification"]]
        self.assertIn("verification log changed after the run", tampered[0]["reasons"])

    def test_a_receipt_from_another_worktree_at_the_same_commit_is_not_reused(self):
        """Identical fingerprints, different trees: ignored files are outside the hash."""
        first = self.rt.verify(self.repo, "printf 'ok\\n'", reuse=True)
        other = self.root / "second worktree"
        self.run_git("worktree", "add", "--detach", str(other), "HEAD")
        self.addCleanup(lambda: subprocess.run(
            ["git", "-C", str(self.repo), "worktree", "remove", "--force", str(other)],
            capture_output=True))
        self.assertEqual(runtime.revision(other)["fingerprint"],
                         runtime.revision(self.repo)["fingerprint"])
        elsewhere = self.rt.verify(other, "printf 'ok\\n'", reuse=True)
        self.assertFalse(elsewhere["reused"])
        self.assertNotEqual(elsewhere["verification"], first["verification"])
        self.assertIn("receipt was produced in a different worktree",
                      self.rt.verifications(other)["verifications"][0]["reasons"])
        # And the original worktree still reuses its own receipt.
        self.assertTrue(self.rt.verify(self.repo, "printf 'ok\\n'", reuse=True)["reused"])

    def test_a_changed_ignored_input_invalidates_a_receipt_the_fingerprint_cannot_see(self):
        """`revision` excludes ignored files, so the fingerprint alone never notices."""
        (self.repo / ".gitignore").write_text("ignored-config\n", encoding="utf-8")
        self.run_git("add", ".gitignore")
        self.run_git("commit", "-qm", "ignore the config")
        config = self.repo / "ignored-config"
        config.write_text("pass\n", encoding="utf-8")
        command = 'test "$(cat ignored-config)" = pass'
        first = self.rt.verify(self.repo, command, reuse=True, depends=[config])
        self.assertEqual(first["exit_code"], 0)
        before = runtime.revision(self.repo)["fingerprint"]
        config.write_text("fail\n", encoding="utf-8")
        self.assertEqual(runtime.revision(self.repo)["fingerprint"], before)
        rerun = self.rt.verify(self.repo, command, reuse=True, depends=[config])
        self.assertFalse(rerun["reused"])
        self.assertEqual(rerun["exit_code"], 1)
        self.assertIn("declared input changed: " + str(config),
                      self.rt.verifications(self.repo)["verifications"][0]["reasons"])

    def test_reuse_requires_the_same_declared_input_set(self):
        extra = self.root / "extra.txt"
        extra.write_text("x\n", encoding="utf-8")
        undeclared = self.rt.verify(self.repo, "printf 'ok\\n'", reuse=True)
        self.assertFalse(undeclared["reused"])
        # A caller that now declares an input must not be served a receipt earned
        # without it: that receipt answered a narrower question.
        widened = self.rt.verify(self.repo, "printf 'ok\\n'", reuse=True, depends=[extra])
        self.assertFalse(widened["reused"])
        self.assertTrue(self.rt.verify(self.repo, "printf 'ok\\n'", reuse=True,
                                       depends=[extra])["reused"])
        # Dropping the declaration goes back to the receipt that answered THAT question,
        # never to the widened one — matching is by set, not by recency.
        again = self.rt.verify(self.repo, "printf 'ok\\n'", reuse=True)
        self.assertTrue(again["reused"])
        self.assertEqual(again["verification"], undeclared["verification"])
        self.assertNotEqual(again["verification"], widened["verification"])
        with self.assertRaisesRegex(runtime.Invalid, "declared verification input"):
            self.rt.verify(self.repo, "printf 'ok\\n'", depends=[self.root / "absent"])

    def test_the_index_never_advertises_a_failed_receipt_as_reusable(self):
        """`applicable` and `reusable` are different questions; the index reports both."""
        failed = self.rt.verify(self.repo, "exit 3")
        entry = self.rt.verifications(self.repo)["verifications"][0]
        self.assertEqual(entry["verification"], failed["verification"])
        self.assertTrue(entry["applicable"])      # intact, current evidence of a failure
        self.assertEqual(entry["reasons"], [])
        self.assertFalse(entry["reusable"])       # ...but never a pass to stand in for
        self.assertIn("the command failed when this receipt was produced",
                      entry["reuse_reasons"])
        self.assertFalse(self.rt.verify(self.repo, "exit 3", reuse=True)["reused"])

    def test_a_command_that_modified_the_tree_is_not_a_reusable_receipt(self):
        receipt = self.rt.verify(self.repo, "printf 'x\\n' >> code.txt")
        self.assertTrue(receipt["changed_during_verification"])
        self.run_git("commit", "-qam", "absorb")
        self.assertIn("the command modified the tree it verified",
                      self.rt.verifications(self.repo)["verifications"][0]["reasons"])

    def test_the_environment_signature_records_the_toolchain_not_the_environment(self):
        signature = runtime.environment_signature()
        self.assertEqual(set(signature), {"signature", "os_name", "platform", "python", "shell"})
        receipt = self.rt.verify(self.repo, "printf 'ok\\n'")
        self.assertEqual(receipt["environment"]["signature"], signature["signature"])
        with patch.object(runtime.sys, "platform", "some-other-host"):
            self.assertIn("toolchain signature changed or unrecorded",
                          self.rt.verifications(self.repo)["verifications"][0]["reasons"])
            self.assertFalse(self.rt.verify(self.repo, "printf 'ok\\n'", reuse=True)["reused"])


class ProbeAndJournalTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp
    run_git = fixtures.RuntimeTests.run_git

    def probe_worker(self):
        key = self.rt.prepare("probe", {"ticket": self.source})["worker"]
        self.rt.attach(key, "agent-probe-" + key)
        return key

    def payload(self, text):
        # `newline=""`, because the probe compares BYTES on purpose. Python's default
        # text mode rewrites "\n" as "\r\n" on Windows, so the expectation file would
        # differ from the payload the worker published and every delivery would read as
        # `mangled` -- a red Windows leg against a correct probe. The expectation file
        # is written LF, like everything else this plugin generates.
        path = self.root / "expected.txt"
        with path.open("w", encoding="utf-8", newline="") as stream:
            stream.write(text)
        return path

    def test_publication_probe_distinguishes_delivered_truncated_and_mangled(self):
        text = "héllo — line one\nline two\n" * 200
        expected = self.payload(text)
        for payload, finding in ((text, "delivered"), (text[:100], "truncated"),
                                 ("something else entirely", "mangled")):
            key = self.probe_worker()
            self.rt.publish(key, {"report": "probe", "payload": payload})
            outcome = self.rt.probe(key, expected)
            self.assertEqual(outcome["finding"], finding, payload[:20])
            self.assertEqual(outcome["passed"], finding == "delivered")
            self.assertEqual(outcome["expected_bytes"], len(text.encode("utf-8")))
            self.rt.consume(key)
            self.rt.accept(key)

    def test_delivery_lag_measures_publication_to_observation_not_the_agent_run(self):
        key = self.probe_worker()
        self.clock.seconds += 300          # the worker's own execution time
        self.rt.publish(key, {"report": "probe", "payload": "x"})
        self.clock.seconds += 7            # the mailbox delay this probe exists to measure
        outcome = self.rt.probe(key, self.payload("x"))
        self.assertEqual(outcome["finding"], "delivered")
        self.assertEqual(outcome["delivery_lag_seconds"], 7)

    def test_a_probe_with_no_delivered_result_fails_rather_than_passing_quietly(self):
        key = self.probe_worker()
        outcome = self.rt.probe(key, self.payload("anything"))
        self.assertEqual(outcome["finding"], "missing")
        self.assertFalse(outcome["passed"])
        self.rt.publish(key, {"report": "acknowledged, no payload"})
        self.assertEqual(self.rt.probe(key, self.payload("anything"))["finding"], "mangled")

    def test_probe_refuses_a_worker_of_another_role(self):
        key = self.rt.prepare("record", {"ticket": self.source})["worker"]
        self.rt.publish(key, {"report": "RECORD: ok", "payload": "x"})
        with self.assertRaisesRegex(runtime.Invalid, "probe role"):
            self.rt.probe(key, self.payload("x"))

    def test_record_journal_keeps_an_unconfirmed_operation_visible(self):
        self.rt.record_op("create-follow-up", "tickets", "attempted")
        self.rt.record_op("status-in-progress", "ticket", "confirmed", provider_id="page-1")
        self.rt.record_op("create-follow-up", "tickets", "unknown-outcome")
        end = self.rt.summary()["end_to_end"]
        # Attempt counts stay per entry; the open list is per operation.
        self.assertEqual(end["record_operations"],
                         {"attempted": 1, "confirmed": 1, "unknown-outcome": 1})
        self.assertEqual(end["unconfirmed_record_operations"], ["create-follow-up"])
        with self.assertRaisesRegex(runtime.Invalid, "invalid record operation outcome"):
            self.rt.record_op("create-follow-up", "tickets", "done")

    def test_a_confirmed_operation_leaves_the_open_list_and_a_retry_returns_to_it(self):
        """The ordinary lifecycle used to report itself as permanently unrecorded."""
        self.rt.record_op("create-follow-up", "tickets", "attempted")
        self.assertEqual(self.rt.summary()["end_to_end"]["unconfirmed_record_operations"],
                         ["create-follow-up"])
        self.rt.record_op("create-follow-up", "tickets", "confirmed", provider_id="page-9")
        self.assertEqual(self.rt.summary()["end_to_end"]["unconfirmed_record_operations"], [])
        # A later attempt on the same logical operation reopens it — latest entry wins in
        # both directions, so this is not a one-way "once confirmed, always confirmed".
        self.rt.record_op("create-follow-up", "tickets", "unknown-outcome")
        end = self.rt.summary()["end_to_end"]
        self.assertEqual(end["unconfirmed_record_operations"], ["create-follow-up"])
        self.assertEqual(end["record_operations"],
                         {"attempted": 1, "confirmed": 1, "unknown-outcome": 1})

    def test_correction_causes_are_recorded_without_replacing_the_baseline(self):
        first = self.rt.correction_needed(self.repo, "reviewer found a false claim")
        self.code.write_text("original\nfix\n", encoding="utf-8")
        self.run_git("commit", "-qam", "fix")
        again = self.rt.correction_needed(self.repo, "second sweep finding")
        self.assertEqual(again["id"], first["id"])
        self.assertEqual(again["before"], first["before"])
        self.assertEqual(self.rt.summary()["end_to_end"]["correction_causes"],
                         ["reviewer found a false claim", "second sweep finding"])

    def test_the_end_to_end_summary_names_its_own_scope(self):
        end = self.rt.summary()["end_to_end"]
        self.assertIn("unknown, not zero", end["scope"])
        self.assertEqual(end["schema"], runtime.SCHEMA)


class SchemaCompatibilityTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp
    run_git = fixtures.RuntimeTests.run_git
    prepare = fixtures.RuntimeTests.prepare
    result = fixtures.RuntimeTests.result

    def test_a_live_schema_1_run_is_read_without_being_rewritten_to_schema_2(self):
        state = runtime.read_json(self.state)
        state["schema"] = 1
        for key in ("verifications", "record_journal"):
            state.pop(key, None)
        runtime.atomic_json(self.state, state)
        self.assertEqual(self.rt.summary()["end_to_end"]["schema"], 1)
        self.rt.verify(self.repo, "printf 'ok\\n'")
        self.assertEqual(runtime.read_json(self.state)["schema"], 1)
        self.assertEqual(self.rt.verifications(self.repo)["count"], 1)

    def test_an_unknown_schema_still_fails_closed(self):
        state = runtime.read_json(self.state)
        state["schema"] = 99
        runtime.atomic_json(self.state, state)
        with self.assertRaisesRegex(runtime.Invalid, "unsupported runtime schema"):
            self.rt.summary()


class CommandLineTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp
    run_git = fixtures.RuntimeTests.run_git
    prepare = fixtures.RuntimeTests.prepare
    result = fixtures.RuntimeTests.result

    def run_cli(self, *args):
        process = subprocess.run(
            [sys.executable, str(fixtures.ROOT / "plugins/notion-dev/scripts/runtime.py"),
             "--state", str(self.state), *args], capture_output=True)
        return process.returncode, process.stdout

    def test_incomplete_evidence_exits_nonzero_while_still_persisting_what_it_got(self):
        key = self.prepare()
        self.rt.publish(key, self.result())
        self.rt.consume(key)
        citations = self.root / "citations.json"
        runtime.atomic_json(citations, [{"id": "P1", "artifact": str(self.code),
                                         "quote": "original"}])
        code, out = self.run_cli("resolve-citations", "--worker", key, "--citations", str(citations))
        self.assertEqual(code, 1)
        self.assertNotIn(b"\r\n", out)
        body = json.loads(out.decode("utf-8"))
        self.assertEqual(body["resolved"], 1)
        self.assertEqual(body["unresolved"], [i["id"] for i in self.inventory["items"]][1:])
        self.assertEqual(self.rt.evidence(key)["reuse_applicable"], ["P1"])
        code, out = self.run_cli("evidence", "--worker", key)
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(out.decode("utf-8"))["complete"])

    def test_verifications_and_record_op_round_trip_through_the_cli(self):
        code, _ = self.run_cli("verify", "--worktree", str(self.repo),
                               "--shell-command", "printf 'ok\\n'", "--reuse")
        self.assertEqual(code, 0)
        code, out = self.run_cli("verify", "--worktree", str(self.repo),
                                 "--shell-command", "printf 'ok\\n'", "--reuse")
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out.decode("utf-8"))["reused"])
        code, out = self.run_cli("verifications", "--worktree", str(self.repo))
        self.assertEqual(code, 0)
        self.assertNotIn(b"\r\n", out)
        self.assertEqual(json.loads(out.decode("utf-8"))["count"], 1)
        code, out = self.run_cli("record-op", "--operation", "create", "--target", "tickets",
                                 "--outcome", "unknown-outcome")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.decode("utf-8"))["outcome"], "unknown-outcome")
        code, _ = self.run_cli("record-op", "--operation", "create", "--target", "tickets",
                               "--outcome", "invented")
        self.assertEqual(code, 2)


class MutationProofTests(unittest.TestCase):
    """Each new gate is shown to fail when the mechanism it guards is removed.

    In-memory patches only; nothing under the user's worktree is edited or restored.
    """

    @staticmethod
    def run_one(case, name):
        return unittest.TextTestRunner(stream=io.StringIO()).run(case(name))

    def test_dropping_the_dependency_check_is_detected(self):
        original = runtime.Runtime.merge_gate

        def ignoring_dependencies(self, key, worktree):
            outcome = original(self, key, worktree)
            outcome["reasons"] = [r for r in outcome["reasons"] if "dependency" not in r]
            outcome["passed"] = not outcome["reasons"]
            return outcome

        with patch.object(runtime.Runtime, "merge_gate", ignoring_dependencies):
            broken = self.run_one(EvidenceTests,
                                  "test_unchanged_log_does_not_survive_a_changed_dependency")
        self.assertEqual(len(broken.failures), 1)
        self.assertEqual(len(broken.errors), 0)

    def test_an_unbounded_index_is_detected(self):
        def unbounded(index, sections, budget=runtime.INDEX_BYTES, page=runtime.PAGE_ITEMS):
            index["sections"] = {"page_items": page, "incomplete": [],
                                 "counts": {n: len(i) for n, i in sections.items()}}
            index.update({name: list(items) for name, items in sections.items()})
            index["index_bytes"] = 0
            index["within_budget"] = True
            index["complete"] = True
            return index

        with patch.object(runtime.Runtime, "bound_index", staticmethod(unbounded)):
            broken = self.run_one(DeltaIndexTests,
                                  "test_an_oversized_section_is_paged_out_and_says_so")
        self.assertEqual(len(broken.failures), 1)
        self.assertEqual(len(broken.errors), 0)

    def test_all_or_nothing_citation_ingestion_is_detected(self):
        original = runtime.Runtime.resolve_citations

        def all_or_nothing(self, key, citations):
            outcome = original(self, key, citations)
            if not outcome["complete"]:
                raise runtime.Invalid("resolve every requirement exactly once")
            return outcome

        with patch.object(runtime.Runtime, "resolve_citations", all_or_nothing):
            broken = self.run_one(
                EvidenceTests, "test_partial_evidence_is_recorded_and_what_is_missing_is_named")
        self.assertEqual(len(broken.errors), 1)

    def test_a_gate_that_ignores_unread_pages_is_detected(self):
        with patch.object(runtime.Runtime, "unread_delta_sections", staticmethod(lambda w: [])):
            broken = self.run_one(DeltaIndexTests,
                                  "test_a_sufficient_delta_cannot_pass_on_a_section_it_never_paged")
        self.assertEqual(len(broken.failures), 1)
        self.assertEqual(len(broken.errors), 0)

    def test_a_probe_that_cannot_fail_is_detected(self):
        with patch.object(runtime.Runtime, "probe",
                          lambda self, key, expect: {"finding": "delivered", "passed": True,
                                                     "expected_bytes": 0}):
            broken = self.run_one(
                ProbeAndJournalTests,
                "test_publication_probe_distinguishes_delivered_truncated_and_mangled")
        self.assertEqual(len(broken.failures), 1)
        self.assertEqual(len(broken.errors), 0)

    def test_a_reused_receipt_that_ignores_the_revision_is_detected(self):
        with patch.object(runtime.Runtime, "receipt_applicable", staticmethod(lambda *a: [])):
            broken = self.run_one(VerificationIndexTests,
                                  "test_reuse_returns_the_receipt_only_while_it_still_applies")
        self.assertEqual(len(broken.failures), 1)
        self.assertEqual(len(broken.errors), 0)


if __name__ == "__main__":
    unittest.main()
