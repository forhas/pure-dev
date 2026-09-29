"""Genericity regression boundaries; synthetic projects only, Windows + WSL2."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

import test_decomposition as base
import recording
import scope


class GenericityRecheckTests(unittest.TestCase):
    setUp = base.GenericityTests.setUp
    config = base.GenericityTests.config
    cli = base.GenericityTests.cli

    def test_reference_cannot_escape_project_or_use_host_specific_paths(self):
        project = self.root / "project"
        project.mkdir()
        outside = self.root / "outside.md"
        base.write_lf(outside, "- not project content\n")
        for reference in ("../outside.md", str(outside), "C:/outside.md", r"..\outside.md"):
            with self.subTest(reference=reference), self.assertRaisesRegex(ValueError, "repo-relative"):
                scope.failure_mode_classes({"failureModeReference": reference}, str(project))

    def test_reference_symlink_cannot_escape_project(self):
        project = self.root / "project"
        project.mkdir()
        outside = self.root / "outside.md"
        base.write_lf(outside, "- not project content\n")
        try:
            (project / "linked.md").symlink_to(outside)
        except OSError:
            self.skipTest("host does not grant symlink creation")
        with self.assertRaisesRegex(ValueError, "inside the project"):
            scope.failure_mode_classes({"failureModeReference": "linked.md"}, str(project))

    def test_failure_mode_list_rejects_invalid_values_instead_of_character_classes(self):
        for value in ("bounds", [], [""], ["  "], [7]):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "failureModeClasses"):
                scope.failure_mode_classes({"failureModeClasses": value}, str(self.root))
        self.assertEqual(scope.failure_mode_classes({"failureModeClasses": ["transaction atomicity"],
            "failureModeReference": "missing.md"}, str(self.root))[0], ["transaction atomicity"])

    def test_generated_unicode_paths_use_literal_git_names(self):
        repo = self.root / "repo"
        repo.mkdir()
        def git(*args):
            return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
        git("init", "-q"); git("config", "user.email", "fixture@example.invalid"); git("config", "user.name", "fixture")
        base.write_lf(repo / "code.txt", "baseline\n")
        git("add", "."); git("commit", "-qm", "baseline"); git("branch", "base")
        folder = repo / "généré"
        folder.mkdir()
        base.write_lf(folder / "出力.json", "generated\n" * 900)
        base.write_lf(repo / "code.txt", "baseline\nreal change\n")
        git("add", "."); git("commit", "-qm", "candidate")
        result = self.cli("changed-lines", "--worktree", str(repo), "--base", "base",
                          "--config", self.config(generatedPaths=["généré/"]))
        self.assertEqual(result["changed_lines"], 1)
        self.assertEqual(result["excluded_generated"], {"généré/出力.json": 900})

    def test_meta_routing_cannot_send_work_back_to_the_product_epic(self):
        for label in ("meta", "META"):
            packet = base.FollowupPacketTests.packet(self, labels=[label], source_epic="EX-1",
                destination="epic:EX-1")
            for config in ({"metaDestination": "epic:EX-1"},
                           {"destinations": [{"match": "meta", "to": "epic:EX-1"}]}):
                with self.subTest(label=label, config=config), self.assertRaisesRegex(ValueError, "meta.*source epic"):
                    recording.followup_body(packet, config)
            with self.assertRaisesRegex(ValueError, "meta.*source epic"):
                recording.followup_body({**packet, "destination": "epic"},
                    {"destinations": [{"match": "meta", "to": "epic"}]})
            self.assertEqual(scope.route_followup("yes", [label], {})[0], "backlog")
            recording.followup_body({**packet, "destination": "epic:EX-90"},
                {"destinations": [{"match": "meta", "to": "epic:EX-90"}]})

    def test_fold_parser_preserves_order_and_conflict_instead_of_granting_authority(self):
        pages = [{"key": "EX-2", "text": r"Lands with: \[EX-7\]"},
                 {"key": "EX-3", "text": "Land before EX-7; this is an independent prerequisite."},
                 {"key": "EX-4", "text": "Do not merge into EX-7. Old text: fold into EX-7."}]
        result = scope.fold_declarations("EX-7", pages)
        self.assertEqual([r["key"] for r in result], ["EX-2", "EX-3", "EX-4"])
        self.assertEqual([r["relation"] for r in result], ["with", "before", "with"])
        self.assertEqual([r["conflicting"] for r in result], [False, False, True])

    def test_pending_spec_change_suppresses_rehome_actions(self):
        brief = base.BRIEF.replace("## Open threads\n", "## Open threads\n"
            "- **Re-scope pending** — spec changed. Unblocked by: task-breakdown re-scope.\n")
        path = self.root / "brief.md"; state = self.root / "state.json"
        base.write_lf(path, brief); base.runtime.atomic_json(state, base.live_state())
        proc = subprocess.run([sys.executable, str(base.KNOWLEDGE), "epic-goal", "--brief", str(path),
                               "--state", str(state)], capture_output=True, encoding="utf-8", check=True)
        result = json.loads(proc.stdout)
        self.assertEqual(result["goal"], "met")
        self.assertEqual(result["recommendation"], "rescope")
        self.assertEqual(result["rehome"], [], "stale goal must not supply a closure batch")


if __name__ == "__main__":
    unittest.main()
