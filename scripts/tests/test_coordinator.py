"""run-epic's coordinator helper: background sessions, state, outcomes, reports and relays.

Every `claude` call goes to scripts/tests/fake_claude.py through $NOTION_DEV_CLAUDE_FAKE, so
nothing here starts a real session. The behaviour the fake emulates was measured live by
scripts/analysis/probe-background-sessions.sh (spec facts 3-13).
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugins/notion-dev/scripts"))
import coordinator
from runtime import Invalid

FAKE = Path(__file__).resolve().parent / "fake_claude.py"
BYPASS = {"-p", "--print", "--dangerously-skip-permissions", "bypassPermissions",
          "--allow-dangerously-skip-permissions"}


class CoordinatorBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="notion-coordinator-")
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.world_path = self.dir / "world.json"
        self.world({})
        env = patch.dict(os.environ, {"NOTION_DEV_CLAUDE_FAKE": str(FAKE),
                                      "NOTION_DEV_FAKE_WORLD": str(self.world_path)})
        env.start()
        self.addCleanup(env.stop)
        waits = patch.multiple(coordinator, LIST_WAIT=0.2, APPEAR_WAIT=0.2)
        waits.start()
        self.addCleanup(waits.stop)

    def world(self, value=None):
        if value is not None:
            self.world_path.write_text(json.dumps(value), encoding="utf-8")
        return json.loads(self.world_path.read_text(encoding="utf-8"))

    def calls(self):
        return self.world()["calls"]


class SessionLayerTests(CoordinatorBase):
    def test_launch_returns_short_id_and_full_session(self):
        launched = coordinator.launch(self.dir, "/notion-dev:next-task STO-1 --non-interactive")
        self.assertRegex(launched["id"], r"^[0-9a-f]{8}$")
        self.assertTrue(launched["session"].startswith(launched["id"]))
        self.assertEqual(self.calls()[0], ["--bg", "/notion-dev:next-task STO-1 --non-interactive"])

    def test_launch_parses_id_after_warning_lines(self):
        self.world({"prefix_lines": [
            "Warning: ANTHROPIC_API_KEY is set and takes precedence over your claude.ai login",
            "\x1b[2m\x1b[33m● starting\x1b[0m"]})
        launched = coordinator.launch(self.dir, "/notion-dev:next-task STO-1")
        self.assertRegex(launched["id"], r"^[0-9a-f]{8}$")

    def test_resume_keeps_identity_after_stop_and_rm(self):
        launched = coordinator.launch(self.dir, "/notion-dev:next-task STO-1")
        resumed = coordinator.resume(self.dir, launched["session"], "continue from the runtime")
        self.assertEqual(resumed["session"], launched["session"])
        tail = [c[0] if c[0] != "--bg" else " ".join(c[:2]) for c in self.calls() if c[0] != "agents"][1:]
        self.assertEqual(tail, ["stop", "rm", "--bg --resume"])
        resumed_call = [c for c in self.calls() if c[:2] == ["--bg", "--resume"]][-1]
        self.assertEqual(resumed_call[2:], [launched["session"], "continue from the runtime"])

    def test_resume_that_forks_is_refused(self):
        launched = coordinator.launch(self.dir, "/notion-dev:next-task STO-1")
        world = self.world(); world["rm_noop"] = True; self.world(world)
        with self.assertRaisesRegex(Invalid, "forked"):
            coordinator.resume(self.dir, launched["session"], "continue")
        fork = [c for c in self.calls() if c[:2] == ["--bg", "--resume"]]
        self.assertEqual(len(fork), 1)
        stopped = [c[1] for c in self.calls() if c[0] == "stop"]
        removed = [c[1] for c in self.calls() if c[0] == "rm"]
        forked_id = [s["id"] for s in self.world()["sessions"] if s["id"] != launched["id"]]
        for short in forked_id:
            self.assertIn(short, stopped)
            self.assertIn(short, removed)

    def test_stop_waits_for_the_process_to_exit(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1.2)"])
        reaper = threading.Thread(target=child.wait)   # a session is never our child: no zombie
        reaper.start()
        self.addCleanup(reaper.join)
        self.world({"sessions": [{"id": "abcdef01", "sessionId": "abcdef01-0000", "kind": "background",
                                  "state": "working", "status": "idle", "pid": child.pid}]})
        coordinator.stop("abcdef01")
        self.assertIsNotNone(child.poll(), "stop returned while the session's process was still alive")

    def test_missing_claude_and_bad_json_are_actionable(self):
        with patch.dict(os.environ, {"PATH": str(self.dir)}):
            os.environ.pop("NOTION_DEV_CLAUDE_FAKE")
            with self.assertRaisesRegex(Invalid, "not on PATH"):
                coordinator.agents()
        self.world({"agents_garbage": True})
        with self.assertRaisesRegex(Invalid, "claude agents --json"):
            coordinator.agents()

    def test_agents_tolerates_entries_without_an_id(self):
        self.world({"sessions": [{"kind": "interactive", "sessionId": "58b815db-host", "status": "busy"}]})
        self.assertIsNone(coordinator.entry("deadbeef-0000"))
        self.assertEqual(coordinator.entry("58b815db-host")["kind"], "interactive")

    def test_no_permission_bypass_flags_are_ever_passed(self):
        launched = coordinator.launch(self.dir, "/notion-dev:next-task STO-1")
        coordinator.resume(self.dir, launched["session"], "continue")
        for call in self.calls():
            self.assertFalse(BYPASS & set(call), call)


if __name__ == "__main__":
    unittest.main()
