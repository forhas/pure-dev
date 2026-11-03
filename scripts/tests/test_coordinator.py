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
        self.dir = Path(self.temp.name).resolve()   # Windows hands tempfile the 8.3 short name
        self.world_path = self.dir / "world.json"
        self.world({})
        env = patch.dict(os.environ, {"NOTION_DEV_CLAUDE_FAKE": str(FAKE),
                                      "NOTION_DEV_FAKE_WORLD": str(self.world_path),
                                      "NOTION_DEV_SESSION_ID": "a"})
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

    def test_a_cmd_shim_is_refused(self):
        os.environ.pop("NOTION_DEV_CLAUDE_FAKE")
        for shim in ("C:/npm/claude.cmd", "C:/npm/claude.BAT"):
            with patch.object(coordinator.shutil, "which", return_value=shim):
                with self.assertRaisesRegex(Invalid, "cmd.exe"):
                    coordinator.claude_command()

    def test_an_unlisted_launch_is_stopped_and_removed(self):
        self.world({"unlisted": True})
        with self.assertRaisesRegex(Invalid, "not listed"):
            coordinator.launch(self.dir, "/notion-dev:next-task STO-1")
        short = [c for c in self.calls() if c[0] == "--bg"]
        self.assertTrue(short)
        self.assertTrue([c for c in self.calls() if c[0] == "stop"] and [c for c in self.calls() if c[0] == "rm"])

    def test_a_waiting_status_is_blocked(self):
        found = {"state": "working", "status": "waiting", "waitingFor": "permission prompt"}
        self.assertEqual(coordinator.agent_state(found, coordinator.stamp()), "blocked")
        found = {"state": "blocked", "status": "waiting"}
        self.assertEqual(coordinator.agent_state(found, coordinator.stamp()), "blocked")

    def test_agents_tolerates_entries_without_an_id(self):
        self.world({"sessions": [{"kind": "interactive", "sessionId": "58b815db-host", "status": "busy"}]})
        self.assertIsNone(coordinator.entry("deadbeef-0000"))
        self.assertEqual(coordinator.entry("58b815db-host")["kind"], "interactive")

    def test_no_permission_bypass_flags_are_ever_passed(self):
        launched = coordinator.launch(self.dir, "/notion-dev:next-task STO-1")
        coordinator.resume(self.dir, launched["session"], "continue")
        for call in self.calls():
            self.assertFalse(BYPASS & set(call), call)


GUARD = ROOT / "plugins/notion-dev/hooks/stop-guard.sh"


def bash():
    return os.environ.get("BASH_EXE") or "bash"


class ProjectBase(CoordinatorBase):
    def setUp(self):
        super().setUp()
        self.project = self.dir / "project"
        self.project.mkdir()
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        self.host("a")

    def host(self, *sessions):
        """The coordinator sessions `claude agents` lists as live (this test process's pid)."""
        world = self.world()
        world["sessions"] = [s for s in world.get("sessions", []) if s.get("kind") != "interactive"] + [
            {"kind": "interactive", "sessionId": s, "status": "busy", "pid": os.getpid()} for s in sessions]
        self.world(world)

    def guard(self, session):
        env = {k: v for k, v in os.environ.items() if k not in {"NOTION_DEV_PRIMARY_ROOT", "CLAUDE_PROJECT_DIR"}}
        done = subprocess.run([bash(), str(GUARD)], input=json.dumps({"session_id": session, "cwd": str(self.project)}),
                              capture_output=True, encoding="utf-8", cwd=str(self.project), env=env)
        return done.stdout


class StateTests(ProjectBase):
    def test_start_creates_state_and_guardable_marker(self):
        started = coordinator.start(self.project, "STO-1", "a", True)
        marker = json.loads(Path(started["marker"]).read_text(encoding="utf-8"))
        self.assertEqual(set(marker), {"run", "phase", "state", "non_interactive", "claude_session",
                                       "heartbeat", "state_path"})
        self.assertEqual(Path(started["marker"]).name, "coordinator-STO-1.json")
        self.assertEqual(marker["state"], "running")
        state = json.loads(Path(started["state"]).read_text(encoding="utf-8"))
        self.assertEqual(Path(state["root"]).resolve(), self.project.resolve())
        self.assertIn('"decision":"block"', self.guard("a"))
        coordinator.finish(started["state"], "complete", None)
        started = coordinator.start(self.project, "STO-3", "a", False)
        self.assertNotIn('"decision":"block"', self.guard("a"))

    def test_exclusivity_is_per_epic(self):
        coordinator.start(self.project, "STO-1", "a", False)
        self.host("a", "b")
        with self.assertRaisesRegex(Invalid, "coordinator-STO-1"):
            coordinator.start(self.project, "STO-1", "b", False)
        self.assertFalse(coordinator.start(self.project, "STO-2", "b", False)["resumed"])

    def test_stale_marker_is_adopted(self):
        started = coordinator.start(self.project, "STO-1", "a", False)
        self.host("a", "b")
        path = Path(started["marker"])
        marker = json.loads(path.read_text(encoding="utf-8"))
        marker["heartbeat"] = coordinator.stamp(time.time() - 121 * 60)
        path.write_text(json.dumps(marker), encoding="utf-8")
        adopted = coordinator.start(self.project, "STO-1", "b", False)
        self.assertEqual(adopted["adopted_from"], "a")
        self.assertTrue(adopted["resumed"])

    def test_ended_coordinator_session_is_adopted(self):
        coordinator.start(self.project, "STO-1", "a", False)
        self.host("b")                      # "a" is no longer listed: its session ended
        self.assertEqual(coordinator.start(self.project, "STO-1", "b", False)["adopted_from"], "a")

    def test_start_checks_claude_before_writing_anything(self):
        world = self.world(); world["agents_garbage"] = True; self.world(world)
        with self.assertRaisesRegex(Invalid, "claude agents --json"):
            coordinator.start(self.project, "STO-1", "a", True)
        self.assertFalse((self.project / ".claude/notion-dev/runs/coordinator-STO-1.json").exists())

    def test_an_adopted_run_refuses_its_old_owner(self):
        started = coordinator.start(self.project, "STO-1", "a", False)
        launched = coordinator.record_launch(started["state"], "next-task", "/notion-dev:next-task STO-1", None, None)
        self.host("b")
        with patch.dict(os.environ, {"NOTION_DEV_SESSION_ID": "b"}):
            coordinator.start(self.project, "STO-1", "b", False)
        launches = len([c for c in self.calls() if c[:1] == ["--bg"]])
        for act in (lambda: coordinator.judge(started["state"], launched["session"], "accepted", ""),
                    lambda: coordinator.record_launch(started["state"], "next-task", "/notion-dev:next-task STO-1", None, None),
                    lambda: coordinator.remediate(started["state"], launched["session"], "x"),
                    lambda: coordinator.retire(started["state"], launched["session"]),
                    lambda: coordinator.wait(started["state"], launched["session"], seconds=0, interval=0),
                    lambda: coordinator.finish(started["state"], "complete", None)):
            with self.assertRaisesRegex(Invalid, "no longer owns"):
                act()
        self.assertEqual(len([c for c in self.calls() if c[:1] == ["--bg"]]), launches)
        self.assertFalse([c for c in self.calls() if c[0] in {"stop", "rm"}])
        marker = json.loads((self.project / ".claude/notion-dev/runs/coordinator-STO-1.json").read_text(encoding="utf-8"))
        self.assertEqual((marker["claude_session"], marker["state"]), ("b", "running"))

    def test_unlisted_host_cannot_prove_the_other_ended(self):
        coordinator.start(self.project, "STO-1", "a", False)
        self.host()                         # neither listed: the list proves nothing
        with self.assertRaisesRegex(Invalid, "coordinator-STO-1"):
            coordinator.start(self.project, "STO-1", "b", False)

    def test_start_resumes_unfinished_state(self):
        started = coordinator.start(self.project, "STO-1", "a", False)
        launched = coordinator.record_launch(started["state"], "next-task", "/notion-dev:next-task STO-1 --non-interactive", None, None)
        again = coordinator.start(self.project, "STO-1", "a", False)
        self.assertTrue(again["resumed"])
        self.assertEqual(again["state"], started["state"])
        self.assertEqual(again["open"], [launched["session"]])
        self.assertEqual(len([c for c in self.calls() if c[:1] == ["--bg"]]), 1)

    def test_remediation_bound_is_two_per_ticket(self):
        started = coordinator.start(self.project, "STO-1", "a", False)
        launched = coordinator.record_launch(started["state"], "next-task", "/notion-dev:next-task STO-1", "STO-7", None)
        coordinator.remediate(started["state"], launched["session"], "run /notion-dev:finalize 12")
        coordinator.remediate(started["state"], launched["session"], "resolve or record the tail")
        with self.assertRaisesRegex(Invalid, "escalate"):
            coordinator.remediate(started["state"], launched["session"], "third")
        self.assertEqual(len([c for c in self.calls() if c[:2] == ["--bg", "--resume"]]), 2)

    def test_followup_launch_counts_toward_the_parent_ticket(self):
        started = coordinator.start(self.project, "STO-1", "a", False)
        launched = coordinator.record_launch(started["state"], "next-task", "/notion-dev:next-task STO-1", "STO-7", None)
        coordinator.record_launch(started["state"], "followup", "/notion-dev:ticket STO-9 --non-interactive", "STO-9", launched["session"])
        coordinator.record_launch(started["state"], "followup", "/notion-dev:ticket STO-10 --non-interactive", "STO-10", launched["session"])
        with self.assertRaisesRegex(Invalid, "escalate"):
            coordinator.remediate(started["state"], launched["session"], "third")

    def test_finish_removes_retired_sessions_and_terminates_marker(self):
        started = coordinator.start(self.project, "STO-1", "a", True)
        one = coordinator.record_launch(started["state"], "next-task", "/notion-dev:next-task STO-1", "STO-7", None)
        two = coordinator.record_launch(started["state"], "next-task", "/notion-dev:next-task STO-1", "STO-8", None)
        coordinator.judge(started["state"], one["session"], "accepted", "all six checks pass")
        coordinator.retire(started["state"], one["session"])
        coordinator.retire(started["state"], two["session"])
        coordinator.finish(started["state"], "complete", None)
        removed = [c[1] for c in self.calls() if c[0] == "rm"]
        self.assertEqual(sorted(removed), sorted([one["id"], two["id"]]))
        marker = json.loads(Path(started["marker"]).read_text(encoding="utf-8"))
        self.assertEqual(marker["state"], "complete")
        self.assertNotIn('"decision":"block"', self.guard("a"))
        state = json.loads(Path(started["state"]).read_text(encoding="utf-8"))
        self.assertEqual(state["launches"][0]["verdict"], "accepted")
        self.assertEqual(state["status"], "complete")

    def test_a_fact_decision_leaves_the_ticket_verdict_alone(self):
        started = coordinator.start(self.project, "STO-1", "a", False)
        launched = coordinator.record_launch(started["state"], "next-task", "/notion-dev:next-task STO-1", "STO-7", None)
        coordinator.judge(started["state"], launched["session"], "accepted", "six checks pass")
        coordinator.judge(started["state"], launched["session"], "declined", "user said no", fact="The list ships next.")
        launch = json.loads(Path(started["state"]).read_text(encoding="utf-8"))["launches"][0]
        self.assertEqual(launch["verdict"], "accepted")
        self.assertEqual(launch["facts"], [{"fact": "The list ships next.", "verdict": "declined",
                                            "note": "user said no", "at": launch["facts"][0]["at"]}])

    def test_judge_rejects_unknown_verdicts_and_sessions(self):
        started = coordinator.start(self.project, "STO-1", "a", False)
        launched = coordinator.record_launch(started["state"], "next-task", "/notion-dev:next-task STO-1", None, None)
        with self.assertRaisesRegex(Invalid, "verdict"):
            coordinator.judge(started["state"], launched["session"], "fine", "")
        with self.assertRaisesRegex(Invalid, "not a launch"):
            coordinator.judge(started["state"], "nope", "accepted", "")


class OutcomeTests(ProjectBase):
    def started(self, **world):
        current = self.world(); current.update(world); self.world(current)
        started = coordinator.start(self.project, "STO-1", "a", False)
        launched = coordinator.record_launch(started["state"], "next-task", "/notion-dev:next-task STO-1", None, None)
        return started["state"], launched

    def runs(self):
        return self.project / ".claude/notion-dev/runs"

    def report(self, session, text="OUTCOME: resolved\n"):
        path = coordinator.report_path(self.project, session)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def ticket_marker(self, session, state, name="STO-7.json"):
        coordinator.atomic_json(self.runs() / name, {"run": "STO-7", "phase": "record", "state": state,
                                                     "non_interactive": True, "claude_session": session})

    def test_wait_returns_pending_then_settles(self):
        state, launched = self.started(settle_after=3)
        first = coordinator.wait(state, launched["session"], seconds=0, interval=0)
        self.assertFalse(first["settled"])
        self.assertEqual(first["outcome"], "working")
        later = coordinator.wait(state, launched["session"], seconds=5, interval=0)
        self.assertTrue(later["settled"])
        self.assertEqual(later["agent_state"], "idle")

    def test_done_without_report_is_handback(self):
        state, launched = self.started()
        session = launched["session"]
        self.assertEqual(coordinator.wait(state, session, seconds=5, interval=0)["outcome"], "handback")
        self.report(session)
        self.ticket_marker(session, "running")
        self.assertEqual(coordinator.wait(state, session, seconds=5, interval=0)["outcome"], "handback")
        self.ticket_marker(session, "complete")
        settled = coordinator.wait(state, session, seconds=5, interval=0)
        self.assertEqual(settled["outcome"], "done")
        self.assertEqual(settled["run_marker"]["state"], "complete")
        self.assertTrue(settled["report"].endswith(".md"))

    def test_a_busy_session_is_never_judged(self):
        state, launched = self.started(settle_after=1000)
        self.report(launched["session"])
        self.ticket_marker(launched["session"], "complete")
        self.assertEqual(coordinator.wait(state, launched["session"], seconds=0, interval=0)["outcome"], "working")

    def test_blocked_is_reported_not_waited_through(self):
        state, launched = self.started(settle_after=1000)
        world = self.world()
        next(s for s in world["sessions"] if s.get("id") == launched["id"]).update(state="blocked")
        self.world(world)
        began = time.monotonic()
        result = coordinator.wait(state, launched["session"], seconds=30, interval=0)
        self.assertLess(time.monotonic() - began, 10)
        self.assertEqual(result["outcome"], "blocked")

    def test_an_exited_session_with_its_report_is_done(self):
        state, launched = self.started()
        world = self.world()
        world["sessions"] = [s for s in world["sessions"] if s.get("id") != launched["id"]]
        self.world(world)
        self.assertEqual(coordinator.wait(state, launched["session"], seconds=0, interval=0)["outcome"], "stopped")
        self.report(launched["session"])
        self.ticket_marker(launched["session"], "complete")
        self.assertEqual(coordinator.wait(state, launched["session"], seconds=0, interval=0)["outcome"], "done")

    def test_a_just_resumed_session_is_starting_not_exited(self):
        state, launched = self.started()
        coordinator.wait(state, launched["session"], seconds=5, interval=0)
        world = self.world(); world["resume_starting_polls"] = 3; self.world(world)
        state_doc = json.loads(Path(state).read_text(encoding="utf-8"))
        state_doc["launches"][0]["launched"] = coordinator.stamp(time.time() - 3600)
        Path(state).write_text(json.dumps(state_doc), encoding="utf-8")
        coordinator.remediate(state, launched["session"], "continue this run from its runtime")
        self.assertEqual(coordinator.wait(state, launched["session"], seconds=0, interval=0)["outcome"], "working")

    def test_a_report_from_before_the_resume_does_not_count(self):
        state, launched = self.started()
        self.report(launched["session"])
        self.ticket_marker(launched["session"], "complete")
        old = time.time() - 600
        os.utime(coordinator.report_path(self.project, launched["session"]), (old, old))
        self.assertEqual(coordinator.wait(state, launched["session"], seconds=0, interval=0)["outcome"], "handback")
        os.utime(coordinator.report_path(self.project, launched["session"]), None)
        self.assertEqual(coordinator.wait(state, launched["session"], seconds=5, interval=0)["outcome"], "done")
        coordinator.remediate(state, launched["session"], "resolve or record the tail")
        old = time.time() - 5
        os.utime(coordinator.report_path(self.project, launched["session"]), (old, old))
        self.assertEqual(coordinator.wait(state, launched["session"], seconds=5, interval=0)["outcome"], "handback")

    def test_recording_outcomes_come_from_the_runtime_record(self):
        state, launched = self.started()
        self.report(launched["session"])
        runtime_dir = self.dir / "runtime" / "inv-1"
        runtime_dir.mkdir(parents=True)
        coordinator.atomic_json(self.runs() / "STO-7.json", {
            "run": "STO-7", "phase": "complete", "state": "complete", "non_interactive": True,
            "claude_session": launched["session"], "runtime_state": str(runtime_dir / "state.json")})
        missing = coordinator.wait(state, launched["session"], seconds=5, interval=0)["recording"]
        self.assertEqual(missing["passed"], None)
        coordinator.atomic_json(runtime_dir / "record-result.json", {
            "passed": True, "unresolved": ["knowledge-delta"], "record": {"EPIC-DOC-RECORD": "failed"}})
        recording = coordinator.wait(state, launched["session"], seconds=5, interval=0)["recording"]
        self.assertEqual((recording["passed"], recording["unresolved"]), (True, ["knowledge-delta"]))

    def test_wait_records_the_ticket_key_and_keeps_the_count(self):
        state, launched = self.started()
        coordinator.remediate(state, launched["session"], "continue")
        self.ticket_marker(launched["session"], "running")
        coordinator.wait(state, launched["session"], seconds=5, interval=0)
        doc = json.loads(Path(state).read_text(encoding="utf-8"))
        self.assertEqual(doc["launches"][0]["ticket"], "STO-7")
        self.assertEqual(doc["remediations"], {"STO-7": 1})

    def test_wait_never_sleeps_past_its_slice(self):
        state, launched = self.started(settle_after=1000)
        began = time.monotonic()
        coordinator.wait(state, launched["session"], seconds=1, interval=30)
        self.assertLess(time.monotonic() - began, 10)

    def test_wait_refreshes_the_coordinator_heartbeat(self):
        state, launched = self.started(settle_after=1000)
        marker = self.runs() / "coordinator-STO-1.json"
        os.utime(marker, (1, 1))
        coordinator.wait(state, launched["session"], seconds=0, interval=0)
        self.assertGreater(marker.stat().st_mtime, 1000)

    def test_run_marker_ignores_preflight_and_coordinator_markers(self):
        self.runs().mkdir(parents=True, exist_ok=True)
        for name in ("preflight-x-1.json", "coordinator-STO-9.json", "STO-7.json"):
            self.ticket_marker("s-1", "running", name)
        found = coordinator.run_marker(self.project, "s-1")
        self.assertEqual(Path(found["path"]).name, "STO-7.json")
        self.assertIsNone(coordinator.run_marker(self.project, "s-2"))

    def test_workspace_flags_leftovers(self):
        git = lambda *a: subprocess.run(["git", "-C", str(self.project), *a], check=True, capture_output=True)
        git("-c", "user.email=t@e", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "base")
        git("branch", "-M", "main")
        (self.project / ".claude").mkdir(exist_ok=True)
        (self.project / ".claude/notion-dev.config.json").write_text(json.dumps({"git": {"baseBranch": "main"}}), encoding="utf-8")
        git("branch", "ticket/STO-7-fix-it")
        tree = self.dir / "project-worktrees" / "STO-7"
        git("worktree", "add", "-q", str(tree), "ticket/STO-7-fix-it")
        view = coordinator.workspace(self.project, "STO-7")
        self.assertEqual((view["worktree_gone"], view["branch_gone"]), (False, False))
        self.assertTrue(view["primary_on_base"] and view["primary_clean"])
        git("worktree", "remove", str(tree))
        git("branch", "-D", "ticket/STO-7-fix-it")
        (self.project / "stray.txt").write_text("x", encoding="utf-8")
        view = coordinator.workspace(self.project, "STO-7")
        self.assertTrue(view["worktree_gone"] and view["branch_gone"] and view["primary_on_base"])
        self.assertFalse(view["primary_clean"])
        (self.project / "stray.txt").unlink()
        self.assertTrue(all(coordinator.workspace(self.project, "STO-7").values()))


class RelayTests(ProjectBase):
    PHRASE = "approve STO-7 review allowance: 2 findings, round 4"

    def setUp(self):
        super().setUp()
        self.transcript = self.dir / "coordinator.jsonl"
        self.transcript.write_text("", encoding="utf-8")
        started = coordinator.start(self.project, "STO-1", "a", False)
        self.state = started["state"]
        self.launched = coordinator.record_launch(self.state, "next-task", "/notion-dev:next-task STO-1", "STO-7", None)
        self.asked = time.time() - 5

    def row(self, text, kind="user", session="a", when=None, **extra):
        stamp = coordinator.stamp(when if when is not None else time.time()).replace("+00:00", "Z")
        value = {"type": kind, "sessionId": session, "uuid": "u-" + str(len(self.transcript.read_text().splitlines())),
                 "timestamp": stamp, "message": {"role": kind, "content": [{"type": "text", "text": text}]}, **extra}
        with self.transcript.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(value) + "\n")
        return value["uuid"]

    def relay(self):
        return coordinator.relay(self.state, self.launched["session"], self.PHRASE, self.PHRASE,
                                 self.transcript, "a", self.asked)

    def test_relay_requires_a_real_user_turn(self):
        self.row(self.PHRASE, kind="assistant")
        self.row(self.PHRASE, isSidechain=True)
        self.row(self.PHRASE, isMeta=True)
        self.row(self.PHRASE, session="someone-else")
        with self.assertRaisesRegex(Invalid, "no matching user answer"):
            self.relay()
        self.assertFalse([c for c in self.calls() if c[:2] == ["--bg", "--resume"]])
        self.row(self.PHRASE)
        self.assertEqual(self.relay()["session"], self.launched["session"])

    def test_relay_ignores_answers_before_the_question(self):
        self.row(self.PHRASE, when=self.asked - 60)
        with self.assertRaisesRegex(Invalid, "no matching user answer"):
            self.relay()

    def test_relay_records_provenance_and_sends_exact_phrase(self):
        uuid = self.row("  " + self.PHRASE + "\n")
        self.relay()
        resumed = [c for c in self.calls() if c[:2] == ["--bg", "--resume"]]
        self.assertEqual(resumed, [["--bg", "--resume", self.launched["session"], self.PHRASE]])
        relays = json.loads(Path(self.state).read_text(encoding="utf-8"))["launches"][0]["relays"]
        self.assertEqual(relays[0]["user_message"], uuid)
        self.assertEqual(relays[0]["phrase"], self.PHRASE)
        self.assertEqual(json.loads(Path(self.state).read_text(encoding="utf-8"))["remediations"], {})

    def test_relay_answer_must_be_in_this_coordinators_session(self):
        self.row(self.PHRASE, session="b")
        with self.assertRaisesRegex(Invalid, "coordinator"):
            coordinator.relay(self.state, self.launched["session"], self.PHRASE, self.PHRASE, self.transcript, "b", self.asked)

    def test_non_interactive_never_relays(self):
        coordinator.finish(self.state, "stopped", "test")
        state = coordinator.start(self.project, "STO-1", "a", True)["state"]
        self.row(self.PHRASE)
        with self.assertRaisesRegex(Invalid, "never relays"):
            coordinator.relay(state, self.launched["session"], self.PHRASE, self.PHRASE, self.transcript, "a", self.asked)


class CliTests(ProjectBase):
    SCRIPT = ROOT / "plugins/notion-dev/scripts/coordinator.py"

    def cli(self, *args, code=0):
        env = {**os.environ, "NOTION_DEV_SESSION_ID": "a"}
        done = subprocess.run([sys.executable, str(self.SCRIPT), *args], capture_output=True, encoding="utf-8",
                              cwd=str(self.project), env=env)
        self.assertEqual(done.returncode, code, done.stdout + done.stderr)
        return json.loads(done.stdout or done.stderr)

    def test_cli_drives_one_iteration(self):
        started = self.cli("start", "--project", ".", "--epic", "STO-1", "--non-interactive")
        state = started["state"]
        launched = self.cli("launch", "--state", state, "--kind", "next-task",
                            "--prompt", "/notion-dev:next-task STO-1 --non-interactive")
        self.cli("wait", "--state", state, "--session", launched["session"], "--seconds", "0", "--interval", "0")
        report = coordinator.report_path(self.project, launched["session"])
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(RESOLVED, encoding="utf-8")
        waited = self.cli("wait", "--state", state, "--session", launched["session"], "--seconds", "5", "--interval", "0")
        self.assertEqual(waited["outcome"], "done")
        view = self.cli("report-view", "--report", waited["report"])
        self.assertEqual(view["outcome"], "resolved")
        self.cli("judge", "--state", state, "--session", launched["session"], "--verdict", "accepted", "--note", "ok")
        self.cli("retire", "--state", state, "--session", launched["session"])
        self.assertEqual(self.cli("finish", "--state", state, "--status", "complete")["status"], "complete")
        self.assertIn("error", self.cli("judge", "--state", state, "--session", "x", "--verdict", "accepted",
                                        "--note", "", code=2))
        self.assertGreater(self.cli("now")["epoch"], 1.7e9)

    def test_cli_wait_exits_one_while_pending(self):
        world = self.world(); world["settle_after"] = 1000; self.world(world)
        state = self.cli("start", "--project", ".", "--epic", "STO-1")["state"]
        launched = self.cli("launch", "--state", state, "--kind", "next-task", "--prompt", "/notion-dev:next-task STO-1")
        pending = self.cli("wait", "--state", state, "--session", launched["session"], "--seconds", "0", code=1)
        self.assertEqual(pending["outcome"], "working")


RESOLVED = """Ticket STO-7 resolved: PR #41 merged as 1a2b3c4.

OUTCOME: resolved
KNOWLEDGE-DELTA: applied
EPIC-BRIEF: unknown — notion-update timed out
NEW-INFO: none

CLOSEOUT:
TAILS-FOUND: 3
RESOLVED: 1
TRACKED: 1
BLOCKED: 1
PASSES: 2
- tracked: retry budget for the faucet client — https://www.notion.so/STO-9-0123456789abcdef0123456789abcdef
- blocked: mainnet fee replay — no mainnet credential here; unblocked by an operator running scripts/replay.sh
"""

FACTS = """OUTCOME: resolved
NEW-INFO:
- fact: The error-code list ships with the next release, as committed to Talles.
  evidence: email thread 'BTC-Gateway v3.4.12 is ready for deployment', 2026-10-28 16:07 UTC
  epics: STO-184
  route: handed off — human-sourced
  run: /notion-dev:new-info "The error-code list ships with the next release, as committed to Talles." --epic STO-184
- fact: STO-187 recorded the regtest CPFP evidence.
  evidence: gh pr view 132: MERGED at 8d8aabb
  epics: STO-184
  route: routed — applied

CLOSEOUT:
TAILS-FOUND: 1
RESOLVED: 0
TRACKED: 0
BLOCKED: 1
PASSES: 1
- blocked: confirm the error-code fact — awaiting the user's confirmation; unblocked by running its run: line
"""


class ReportTests(unittest.TestCase):
    def test_report_view_parses_resolved_report(self):
        view = coordinator.report_view(RESOLVED)
        self.assertEqual(view["outcome"], "resolved")
        self.assertEqual(view["closeout"], {"TAILS-FOUND": 3, "RESOLVED": 1, "TRACKED": 1, "BLOCKED": 1, "PASSES": 2})
        self.assertEqual(view["tracked"], [{"item": "retry budget for the faucet client",
                                            "url": "https://www.notion.so/STO-9-0123456789abcdef0123456789abcdef"}])
        self.assertEqual(view["blocked"], [{"item": "mainnet fee replay", "cause": "no mainnet credential here",
                                            "unblock": "an operator running scripts/replay.sh"}])
        self.assertEqual(view["fields"]["EPIC-BRIEF"], "unknown — notion-update timed out")
        self.assertEqual(view["facts"], [])
        self.assertEqual(view["problems"], ["EPIC-BRIEF: unknown — notion-update timed out"])

    def test_tracked_item_may_contain_a_dash(self):
        view = coordinator.report_view("- tracked: fee cap — mainnet only - later — https://example.org/9\n")
        self.assertEqual(view["tracked"], [{"item": "fee cap — mainnet only - later", "url": "https://example.org/9"}])

    def test_report_view_extracts_handed_off_facts(self):
        view = coordinator.report_view(FACTS)
        self.assertEqual(len(view["facts"]), 2)
        handed = view["facts"][0]
        self.assertEqual(handed["route"], "handed off — human-sourced")
        self.assertEqual(handed["epics"], "STO-184")
        self.assertEqual(handed["run"], '/notion-dev:new-info "The error-code list ships with the next release, '
                                        'as committed to Talles." --epic STO-184')
        self.assertIsNone(view["facts"][1]["run"])
        self.assertEqual(view["problems"], [])

    def test_report_view_flags_inconsistencies(self):
        text = RESOLVED.replace("TRACKED: 1", "TRACKED: 2").replace(
            "- tracked: retry budget for the faucet client — https://www.notion.so/STO-9-0123456789abcdef0123456789abcdef",
            "- tracked: retry budget for the faucet client\n- tracked: second item — https://example.org/2").replace(
            "EPIC-BRIEF: unknown — notion-update timed out", "EPIC-BRIEF: applied")
        problems = coordinator.report_view(text)["problems"]
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("without a URL", problems[0])
        text = RESOLVED.replace("TRACKED: 1", "TRACKED: 2").replace("EPIC-BRIEF: unknown — notion-update timed out", "")
        self.assertIn("TRACKED: 2", coordinator.report_view(text)["problems"][0])
        text = RESOLVED.replace("; unblocked by an operator running scripts/replay.sh", "").replace(
            "EPIC-BRIEF: unknown — notion-update timed out", "")
        self.assertIn("unblocked by", coordinator.report_view(text)["problems"][0])
        missing = coordinator.report_view("OUTCOME: resolved\n")
        self.assertEqual(missing["closeout"], None)
        self.assertIn("CLOSEOUT", missing["problems"][0])
        self.assertIn("OUTCOME", coordinator.report_view("all good")["problems"][0])


if __name__ == "__main__":
    unittest.main()
