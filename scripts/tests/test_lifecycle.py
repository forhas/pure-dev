"""Scoped lifecycle regressions on synthetic repositories; no provider writes."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_boundaries as support
import test_review_repair as repair
from test_lean_workflow import runtime, workflow, ROOT
import knowledge
import recording
import review_inputs


class RetrievalTests(unittest.TestCase):
    def state(self):
        return {"boundary": "live-1", "epic": {"key": "TEST-100", "status_class": "open"},
                "children": [{"key": "TEST-" + str(i), "id": i, "title": "Task " + str(i),
                              "status_class": "open", "blocked_by": []} for i in range(1, 26)]}

    def test_lifecycle_never_requests_sibling_bodies_or_implies_readiness(self):
        value = knowledge.retrieval_plan(self.state())
        self.assertEqual(value['fetch'], [])
        self.assertTrue(all(not c['dependencies_known'] for c in value['state']['children']))
        self.assertIsNone(knowledge.derive_next(value['state'], set())[3])

    def test_selection_requests_one_candidate_not_twenty_five(self):
        result = knowledge.retrieval_plan(self.state(), 'select')
        self.assertEqual([r['key'] for r in result['fetch']], ['TEST-1'])
        self.assertIsNone(result['candidate'])

    def test_revision_and_boundary_are_required_for_dependency_reuse(self):
        state = self.state(); child = state['children'][0]
        child.update(dependencies_known=True, content_revision='r2', dependency_revision='r1')
        self.assertEqual(knowledge.retrieval_plan(state, 'select')['fetch'][0]['key'], 'TEST-1')
        child['dependency_revision'] = 'r2'
        self.assertEqual(knowledge.retrieval_plan(state, 'select')['candidate'], 'TEST-1')
        child.pop('content_revision'); child['checked_boundary'] = 'live-1'
        self.assertEqual(knowledge.retrieval_plan(state, 'select')['candidate'], 'TEST-1')
        state['boundary'] = 'after-write'
        self.assertIsNone(knowledge.retrieval_plan(state, 'select')['candidate'])

    def test_blocked_external_dependency_and_claimed_children_are_not_eligible(self):
        state = self.state(); child = state['children'][0]
        child.update(dependencies_known=True, checked_boundary='live-1', blocked_by=['EXT-9'])
        result = knowledge.retrieval_plan(state, 'select')
        self.assertEqual(result['fetch'][0]['kind'], 'status')
        state['external_statuses'] = {'EXT-9': 'open'}
        self.assertEqual(knowledge.retrieval_plan(state, 'select')['fetch'][0]['key'], 'TEST-2')
        state['external_statuses']['EXT-9'] = 'resolved'
        self.assertEqual(knowledge.retrieval_plan(state, 'select')['candidate'], 'TEST-1')
        child['status_class'] = 'in_progress'
        self.assertEqual(knowledge.retrieval_plan(state, 'select')['fetch'][0]['key'], 'TEST-2')

    def test_threads_stops_and_brief_order_survive_progressive_selection(self):
        state = self.state(); state.update(thread_blocked=['TEST-3'], stopped_keys=['TEST-4'],
                                         candidate_order=['TEST-3', 'TEST-4', 'TEST-8'])
        self.assertEqual(knowledge.retrieval_plan(state, 'select')['fetch'][0]['key'], 'TEST-8')
        state['epic']['status_class'] = 'resolved'
        self.assertEqual(knowledge.retrieval_plan(state, 'select')['fetch'], [])

    def test_unavailable_reads_do_not_create_an_infinite_fetch_loop(self):
        state = self.state(); state['unavailable_keys'] = ['TEST-' + str(i) for i in range(1, 26)]
        result = knowledge.retrieval_plan(state, 'select')
        self.assertEqual(result['fetch'], [])
        self.assertIsNone(result['candidate'])
        self.assertEqual(result['state']['epic']['status_class'], 'open')

    def test_cli_and_unknown_as_ready_mutation(self):
        original = knowledge.retrieval_plan
        def broken(*args, **kwargs):
            value = original(*args, **kwargs)
            for c in value['state']['children']: c['dependencies_known'] = True
            return value
        with patch.object(knowledge, 'retrieval_plan', side_effect=broken):
            with self.assertRaises(AssertionError): self.test_lifecycle_never_requests_sibling_bodies_or_implies_readiness()


class LifecycleTests(unittest.TestCase):
    setUp = support.BoundaryTests.setUp
    config = support.BoundaryTests.config
    fetch = support.BoundaryTests.fetch
    new_schema = support.BoundaryTests.new_schema
    capture = support.BoundaryTests.capture
    log = support.BoundaryTests.log
    run_git = support.BoundaryTests.run_git
    prepare = support.BoundaryTests.prepare
    result = support.BoundaryTests.result
    resolve = support.BoundaryTests.resolve
    reviewed = support.BoundaryTests.reviewed
    exhausted = repair.ReviewRepairTests.exhausted
    delta_finish = repair.ReviewRepairTests.delta_finish
    approval = repair.ReviewRepairTests.approval

    def project(self):
        self.capture()
        self.run_git('add', '.'); self.run_git('commit', '-qm', 'config')
        head = runtime.git(self.repo, 'rev-parse', 'HEAD')
        return {'number': 7, 'url': 'https://github.com/example/project/pull/7', 'state': 'OPEN',
                'headRefOid': head, 'baseRefOid': head, 'body': 'Current reviewed facts'}

    def inputs(self, observed=None, sources=None):
        observed = observed or self.project()
        with patch.object(review_inputs, 'github', return_value=observed), patch.object(review_inputs, 'Runtime', return_value=self.rt):
            return review_inputs.prepare(self.state, self.repo, 'example/project#7', sources)

    def test_resume_is_read_only_small_and_preserves_every_budget_and_outcome(self):
        with self.rt.transaction() as state:
            state['record_journal'] = [{'operation': 'op1', 'outcome': 'attempted'}, {'operation': 'op1', 'outcome': 'confirmed'}]
            state['review_allowances'] = [{'authority': {'private': 'SECRET_APPROVAL'}, 'session': 'old'}]
            state['events'].append({'huge_history': 'x' * 500000})
        before = self.state.read_bytes()
        value = workflow.resume_view(self.state, self.repo)
        self.assertEqual(before, self.state.read_bytes())
        self.assertEqual(value['record_outcomes'], {'op1': 'confirmed'})
        self.assertFalse(value['approval_transfer'])
        self.assertEqual(value['attempts']['authorized_corrections'], 1)
        self.assertLess(len(json.dumps(value)), 6000)
        self.assertNotIn('SECRET_APPROVAL', json.dumps(value))

    def test_resume_reports_unaccepted_worker_and_real_head(self):
        key = self.prepare()
        value = workflow.resume_view(self.state, self.repo)
        self.assertEqual(value['outstanding_workers'], [key])
        self.assertEqual(value['review']['worker'], key)
        self.assertEqual(value['revision']['head'], runtime.git(self.repo, 'rev-parse', 'HEAD'))

    def test_generated_inputs_reject_head_body_and_arbitrary_spec(self):
        observed = self.project(); result = self.inputs(observed)
        with patch.object(review_inputs, 'github', return_value=observed):
            files = review_inputs.validate(self.state, self.repo, result['inputs'], live=True)
        self.assertEqual(runtime.read_json(files['diff'])['head'], observed['headRefOid'])
        self.assertEqual(runtime.read_json(files['pr_body'])['body'], observed['body'])
        with patch.object(review_inputs, 'github', return_value={**observed, 'body': 'new requirement'}):
            with self.assertRaisesRegex(ValueError, 'live PR changed'):
                review_inputs.validate(self.state, self.repo, result['inputs'], live=True)
        with self.assertRaisesRegex(ValueError, 'actual host page capture'):
            self.inputs(observed, {'spec': self.code})
        self.code.write_text('changed\n', encoding='utf-8')
        self.run_git('add', '.'); self.run_git('commit', '-qm', 'changed')
        with self.assertRaisesRegex(ValueError, 'stale revision'):
            review_inputs.validate(self.state, self.repo, result['inputs'])
        with self.assertRaisesRegex(ValueError, 'HEAD/state'):
            self.inputs(observed)

    def test_captured_spec_is_typed_and_immutable(self):
        observed = self.project()
        with patch.object(workflow, 'Runtime', return_value=self.rt):
            capture = workflow.record_capture(self.state, self.log(runtime.read_json(self.fetch())), 'fixture-session', 'a' * 32)
        prepared = self.inputs(observed, {'spec': capture['snapshot']})
        manifest = runtime.read_json(prepared['inputs'])
        self.assertEqual(manifest['sources']['spec']['kind'], 'notion-page')
        Path(capture['snapshot']).write_text('changed', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'review source changed'):
            review_inputs.validate(self.state, self.repo, prepared['inputs'])

    def test_identical_source_refetch_does_not_manufacture_a_review_delta(self):
        observed = self.project(); paths = []
        for call_id in ('first-source', 'second-source'):
            self.clock.seconds += 1
            with patch.object(workflow, 'Runtime', return_value=self.rt):
                capture = workflow.record_capture(self.state, self.log(runtime.read_json(self.fetch()), call_id), 'fixture-session', 'a' * 32)
            paths.append(self.inputs(observed, {'spec': capture['snapshot']})['inputs'])
        self.assertEqual(paths[0], paths[1])

    def test_review_dispatch_uses_typed_files_and_cannot_downgrade(self):
        observed = self.project(); inputs = self.inputs(observed)
        with patch.object(review_inputs, 'github', return_value=observed):
            prepared = workflow.review_prepare(self.state, self.repo, self.repo, {}, inputs_file=inputs['inputs'])
        packet = runtime.read_json(prepared['packet'])
        self.assertIn('review_inputs', packet['inputs'])
        self.assertIn('verification_receipts', packet['inputs'])
        # Even the lower-level dispatch cannot replace managed files with a stale prompt.
        with self.assertRaises(ValueError):
            self.rt.prepare('completeness', {'ticket': self.source}, self.repo)

    def test_typed_binding_and_authorization_bind_current_inputs_not_old_diff(self):
        observed = self.project()
        key = self.reviewed(); self.resolve(key)
        before = runtime.Runtime.budget_binding(runtime.read_json(self.state), key, runtime.revision(self.repo))
        inputs = self.inputs(observed)
        after = runtime.Runtime.budget_binding(runtime.read_json(self.state), key, runtime.revision(self.repo))
        self.assertNotIn('review_inputs', before['inputs'])
        self.assertEqual(after['inputs']['review_inputs'], runtime.digest(inputs['inputs']))
        self.inputs({**observed, 'body': 'Corrected claim'})
        changed = runtime.Runtime.budget_binding(runtime.read_json(self.state), key, runtime.revision(self.repo))
        self.assertNotEqual(changed, after)

    def test_foreign_session_cannot_reuse_typed_inputs(self):
        inputs = self.inputs()
        with self.rt.transaction() as state: state['host_session'] = 'new-owner'
        with self.assertRaisesRegex(ValueError, 'this session'):
            review_inputs.validate(self.state, self.repo, inputs['inputs'])

    def test_unspent_approval_can_be_reauthorized_without_granting_another_worker(self):
        key = self.exhausted()
        first = self.rt.budget_request(key, self.repo, 'reason', 'scope')
        old = self.approval(first)
        self.rt.budget_extend(first['request'], old, 'fixture-session', None, self.repo)
        with self.rt.transaction() as state: state['host_session'] = 'new-owner'
        with self.assertRaises(ValueError): self.rt.prepare('completeness', {}, self.repo, previous=key)
        second = self.rt.budget_request(key, self.repo, 'same allowance, new owner', 'scope')
        with self.assertRaises(ValueError): self.rt.budget_extend(first['request'], old, 'fixture-session', None, self.repo)
        fresh = self.approval(second, sessionId='new-owner')
        self.rt.budget_extend(second['request'], fresh, 'new-owner', None, self.repo)
        key = self.delta_finish(key)
        self.assertEqual(self.rt.summary()['delta_attempts'], 3)
        with self.assertRaises(ValueError): self.rt.budget_request(key, self.repo, 'no fourth', 'scope')

    def test_extra_correction_dispatch_uses_new_diff_not_stale_baseline(self):
        observed = self.project(); key = self.exhausted()
        self.code.write_text('corrected claim\n', encoding='utf-8')
        self.run_git('add', '.'); self.run_git('commit', '-qm', 'correct claim')
        observed['headRefOid'] = runtime.git(self.repo, 'rev-parse', 'HEAD')
        inputs = self.inputs(observed)
        request = self.rt.budget_request(key, self.repo, 'correct claim', 'one correction')
        self.rt.budget_extend(request['request'], self.approval(request), 'fixture-session', None, self.repo)
        with patch.object(review_inputs, 'github', return_value=observed):
            prepared = workflow.review_prepare(self.state, self.repo, self.repo, {}, previous=key, inputs_file=inputs['inputs'])
        packet = runtime.read_json(prepared['packet'])
        diff = runtime.read_json(packet['inputs']['diff']['path'])
        self.assertIn('+corrected claim', diff['diff'])
        self.assertEqual(diff['head'], observed['headRefOid'])
        self.assertEqual(self.rt.summary()['delta_attempts'], 3)

    def test_instruction_routes_remain_scoped(self):
        plugin = ROOT / 'plugins/notion-dev'
        for name, text in [('commands/finalize.md', 'workflow.py resume-view'),
                           ('references/boundaries.md', 'review-inputs --state'),
                           ('skills/epic-doc/references/refresh.md', '--purpose lifecycle'),
                           ('skills/epic-doc/references/schedule.md', '--purpose select'),
                           ('skills/epic-update/SKILL.md', 'references/approved-followup.md')]:
            source = (plugin / name).read_text(encoding='utf-8')
            self.assertIn(text, source)
            with self.assertRaises(AssertionError): self.assertIn(text, source.replace(text, 'REMOVED'))

    def test_review_check_is_bound_to_accepted_worker_and_expires(self):
        observed = self.project(); inputs = self.inputs(observed)
        with patch.object(review_inputs, 'github', return_value=observed):
            prepared = workflow.review_prepare(self.state, self.repo, self.repo, {}, inputs_file=inputs['inputs'])
            key = prepared['worker']
            with self.assertRaisesRegex(ValueError, 'accepted review'): review_inputs.check(self.state, self.repo, key)
            self.rt.attach(key, 'host-agent'); self.rt.publish(key, self.result()); self.rt.consume(key); self.rt.accept(key)
            self.assertIn('live reviewed PR inputs', ' '.join(self.rt.merge_gate(key, self.repo)['reasons']))
            with patch.object(review_inputs, 'Runtime', return_value=self.rt): review_inputs.check(self.state, self.repo, key)
            self.assertNotIn('live reviewed PR inputs', ' '.join(self.rt.merge_gate(key, self.repo)['reasons']))
            self.clock.seconds += 301
            self.assertIn('live reviewed PR inputs', ' '.join(self.rt.merge_gate(key, self.repo)['reasons']))
        self.inputs({**observed, 'body': 'different'})
        with patch.object(review_inputs, 'github', return_value={**observed, 'body': 'different'}):
            with self.assertRaisesRegex(ValueError, 'this session'): review_inputs.check(self.state, self.repo, key)

    def test_cli_handoff_and_retrieval_are_utf8_and_read_only(self):
        value = RetrievalTests().state(); value['children'][0]['title'] = 'café'
        source = self.root / 'live state.json'; runtime.atomic_json(source, value)
        for script, args in [('workflow', ['resume-view', '--state', str(self.state)]),
                             ('knowledge', ['retrieval-plan', '--state', str(source)])]:
            result = subprocess.run([sys.executable, str(ROOT / 'plugins/notion-dev/scripts' / (script + '.py'))] + args, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
            json.loads(result.stdout.decode('utf-8')); self.assertNotIn(b'\r\n', result.stdout)


class FactTests(unittest.TestCase):
    def packet(self):
        return {'title': 'Bound retry', 'goal': 'Keep failures bounded', 'scope': 'Worker retry only',
                'evidence': 'Accepted finding evidence', 'provenance': 'Follow-up-of: TEST-1 · finding-hash: abc',
                'source': 'https://example.invalid/pr/7', 'decision': 'file', 'requirements': ['Retry once'],
                'acceptance': ['Transient failure recovers once'], 'edge_cases': ['Permanent failure'],
                'dependencies': [], 'open_questions': []}

    def test_followup_preserves_requirements_and_atomic_marker(self):
        packet = self.packet(); result = recording.followup_body(packet)
        self.assertEqual(result['title'], packet['title'])
        self.assertEqual(result['body'].count(packet['provenance']), 1)
        self.assertIn('- [ ] Transient failure recovers once', result['body'])
        self.assertIn('## Blocked by', result['body'])

    def test_followup_missing_answers_and_unapproved_decision_fail(self):
        for field in self.packet():
            packet = self.packet(); packet.pop(field)
            with self.subTest(field=field), self.assertRaises(ValueError): recording.followup_body(packet)
        for changes in ({'decision': 'absorb'}, {'open_questions': ['Which timeout?']}, {'acceptance': []}):
            with self.assertRaises(ValueError): recording.followup_body({**self.packet(), **changes})

    def test_named_pr_facts_replace_in_place_and_reject_duplicate_paragraph(self):
        facts = {'requirement': 'Bound retry', 'behavior': {'bounded': 'One retry'}, 'validation': {'suite': 'Passed'},
                 'risks': {'rate-shortfall': 'Old explanation'}, 'mandatory': {}}
        facts['risks']['rate-shortfall'] = 'Corrected explanation'
        body = recording.pr_body(facts)
        self.assertNotIn('Old explanation', body)
        self.assertEqual(body.count('Corrected explanation'), 1)
        facts['risks']['duplicate'] = 'Corrected explanation'
        with self.assertRaisesRegex(ValueError, 'duplicate'): recording.pr_body(facts)

    def test_arithmetic_keeps_count_denominator_and_population(self):
        ratio = {'kind': 'ratio', 'numerator': 19, 'denominator': 71, 'unit': 'errors',
                 'population': 'retained tail only', 'source': 'immutable archive'}
        text = recording.measured_fact(ratio)
        self.assertIn('19/71 errors (26.76%)', text)
        self.assertIn('retained tail only', text)
        self.assertIn('No causal or significance inference', text)
        with self.assertRaises(ValueError): recording.measured_fact({**ratio, 'denominator': 0})

    def test_nonincrease_claim_checks_every_column(self):
        value = {'kind': 'comparison', 'baseline': {'p50': 100, 'p95': 200},
                 'observed': {'p50': 104, 'p95': 190}, 'nonincrease': True,
                 'unit': 'ms', 'population': 'one run', 'source': 'immutable archive'}
        with self.assertRaisesRegex(ValueError, 'contradicted'): recording.measured_fact(value)
        self.assertIn('p50: 100 → 104', recording.measured_fact({**value, 'nonincrease': False}))


if __name__ == '__main__': unittest.main()
