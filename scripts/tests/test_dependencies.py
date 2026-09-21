"""Live dependency checks use synthetic settings; never alter host/client configuration."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_runtime import module, ROOT, runtime


class DependencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dependency café ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.local = self.root / ".claude/settings.local.json"
        self.project = self.root / ".claude/settings.json"
        self.config = self.root / ".claude/notion-dev.config.json"
        self.write(self.config, {"dependencies": {"superpowers": True, "featureDev": True}})
        self.dep = module("dependencies")
        self.live = ["superpowers:writing-plans", "superpowers:subagent-driven-development",
                     "superpowers:receiving-code-review", "feature-dev:feature-dev"]

    @staticmethod
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def probe(self, live=None, **kwargs):
        return self.dep.check(self.root, self.live if live is None else live,
                              settings=[self.project, self.local], **kwargs)

    def test_local_false_overrides_project_true_but_never_changes_files(self):
        key = "feature-dev@claude-plugins-official"
        self.write(self.project, {"enabledPlugins": {key: True}})
        self.write(self.local, {"enabledPlugins": {key: False}, "permissions": {"allow": ["secret"]}})
        before = self.local.read_bytes()
        result = self.probe(self.live[:-1])
        row = result["plugins"]["featureDev"]
        self.assertFalse(result["passed"])
        self.assertEqual(row["status"], "disabled")
        self.assertTrue(row["cache_mismatch"])
        self.assertEqual(row["settings"][0]["path"], str(self.local))
        self.assertIn("enable", row["remedy"])
        self.assertNotIn("secret", json.dumps(result))
        self.assertEqual(self.local.read_bytes(), before)

    def test_false_or_missing_cache_does_not_block_available_skills(self):
        self.write(self.config, {"dependencies": {"featureDev": False}})
        result = self.probe()
        self.assertTrue(result["passed"])
        self.assertTrue(result["plugins"]["featureDev"]["cache_mismatch"])

    def test_true_cache_never_proves_availability(self):
        result = self.probe([])
        self.assertFalse(result["passed"])
        self.assertEqual(result["plugins"]["superpowers"]["status"], "unavailable")

    def test_superpowers_disablement_has_same_diagnosis(self):
        self.write(self.local, {"enabledPlugins": {"superpowers@claude-plugins-official": False}})
        result = self.probe(["feature-dev:feature-dev"])
        self.assertEqual(result["plugins"]["superpowers"]["status"], "disabled")

    def test_partial_superpowers_catalog_does_not_pass_ticket(self):
        self.assertFalse(self.probe(["superpowers:receiving-code-review", "feature-dev:feature-dev"])["passed"])
        self.assertTrue(self.probe(["superpowers:receiving-code-review"], mode="review")["passed"])

    def test_settings_do_not_override_live_presence(self):
        self.write(self.local, {"enabledPlugins": {"feature-dev@claude-plugins-official": False}})
        result = self.probe()
        self.assertTrue(result["passed"])
        self.assertTrue(result["plugins"]["featureDev"]["settings_mismatch"])

    def test_custom_claude_home_is_diagnostic_input(self):
        custom = self.root / "custom home"
        self.write(custom / "settings.json", {"enabledPlugins": {"feature-dev@official": False}})
        with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(custom)}):
            result = self.dep.check(self.root, self.live[:-1])
        self.assertEqual(result["plugins"]["featureDev"]["status"], "disabled")

    def test_malformed_input_fails_closed(self):
        with self.assertRaises(ValueError):
            self.probe({"invented": "catalog"})
        self.local.write_text("not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.probe()

    def test_cli_reports_failure_as_json_without_rewriting_cached_flags(self):
        live = self.root / "live.json"
        self.write(live, [])
        before = self.config.read_bytes()
        process = subprocess.run([sys.executable, str(ROOT / "plugins/notion-dev/scripts/dependencies.py"),
            "--project", str(self.root), "--live-skills", str(live),
            "--settings", str(self.project), "--settings", str(self.local)], capture_output=True)
        self.assertEqual(process.returncode, 1)
        self.assertFalse(json.loads(process.stdout.decode("utf-8"))["passed"])
        self.assertNotIn(b"\r\n", process.stdout)
        self.assertEqual(self.config.read_bytes(), before)

    def test_schema_does_not_make_cached_hints_mandatory(self):
        schema = json.loads((ROOT / "plugins/notion-dev/schema/notion-dev.config.schema.json").read_text(encoding="utf-8"))
        self.assertNotIn("dependencies", schema["required"])
        self.assertNotIn("required", schema["properties"]["dependencies"])

    def test_live_probe_false_pass_mutation_is_detected(self):
        original = self.dep.check
        def broken(*args, **kwargs):
            result = original(*args, **kwargs)
            result["passed"] = True
            return result
        with patch.object(self.dep, "check", side_effect=broken):
            with self.assertRaises(AssertionError):
                self.test_true_cache_never_proves_availability()

    def test_command_contracts_fail_when_diagnostics_are_removed(self):
        prefix = 'fails=0; ok() { :; }; bad() { fails=$((fails + 1)); }; . "$1"; '
        command = prefix + 'assert_has contract "$2" "$3"; test "$fails" -eq 0'
        candidate = self.root / "command.md"
        contracts = [("commands/" + name + ".md", "references/dependencies.md")
                     for name in ("init", "ticket", "next-task", "finalize")]
        contracts += [("commands/init.md", "**confirmed not installed**"),
                      ("references/dependencies.md", "**Never reinstall over an explicit `false`**"),
                      ("references/dependencies.md", "cached setup hints, not"),
                      ("references/dependencies.md", "`CLAUDE_CONFIG_DIR/settings.json`")]
        for name, fragment in contracts:
            source = (ROOT / "plugins/notion-dev" / name).read_text(encoding="utf-8")
            for content, expected in ((source, 0), (source.replace(fragment, "REMOVED"), 1)):
                candidate.write_text(content, encoding="utf-8")
                actual = subprocess.run([runtime.bash_exe(), "-c", command, "--",
                    (ROOT / "scripts/lib/assert.sh").as_posix(), candidate.as_posix(), fragment], capture_output=True)
                self.assertEqual(actual.returncode, expected, (name, fragment, actual.stderr.decode("utf-8")))


if __name__ == "__main__":
    unittest.main()
