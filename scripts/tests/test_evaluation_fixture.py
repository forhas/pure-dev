"""Proves the evaluation fixture is still a fixture.

A seeded defect that quietly stopped being a defect, or an oracle that stopped
checking one, turns every later comparison into a measurement of nothing. So the
fixture is re-proved mechanically on every run rather than by whoever remembers:
the oracle must PASS against the corrected twin and FAIL against the candidate, on
exactly the seeded findings, and the intake inventory must still match the ticket.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import test_runtime as fixtures

runtime = fixtures.runtime
FIXTURE = fixtures.ROOT / "scripts/fixtures/evaluation"
ORACLE = FIXTURE / "oracle/test_scheduler.py"
FINDINGS = json.loads((FIXTURE / "expected-findings.json").read_text(encoding="utf-8"))


def run_oracle(implementation):
    environment = dict(os.environ, EVAL_SCHEDULER=str(FIXTURE / implementation),
                       PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, str(ORACLE), "-v"], capture_output=True,
                          encoding="utf-8", env=environment)


def oracle_methods():
    tree = ast.parse(ORACLE.read_text(encoding="utf-8"))
    return [node.name for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]


class EvaluationFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="evaluation-fixture-")
        self.addCleanup(self.temp.cleanup)

    def test_the_oracle_passes_against_the_corrected_twin(self):
        outcome = run_oracle("reference")
        self.assertEqual(outcome.returncode, 0, outcome.stderr)

    def test_the_oracle_fails_against_every_seeded_defect(self):
        """Not merely 'fails': fails on each defect, so none can rot unnoticed."""
        outcome = run_oracle("project")
        self.assertEqual(outcome.returncode, 1, outcome.stdout + outcome.stderr)
        failed = set(re.findall(r"^(test_\w+) \(", outcome.stderr, re.M))
        expected = {"test_" + f["id"].replace("-", "_") for f in FINDINGS["findings"]
                    if f["detectable_by"] == "oracle"}
        self.assertEqual(failed, expected)

    def test_every_oracle_test_names_a_declared_finding_and_the_reverse(self):
        declared = {f["id"] for f in FINDINGS["findings"] if f["detectable_by"] == "oracle"}
        named = {name[len("test_"):].replace("_", "-") for name in oracle_methods()}
        self.assertEqual(named, declared)
        # Review-only findings have no oracle by design; they must still be declared
        # with the reason they survive, or the fixture is advertising coverage it lacks.
        for finding in FINDINGS["findings"]:
            self.assertIn(finding["detectable_by"], {"oracle", "review"}, finding["id"])
            self.assertTrue(finding["why_it_survives_a_weak_review"].strip(), finding["id"])
            self.assertTrue(finding["requirement"].strip(), finding["id"])

    def test_the_inventory_is_the_whole_ticket_and_still_matches_it(self):
        ticket = FIXTURE / "ticket.md"
        inventory = json.loads((FIXTURE / "requirements.json").read_text(encoding="utf-8"))
        self.assertEqual(inventory["source_sha256"],
                         hashlib.sha256(ticket.read_bytes()).hexdigest())
        body = ticket.read_text(encoding="utf-8")
        acceptance = body.index("## Acceptance criteria")
        notes = body.index("## Notes")
        outside = [item for item in inventory["items"]
                   if body.index(item["text"]) > notes or body.index(item["text"]) < acceptance]
        # The point of the fixture: an intake that reads only the acceptance section
        # produces a complete-looking inventory that is missing mandatory items.
        self.assertGreaterEqual(len(outside), 3)
        self.assertTrue(any(item["kind"] == "prerequisite" for item in inventory["items"]))

    def test_the_inventory_loads_through_the_runtime_and_gates_readiness(self):
        state = Path(self.temp.name) / "state.json"
        rt = runtime.Runtime(state)
        rt.init("evaluation-fixture", "EVAL-1")
        inventory = json.loads((FIXTURE / "requirements.json").read_text(encoding="utf-8"))
        recorded = rt.requirements(FIXTURE / "ticket.md", inventory)
        self.assertEqual(recorded["requirements"], len(inventory["items"]))
        self.assertTrue(rt.ready()["passed"])

    def test_the_pull_request_body_states_a_figure_the_workload_contradicts(self):
        body = (FIXTURE / "pr-body.md").read_text(encoding="utf-8")
        claimed = re.search(r"\*\*(\d+)% of registry lookups\*\*", body)
        self.assertIsNotNone(claimed, "the false claim is part of the fixture")
        self.assertNotEqual(int(claimed.group(1)), 50,
                            "the claim must differ from the workload's real 50%")


if __name__ == "__main__":
    unittest.main()
