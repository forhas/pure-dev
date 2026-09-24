"""Sanitized two-host failure replays. No network, credentials or provider writes."""
import copy
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_boundaries as boundaries
from test_lean_workflow import runtime, workflow
import recording
import knowledge


class ConvergenceTests(unittest.TestCase):
    setUp = boundaries.BoundaryTests.setUp
    config = boundaries.BoundaryTests.config
    fetch = boundaries.BoundaryTests.fetch
    prepare = boundaries.BoundaryTests.prepare
    result = boundaries.BoundaryTests.result
    reviewed = boundaries.BoundaryTests.reviewed
    resolve = boundaries.BoundaryTests.resolve
    run_git = boundaries.BoundaryTests.run_git
    facts = boundaries.BoundaryTests.facts
    new_schema = boundaries.BoundaryTests.new_schema
    record = boundaries.BoundaryTests.record
    child = boundaries.BoundaryTests.child
    log = boundaries.BoundaryTests.log

    def verified_project(self):
        self.new_schema()
        config = self.config()
        config['verify']['steps'][0].update(cmd="printf 'measured café' > report.json", outputs=['report.json'])
        runtime.atomic_json(self.repo / '.claude/notion-dev.config.json', config)
        (self.repo / '.gitignore').write_text('report.json\n', encoding='utf-8')
        self.run_git('add', '.'); self.run_git('commit', '-qm', 'verification setup')

    def test_outputs_are_archived_and_live_regeneration_does_not_destroy_review(self):
        self.verified_project()
        prepared = workflow.review_prepare(self.state, self.repo, self.repo, {'ticket': self.source})
        manifest = runtime.read_json(prepared['verification'])
        archived = manifest['receipts'][0]['outputs'][0]
        (self.repo / 'report.json').write_text('later coverage', encoding='utf-8')
        self.assertEqual(Path(archived['path']).read_text(encoding='utf-8'), 'measured café')
        state = runtime.read_json(self.state)
        self.assertEqual(runtime.Runtime.verification_reasons(state, manifest['verifications'], runtime.revision(self.repo)), [])
        Path(archived['path']).write_bytes(b'tampered')
        self.assertTrue(runtime.Runtime.verification_reasons(state, manifest['verifications'], runtime.revision(self.repo)))
        self.assertIn('verification archive missing or changed', ' '.join(self.rt.merge_gate(prepared['worker'], self.repo)['reasons']))

    def test_review_rejects_dirty_source_before_spending_verification(self):
        self.verified_project(); self.code.write_text('correction', encoding='utf-8')
        with patch.object(workflow, 'verify_config', side_effect=AssertionError('ran before commit')):
            with self.assertRaisesRegex(workflow.Invalid, 'commit'):
                workflow.review_prepare(self.state, self.repo, self.repo, {'ticket': self.source})

    def test_precommit_receipt_cannot_be_named_as_current_review_evidence(self):
        self.verified_project(); self.code.write_text('correction', encoding='utf-8')
        receipt = workflow.verify_config(self.state, self.repo, self.repo)['receipts'][0]
        self.run_git('add', 'code.txt'); self.run_git('commit', '-qm', 'correction')
        with self.assertRaisesRegex(ValueError, 'named test log is stale'):
            workflow.review_prepare(self.state, self.repo, self.repo, {'ticket': self.source, 'test_log': receipt['log']})
        self.assertEqual(runtime.read_json(self.state)['workers'], {})

    def test_stale_output_is_not_archived_as_new_evidence(self):
        self.verified_project()
        (self.repo / 'report.json').write_text('old', encoding='utf-8')
        receipt = self.rt.verify(self.repo, 'printf pass', outputs=['report.json'])
        self.assertTrue(receipt['output_errors'])
        self.assertFalse(receipt['outputs'])
        self.assertTrue(runtime.Runtime.receipt_reusable(receipt, runtime.revision(self.repo), runtime.environment_signature()))

    def test_later_failed_or_different_measurement_invalidates_old_pass(self):
        self.verified_project()
        first = self.rt.verify(self.repo, 'printf measured > report.json', outputs=['report.json'])
        state = runtime.read_json(self.state)
        failed = copy.deepcopy(first); failed.update(verification='later', exit_code=1)
        state['verifications'].append(failed)
        self.assertIn('later verification contradicted', ' '.join(runtime.Runtime.verification_reasons(state, [first['verification']], runtime.revision(self.repo))))
        failed['exit_code'] = 0; failed['outputs'][0]['sha256'] = 'changed'
        self.assertIn('generated evidence changed', ' '.join(runtime.Runtime.verification_reasons(state, [first['verification']], runtime.revision(self.repo))))

    def test_review_prepare_cli_uses_configured_steps_and_native_paths(self):
        self.verified_project()
        proc = subprocess.run([sys.executable, workflow.__file__, 'review-prepare', '--project', str(self.repo),
            '--worktree', str(self.repo), '--state', str(self.state), '--file', 'ticket=' + str(self.source)],
            capture_output=True, encoding='utf-8')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('verification_sha256', proc.stdout)

    def test_newer_failed_run_cannot_resurrect_older_cached_pass(self):
        self.verified_project()
        first = self.rt.verify(self.repo, 'printf measured')
        with self.rt.transaction() as state:
            state['verifications'].append({**copy.deepcopy(first), 'verification': 'later-failure', 'exit_code': 1})
        self.assertFalse(self.rt.verifications(self.repo)['verifications'][0]['reusable'])
        fresh = self.rt.verify(self.repo, 'printf measured', reuse=True)
        self.assertFalse(fresh['reused'])
        self.assertNotEqual(fresh['verification'], first['verification'])

    def write_and_readback(self, command='insert_content', difference='newline', body=None):
        _, _, plan = self.record()
        args = {'page_id': 'a' * 32, 'command': command}
        if command == 'insert_content': args.update(position={'type': 'end'}, content='Merged café → facts\n')
        else: args['content_updates'] = [{'old_str': '- [ ] verified', 'new_str': '- [x] verified'}]
        expected = {'name': 'mcp__notion__notion-update-page', 'input': args}
        operation = self.child(plan['ticket-resolution']['operation'], {'host_call': expected})
        workflow.record_input(self.state, operation, begin=True)
        actual = copy.deepcopy(args)
        if difference == 'newline': actual['content'] = actual['content'][:-1]
        elif difference == 'default': actual['allow_async'] = False
        self.clock.seconds = datetime.now(timezone.utc).timestamp() - 1790000000
        log = self.log({'page_id': 'a' * 32}, 'write', name=expected['name'], args=actual, offset=0)
        self.clock.seconds = datetime.now(timezone.utc).timestamp() - 1790000000
        response = runtime.read_json(self.fetch(body=body if body is not None else actual.get('content', '- [x] verified')))
        readback = self.log(response, 'readback', offset=0)
        log.write_bytes(log.read_bytes() + readback.read_bytes())
        return operation, log, expected

    def test_terminal_newline_reconciles_without_replaying_or_editing_journal_intent(self):
        operation, log, _ = self.write_and_readback()
        before = workflow.record_input(self.state, operation)['data_sha256']
        workflow.record_receipt(self.state, operation, log, 'fixture-session', 'write', 'readback')
        workflow.record_outcome(self.state, operation, 'confirmed', 'fresh exact readback')
        self.assertEqual(workflow.record_input(self.state, operation)['action'], 'skip')
        self.assertEqual(workflow.record_input(self.state, operation)['data_sha256'], before)
        self.assertEqual(sum(e['outcome'] == 'attempted' for e in runtime.read_json(self.state)['record_journal'] if e['operation'] == operation), 1)

    def test_extra_false_default_reconciles_without_unchecking_acceptance(self):
        operation, log, _ = self.write_and_readback('update_content', 'default')
        workflow.record_receipt(self.state, operation, log, 'fixture-session', 'write', 'readback')
        workflow.record_outcome(self.state, operation, 'confirmed', 'checkbox readback')
        self.assertEqual(len(log.read_text(encoding='utf-8').splitlines()), 4)

    def test_duplicate_or_missing_effect_stays_unknown(self):
        for body in ('absent', 'Merged café → facts\nMerged café → facts'):
            with self.subTest(body=body):
                # Independent fixture per scenario; never reset a real journal.
                if hasattr(self, '_used'): self.setUp()
                self._used = True
                operation, log, _ = self.write_and_readback(body=body)
                pending = workflow.record_receipt(self.state, operation, log, 'fixture-session', 'write', 'readback')
                self.assertEqual(pending['action'], 'judge-effect')
                with self.assertRaises(ValueError): workflow.record_outcome(self.state, operation, 'confirmed', 'unbound claim')
                self.assertEqual(workflow.record_input(self.state, operation, begin=True)['action'], 'reconcile')

    def test_reformatted_readback_needs_explicit_bound_adapter_judgment(self):
        operation, log, _ = self.write_and_readback(body='<callout>\n\tMerged café → facts\n</callout>')
        # This example actually has an exact substring; make presentation different.
        rows = log.read_text(encoding='utf-8').replace('Merged café → facts', 'Merged **café** → facts')
        # Alter only the fetched response, never the write request.
        original = log.read_text(encoding='utf-8').splitlines(True)
        original[-1] = rows.splitlines(True)[-1]; log.write_bytes(''.join(original).encode('utf-8'))
        pending = workflow.record_receipt(self.state, operation, log, 'fixture-session', 'write', 'readback')
        self.assertEqual(pending['action'], 'judge-effect')
        verdict = {k: pending[k] for k in ('intent_sha256', 'call_sha256', 'readback_sha256')}
        path = self.root / 'adapter.json'; runtime.atomic_json(path, {**verdict, 'verdict': 'matched', 'evidence': 'Read entire effect; provider bold formatting only; one occurrence.'})
        valid = runtime.read_json(path)
        for change in ({'readback_sha256': 'wrong'}, {'call_sha256': 'wrong'},
                       {'intent_sha256': 'wrong'}, {'verdict': 'unknown'}, {'evidence': ''}):
            runtime.atomic_json(path, {**valid, **change})
            with self.assertRaisesRegex(ValueError, 'adapter verdict'):
                workflow.record_receipt(self.state, operation, log, 'fixture-session', 'write', 'readback', path)
        runtime.atomic_json(path, valid)
        workflow.record_receipt(self.state, operation, log, 'fixture-session', 'write', 'readback', path)
        workflow.record_outcome(self.state, operation, 'confirmed', 'adapter verified fresh effect')

    def test_equivalence_does_not_hide_material_or_anchor_changes(self):
        operation, log, expected = self.write_and_readback('update_content', 'default')
        for change in ({'allow_async': True}, {'page_id': 'b' * 32},
                       {'content_updates': [{'old_str': 'wrong', 'new_str': '- [x] verified'}]}):
            actual = copy.deepcopy(expected); actual['input'].update(change)
            self.assertFalse(recording.equivalent_write(expected, actual))
        with self.assertRaises(ValueError): workflow.record_receipt(self.state, operation, log, 'foreign', 'write', 'readback')

    def test_exact_and_equivalent_duplicate_calls_cannot_choose_one_receipt(self):
        operation, log, expected = self.write_and_readback()
        extra = self.log({'page_id': 'a' * 32}, 'second', name=expected['name'], args=expected['input'], offset=0)
        log.write_bytes(log.read_bytes() + extra.read_bytes())
        with self.assertRaisesRegex(workflow.Invalid, 'multiple matching'):
            workflow.record_receipt(self.state, operation, log, 'fixture-session', 'write', 'readback')

    def test_reconciliation_requires_current_successful_target_readback(self):
        operation, log, _ = self.write_and_readback()
        response = runtime.read_json(self.fetch(body='Merged café → facts'))
        for name, value, options in (
                ('old', response, {'offset': -301}),
                ('failed', response, {'error': True}),
                ('foreign-page', {**response, 'text': response['text'].replace('a' * 32, 'b' * 32)}, {})):
            with self.subTest(name=name):
                readback = self.log(value, name, **options)
                combined = self.root / (name + '-combined.jsonl')
                combined.write_bytes(log.read_bytes() + readback.read_bytes())
                with self.assertRaises(ValueError):
                    workflow.record_receipt(self.state, operation, combined, 'fixture-session', 'write', name)

    def test_config_schema_accepts_declared_evidence_outputs(self):
        schema = runtime.read_json(boundaries.ROOT / 'plugins/notion-dev/schema/notion-dev.config.schema.json')
        output = schema['properties']['verify']['properties']['steps']['items']['properties']['outputs']
        self.assertEqual(output['type'], 'array')
        self.assertEqual(output['items'], {'type': 'string', 'minLength': 1})

    def test_recording_omits_duplicate_requirement_text_not_evidence_or_obligations(self):
        result = self.result(); result['recording']['release_obligations'] = ['Human release approval required.']
        facts = {'pr_url': 'https://example.invalid/pr/1', 'merge_sha': 'abc', 'base': 'main', 'merged_at': 'now', 'strategy': 'squash'}
        section = recording.ticket_sections(facts, self.inventory, result)['Implementation']
        self.assertNotIn(self.inventory['items'][0]['text'], section)
        for v in result['requirements']:
            self.assertIn(v['id'] + ' — met', section); self.assertIn(v['citation'], section)
        self.assertIn('Human release approval required.', section)
        self.assertFalse(recording.section_edits('', {'Implementation': section})[0]['content'].endswith('\n'))

    def test_progressive_schedule_does_not_claim_unknown_dependencies_are_ready(self):
        children = [{'key': 'TEST-' + str(i), 'id': i, 'title': 'candidate', 'status_class': 'open',
                     'blocked_by': [], 'dependencies_known': False} for i in (1, 2)]
        state = {'epic': {'key': 'TEST-9', 'status_class': 'open'}, 'children': children}
        knowledge._validate_state(state)
        ip, blocked, numbered, first, resolved = knowledge.derive_next(state, [])
        self.assertIsNone(first)
        text = '\n'.join(knowledge.render_next(state, ip, blocked, numbered, first, resolved, [], {}, 'today'))
        self.assertEqual(text.count('dependency check pending'), 2)
        children[1]['dependencies_known'] = True
        self.assertEqual(knowledge.derive_next(state, [])[3]['key'], 'TEST-2')
        children[1]['blocked_by'] = ['OTHER-1']
        self.assertIsNone(knowledge.derive_next(state, [])[3])
        state['external_statuses'] = {'OTHER-1': 'resolved'}
        self.assertEqual(knowledge.derive_next(state, [])[3]['key'], 'TEST-2')


if __name__ == '__main__': unittest.main()
