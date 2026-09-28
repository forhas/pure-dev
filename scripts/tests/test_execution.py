"""Sanitized execution/convergence regressions, run on native Windows and Ubuntu."""
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_convergence as convergence
from test_boundaries import typed_fixture
from test_lean_workflow import runtime, workflow, account_findings
import corrections
import execution
import record_recovery


class ExecutionTests(unittest.TestCase):
    setUp = convergence.ConvergenceTests.setUp
    config = convergence.ConvergenceTests.config
    fetch = convergence.ConvergenceTests.fetch
    prepare = convergence.ConvergenceTests.prepare
    result = convergence.ConvergenceTests.result
    reviewed = convergence.ConvergenceTests.reviewed
    resolve = convergence.ConvergenceTests.resolve
    run_git = convergence.ConvergenceTests.run_git
    facts = convergence.ConvergenceTests.facts
    new_schema = convergence.ConvergenceTests.new_schema
    record = convergence.ConvergenceTests.record
    child = convergence.ConvergenceTests.child
    log = convergence.ConvergenceTests.log

    def test_file_builder_preserves_unicode_under_cp1252_without_downstream_pipe(self):
        packet = self.root / 'packet café.json'
        runtime.atomic_json(packet, dict(title='Café — שלום', goal='Preserve · text', scope='generic',
            evidence='observed', provenance='approved finding', source='fixture', decision='file',
            requirements=[{'text': 'Exact UTF-8', 'facts': [1]}], acceptance=['No corruption'], edge_cases=[], dependencies=[], open_questions=[],
            verified_facts=[{'fact': 'observed', 'citation': 'fixture'}], premises_to_verify=[], hypothesis=[],
            blocks_goal={'value': 'yes', 'reason': 'goal item'}, destination='epic'))
        recipe = self.root / 'recipe.json'
        runtime.atomic_json(recipe, {'name': 'followup', 'target': 'database', 'title_property': 'Name',
            'tool': 'mcp__notion__notion-create-pages', 'input': {'parent': {'data_source_id': 'a' * 32},
                'pages': [{'properties': {'Status': 'Backlog'}}]}})
        output = self.root / 'payload café.json'
        proc = subprocess.run([sys.executable, workflow.__file__, 'followup-body', '--packet', str(packet),
            '--recipe', str(recipe), '--output', str(output)], capture_output=True, encoding='utf-8',
            env={**os.environ, 'PYTHONIOENCODING': 'cp1252', 'PYTHONUTF8': '0'})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        page = runtime.read_json(output)[0]['input']['pages'][0]
        self.assertEqual(page['properties']['Name'], 'Café — שלום')
        self.assertIn('Preserve · text', page['content'])
        self.assertNotIn(b'\r\n', output.read_bytes())
        self.assertEqual(json.loads(proc.stdout)['sha256'], runtime.digest(output))
        self.assertNotIn('Exact UTF-8', proc.stdout)  # Return a reference, not the payload again.
        changed = runtime.read_json(packet); changed['title'] = 'other'; runtime.atomic_json(packet, changed)
        with self.assertRaisesRegex(ValueError, 'different data'): execution.followup_file(packet, output, recipe)

    def knowledge_setup(self):
        self.config()
        folder = self.repo / 'knowledge'; folder.mkdir()
        (folder / 'concept.md').write_text('baseline', encoding='utf-8')
        self.run_git('add', '.'); self.run_git('commit', '-qm', 'knowledge baseline')
        owner = self.repo / '.claude/notion-dev/locks/primary/owner'
        owner.parent.mkdir(parents=True, exist_ok=True); owner.write_text('run: fixture\n', encoding='utf-8')
        (folder / 'concept.md').write_text('candidate café', encoding='utf-8')
        return folder, runtime.git(self.repo, 'branch', '--show-current')

    def checker(self, exit_code, change=None):
        original = subprocess.run
        def run(argv, **kwargs):
            if len(argv) > 1 and Path(argv[1]).name == 'knowledge.py':
                kwargs['stdout'].write(b'full producer diagnostics\n')
                if change: change()
                return subprocess.CompletedProcess(argv, exit_code)
            return original(argv, **kwargs)
        return patch.object(execution.subprocess, 'run', side_effect=run)

    def test_failing_producer_never_commits_even_when_output_formatter_would_succeed(self):
        folder, branch = self.knowledge_setup(); before = runtime.git(self.repo, 'rev-parse', 'HEAD')
        receipts = []
        for code in (1, 2):
            with self.checker(code): result = execution.knowledge_commit(self.repo, branch, 'fixture', 'docs: check')
            receipts.append(result)
            self.assertFalse(result['passed']); self.assertEqual(result['exit_code'], code)
            self.assertEqual(runtime.git(self.repo, 'rev-parse', 'HEAD'), before)
            self.assertEqual(Path(result['log']).read_bytes(), b'full producer diagnostics\n')
            self.assertEqual((folder / 'concept.md').read_text(encoding='utf-8'), 'candidate café')
        # A retry on an unchanged tree keeps the earlier attempt's audited log intact.
        self.assertNotEqual(receipts[0]['log'], receipts[1]['log'])
        self.assertEqual(runtime.digest(Path(receipts[0]['log'])), receipts[0]['log_sha256'])

    def test_successful_knowledge_commit_preserves_unrelated_staged_work(self):
        _, branch = self.knowledge_setup()
        other = self.repo / 'unrelated.txt'; other.write_text('user work', encoding='utf-8')
        self.run_git('add', 'unrelated.txt')
        with self.checker(0): result = execution.knowledge_commit(self.repo, branch, 'fixture', 'docs: checked')
        self.assertTrue(result['passed'])
        self.assertIn('A  unrelated.txt', runtime.git(self.repo, 'status', '--porcelain'))
        self.assertEqual(runtime.git(self.repo, 'show', '--format=', '--name-only', 'HEAD'), 'knowledge/concept.md')

    def test_knowledge_change_during_check_and_foreign_lock_block_commit(self):
        folder, branch = self.knowledge_setup(); before = runtime.git(self.repo, 'rev-parse', 'HEAD')
        with self.assertRaisesRegex(ValueError, 'lock'): execution.knowledge_commit(self.repo, branch, 'foreign', 'docs')
        with self.checker(0, lambda: (folder / 'concept.md').write_text('raced', encoding='utf-8')):
            with self.assertRaisesRegex(ValueError, 'changed during'): execution.knowledge_commit(self.repo, branch, 'fixture', 'docs')
        self.assertEqual(runtime.git(self.repo, 'rev-parse', 'HEAD'), before)

    def test_mutations_require_clean_committed_baseline(self):
        self.assertTrue(execution.mutation_baseline(self.repo)['passed'])
        self.code.write_text('uncommitted implementation', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'commit implementation'): execution.mutation_baseline(self.repo)
        self.assertEqual(self.code.read_text(encoding='utf-8'), 'uncommitted implementation')

    def test_wait_consumes_ready_result_without_mailbox_but_never_accepts(self):
        key = self.prepare('plan')
        with patch.object(runtime, 'Runtime', return_value=self.rt):
            pending = execution.await_worker(self.state, key, 0)
            self.assertFalse(pending['passed'])
            self.rt.publish(key, {'report': 'independent plan findings'})
            ready = execution.await_worker(self.state, key, 0)
        self.assertEqual(ready['action'], 'judge-result')
        self.assertEqual(self.rt.inspect(key)['status'], 'consumed')
        self.assertFalse(self.rt.inspect(key)['accepted'])
        self.assertEqual(len(runtime.read_json(self.state)['workers']), 1)

    def test_stage_guides_retain_complete_sections_without_loading_later_stages(self):
        intake = execution.guide('intake')
        self.assertIn('Inventory every mandatory', intake)
        self.assertNotIn('## Compact delta publication', intake)
        self.assertNotIn('## Canonical recording and execution', intake)
        for stage in execution.GUIDES: self.assertTrue(execution.guide(stage))

    def correction_setup(self):
        self.new_schema(); self.config()
        self.code.write_text('original\nretired claim\n', encoding='utf-8')
        self.run_git('add', '.'); self.run_git('commit', '-qm', 'baseline claim')
        key = self.prepare(); value = self.result()
        value['claims']['findings'] = [{'finding': 'retired claim in code and PR', 'disposition': 'absorb',
            'rationale': 'contradicted by evidence', 'obligation': 'mandatory', 'resolved': False, 'blocking': True}]
        self.rt.publish(key, value); self.rt.consume(key); account_findings(self.rt, key); self.rt.accept(key); self.resolve(key)
        files = typed_fixture(self, {'ticket': self.source})
        return key, files['review_inputs']

    def test_correction_batch_finds_missed_occurrence_and_rejects_stale_or_missing_accounting(self):
        key, inputs = self.correction_setup()
        generated = corrections.batch(self.state, key, self.repo, inputs)
        self.assertFalse(generated['passed'])
        path = Path(generated['checklist']); data = runtime.read_json(path)
        item = data['items'][0]; item.update(anchors=['retired claim'], locations=['input:pr_body', 'repo:code.txt'],
            disposition='corrected', evidence='corrected prose')
        runtime.atomic_json(path, data)
        checked = corrections.batch(self.state, key, self.repo, inputs, path)
        self.assertFalse(checked['passed'])
        self.assertEqual(checked['unresolved'][0]['source'], 'repo:code.txt')
        item['retained'] = {'repo:code.txt': 'quoted old wording in a negative regression fixture'}
        runtime.atomic_json(path, data)
        self.assertTrue(corrections.batch(self.state, key, self.repo, inputs, path)['passed'])
        missing = copy.deepcopy(data); missing['items'] = []; runtime.atomic_json(path, missing)
        with self.assertRaisesRegex(ValueError, 'every finding'): corrections.batch(self.state, key, self.repo, inputs, path)
        runtime.atomic_json(path, data); self.code.write_text('changed', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'stale'): corrections.batch(self.state, key, self.repo, inputs, path)

    def test_prepare_stops_before_verification_or_new_worker_on_missing_correction_batch(self):
        key, inputs = self.correction_setup(); before = len(runtime.read_json(self.state)['workers'])
        with patch('review_inputs.github', return_value={k: v for k, v in runtime.read_json(
                runtime.read_json(inputs)['files']['pr_body']['path']).items() if k not in {'kind', 'pr'}}), \
                patch.object(workflow, 'verify_config', side_effect=AssertionError('verification should not run')):
            result = workflow.review_prepare(self.state, self.repo, self.repo, {}, previous=key, inputs_file=inputs)
        self.assertEqual(result['action'], 'complete-correction-batch')
        self.assertEqual(len(runtime.read_json(self.state)['workers']), before)

    def test_checked_worksheet_does_not_become_inherited_authoritative_input(self):
        key, inputs = self.correction_setup()
        generated = corrections.batch(self.state, key, self.repo, inputs)
        path = Path(generated['checklist']); value = runtime.read_json(path)
        for item in value['items']:
            item.update(anchors=['retired claim'], disposition='not-applicable', evidence='quoted negative test',
                        retained={'repo:code.txt': 'old text remains intentionally quoted for a negative test'})
        runtime.atomic_json(path, value)
        observed = runtime.read_json(runtime.read_json(inputs)['files']['pr_body']['path'])
        with patch('review_inputs.github', return_value={k: v for k, v in observed.items() if k not in {'kind', 'pr'}}):
            prepared = workflow.review_prepare(self.state, self.repo, self.repo, {}, previous=key,
                inputs_file=inputs, corrections=path)
        self.assertTrue(prepared['passed'])
        self.assertEqual(prepared['correction_preflight']['sha256'], runtime.digest(path))
        worker = runtime.read_json(self.state)['workers'][prepared['worker']]
        self.assertNotIn('correction_batch', worker['files'])

    def test_scan_reports_dangling_tracked_symlink(self):
        try: os.symlink('missing-target', str(self.repo / 'dangling'))
        except (OSError, NotImplementedError): self.skipTest('symlinks unavailable on this host')
        self.run_git('add', 'dangling')
        _, excluded = corrections.sources(self.repo, {})
        self.assertEqual(excluded.get('repo:dangling'), 'symlink: missing-target')

    def test_scan_reports_tracked_path_absent_from_worktree(self):
        self.run_git('update-index', '--skip-worktree', 'code.txt'); (self.repo / 'code.txt').unlink()
        values, excluded = corrections.sources(self.repo, {})
        self.assertNotIn('repo:code.txt', values)
        self.assertIn('repo:code.txt', excluded)

    def test_scan_reports_uninitialized_submodules_without_crawling_dependencies(self):
        self.run_git('update-index', '--add', '--cacheinfo', '160000', runtime.git(self.repo, 'rev-parse', 'HEAD'), 'vendor/example')
        values, excluded = corrections.sources(self.repo, {})
        self.assertIn('repo:code.txt', values)
        self.assertIn('repo:vendor/example', excluded)
        self.assertNotIn('repo:vendor/example', values)

    def discrepancy_setup(self):
        _, _, plan = self.record()
        expected = {'parent': {'page_id': 'b' * 32}, 'pages': [
            {'properties': {'Name': 'A follow-up'}, 'content': 'Broken â€” text'}]}
        operation = self.child(plan['epic-record']['operation'], {'host_call': {
            'name': 'mcp__notion__notion-create-pages', 'input': expected}})
        workflow.record_input(self.state, operation, begin=True)
        self.clock.seconds = datetime.now(timezone.utc).timestamp() - 1790000000
        actual = copy.deepcopy(expected); actual['pages'][0]['content'] = 'Correct — text'
        transcript = self.log({'pages': [{'id': 'c' * 32}]}, 'create',
            name='mcp__notion__notion-create-pages', args=actual, offset=0)
        response = runtime.read_json(self.fetch('created.json', body='Correct — text', page='c' * 32))
        response['text'] = response['text'].replace('"Status":', '"Name": "A follow-up", "Status":', 1)
        fetched = self.log(response, 'readback', args={'id': 'c' * 32}, offset=0)
        transcript.write_bytes(transcript.read_bytes() + fetched.read_bytes())
        return operation, transcript, actual

    def recovery_approval(self, transcript, requested, role='user', content=None):
        row = {'type': role, 'uuid': 'human-decision', 'sessionId': 'fixture-session',
               'timestamp': datetime.now(timezone.utc).isoformat(),
               'message': {'role': role, 'content': content or requested['approval_phrase']}}
        transcript.write_bytes(transcript.read_bytes() + (json.dumps(row) + '\n').encode('utf-8'))

    def test_mismatched_create_quarantines_even_failed_and_recovery_never_replays(self):
        operation, transcript, actual = self.discrepancy_setup()
        with self.assertRaises(ValueError): workflow.record_receipt(self.state, operation, transcript, 'fixture-session')
        workflow.record_outcome(self.state, operation, 'failed', 'cannot bind receipt, but effect exists')
        self.assertEqual(workflow.record_input(self.state, operation, begin=True)['action'], 'reconcile')
        current = workflow.record_input(self.state, operation)
        with self.assertRaisesRegex(ValueError, 'discrepancy'):
            self.rt.record_op(operation, current['target'], 'attempted', data_sha256=current['data_sha256'])
        with self.assertRaisesRegex(ValueError, 'discrepancy'):
            self.rt.record_op(operation, current['target'], 'confirmed', 'guessed', current['data_sha256'])
        with self.assertRaisesRegex(ValueError, 'discrepancy'):
            workflow.record_outcome(self.state, operation, 'confirmed', 'not a recovery decision')
        before = copy.deepcopy(runtime.read_json(self.state)['record_journal'])
        request = record_recovery.request(self.state, operation, transcript, 'fixture-session', 'create', 'readback',
            'Accept the corrected Unicode text; complete readback matches the actual create, with original parent/properties.')
        with self.assertRaises(ValueError): record_recovery.approve(self.state, operation, transcript, 'fixture-session')
        self.recovery_approval(transcript, request)
        done = record_recovery.approve(self.state, operation, transcript, 'fixture-session')
        self.assertEqual(done['outcome'], 'accepted-discrepancy')
        after = runtime.read_json(self.state)['record_journal']
        self.assertEqual(after[:-1], before)
        self.assertEqual(workflow.record_input(self.state, operation, begin=True)['action'], 'skip')
        self.assertEqual(after[-1]['data_sha256'], before[-1]['data_sha256'])
        with self.assertRaises(ValueError): record_recovery.approve(self.state, operation, transcript, 'fixture-session')

    def test_failed_mismatched_create_stays_retryable_without_quarantine(self):
        _, _, plan = self.record()
        expected = {'parent': {'page_id': 'b' * 32}, 'pages': [{'properties': {'Name': 'A follow-up'}, 'content': 'text'}]}
        operation = self.child(plan['epic-record']['operation'], {'host_call': {
            'name': 'mcp__notion__notion-create-pages', 'input': expected}})
        workflow.record_input(self.state, operation, begin=True)
        self.clock.seconds = datetime.now(timezone.utc).timestamp() - 1790000000
        actual = copy.deepcopy(expected); actual['pages'][0]['content'] = 'other text'
        transcript = self.log({'error': 'rejected'}, 'create', name='mcp__notion__notion-create-pages',
                              args=actual, offset=0, error=True)
        with self.assertRaises(ValueError): workflow.record_receipt(self.state, operation, transcript, 'fixture-session')
        self.assertNotIn(operation, runtime.read_json(self.state).get('record_discrepancies', {}))
        workflow.record_outcome(self.state, operation, 'failed', 'provider rejected the call')
        self.assertEqual(workflow.record_input(self.state, operation, begin=True)['action'], 'execute')

    def test_wrong_call_id_still_quarantines_observed_post_begin_create(self):
        operation, transcript, _ = self.discrepancy_setup()
        with self.assertRaises(ValueError):
            workflow.record_receipt(self.state, operation, transcript, 'fixture-session', call_id='stale-id')
        self.assertIn(operation, runtime.read_json(self.state).get('record_discrepancies', {}))
        workflow.record_outcome(self.state, operation, 'failed', 'wrong id supplied')
        self.assertEqual(workflow.record_input(self.state, operation, begin=True)['action'], 'reconcile')

    def test_recovery_rejects_agent_approval_changed_evidence_and_duplicate_creates(self):
        operation, transcript, actual = self.discrepancy_setup()
        request = record_recovery.request(self.state, operation, transcript, 'fixture-session', 'create', 'readback', 'difference checked')
        self.recovery_approval(transcript, request, role='assistant')
        with self.assertRaises(ValueError): record_recovery.approve(self.state, operation, transcript, 'fixture-session')
        saved = Path(request['evidence']); original = saved.read_bytes(); saved.write_bytes(original + b' ')
        with self.assertRaisesRegex(ValueError, 'evidence changed'): record_recovery.approve(self.state, operation, transcript, 'fixture-session')
        saved.write_bytes(original)
        extra = self.log({'pages': [{'id': 'd' * 32}]}, 'duplicate',
            name='mcp__notion__notion-create-pages', args=actual, offset=0)
        transcript.write_bytes(transcript.read_bytes() + extra.read_bytes())
        with self.assertRaisesRegex(ValueError, 'multiple creates'):
            record_recovery.request(self.state, operation, transcript, 'fixture-session', 'create', 'readback', 'difference checked')

    def test_recovery_rejects_foreign_target_session_and_stale_readback(self):
        operation, transcript, actual = self.discrepancy_setup()
        requested = record_recovery.request(self.state, operation, transcript, 'fixture-session', 'create', 'readback', 'checked')
        self.recovery_approval(transcript, requested)
        self.clock.seconds += 601
        with patch.object(record_recovery, 'Runtime', return_value=self.rt):
            with self.assertRaisesRegex(ValueError, 'expired'):
                record_recovery.approve(self.state, operation, transcript, 'fixture-session')
        with self.assertRaisesRegex(ValueError, 'foreign'):
            record_recovery.request(self.state, operation, transcript, 'foreign', 'create', 'readback', 'checked')
        rows = [json.loads(r) for r in transcript.read_text(encoding='utf-8').splitlines()]
        rows[0]['message']['content'][0]['input']['parent']['page_id'] = 'd' * 32
        transcript.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'retargeting'):
            record_recovery.request(self.state, operation, transcript, 'fixture-session', 'create', 'readback', 'checked')

    def test_recording_resume_uses_old_write_evidence_but_new_session_authority(self):
        operation, original, _ = self.discrepancy_setup()
        with self.rt.transaction() as data: data['host_session'] = 'new-owner'
        response = runtime.read_json(self.fetch('new-readback.json', body='Correct — text', page='c' * 32))
        response['text'] = response['text'].replace('"Status":', '"Name": "A follow-up", "Status":', 1)
        current = self.log(response, 'new-readback', session='new-owner', args={'id': 'c' * 32}, offset=0)
        requested = record_recovery.request(self.state, operation, current, 'new-owner', 'create', 'new-readback',
            'readback and corrected text checked', original, 'fixture-session')
        # Old-session approval cannot transfer even with the right phrase.
        self.recovery_approval(current, requested)
        with self.assertRaises(ValueError): record_recovery.approve(self.state, operation, current, 'new-owner')
        rows = [json.loads(r) for r in current.read_text(encoding='utf-8').splitlines()]
        rows[-1]['sessionId'] = 'new-owner'
        current.write_bytes(b''.join((json.dumps(r) + '\n').encode('utf-8') for r in rows))
        self.assertTrue(record_recovery.approve(self.state, operation, current, 'new-owner')['passed'])

    def test_text_recovery_does_not_waive_different_readback_properties(self):
        operation, transcript, _ = self.discrepancy_setup()
        rows = [json.loads(r) for r in transcript.read_text(encoding='utf-8').splitlines()]
        block = rows[-1]['message']['content'][0]['content'][0]
        block['text'] = block['text'].replace('A follow-up', 'Different title')
        transcript.write_bytes(b''.join((json.dumps(r) + '\n').encode('utf-8') for r in rows))
        with self.assertRaisesRegex(ValueError, 'readback properties'):
            record_recovery.request(self.state, operation, transcript, 'fixture-session', 'create', 'readback', 'checked')


if __name__ == '__main__': unittest.main()
