"""Hidden oracle for the evaluation fixture. Specified from the ticket, not the code.

Run against either implementation by pointing `EVAL_SCHEDULER` at the directory that
holds `scheduler.py`:

    EVAL_SCHEDULER=scripts/fixtures/evaluation/reference python3 <this file>

Each test method's name ends in the finding ID it proves, and
`../expected-findings.json` requires every ID to have one. That link is what stops the
fixture drifting into an oracle that no longer checks the defects it advertises.
"""
import importlib.util
import os
from pathlib import Path
import unittest

TARGET = Path(os.environ["EVAL_SCHEDULER"]).resolve() / "scheduler.py"
SPEC = importlib.util.spec_from_file_location("scheduler_under_test", TARGET)
scheduler = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scheduler)

# A graph whose nodes outlive the round that starts them. A cap that is recomputed
# without subtracting running work looks correct on single-round nodes, which is why
# the fixture graph does not use any.
GRAPH = {
    "root": {"next": ["a", "b", "c", "d"], "cost": 2},
    "a": {"next": ["e", "f"], "cost": 3},
    "b": {"next": ["g"], "cost": 3},
    "c": {"next": [], "cost": 2},
    "d": {"next": [], "cost": 2},
    "e": {"next": [], "cost": 2},
    "f": {"next": [], "cost": 2},
    "g": {"next": [], "cost": 2},
}

REGISTRY = {("parser", "1"): "parser-v1", ("parser", "2"): "parser-v2",
            ("writer", "1"): "writer-v1"}


class OracleTests(unittest.TestCase):
    def test_concurrency_limit(self):
        """concurrency-limit: no round may have more nodes running than the cap."""
        for limit in (1, 2, 3):
            outcome = scheduler.Walker(GRAPH, limit).run("root")
            self.assertLessEqual(outcome["max_in_flight"], limit,
                                 "limit %d exceeded" % limit)
            self.assertEqual(outcome["visited"], len(GRAPH))

    def test_memoization_key(self):
        """memoization-key: two versions of one name are two distinct entries."""
        cache = {}
        self.assertEqual(scheduler.resolve("parser", "1", REGISTRY, cache), "parser-v1")
        self.assertEqual(scheduler.resolve("parser", "2", REGISTRY, cache), "parser-v2")
        self.assertEqual(scheduler.resolve("parser", "1", REGISTRY, cache), "parser-v1")

    def test_config_validation(self):
        """config-validation: an unusable limit is refused, never reinterpreted."""
        for limit in (0, -1):
            with self.assertRaises(scheduler.ConfigError):
                scheduler.validate_config({"name": "walk", "limit": limit})
        with self.assertRaises(scheduler.ConfigError):
            scheduler.validate_config({"name": "walk", "limit": 2, "retries": -1})
        self.assertEqual(scheduler.validate_config({"name": " walk ", "limit": 2}),
                         {"name": "walk", "limit": 2, "retries": 0})

    def test_lookup_reduction_claim(self):
        """lookup-reduction-claim: the PR's measured figure must be the real one.

        The claim in `pr-body.md` is 60%. Memoization on this workload removes exactly
        the repeats, and the fixture workload is chosen so that figure is not 60% --
        a review that accepts the number without deriving it fails here.
        """
        requests = [("parser", "1"), ("writer", "1"), ("parser", "2"),
                    ("parser", "1"), ("writer", "1"), ("parser", "2")]
        outcome = scheduler.resolve_all(requests, REGISTRY)
        self.assertEqual(outcome["values"],
                         ["parser-v1", "writer-v1", "parser-v2",
                          "parser-v1", "writer-v1", "parser-v2"])
        reduction = 1 - outcome["registry_lookups"] / float(outcome["requests"])
        self.assertAlmostEqual(reduction, 0.5, places=6)


if __name__ == "__main__":
    unittest.main()
