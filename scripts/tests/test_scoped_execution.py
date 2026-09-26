"""Sanitized STO-159 failure shapes, not client-specific behavior or provider writes."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys
import unittest

import test_boundaries as boundaries
from test_lean_workflow import runtime, workflow, account_findings
import host_capture
import recording


class ScopedExecutionTests(unittest.TestCase):
    setUp = boundaries.BoundaryTests.setUp
    config = boundaries.BoundaryTests.config
    fetch = boundaries.BoundaryTests.fetch
    reviewed = boundaries.BoundaryTests.reviewed
    prepare = boundaries.BoundaryTests.prepare
    result = boundaries.BoundaryTests.result
    resolve = boundaries.BoundaryTests.resolve
    run_git = boundaries.BoundaryTests.run_git
    facts = boundaries.BoundaryTests.facts
    log = boundaries.BoundaryTests.log
    new_schema = boundaries.BoundaryTests.new_schema

    def plan_recording(self):
        self.new_schema(); self.config()
        key = self.prepare()
        result = self.result()
        result['recording']['release_obligations'] = ['Human approval still required before release.']
        result['recording']['claim_corrections'] = ['There are four outcomes, not three.']
        self.rt.publish(key, result); self.rt.consume(key); account_findings(self.rt, key); self.rt.accept(key)
        path = self.facts(); facts = runtime.read_json(path)
        for name in ('requirements', 'review', 'verification'): facts.pop(name)
        facts['ticket_url'] = 'https://app.notion.com/p/' + 'a' * 32
        runtime.atomic_json(path, facts)
        plan = workflow.record_plan(self.state, path, key)
        return {p['kind']: p for p in plan['operations']}

    def capture_recording(self, body=None):
        self.clock.seconds = datetime.now(timezone.utc).timestamp() - 1790000000
        response = runtime.read_json(self.fetch(body=body))
        log = self.log(response)
        return workflow.record_capture(self.state, log, 'fixture-session', 'a' * 32)['snapshot']

    def test_publication_kit_is_nonpassing_and_command_is_exact_on_native_paths(self):
        self.new_schema(); key = self.prepare()
        packet = runtime.read_json(runtime.read_json(self.state)['workers'][key]['packet'])
        kit = packet['publication']
        self.assertEqual(shlex.split(kit['command']), kit['argv'])
        self.assertEqual(kit['argv'][0], sys.executable)
        self.assertIn('do not try another writing tool', kit['host_return'])
        with self.assertRaises(runtime.Invalid): self.rt.publish(key, runtime.read_json(kit['submission']))
        # Supported host-return: parent stores the unchanged final JSON, never rewrites
        # the review or dispatches a replacement worker to fix the transport.
        returned = json.dumps(self.result(), ensure_ascii=False)
        runtime.atomic_json(kit['submission'], json.loads(returned))
        proc = subprocess.run(kit['argv'], capture_output=True, encoding='utf-8')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        locator = json.loads(proc.stdout)['artifact']
        self.assertEqual(Path(locator['path']).parent, Path(kit['result_directory']))
        self.assertEqual(runtime.digest(locator['path']), locator['sha256'])
        consumed = self.rt.consume(key, summary=True)
        self.assertNotIn('result', consumed)
        self.assertEqual(consumed['verdict_counts']['met'], len(self.inventory['items']))
        self.assertEqual(self.rt.result_view(key, 'requirements')['data'], self.result()['requirements'])
        self.assertEqual(len(runtime.read_json(self.state)['workers']), 1)

    def test_published_artifact_tampering_does_not_change_canonical_result(self):
        key = self.prepare(); published = self.rt.publish(key, self.result())
        runtime.atomic_json(published['artifact']['path'], {'report': 'fabricated'})
        with self.assertRaisesRegex(runtime.Invalid, 'artifact changed'): self.rt.result_view(key)
        self.assertEqual(runtime.read_json(self.state)['workers'][key]['result']['requirements'], self.result()['requirements'])

    def test_pr_only_delta_supplies_exact_hunks_and_preserves_all_reuse_candidates(self):
        self.new_schema()
        body = self.root / 'pr body café.md'; body.write_text('Four cases.\nOld test count.\n', encoding='utf-8')
        baseline = self.reviewed(inputs={'ticket': self.source, 'pr_body': body}); self.resolve(baseline)
        body.write_text('Four cases.\nCurrent verification receipt.\n', encoding='utf-8')
        prepared = self.rt.prepare('completeness', {'pr_body': body}, self.repo, previous=baseline)
        packet = runtime.read_json(prepared['packet']); index = runtime.read_json(packet['delta']['path'])
        inputs = runtime.read_json(runtime.Runtime.ref_path(index, index['inputs']))
        self.assertEqual(len(inputs['changes']), 1)
        self.assertEqual(inputs['changes'][0]['name'], 'pr_body')
        self.assertIn('-Old test count.', inputs['changes'][0]['diff'])
        self.assertIn('+Current verification receipt.', inputs['changes'][0]['diff'])
        self.assertEqual(index['evidence']['reuse_applicable'], len(self.inventory['items']))
        self.assertEqual(Path(runtime.Runtime.ref_path(index, index['patch'])).stat().st_size, 0)
        self.assertNotIn('workers', packet)
        self.assertIn('delta_result', runtime.read_json(packet['publication']['submission']))

    def test_changed_input_includes_add_remove_and_does_not_read_live_old_path(self):
        self.new_schema()
        old = self.root / 'old.txt'; old.write_text('frozen old\n', encoding='utf-8')
        key = self.reviewed(inputs={'ticket': self.source, 'removed': old}); self.resolve(key)
        old.write_text('changed after snapshot\n', encoding='utf-8')
        added = self.root / 'added.txt'; added.write_text('new\n', encoding='utf-8')
        prepared = self.rt.prepare('completeness', {'added': added}, self.repo, previous=key, remove_inputs=['removed'])
        packet = runtime.read_json(prepared['packet']); index = runtime.read_json(packet['delta']['path'])
        changes = runtime.read_json(runtime.Runtime.ref_path(index, index['inputs']))['changes']
        self.assertEqual({c['name'] for c in changes}, {'added', 'removed'})
        removed = next(c for c in changes if c['name'] == 'removed')
        self.assertIn('-frozen old', removed['diff'])
        self.assertNotIn('changed after snapshot', removed['diff'])

    def test_input_diff_keeps_records_distinct_without_trailing_newline(self):
        self.new_schema()
        body = self.root / 'body.md'; body.write_text('old', encoding='utf-8')
        key = self.reviewed(inputs={'ticket': self.source, 'pr_body': body}); self.resolve(key)
        body.write_text('new', encoding='utf-8')
        prepared = self.rt.prepare('completeness', {'pr_body': body}, self.repo, previous=key)
        index = runtime.read_json(runtime.read_json(prepared['packet'])['delta']['path'])
        diff = runtime.read_json(runtime.Runtime.ref_path(index, index['inputs']))['changes'][0]['diff']
        self.assertIn('\n-old\n\\ No newline at end of file\n+new\n', diff)

    def test_page_id_never_joins_a_hex_ending_slug_to_the_uuid(self):
        uuid = '0123456789abcdef0123456789abcdef'
        dashed = '01234567-89ab-cdef-0123-456789abcdef'
        for value in (uuid, dashed, 'https://www.notion.so/team/feature-scope-' + uuid, 'https://notion.so/cafe-' + dashed):
            self.assertEqual(recording.page_id(value), uuid)
        with self.assertRaisesRegex(Exception, 'one exact'): recording.page_id('https://notion.so/a-' + uuid + '?p=' + 'f' * 32)

    def test_stable_pr_renderer_preserves_disclosures_and_refuses_overwriting_human_body(self):
        facts = {'requirement': 'Exact requirement', 'behavior': ['Four outcomes.'], 'validation': ['See passing receipt.'],
                 'risks': ['Operator judgment required.'], 'mandatory': ['- [ ] Obtain release sign-off.']}
        source = self.root / 'facts café.json'; runtime.atomic_json(source, facts)
        target = self.root / 'PR body.md'
        first = workflow.render_pr_body(source, target)
        self.assertEqual(first, workflow.render_pr_body(source, target))
        self.assertIn('- [ ] Obtain release sign-off.', target.read_text(encoding='utf-8'))
        self.assertNotIn(b'\r', target.read_bytes())
        with self.assertRaises(ValueError): recording.pr_body({**facts, 'review_history': 'Round 1 passed'})
        target.write_text('human content', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'different content'): workflow.render_pr_body(source, target)
        self.assertEqual(target.read_text(), 'human content')

    def test_nested_transport_is_decoded_without_losing_unknown_page_fields(self):
        page = runtime.read_json(self.fetch()); page['unknown'] = {'value': '→ café "quotes" C:\\repo'}
        nested = [{'type': 'text', 'text': json.dumps({'content': [{'type': 'text', 'text': json.dumps(page)}]})}]
        self.assertEqual(host_capture.page_response(nested), page)
        for invalid in ({'isError': True, 'content': nested}, {'truncated': True, **page}, nested * 2):
            with self.assertRaises(ValueError): host_capture.page_response(invalid)

    def spilled_log(self, path=None, error=False):
        page = runtime.read_json(self.fetch())
        log = self.log(page, error=error)
        directory = log.with_suffix('') / 'tool-results'; directory.mkdir(parents=True, exist_ok=True)
        path = path or directory / 'mcp-notion-notion-fetch-123.txt'
        runtime.atomic_json(path, page)
        rows = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
        rows[1]['message']['content'][0]['content'] = ('Error: result (68,470 characters across 1 line) exceeds maximum allowed tokens. '
            'Output has been saved to ' + str(path) + '.\nFormat: Plain text\nHost directions are not executed.\n')
        log.write_bytes(b''.join((json.dumps(r) + '\n').encode('utf-8') for r in rows))
        return log, path, page

    def test_persisted_host_page_is_loaded_from_exact_session_without_model_decoding(self):
        log, path, page = self.spilled_log()
        value, observed = host_capture.notion_fetch(log, 'fixture-session', 'actual-1')
        self.assertEqual(value, page)
        self.assertEqual(observed['persisted_result']['sha256'], runtime.digest(path))
        path.write_bytes(b'{"partial":')
        with self.assertRaises(ValueError): host_capture.notion_fetch(log, 'fixture-session', 'actual-1')

    def test_persisted_path_does_not_allow_foreign_files_or_failed_results(self):
        log, _, _ = self.spilled_log(self.root / 'not-session-owned.txt')
        with self.assertRaisesRegex(ValueError, 'exact host session'): host_capture.notion_fetch(log, 'fixture-session', 'actual-1')
        log, _, _ = self.spilled_log(error=True)
        with self.assertRaisesRegex(ValueError, 'failed host'): host_capture.notion_fetch(log, 'fixture-session', 'actual-1')

    def test_status_builder_uses_config_and_existing_unknown_outcome_guard(self):
        plan = self.plan_recording(); config = self.repo / '.claude/notion-dev.config.json'
        value = runtime.read_json(config); value['ticketSystem']['statusMap'] = {'implemented': 'Ready for release'}
        runtime.atomic_json(config, value)
        snapshot = self.capture_recording()
        parent = plan['ticket-status']['operation']
        workflow.record_build(self.state, parent, config, snapshot)
        op = workflow.record_next(self.state, begin=True)
        self.assertEqual(op['data']['host_call']['input']['properties'], {'Status': 'Ready for release'})
        self.assertEqual(workflow.record_next(self.state, begin=True)['action'], 'reconcile')
        with self.assertRaises(ValueError): workflow.record_outcome(self.state, op['operation'], 'confirmed', 'invented')

    def test_status_builder_does_not_overwrite_a_human_terminal_transition(self):
        config = self.config()
        for status in ('Done', 'Cancelled'):
            page = recording.page_data(runtime.read_json(self.fetch(status=status)))
            with self.assertRaisesRegex(ValueError, 'never regress'):
                recording.build_writes('ticket-status', 'a' * 32, {}, config, page, {})

    def test_record_builder_rejects_wrong_page_and_capture_tampering(self):
        plan = self.plan_recording(); snapshot = self.capture_recording()
        config = self.repo / '.claude/notion-dev.config.json'; parent = plan['ticket-status']['operation']
        value = runtime.read_json(snapshot); value['page']['page'] = 'b' * 32; runtime.atomic_json(snapshot, value)
        with self.assertRaisesRegex(ValueError, 'unchanged host'): workflow.record_build(self.state, parent, config, snapshot)
        page = recording.page_data(runtime.read_json(self.fetch(page='b' * 32)))
        with self.assertRaisesRegex(ValueError, 'another target'):
            recording.build_writes('ticket-status', 'a' * 32, {}, runtime.read_json(config), page, {})

    def test_record_capture_rejects_foreign_session_old_fetch_and_failed_response(self):
        self.plan_recording(); self.capture_recording()
        response = runtime.read_json(self.fetch())
        for log, session in ((self.log(response, session='foreign'), 'foreign'),
                             (self.log(response, offset=-301), 'fixture-session'),
                             (self.log(response, error=True), 'fixture-session')):
            with self.assertRaises(ValueError): workflow.record_capture(self.state, log, session, 'a' * 32)

    def test_stale_capture_cannot_freeze_a_new_write_set(self):
        plan = self.plan_recording(); snapshot = self.capture_recording()
        with workflow.Runtime(self.state).transaction() as state:
            state['record_captures'][str(Path(snapshot).resolve())]['fetched_at'] -= 301
        with self.assertRaisesRegex(ValueError, 'capture stale'):
            workflow.record_build(self.state, plan['ticket-status']['operation'],
                                  self.repo / '.claude/notion-dev.config.json', snapshot)
        self.assertNotIn('record_child_sets', runtime.read_json(self.state))

    def test_flat_host_recipes_freeze_the_same_protocol_and_reject_mixed_shapes(self):
        plan = self.plan_recording(); parent = plan['epic-record']['operation']
        source = self.root / 'recipes.json'
        recipe = {'name': 'authorized-followup', 'target': 'configured-database',
                  'tool': 'mcp__notion__notion-create-pages',
                  'input': {'pages': [{'properties': {'Title': 'Approved café "follow-up"'}, 'content': 'Authorized facts.'}]}}
        runtime.atomic_json(source, [recipe])
        result = workflow.record_children(self.state, parent, source)
        op = result['children'][0]['operation']
        self.assertEqual(workflow.record_input(self.state, op)['data'],
                         {'host_call': {'name': recipe['tool'], 'input': recipe['input']}})
        runtime.atomic_json(source, [{'name': recipe['name'], 'target': recipe['target'],
                                    'data': {'host_call': {'name': recipe['tool'], 'input': recipe['input']}}}])
        workflow.record_children(self.state, parent, source)  # normalized retry is identical
        runtime.atomic_json(source, [{**recipe, 'data': {}}])
        with self.assertRaisesRegex(ValueError, 'mixed payload'): workflow.record_children(self.state, parent, source)

    def test_recording_cli_outputs_unicode_and_native_paths_without_shell_escaping(self):
        self.plan_recording(); self.capture_recording()
        transcript = self.log(runtime.read_json(self.fetch()), call_id='cli-café')
        proc = subprocess.run([sys.executable, str(Path(workflow.__file__)), 'record-capture',
                               '--state', str(self.state), '--page', 'a' * 32,
                               '--transcript', str(transcript), '--session', 'fixture-session'],
                              capture_output=True, encoding='utf-8')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        snapshot = Path(json.loads(proc.stdout)['snapshot'])
        self.assertTrue(snapshot.is_file())
        self.assertEqual(runtime.read_json(snapshot)['host']['transcript'], str(transcript.resolve()))

    def test_record_page_is_complete_scoped_and_absence_is_explicit(self):
        self.plan_recording()
        snapshot = self.capture_recording('## Tasks {color="blue"}\nAll task rows.\n## Notes\nKeep private unrelated notes.\n')
        index = workflow.record_page(self.state, snapshot)
        self.assertEqual(index['headings'], ['Tasks', 'Notes'])
        self.assertNotIn('content', index)
        section = workflow.record_page(self.state, snapshot, 'Tasks')
        self.assertEqual(section['content'], '## Tasks {color="blue"}\nAll task rows.\n')
        self.assertFalse(workflow.record_page(self.state, snapshot, 'Absent')['present'])

    def test_legacy_array_review_stays_available_without_a_scoped_view_crash(self):
        with self.rt.transaction() as state: state['schema'] = 4
        facts = self.facts(); value = runtime.read_json(facts)
        value['review'] = [{'legacy_obligation': 'Needs explicit reconciliation.'}]
        runtime.atomic_json(facts, value)
        plan = workflow.record_plan(self.state, facts)
        status = next(p for p in plan['operations'] if p['kind'] == 'ticket-status')
        workflow.record_input(self.state, status['operation'], begin=True)
        workflow.record_outcome(self.state, status['operation'], 'confirmed', 'fixture readback')
        next_op = workflow.record_next(self.state)
        self.assertEqual(next_op['data']['recording']['status'], 'unknown')
        self.assertEqual(workflow.record_view(self.state, 'review')['data'], value['review'])

    def test_resolution_builder_batches_sections_preserving_human_content_and_release_obligations(self):
        plan = self.plan_recording()
        body = '## Implementation {color="red"}\nHuman prerequisite: contact owner.\n\n## Notes\nKeep this note.\n'
        snapshot = self.capture_recording(body)
        built = workflow.record_build(self.state, plan['ticket-resolution']['operation'],
                                      self.repo / '.claude/notion-dev.config.json', snapshot)
        writes = runtime.read_json(built['writes'])
        self.assertEqual(len(writes), 2)
        update = writes[0]['data']['host_call']['input']['content_updates'][0]
        self.assertIn('{color="red"}', update['new_str'])
        self.assertIn('Human prerequisite: contact owner.', update['new_str'])
        self.assertIn('Human approval still required', update['new_str'])
        self.assertIn('four outcomes, not three', update['new_str'])
        self.assertNotIn('## Notes', update['old_str'])
        self.assertIn('## Merged', writes[1]['data']['host_call']['input']['content'])

    def test_acceptance_ticks_only_exact_source_text_and_never_swallows_human_sections(self):
        inventory = {'items': [{'id': 'AC1', 'kind': 'acceptance', 'text': 'Exact criterion.'}]}
        review = {'requirements': [{'id': 'AC1', 'verdict': 'met'}]}
        body = '## Acceptance Criteria\n- [ ] Exact criterion.\n## Notes\nUntouched.\n'
        self.assertEqual(recording.acceptance_edits(body, inventory, review),
                         [{'old_str': '- [ ] Exact criterion.', 'new_str': '- [x] Exact criterion.'}])
        with self.assertRaises(ValueError): recording.acceptance_edits(body.replace('Exact', 'Paraphrased'), inventory, review)
        review['requirements'][0]['verdict'] = 'unverified'
        self.assertEqual(recording.acceptance_edits(body, inventory, review), [])
        self.assertEqual(recording.acceptance_edits(body.replace('[ ]', '[x]'), inventory, review), [])

    def test_section_parser_ignores_fenced_examples_and_rejects_ambiguous_headings(self):
        body = '```markdown\n## Implementation\nexample\n```\n## Notes\nHuman note\n'
        self.assertEqual(recording.section_edits(body, {'Implementation': 'new facts'})[0]['command'], 'insert_content')
        with self.assertRaises(ValueError): recording.section_edits('## Notes\na\n## Notes\nb\n', {'Notes': 'new'})
        with self.assertRaises(ValueError): recording.section_edits('## Notes\na\n', {'Notes': '## Other\nx'})
        with self.assertRaises(ValueError): recording.section_edits('## Notes\na\n', {'Notes': 'a'})


if __name__ == '__main__':
    unittest.main()
