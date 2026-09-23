"""Generic host-boundary and compact delta regressions; no live provider writes."""
import copy
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_handoffs as handoffs
from test_lean_workflow import runtime, workflow, ROOT
import host_capture


class BoundaryTests(unittest.TestCase):
    setUp = handoffs.HandoffTests.setUp
    config = handoffs.HandoffTests.config
    fetch = handoffs.HandoffTests.fetch
    reviewed = handoffs.HandoffTests.reviewed
    prepare = handoffs.HandoffTests.prepare
    result = handoffs.HandoffTests.result
    resolve = handoffs.HandoffTests.resolve
    run_git = handoffs.HandoffTests.run_git
    facts = handoffs.HandoffTests.facts

    def new_schema(self):
        with self.rt.transaction() as state:
            state['schema'] = 5
            state['host_session'] = 'fixture-session'

    def log(self, response, call_id='actual-1', session='fixture-session', name='mcp__notion__notion-fetch',
            args=None, offset=-1, error=False, tail=b''):
        stamp = datetime.fromtimestamp(self.clock.stamp()['wall'] + offset, timezone.utc).isoformat()
        rows = [dict(type='assistant', sessionId=session, timestamp=stamp,
                     message=dict(role='assistant', content=[dict(type='tool_use', id=call_id, name=name,
                         input=args or {'id': 'a' * 32})])),
                dict(type='user', sessionId=session, timestamp=stamp,
                     message=dict(role='user', content=[dict(type='tool_result', tool_use_id=call_id,
                         is_error=error, content=[dict(type='text', text=json.dumps(response, ensure_ascii=False))])]))]
        path = self.root / (call_id + '.jsonl')
        path.write_bytes(b''.join((json.dumps(r, ensure_ascii=False) + '\n').encode('utf-8') for r in rows) + tail)
        return path

    def capture(self):
        self.new_schema(); self.config()
        fetched = runtime.read_json(self.fetch())
        transcript = self.log(fetched)
        result = self.rt.capture_ticket(transcript, 'fixture-session', 'actual-1', self.repo / '.claude/notion-dev.config.json')
        self.source = Path(result['source'])
        self.inventory['source_sha256'] = result['source_sha256']
        self.rt.requirements(self.source, self.inventory)
        return fetched

    def test_capture_preserves_raw_unicode_escaped_properties_and_source(self):
        self.new_schema(); self.config()
        fetched = runtime.read_json(self.fetch())
        fetched['title'] = 'Quoted "name" → café [brackets]'
        fetched['unknown_property'] = {'value': '\\path\\quote"'}
        log = self.log(fetched, tail=b'{"partial":')
        value = self.rt.capture_ticket(log, 'fixture-session', 'actual-1', self.repo / '.claude/notion-dev.config.json')
        state = runtime.read_json(self.state)
        self.assertEqual(runtime.read_json(state['ticket_source']['response']), fetched)
        self.assertIn(fetched['title'], Path(value['source']).read_text(encoding='utf-8'))
        with self.assertRaisesRegex(runtime.Invalid, 'capture-ticket'):
            self.rt.ticket_source(self.fetch('copied.json'), self.repo / '.claude/notion-dev.config.json')

    def test_capture_rejects_foreign_failed_missing_and_wrong_tool(self):
        response = runtime.read_json(self.fetch())
        for changes in ({'session': 'foreign'}, {'error': True}, {'name': 'mcp__notion__notion-query-data-sources'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                host_capture.notion_fetch(self.log(response, **changes), 'fixture-session', 'actual-1')
        with self.assertRaisesRegex(ValueError, 'completed tool exchange'):
            host_capture.notion_fetch(self.log(response), 'fixture-session', 'invented-call')
        with self.assertRaises(ValueError):
            host_capture.notion_fetch(self.log(response, offset=1), 'fixture-session', 'actual-1', before=self.clock.stamp()['wall'])

    def test_conflicting_or_partial_result_never_becomes_a_receipt(self):
        path = self.log(runtime.read_json(self.fetch()))
        rows = path.read_bytes().splitlines(keepends=True)
        path.write_bytes(rows[0] + rows[1][:-1])
        with self.assertRaises(ValueError): host_capture.exchange(path, 'fixture-session', 'actual-1')
        conflict = json.loads(rows[1]); conflict['message']['content'][0]['content'] = 'different'
        path.write_bytes(b''.join(rows) + (json.dumps(conflict) + '\n').encode())
        with self.assertRaisesRegex(ValueError, 'conflicting'): host_capture.exchange(path, 'fixture-session', 'actual-1')

    def test_automatic_capture_selects_exact_page_without_model_visible_call_id(self):
        self.new_schema(); self.config(); fetched = runtime.read_json(self.fetch())
        old = self.log(fetched, 'old'); latest = self.log(fetched, 'latest')
        other = self.log(fetched, 'other', args={'id': 'b' * 32})
        old.write_bytes(old.read_bytes() + latest.read_bytes() + other.read_bytes())
        result = self.rt.capture_ticket(old, 'fixture-session', config=self.repo / '.claude/notion-dev.config.json', page='a' * 32)
        state = runtime.read_json(self.state)
        binding = state['host_captures'][state['ticket_source']['response']]
        self.assertEqual(binding['call_id'], 'latest')
        self.assertTrue(Path(result['source']).is_file())
        with self.assertRaisesRegex(ValueError, 'UUID'): host_capture.latest_call(old, 'fixture-session', 'mcp__notion__notion-fetch', page='a')

    def test_automatic_capture_does_not_fall_back_from_incomplete_or_failed_latest(self):
        fetched = runtime.read_json(self.fetch()); old = self.log(fetched, 'old'); complete = old.read_bytes()
        failed = self.log(fetched, 'latest', error=True).read_bytes()
        for tail in (failed.splitlines(keepends=True)[0], failed, failed.splitlines()[0]):
            old.write_bytes(complete + tail)
            with self.assertRaises(ValueError): host_capture.notion_fetch(old, 'fixture-session', page='a' * 32)

    def test_new_refresh_requires_actual_call_after_challenge(self):
        fetched = self.capture(); key = self.reviewed(); self.resolve(key)
        self.assertFalse(self.rt.merge_gate(key, self.repo)['passed'])
        pending = self.rt.refresh_ticket(key)
        with self.assertRaisesRegex(ValueError, 'window'):
            self.rt.capture_ticket(self.log(fetched, 'old'), 'fixture-session', 'old', worker=key, request=pending['request'])
        self.clock.seconds += 2
        result = self.rt.capture_ticket(self.log(fetched, 'fresh'), 'fixture-session', 'fresh', worker=key, request=pending['request'])
        self.assertTrue(result['passed'])
        self.assertTrue(self.rt.merge_gate(key, self.repo)['passed'])
        pending = self.rt.refresh_ticket(key); self.clock.seconds += 2
        changed = {**fetched, 'text': fetched['text'].replace('</content>', '\n## Implementation\nHuman prerequisite: offline mode.\n</content>')}
        self.assertFalse(self.rt.capture_ticket(self.log(changed, 'changed'), 'fixture-session', 'changed', worker=key, request=pending['request'])['passed'])
        self.assertFalse(self.rt.merge_gate(key, self.repo)['passed'])

    def test_refresh_rejects_wrong_page_and_changed_capture_bytes(self):
        fetched = self.capture(); key = self.reviewed(); pending = self.rt.refresh_ticket(key)
        self.clock.seconds += 2
        wrong = runtime.read_json(self.fetch('wrong.json', page='b' * 32))
        with self.assertRaisesRegex(runtime.Invalid, 'foreign'):
            self.rt.capture_ticket(self.log(wrong, 'wrong', args={'id': 'b' * 32}), 'fixture-session', 'wrong', worker=key, request=pending['request'])
        capture = Path(runtime.read_json(self.state)['ticket_source']['response'])
        runtime.atomic_json(capture, {**fetched, 'title': 'changed'})
        with self.assertRaisesRegex(runtime.Invalid, 'capture-ticket'):
            self.rt.ticket_source(capture, self.repo / '.claude/notion-dev.config.json')

    def delta(self):
        self.new_schema(); key = self.reviewed(); self.resolve(key)
        prepared = self.rt.prepare('completeness', {}, self.repo, previous=key)
        worker = runtime.read_json(self.state)['workers'][prepared['worker']]
        packet = runtime.read_json(prepared['packet'])
        compact = {'report': 'Checked changed claims and indirect effects; no duplicate narrative.',
                   'requirements_complete': True,
                   'delta_review': {**packet['result_contract']['required']['delta_review'], 'disposition': 'sufficient'},
                   'delta_result': {'baseline_sha256': packet['delta_publication']['baseline_sha256'],
                       'changed_requirements': [], 'reused_requirement_ids': [v['id'] for v in self.inventory['items']],
                       'updated_sections': {}, 'reused_sections': ['code_review', 'blocking_findings', 'claims', 'caveats', 'triage', 'recording']}}
        self.rt.attach(worker['id'], 'delta-host')
        return key, worker, compact

    def test_compact_delta_expands_complete_verdicts_and_citations(self):
        key, worker, value = self.delta()
        self.rt.publish(worker['id'], value)
        self.rt.publish(worker['id'], value)  # Immutable retry is idempotent.
        result = self.rt.consume(worker['id'])['result']; self.rt.accept(worker['id'])
        state = runtime.read_json(self.state)
        self.assertEqual(result['requirements'], state['workers'][key]['result']['requirements'])
        self.assertEqual(state['workers'][worker['id']]['citation_resolutions'], state['workers'][key]['citation_resolutions'])
        self.assertEqual(result['recording'], state['workers'][key]['result']['recording'])

    def test_compact_delta_missing_duplicate_and_foreign_ids_fail(self):
        _, worker, value = self.delta()
        for ids in ([], ['foreign'], value['delta_result']['reused_requirement_ids'] * 2):
            bad = copy.deepcopy(value); bad['delta_result']['reused_requirement_ids'] = ids
            with self.assertRaisesRegex(runtime.Invalid, 'partition'): self.rt.publish(worker['id'], bad)
        bad = copy.deepcopy(value); bad['delta_result']['reused_sections'].remove('claims')
        with self.assertRaisesRegex(runtime.Invalid, 'partition'): self.rt.publish(worker['id'], bad)
        bad = copy.deepcopy(value); bad['delta_result']['baseline_sha256'] = 'wrong'
        with self.assertRaisesRegex(runtime.Invalid, 'baseline'): self.rt.publish(worker['id'], bad)

    def test_compact_delta_stale_dependency_cannot_inherit(self):
        _, worker, value = self.delta()
        self.code.write_text('changed behavior', encoding='utf-8')
        # Fixture evidence is the source, so invalidate that too, without altering
        # the snapshot; this covers a dependency/source changing after preparation.
        self.source.write_text('changed source', encoding='utf-8')
        with self.assertRaisesRegex(runtime.Invalid, 'stale/unknown'): self.rt.publish(worker['id'], value)

    def test_compact_delta_updated_findings_are_not_cleared_by_old_clean_sections(self):
        _, worker, value = self.delta()
        value['delta_result']['reused_sections'].remove('claims')
        value['delta_result']['updated_sections']['claims'] = {'status': 'checked', 'evidence': 'new claim',
            'findings': [{'finding': 'unsupported prerequisite', 'disposition': 'blocked', 'rationale': 'source contradicts claim', 'blocking': True}]}
        self.rt.publish(worker['id'], value)
        result = self.rt.consume(worker['id'])['result']
        self.assertFalse(runtime.audits_pass(result))
        self.assertTrue(result['claims']['findings'][0]['blocking'])

    def test_compact_delta_replaces_one_judgment_and_preserves_obligations(self):
        self.new_schema()
        value = self.result()
        value['recording']['release_obligations'] = ['Operator verifies service readiness.']
        value['recording']['claim_corrections'] = ['Do not claim network isolation.']
        key = self.prepare(); self.rt.publish(key, value); self.rt.consume(key); self.rt.accept(key); self.resolve(key)
        prepared = self.rt.prepare('completeness', {}, self.repo, previous=key)
        packet = runtime.read_json(prepared['packet']); worker = prepared['worker']
        changed = {**value['requirements'][0], 'citation': 'new independently checked evidence'}
        compact = {'report': 'One revised judgment.', 'requirements_complete': True,
            'delta_review': {**packet['result_contract']['required']['delta_review'], 'disposition': 'sufficient'},
            'delta_result': {'baseline_sha256': packet['delta_publication']['baseline_sha256'],
                'changed_requirements': [changed], 'reused_requirement_ids': [v['id'] for v in value['requirements'][1:]],
                'updated_sections': {}, 'reused_sections': ['code_review', 'blocking_findings', 'claims', 'caveats', 'triage', 'recording']}}
        self.rt.attach(worker, 'delta-host'); self.rt.publish(worker, compact)
        result = self.rt.consume(worker)['result']; self.rt.accept(worker)
        self.assertEqual(result['requirements'][0], changed)
        self.assertEqual(result['recording'], value['recording'])
        resolutions = runtime.read_json(self.state)['workers'][worker]['citation_resolutions']
        self.assertNotIn(changed['id'], [r['id'] for r in resolutions])
        self.assertFalse(self.rt.merge_gate(worker, self.repo)['passed'])

    def test_compact_prior_section_tampering_is_rejected(self):
        _, worker, value = self.delta()
        prior = runtime.read_json(worker['delta_publication']['prior']['path'])
        runtime.atomic_json(prior['sections']['recording']['path'], {'release_obligations': []})
        with self.assertRaisesRegex(runtime.Invalid, 'prior section'): self.rt.publish(worker['id'], value)

    def test_schema_four_keeps_old_capture_and_worker_contract(self):
        with self.rt.transaction() as state: state['schema'] = 4
        self.config()
        captured = self.rt.ticket_source(self.fetch(), self.repo / '.claude/notion-dev.config.json')
        self.source = Path(captured['source']); self.inventory['source_sha256'] = captured['source_sha256']
        self.rt.requirements(self.source, self.inventory)
        self.run_git('add', '.claude/notion-dev.config.json'); self.run_git('commit', '-qm', 'config fixture')
        key = self.reviewed(); self.resolve(key)
        prepared = self.rt.prepare('completeness', {}, self.repo, previous=key)
        packet = runtime.read_json(prepared['packet'])
        self.assertEqual(packet['result_contract']['version'], 3)
        self.assertNotIn('delta_publication', packet)

    def test_authorized_resume_changes_host_without_resetting_journal(self):
        self.new_schema(); self.config()
        pending = workflow.preflight(self.repo, 'new-host', True)
        with self.rt.transaction() as state:
            state['ticket_refresh'] = {'old': True}; state['ticket_refresh_request'] = {'old': True}
        before = runtime.read_json(self.state)
        workflow.resume_pr(self.repo, pending['marker'], 'TEST-1', self.state, self.root / 'removed', 'ticket/TEST-1', True)
        after = runtime.read_json(self.state)
        self.assertEqual(after['host_session'], 'new-host')
        self.assertEqual(after['workers'], before['workers'])
        self.assertEqual(after['record_journal'], before['record_journal'])
        self.assertNotIn('ticket_refresh', after); self.assertNotIn('ticket_refresh_request', after)

    def test_merged_recovery_without_review_keeps_unknown_visible(self):
        self.new_schema(); self.config(); facts = self.facts()
        value = runtime.read_json(facts)
        for name in ('requirements', 'review', 'verification'): value.pop(name)
        runtime.atomic_json(facts, value)
        with self.assertRaisesRegex(workflow.Invalid, 'final accepted'): workflow.record_plan(self.state, facts)
        pending = workflow.preflight(self.repo, 'fixture-session', True)
        workflow.resume_pr(self.repo, pending['marker'], 'TEST-1', self.state, self.root / 'removed', 'ticket/TEST-1', True)
        workflow.record_plan(self.state, facts)
        self.assertEqual(workflow.record_view(self.state, 'review')['data']['status'], 'unknown')
        self.assertIn('Unknown:', workflow.record_view(self.state, 'release_obligations')['data'][0])

    def test_takeover_makes_previous_session_capture_not_ready(self):
        self.capture()
        self.assertTrue(self.rt.ready()['passed'])
        with self.rt.transaction() as state: state['host_session'] = 'new-host'
        self.assertIn('ticket source predates this host session', self.rt.ready()['reasons'][0])

    def test_takeover_cannot_record_from_previous_session_capture(self):
        self.capture(); facts = self.facts()
        value = runtime.read_json(facts)
        for name in ('requirements', 'review', 'verification'): value.pop(name)
        runtime.atomic_json(facts, value)
        pending = workflow.preflight(self.repo, 'new-host', True)
        workflow.resume_pr(self.repo, pending['marker'], 'TEST-1', self.state, self.root / 'removed', 'ticket/TEST-1', True)
        with self.assertRaisesRegex(workflow.Invalid, 'predates this host session'):
            workflow.record_plan(self.state, facts)
        fetched = runtime.read_json(self.fetch())
        self.rt.capture_ticket(self.log(fetched, 'recaptured', session='new-host'), 'new-host', 'recaptured',
                               self.repo / '.claude/notion-dev.config.json')
        workflow.record_plan(self.state, facts)

    def test_schema_five_claim_and_takeover_preserve_host_ownership(self):
        self.new_schema()
        handoffs.lean.LeanTests.test_claim_and_stopped_resume_keep_identity_and_do_not_steal_live_runs(self)
        self.assertEqual(runtime.read_json(self.state)['host_session'], 'second-host')

    def test_no_epic_does_not_require_invented_provider_writes(self):
        _, _, plan = self.record()
        self.assertFalse(plan['epic-record']['requires_children'])

    def test_invalid_hook_plan_is_rejected_before_freezing_manifest(self):
        _, _, plan = self.record(); parent = plan['post-merge-hooks']['operation']
        with self.assertRaisesRegex(workflow.Invalid, 'argv strings'):
            self.child(parent, {'local_command': {'argv': 'shell string', 'cwd': str(self.repo)}})
        manifest = workflow.child_payload_path(self.state.parent / 'record', parent + ':manifest')
        self.assertFalse(manifest.exists())

    def record(self):
        self.new_schema(); key = self.reviewed(); path = self.facts()
        facts = runtime.read_json(path)
        for name in ('requirements', 'review', 'verification'): facts.pop(name)
        facts['hooks'] = ['explicit-local-fixture']
        runtime.atomic_json(path, facts)
        plan = workflow.record_plan(self.state, path, key)
        return key, path, {p['kind']: p for p in plan['operations']}

    def child(self, parent, data):
        manifest = self.root / 'writes.json'
        runtime.atomic_json(manifest, [{'name': 'one', 'target': 'fixture-target', 'data': data}])
        workflow.record_children(self.state, parent, manifest)
        return parent + ':child:one'

    def test_record_plan_selects_canonical_worker_not_consume_wrapper(self):
        key, path, plan = self.record()
        view = workflow.record_view(self.state, 'review')['data']
        canonical = runtime.read_json(self.state)['workers'][key]['result']
        self.assertEqual(view, {k: v for k, v in canonical.items() if k != 'report'})
        self.assertNotIn('worker', view)
        self.assertEqual(workflow.record_view(self.state, 'review', 'recording')['data'], canonical['recording'])
        with self.assertRaisesRegex(workflow.Invalid, 'final accepted'): workflow.record_plan(self.state, path, 'foreign')
        facts = runtime.read_json(path); facts['review'] = {'worker': key, 'result': canonical}; runtime.atomic_json(path, facts)
        with self.assertRaisesRegex(workflow.Invalid, 'do not copy'): workflow.record_plan(self.state, path, key)

    def test_record_next_is_scoped_and_unknown_outcome_never_replays(self):
        _, _, plan = self.record()
        self.assertEqual(workflow.record_next(self.state)['action'], 'plan-children')
        operation = self.child(plan['ticket-status']['operation'], {'host_call': {'name': 'ProviderWrite', 'input': {'status': 'done'}}})
        next_op = workflow.record_next(self.state, begin=True)
        self.assertEqual(next_op['operation'], operation)
        self.assertEqual(next_op['data'], {'host_call': {'name': 'ProviderWrite', 'input': {'status': 'done'}}})
        self.assertEqual(workflow.record_next(self.state, begin=True)['action'], 'reconcile')
        with self.assertRaisesRegex(workflow.Invalid, 'actual host receipt'):
            workflow.record_outcome(self.state, operation, 'confirmed', 'guessed')

    def test_host_receipt_binds_session_arguments_and_write_ahead(self):
        _, _, plan = self.record(); args = {'status': 'done'}
        operation = self.child(plan['ticket-status']['operation'], {'host_call': {'name': 'ProviderWrite', 'input': args}})
        workflow.record_input(self.state, operation, begin=True)
        # workflow uses the real clock; construct a host record just after begin.
        wall = runtime.read_json(self.state)['record_journal'][-1]['wall']
        self.clock.seconds = wall - 1790000000
        before = self.log({'ok': True}, name='ProviderWrite', args=args, offset=-1)
        with self.assertRaisesRegex(workflow.Invalid, 'predates'): workflow.record_receipt(self.state, operation, before, 'fixture-session', 'actual-1')
        wrong = self.log({'ok': True}, name='ProviderWrite', args={'status': 'wrong'}, offset=0)
        with self.assertRaisesRegex(workflow.Invalid, 'arguments'): workflow.record_receipt(self.state, operation, wrong, 'fixture-session', 'actual-1')
        self.clock.seconds = datetime.now(timezone.utc).timestamp() - 1790000000
        correct = self.log({'ok': True}, name='ProviderWrite', args=args, offset=0)
        workflow.record_receipt(self.state, operation, correct, 'fixture-session')
        workflow.record_outcome(self.state, operation, 'confirmed', 'provider-readback')
        self.assertEqual(workflow.record_next(self.state)['action'], 'confirm-children')

    def test_duplicate_writes_after_one_begin_require_reconciliation(self):
        _, _, plan = self.record(); args = {'status': 'done'}
        operation = self.child(plan['ticket-status']['operation'], {'host_call': {'name': 'ProviderWrite', 'input': args}})
        workflow.record_input(self.state, operation, begin=True)
        self.clock.seconds = datetime.now(timezone.utc).timestamp() - 1790000000
        first = self.log({'ok': None}, 'first', name='ProviderWrite', args=args, offset=0)
        second = self.log({'ok': True}, 'second', name='ProviderWrite', args=args, offset=0)
        first.write_bytes(first.read_bytes() + second.read_bytes())
        for call_id in (None, 'second'):
            with self.assertRaisesRegex(workflow.Invalid, 'multiple matching'):
                workflow.record_receipt(self.state, operation, first, 'fixture-session', call_id)

    def test_unjournaled_effect_is_explicit_reconciliation_not_fake_begin(self):
        _, _, plan = self.record()
        operation = self.child(plan['ticket-status']['operation'], {'host_call': {'name': 'ProviderWrite', 'input': {}}})
        workflow.record_observed(self.state, operation, 'existing provider effect read back')
        self.assertEqual(workflow.record_input(self.state, operation, begin=True)['action'], 'reconcile')
        workflow.record_outcome(self.state, operation, 'confirmed', 'verified readback')
        entries = [e for e in runtime.read_json(self.state)['record_journal'] if e['operation'] == operation]
        self.assertNotIn('attempted', [e['outcome'] for e in entries])

    def test_observation_after_begin_cannot_bypass_host_receipt(self):
        _, _, plan = self.record()
        operation = self.child(plan['ticket-status']['operation'], {'host_call': {'name': 'ProviderWrite', 'input': {}}})
        workflow.record_input(self.state, operation, begin=True)
        with self.assertRaisesRegex(workflow.Invalid, 'before begin'):
            workflow.record_observed(self.state, operation, 'claimed readback')
        with self.assertRaisesRegex(workflow.Invalid, 'actual host receipt'):
            workflow.record_outcome(self.state, operation, 'confirmed', 'claimed readback')

    def test_retry_cannot_reuse_previous_attempt_receipt(self):
        _, _, plan = self.record(); args = {'status': 'done'}
        operation = self.child(plan['ticket-status']['operation'], {'host_call': {'name': 'ProviderWrite', 'input': args}})
        workflow.record_input(self.state, operation, begin=True)
        self.clock.seconds = datetime.now(timezone.utc).timestamp() - 1790000000
        log = self.log({'ok': False}, name='ProviderWrite', args=args, offset=0)
        workflow.record_receipt(self.state, operation, log, 'fixture-session', 'actual-1')
        workflow.record_outcome(self.state, operation, 'failed', 'provider confirms no write')
        workflow.record_input(self.state, operation, begin=True)
        with self.assertRaisesRegex(workflow.Invalid, 'actual host receipt'):
            workflow.record_outcome(self.state, operation, 'confirmed', 'old response')

    def test_reconciled_history_does_not_authorize_later_retry(self):
        _, _, plan = self.record()
        operation = self.child(plan['ticket-status']['operation'], {'host_call': {'name': 'ProviderWrite', 'input': {}}})
        workflow.record_observed(self.state, operation, 'inspect possible effect')
        workflow.record_outcome(self.state, operation, 'failed', 'readback confirms absence')
        workflow.record_input(self.state, operation, begin=True)
        with self.assertRaisesRegex(workflow.Invalid, 'actual host receipt'):
            workflow.record_outcome(self.state, operation, 'confirmed', 'unproven retry')

    def test_local_hook_begins_before_execution_and_runs_only_once(self):
        _, _, plan = self.record()
        out = self.root / 'quoted café output.txt'
        code = 'import pathlib; pathlib.Path(__import__("sys").argv[1]).write_text("executed", encoding="utf-8")'
        operation = self.child(plan['post-merge-hooks']['operation'], {'local_command': {'argv': [sys.executable, '-c', code, str(out)], 'cwd': str(self.repo)}})
        original = subprocess.run
        def observed(*args, **kwargs):
            self.assertEqual(workflow.record_input(self.state, operation)['action'], 'reconcile')
            return original(*args, **kwargs)
        with patch.object(workflow.subprocess, 'run', side_effect=observed):
            self.assertTrue(workflow.record_run(self.state, operation)['passed'])
        self.assertEqual(out.read_text(), 'executed')
        with patch.object(workflow.subprocess, 'run', side_effect=AssertionError('replayed')):
            self.assertEqual(workflow.record_run(self.state, operation)['action'], 'skip')

    def test_local_hook_that_loses_the_begin_race_never_launches(self):
        _, _, plan = self.record()
        operation = self.child(plan['post-merge-hooks']['operation'], {'local_command': {'argv': [sys.executable, '-c', 'pass'], 'cwd': str(self.repo)}})
        original = workflow.record_input
        def racing(state, op, begin=False, field=None):
            if begin:
                original(state, op, begin=True)  # the other dispatcher wins first
            return original(state, op, begin=begin, field=field)
        with patch.object(workflow, 'record_input', side_effect=racing), \
                patch.object(workflow.subprocess, 'run', side_effect=AssertionError('launched twice')):
            with self.assertRaisesRegex(workflow.Invalid, 'another dispatcher'):
                workflow.record_run(self.state, operation)

    def test_failed_hook_with_possible_partial_effect_requires_reconciliation(self):
        _, _, plan = self.record()
        operation = self.child(plan['post-merge-hooks']['operation'], {'local_command': {'argv': [sys.executable, '-c', 'raise SystemExit(2)'], 'cwd': str(self.repo)}})
        self.assertFalse(workflow.record_run(self.state, operation)['passed'])
        self.assertEqual(workflow.record_run(self.state, operation)['action'], 'reconcile')

    def test_session_bridge_quotes_windows_paths_without_shell_execution(self):
        target = self.root / 'env'
        path = "C:\\Users\\O'Brien & cafe\\session.jsonl"
        with patch.dict(os.environ, {'CLAUDE_ENV_FILE': str(target)}), patch.object(sys, 'stdin', io.StringIO(json.dumps({'transcript_path': path}))):
            host_capture.session_env()
        proc = subprocess.run([runtime.bash_exe(), '-c', '. "$1"; printf "%s" "$NOTION_DEV_TRANSCRIPT"', 'fixture', str(target)], capture_output=True, check=True)
        self.assertEqual(proc.stdout.decode('utf-8'), path)

    def test_session_hook_and_capture_cli_preserve_native_paths_and_utf8(self):
        self.new_schema(); self.config()
        fetched = runtime.read_json(self.fetch()); fetched['title'] = 'Quoted café → value'
        original = self.log(fetched)
        transcript = self.root / "parent's café log.jsonl"
        original.rename(transcript)
        target = self.root / 'host env'
        env = {**os.environ, 'CLAUDE_ENV_FILE': str(target), 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'}
        subprocess.run([runtime.bash_exe(), str(ROOT / 'plugins/notion-dev/hooks/session-env.sh')],
            input=json.dumps({'session_id': 'fixture-session', 'cwd': str(self.repo), 'transcript_path': str(transcript)}),
            encoding='utf-8', capture_output=True, check=True, env=env)
        proc = subprocess.run([runtime.bash_exe(), '-c', '. "$1"; printf "%s\\n%s" "$NOTION_DEV_SESSION_ID" "$NOTION_DEV_TRANSCRIPT"',
            'fixture', str(target)], capture_output=True, check=True)
        session, path = proc.stdout.decode('utf-8').split('\n', 1)
        self.assertEqual(session, 'fixture-session'); self.assertEqual(path, str(transcript))
        env.update(NOTION_DEV_TRANSCRIPT=path, NOTION_DEV_SESSION_ID=session)
        proc = subprocess.run([sys.executable, str(ROOT / 'plugins/notion-dev/scripts/runtime.py'), '--state', str(self.state),
            'capture-ticket', '--page', 'a' * 32, '--config', str(self.repo / '.claude/notion-dev.config.json')],
            encoding='utf-8', capture_output=True, check=True, env=env)
        result = json.loads(proc.stdout)
        self.assertIn(fetched['title'], Path(result['source']).read_text(encoding='utf-8'))

    def test_version_four_report_does_not_repeat_structured_audits(self):
        self.new_schema(); key = self.prepare(); result = self.result()
        result['claims']['evidence'] = 'Distinctive full audit evidence ' * 200
        worker = runtime.read_json(self.state)['workers'][key]
        rendered = runtime.render_result(worker, result)
        self.assertEqual(rendered['claims'], result['claims'])
        self.assertNotIn(result['claims']['evidence'], rendered['report'])
        self.assertEqual(runtime.render_result(worker, rendered), rendered)
