"""Real local Git remotes: never publish to GitHub from a test."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("release_tags", ROOT / "scripts/tag-notion-release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTagsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="release-tags-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        previous_cwd = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous_cwd)
        release.git("init", "--bare", "remote.git")
        release.git("init", "repo")
        os.chdir(self.root / "repo")
        release.git("config", "user.name", "Test")
        release.git("config", "user.email", "test@example.invalid")
        release.git("config", "commit.gpgsign", "false")
        release.git("config", "tag.gpgsign", "false")
        release.git("remote", "add", "origin", str(self.root / "remote.git"))
        self.manifest = Path(release.MANIFEST)
        self.manifest.parent.mkdir(parents=True)
        self.before = self.commit("0.1.0")
        self.sha = self.commit("0.2.0")
        self.tag = "notion-dev-v0.2.0"

    def commit(self, value):
        self.manifest.write_text(json.dumps({"name": "notion-dev", "version": value}), encoding="utf-8")
        release.git("add", ".")
        release.git("commit", "-qm", "fixture")
        return release.git("rev-parse", "HEAD")

    def test_publish_exact_commit_annotated_and_idempotent(self):
        self.assertIn("Published", release.publish(self.sha, self.before))
        self.assertEqual(release.remote_target(self.tag), self.sha)
        self.assertEqual(release.git("cat-file", "-t", "refs/tags/" + self.tag), "tag")
        refs = release.git("ls-remote", "--tags", "origin")
        self.assertIn("already", release.publish(self.sha, self.before))
        self.assertEqual(release.git("ls-remote", "--tags", "origin"), refs)

    def test_remote_conflict_never_moves_lightweight_or_annotated_tag(self):
        for annotated in (False, True):
            tag = "notion-dev-v0.2.%d" % annotated
            sha = self.sha if not annotated else self.commit("0.2.1")
            args = ["tag", "-a", "-m", "old"] if annotated else ["tag"]
            release.git(*args, tag, self.before)
            release.git("push", "origin", "refs/tags/" + tag)
            with self.assertRaisesRegex(ValueError, "refusing to move"):
                release.publish(sha, self.before)
            self.assertEqual(release.remote_target(tag), self.before)

    def test_unrelated_push_skips_but_plugin_change_requires_bump(self):
        Path("unrelated.txt").write_text("docs", encoding="utf-8")
        unrelated = self.commit("0.2.0")
        self.assertIn("nothing to tag", release.publish(unrelated, self.sha))
        (self.manifest.parent / "extra.txt").write_text("plugin change", encoding="utf-8")
        changed = self.commit("0.2.0")
        with self.assertRaisesRegex(ValueError, "without a version bump"):
            release.publish(changed, unrelated)
        self.assertIsNone(release.remote_target(self.tag))

    def test_old_run_never_tags_later_checkout(self):
        self.commit("0.3.0")
        with self.assertRaisesRegex(ValueError, "exact tested commit"):
            release.publish(self.sha, self.before)
        self.assertIsNone(release.remote_target(self.tag))

    def test_batched_push_tags_only_final_tested_version(self):
        latest = self.commit("0.3.0")
        release.publish(latest, self.before)
        self.assertEqual(release.remote_target("notion-dev-v0.3.0"), latest)
        self.assertIsNone(release.remote_target(self.tag))

    def test_invalid_or_decreasing_version_rejected(self):
        for value in ("../bad", "0.2.0\n", 12, "0.0.9"):
            sha = self.commit(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                release.publish(sha, self.before)

    def test_unavailable_remote_is_not_treated_as_missing_tag(self):
        release.git("remote", "set-url", "origin", str(self.root / "missing.git"))
        with self.assertRaises(subprocess.CalledProcessError):
            release.publish(self.sha, self.before)
        self.assertEqual(release.git("tag", "--list"), "")

    def test_lost_push_acknowledgment_is_reconciled(self):
        real_git = release.git
        def lost_ack(*args):
            result = real_git(*args)
            if args[0] == "push":
                raise subprocess.CalledProcessError(1, "git push")
            return result
        with patch.object(release, "git", side_effect=lost_ack):
            release.publish(self.sha, self.before)
        self.assertEqual(release.remote_target(self.tag), self.sha)

    def test_conflicting_local_tag_is_not_overwritten(self):
        release.git("tag", self.tag, self.before)
        with self.assertRaisesRegex(ValueError, "conflicting local"):
            release.publish(self.sha, self.before)
        self.assertIsNone(release.remote_target(self.tag))

    def test_push_failure_remains_failure_and_local_tag_can_retry(self):
        real_git = release.git
        def reject_push(*args):
            if args[0] == "push":
                raise subprocess.CalledProcessError(1, "git push")
            return real_git(*args)
        with patch.object(release, "git", side_effect=reject_push):
            with self.assertRaises(subprocess.CalledProcessError):
                release.publish(self.sha, self.before)
        self.assertIsNone(release.remote_target(self.tag))
        release.publish(self.sha, self.before)
        self.assertEqual(release.remote_target(self.tag), self.sha)

    def test_global_follow_tags_cannot_publish_other_tags(self):
        release.git("config", "push.followTags", "true")
        release.git("tag", "-a", "-m", "unrelated", "other-plugin-v1.0.0", self.before)
        release.publish(self.sha, self.before)
        self.assertIsNone(release.remote_target("other-plugin-v1.0.0"))


class ReleaseWorkflowTests(unittest.TestCase):
    def test_release_job_is_gated_and_bound(self):
        workflow = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
        job = workflow.split("\n  tag-notion-release:\n", 1)[1]
        self.assertIn("needs: [verify, verify-windows, verify-python-floor]", job)
        jobs = set(re.findall(r"^  ([\w-]+):$", workflow.split("\njobs:\n", 1)[1], re.M)) - {"tag-notion-release"}
        self.assertEqual(jobs, {"verify", "verify-windows", "verify-python-floor"})
        self.assertIn("if: github.event_name == 'push' && github.ref == 'refs/heads/main'", job)
        self.assertNotIn("always()", job)
        self.assertIn("ref: ${{ github.sha }}", job)
        self.assertIn("fetch-depth: 0", job)
        self.assertIn("RELEASE_SHA: ${{ github.sha }}", job)
        self.assertIn("RELEASE_BEFORE: ${{ github.event.before }}", job)
        self.assertIn('run: python3 scripts/tag-notion-release.py --sha "$RELEASE_SHA" --before "$RELEASE_BEFORE"', job)
        self.assertIn("permissions:\n      contents: write", job)
        self.assertEqual(workflow.count("contents: write"), 1)
        self.assertIn("permissions:\n  contents: read", workflow)


if __name__ == "__main__":
    unittest.main()
