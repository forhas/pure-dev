"""Cross-epic fact routing: the fact-check worker contract and the routing decision.

A ticket run may route a fact about another epic only through these mechanisms, so each
rule that keeps the route honest is pinned here: the checker's contract, the decision
table, and the binding that stops an edited route file from being applied.
"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import test_runtime as support
from test_runtime import runtime, ROOT

sys.path.insert(0, str(ROOT / "plugins/notion-dev/scripts"))
import facts
import workflow

WORKFLOW = ROOT / "plugins/notion-dev/scripts/workflow.py"

FACTS = {"facts": [
    {"id": "F1", "fact": "STO-187 recorded the regtest CPFP evidence; STO-184's regtest line is met.",
     "evidence": "PR #132 merged as 8d8aabb; nodes-maintenance/sto-187-regtest-cpfp-harness-2026-10-29.md",
     "epics": ["STO-184"]},
    {"id": "F2", "fact": "The error-code list ships with the next release, as committed to Talles.",
     "evidence": "email thread 'BTC-Gateway v3.4.12 is ready for deployment', 2026-10-28 16:07 UTC",
     "epics": ["STO-184"]},
]}


def check(id, verdict="supported", source="reproducible", narrowed=None, citation="gh pr view 132: MERGED at 8d8aabb"):
    return {"id": id, "verdict": verdict, "source": source, "narrowed": narrowed, "citation": citation}


class FactRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="notion-facts-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.state = self.root / "runtime" / "state.json"
        self.rt = runtime.Runtime(self.state, support.Clock())
        self.rt.init("invocation-1", "STO-187")

    def facts_file(self, document=FACTS, name="facts.json"):
        path = self.root / name
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def checked(self, checks, document=FACTS):
        """A fact-check worker carried through publish, consume and accept."""
        prepared = self.rt.prepare("fact-check", {"facts": str(self.facts_file(document))})
        key = prepared["worker"]
        self.rt.attach(key, "agent-" + key)
        self.rt.publish(key, {"report": "checked", "facts": checks})
        self.rt.consume(key)
        self.rt.accept(key)
        return key

    def route(self, key, own_epic="none", interactive=True, name="route.json"):
        output = self.root / name
        workflow.fact_route(str(self.state), key, own_epic, interactive, str(output))
        return output, json.loads(output.read_text(encoding="utf-8"))

    def test_packet_carries_the_fact_contract_and_a_nonpassing_draft(self):
        prepared = self.rt.prepare("fact-check", {"facts": str(self.facts_file())})
        packet = json.loads(Path(prepared["packet"]).read_text(encoding="utf-8"))
        required = packet["result_contract"]["required"]["facts"]
        self.assertEqual([item["id"] for item in required], ["F1", "F2"])
        self.assertIn("read-only", packet["result_contract"]["fact_rules"])
        draft = json.loads(Path(packet["publication"]["submission"]).read_text(encoding="utf-8"))
        self.assertNotIn("requirements", packet)
        self.assertEqual({(c["verdict"], c["source"]) for c in draft["facts"]}, {("unsupported", "human")})

    def test_the_checker_gets_nothing_of_the_ticket(self):
        inventory = {"source_sha256": "0" * 64, "reviewed_whole_ticket": True,
                     "items": [{"id": "AC1", "kind": "acceptance", "text": "STO-184 is unblocked"}]}
        with self.rt.transaction() as state:
            state["requirements"] = inventory
        prepared = self.rt.prepare("fact-check", {"facts": str(self.facts_file())})
        directory = Path(prepared["packet"]).parent
        self.assertNotIn("STO-184 is unblocked", Path(prepared["packet"]).read_text(encoding="utf-8"))
        self.assertIsNone(json.loads((directory / "requirements.json").read_text(encoding="utf-8")))
        with self.rt.transaction() as state:
            self.assertIsNone(state["workers"][prepared["worker"]]["requirements"])

    def test_prepare_takes_only_a_valid_facts_input(self):
        with self.assertRaisesRegex(ValueError, "exactly one input"):
            self.rt.prepare("fact-check", {"facts": str(self.facts_file()), "ticket": str(self.facts_file())})
        bad = copy.deepcopy(FACTS)
        bad["facts"][0]["epics"] = ["the CPFP epic"]
        with self.assertRaisesRegex(ValueError, "logical keys"):
            self.rt.prepare("fact-check", {"facts": str(self.facts_file(bad, "bad.json"))})
        duplicate = copy.deepcopy(FACTS)
        duplicate["facts"][1]["id"] = "F1"
        with self.assertRaisesRegex(ValueError, "unique"):
            self.rt.prepare("fact-check", {"facts": str(self.facts_file(duplicate, "dup.json"))})

    def test_an_older_schema_run_cannot_dispatch_a_fact_check(self):
        # Schemas 3 and 4 still carry a result contract, so the contract is not the gate.
        for schema in (2, 3, 4):
            with self.rt.transaction() as state:
                state["schema"] = schema
            with self.assertRaisesRegex(ValueError, "schema-5"):
                self.rt.prepare("fact-check", {"facts": str(self.facts_file())})
        # A refused attempt writes nothing: no unregistered worker directory, no copied facts.
        self.assertEqual(list(self.state.parent.glob("worker-*")), [])

    def test_publication_rejects_a_check_that_misses_or_reorders_facts(self):
        key = self.rt.prepare("fact-check", {"facts": str(self.facts_file())})["worker"]
        self.rt.attach(key, "agent-1")
        for checks, message in (
                ([check("F1")], "every fact id exactly once"),
                ([check("F2"), check("F1")], "in order"),
                ([check("F1", verdict="probably"), check("F2")], "valid verdict"),
                ([check("F1", source="unknown"), check("F2")], "valid verdict and source"),
                ([check("F1", citation=" "), check("F2")], "nonempty citation"),
                ([check("F1", verdict="narrowed"), check("F2")], "narrowed wording"),
                ([check("F1", narrowed="weaker"), check("F2")], "only for a narrowed verdict")):
            with self.assertRaisesRegex(ValueError, message):
                self.rt.publish(key, {"report": "checked", "facts": checks})

    def test_publication_is_idempotent_and_renders_one_header(self):
        key = self.rt.prepare("fact-check", {"facts": str(self.facts_file())})["worker"]
        self.rt.attach(key, "agent-1")
        result = {"report": "checked", "facts": [check("F1"), check("F2", source="human")]}
        self.rt.publish(key, result)
        self.rt.publish(key, copy.deepcopy(result))
        report = self.rt.consume(key)["result"]["report"]
        self.assertEqual(report.count("FACT-CHECK: 2"), 1)
        self.assertIn("F2: supported / human", report)

    def test_routing_needs_an_accepted_check(self):
        key = self.rt.prepare("fact-check", {"facts": str(self.facts_file())})["worker"]
        self.rt.attach(key, "agent-1")
        self.rt.publish(key, {"report": "checked", "facts": [check("F1"), check("F2")]})
        self.rt.consume(key)
        with self.assertRaisesRegex(ValueError, "accept the fact-check"):
            workflow.fact_route(str(self.state), key, "none", True, str(self.root / "route.json"))

    def test_a_reproducible_supported_fact_routes_without_a_gate(self):
        key = self.checked([check("F1"), check("F2", source="human")])
        _, route = self.route(key)
        first = route["routed"][0]
        self.assertEqual((first["id"], first["gate"], first["epics"]), ("F1", False, ["STO-184"]))

    def test_a_human_fact_routes_through_the_gate_only_when_interactive(self):
        key = self.checked([check("F1"), check("F2", source="human")])
        _, route = self.route(key, interactive=True)
        self.assertEqual([(r["id"], r["gate"]) for r in route["routed"]], [("F1", False), ("F2", True)])

    def test_a_non_interactive_run_hands_a_human_fact_off(self):
        key = self.checked([check("F1"), check("F2", source="human")])
        _, route = self.route(key, interactive=False)
        self.assertEqual([r["id"] for r in route["routed"]], ["F1"])
        self.assertIn("cannot ask you to confirm", route["handed_off"][0]["reason"])

    def test_an_unsupported_fact_is_handed_off_with_the_checker_reason(self):
        key = self.checked([check("F1", verdict="unsupported", citation="PR #132 is still open"), check("F2")])
        _, route = self.route(key)
        self.assertEqual(route["handed_off"][0]["id"], "F1")
        self.assertIn("PR #132 is still open", route["handed_off"][0]["reason"])

    def test_a_narrowed_fact_routes_the_weaker_wording(self):
        key = self.checked([check("F1", verdict="narrowed", narrowed="STO-187 recorded the regtest CPFP evidence."),
                            check("F2")])
        _, route = self.route(key)
        self.assertEqual(route["routed"][0]["fact"], "STO-187 recorded the regtest CPFP evidence.")
        self.assertEqual(route["routed"][0]["original"], FACTS["facts"][0]["fact"])

    def test_unknown_or_own_epics_are_never_routed(self):
        document = copy.deepcopy(FACTS)
        document["facts"][0]["epics"] = ["unknown"]
        document["facts"][1]["epics"] = ["STO-67", "STO-184"]
        key = self.checked([check("F1"), check("F2")], document)
        _, route = self.route(key, own_epic="STO-67")
        self.assertEqual(route["handed_off"][0]["id"], "F1")
        self.assertEqual(route["routed"][0]["epics"], ["STO-184"])
        own_only = copy.deepcopy(FACTS)
        own_only["facts"] = own_only["facts"][:1]
        own_only["facts"][0]["epics"] = ["STO-67"]
        decision = facts.decide(own_only["facts"], {"facts": [check("F1")]}, "STO-67", True)
        self.assertEqual(decision["routed"], [])
        self.assertIn("no other epic", decision["handed_off"][0]["reason"])

    def test_at_most_three_facts_route_per_run(self):
        items = [{"id": "F" + str(i), "fact": "fact " + str(i), "evidence": "e", "epics": ["STO-1"]} for i in range(5)]
        decision = facts.decide(items, {"facts": [check(i["id"]) for i in items]}, "none", True)
        self.assertEqual([r["id"] for r in decision["routed"]], ["F0", "F1", "F2"])
        self.assertTrue(all("cap of 3" in h["reason"] for h in decision["handed_off"]))

    def test_route_view_applies_only_the_unedited_bound_route(self):
        key = self.checked([check("F1"), check("F2")])
        output, route = self.route(key)
        self.assertEqual(len(workflow.route_view(str(output))["routed"]), 2)
        route["routed"][0]["fact"] = "a fact nobody checked"
        output.write_text(json.dumps(route), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed after fact-route"):
            workflow.route_view(str(output))
        copy_path = self.root / "elsewhere.json"
        copy_path.write_text(json.dumps(route), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not decided by fact-route"):
            workflow.route_view(str(copy_path))

    def test_one_accepted_check_per_run(self):
        first = self.checked([check("F1"), check("F2", verdict="unsupported")])
        with self.assertRaisesRegex(ValueError, "one accepted fact-check per run"):
            self.rt.prepare("fact-check", {"facts": str(self.facts_file(name="again.json"))})
        self.assertEqual([p.name for p in self.state.parent.glob("worker-*")], ["worker-" + first])
        # Even a second accepted check slipped into state cannot be routed from.
        with self.rt.transaction() as state:
            state["workers"]["forged"] = dict(state["workers"][first], id="forged")
        with self.assertRaisesRegex(ValueError, "one accepted fact-check"):
            workflow.fact_route(str(self.state), "forged", "none", True, str(self.root / "route.json"))

    def test_one_route_per_run(self):
        key = self.checked([check("F1"), check("F2", source="human")])
        output, first = self.route(key)
        with self.assertRaisesRegex(ValueError, "one route per run"):
            self.route(key, name="second.json")
        # The same worker and path cannot re-decide under different parameters.
        for own_epic, interactive in (("STO-184", True), ("none", False)):
            with self.assertRaisesRegex(ValueError, "one route per run"):
                workflow.fact_route(str(self.state), key, own_epic, interactive, str(output))
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), first)
        # An exact replay is answered and rewrites nothing.
        before = output.stat().st_mtime_ns
        workflow.fact_route(str(self.state), key, "none", True, str(output))
        self.assertEqual(output.stat().st_mtime_ns, before)
        self.assertEqual(len(workflow.route_view(str(output))["routed"]), 2)

    def test_route_view_cli_fails_closed_on_an_edited_route(self):
        key = self.checked([check("F1"), check("F2")])
        output, route = self.route(key)
        route["interactive"] = False
        output.write_text(json.dumps(route), encoding="utf-8")
        completed = subprocess.run([sys.executable, str(WORKFLOW), "route-view", "--route", str(output)],
                                   capture_output=True, encoding="utf-8")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("changed after fact-route", completed.stderr)


if __name__ == "__main__":
    unittest.main()
