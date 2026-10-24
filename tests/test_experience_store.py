"""Synthetic protocol checks. Host confirmation and technical verification are simulated."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import experience_store as m


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='经验 测试 ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / '私有 root'
        self.inv = self.begin('session-1')

    def call(self, action, **kwargs):
        return m.execute(dict(action=action, **kwargs), self.root)

    def begin(self, session, **extra):
        return self.call('begin', host='synthetic', native_session_id=session, task_id='task-1',
                         explicit_use_ref='synthetic:explicit-skill-use',
                         materials_read={'refs': ['synthetic:task/template/rubric'], 'constraints': {'template': 'v1'}}, **extra)

    def collect(self, record='event-1', **extra):
        value = dict(invocation_id=self.inv['invocation_id'], source={'provider': 'original', 'namespace': 'test', 'record_id': record, 'revision': '1'},
                     event_type='correction', payload={'text': 'Synthetic original observation'},
                     occurred_at='2026-10-24T10:00:00+08:00', origin='experiment', source_lineage='execution-1', verification_run_id='run-1')
        value.update(extra)
        return self.call('collect', **value)['event_id']

    def draft(self, refs, **extra):
        value = dict(kind='method', scope={'template': 'v1'}, source_refs=refs,
                     verification={'status': 'verified', 'verifier': 'synthetic-independent', 'independent': True,
                                   'evidence_refs': ['synthetic:original-run']},
                     sections={h: 'Synthetic ' + h for h in m.BODY_FIELDS})
        value.update(extra)
        return value

    def candidate(self, record='event-1', **extra):
        eid = self.collect(record)
        return self.call('consolidate', invocation_id=self.inv['invocation_id'], candidates=[self.draft([eid], **extra)])['candidates'][0]

    def display(self, ref, operation='activate', management=True):
        return self.call('display', invocation_id=self.inv['invocation_id'],
                         items=[dict(ref, operation=operation)], **({'management_ref': 'synthetic:immediate-user-management'} if management else {}))

    def confirm(self, display, decisions=None):
        decisions = decisions or [{k: x[k] for k in ('id', 'revision', 'content_digest', 'operation')} for x in display['items']]
        return self.call('confirm', display_id=display['display_id'], decisions=decisions,
                         host_check=dict(checked_by='synthetic-host', message_ref='synthetic:explicit-response',
                                         message_digest=m.sha('synthetic user message'), matched_display_digest=display['display_digest'],
                                         decisions_digest=m.sha(decisions)))

    def decide(self, ref, operation='activate'):
        return self.call('consume', **self.confirm(self.display(ref, operation)))

    def query(self, **extra):
        return self.call('query', context={'template': 'v1'}, invocation_id=self.inv['invocation_id'], **extra)

    def registry(self):
        return m.read(self.root / 'registry.json')

    def test_candidates_wait_for_next_explicit_begin(self):
        ref = self.candidate()
        self.assertFalse(self.query()['items'])
        with self.assertRaisesRegex(m.MemoryError, 'later explicit'):
            self.display(ref, management=False)
        self.inv = self.begin('session-2')
        display = self.display(ref, management=False)
        self.assertEqual(display['items'][0]['status'], 'candidate')
        self.assertEqual(self.call('consume', **self.confirm(display))['applied'], [m.key(ref)])
        self.assertEqual(len(self.query()['items']), 1)

    def test_identity_resume_and_materials_first(self):
        again = self.begin('session-1')
        self.assertEqual(self.inv['invocation_id'], again['invocation_id'])
        resumed = self.begin('session-1', resume=True, invocation_id=self.inv['invocation_id'])
        self.assertEqual(again, resumed)
        with self.assertRaises(m.MemoryError):
            self.begin('other', resume=True, invocation_id=self.inv['invocation_id'])
        with self.assertRaises(m.MemoryError):
            self.call('begin', task_id='t', session_token='s', explicit_use_ref='u')

    def test_event_retry_conflict_and_summary_excluded(self):
        eid = self.collect()
        self.assertEqual(eid, self.collect(payload={'text': 'Synthetic original observation', 'retry_count': 9, 'adapter_summary': 'another summary'}))
        with self.assertRaisesRegex(m.MemoryError, 'conflicting'):
            self.collect(payload={'text': 'changed actual content'})
        self.assertEqual(self.call('consolidate', invocation_id=self.inv['invocation_id'])['new_events'], 1)
        self.assertEqual(self.call('consolidate', invocation_id=self.inv['invocation_id'])['new_events'], 0)

    def test_partial_tail_and_no_session_end_recovery(self):
        self.collect()
        journal = next((self.root / 'sessions').glob('*/collection_events.jsonl'))
        with open(journal, 'ab') as f:
            f.write(b'{"incomplete":')
        self.assertEqual(self.call('consolidate', invocation_id=self.inv['invocation_id'])['new_events'], 1)
        self.assertTrue(list(journal.parent.glob('incomplete-*.bin')))
        self.collect('event-2')
        self.assertEqual(self.call('consolidate', invocation_id=self.inv['invocation_id'])['new_events'], 1)

    def test_approval_requires_bound_host_check_and_subset(self):
        first = self.candidate()
        second = self.candidate('event-2')
        display = self.call('display', invocation_id=self.inv['invocation_id'], management_ref='synthetic:user-management',
                            items=[dict(first, operation='activate'), dict(second, operation='activate')])
        with self.assertRaises(m.MemoryError):
            self.call('confirm', display_id=display['display_id'], reviewed=True, decisions=display['items'])
        decisions = [{k: display['items'][0][k] for k in ('id', 'revision', 'content_digest', 'operation')}]
        confirmation = self.confirm(display, decisions)
        self.assertEqual(len(self.call('consume', **confirmation)['applied']), 1)
        self.assertEqual(len(self.query()['items']), 1)
        with self.assertRaises(m.MemoryError):
            self.call('consume', **confirmation)
        decisions[0]['operation'] = 'delete'
        with self.assertRaises(m.MemoryError):
            self.confirm(display, decisions)

    def test_display_and_body_tampering_rejected(self):
        ref = self.candidate()
        display = self.display(ref)
        confirmation = self.confirm(display)
        body = next((self.root / 'lessons').glob('*/*.md'))
        body.write_text('tampered', encoding='utf-8')
        self.assertTrue(self.call('consume', **confirmation)['errors'])
        self.assertFalse(self.query()['items'])
        p = self.root / 'reviews' / (display['display_id'] + '.json')
        value = m.read(p)
        value['items'][0]['scope'] = {}
        m.atomic(p, value)
        with self.assertRaises(m.MemoryError):
            self.confirm(value)

    def test_scope_and_hypothesis_and_unknown_dependency(self):
        for extra in ({'kind': 'hypothesis'}, {'depends_on': [{'id': 'unknown', 'revision': 1}]}, {'scope': {'template': 'v2'}}):
            ref = self.candidate('event-' + str(len(self.registry()['records'])), **extra)
            self.assertTrue(self.decide(ref)['errors'])
        self.assertFalse(self.query()['items'])

    def test_dependency_revocation_and_user_pause(self):
        parent = self.candidate()
        self.decide(parent)
        child = self.candidate('event-2', kind='playbook', depends_on=[{'id': parent['id'], 'revision': 1}])
        self.decide(child)
        self.assertEqual(len(self.query()['items']), 2)
        self.decide(parent, 'pause')
        self.assertFalse(self.query()['items'])
        self.assertTrue(self.decide(parent, 'activate')['errors'])
        self.assertFalse(self.decide(parent, 'resume')['errors'])
        self.assertEqual(len(self.query()['items']), 1)
        self.decide(parent, 'revoke')
        self.assertFalse(self.query()['items'])
        with self.assertRaisesRegex(m.MemoryError, 'lineage'):
            self.candidate('event-3', id='different-id', predecessors=[{'id': parent['id'], 'revision': 1}])

    def test_candidate_revision_does_not_replace_active(self):
        first = self.candidate(id='method')
        self.decide(first)
        second = self.candidate('event-2', id='method', replaces={'id': 'method', 'revision': 1})
        self.assertEqual(self.query()['items'][0]['revision'], 1)
        self.decide(second)
        self.assertEqual(self.query()['items'][0]['revision'], 2)
        self.assertEqual(self.registry()['records']['method@1']['status'], 'superseded')

    def test_invocation_only_is_not_long_term(self):
        ref = self.candidate()
        self.decide(ref, 'use')
        self.assertEqual(len(self.query()['items']), 1)
        self.inv = self.begin('next-session')
        self.assertFalse(self.query()['items'])

    def test_rebuild_never_activates_orphan_and_old_backup_cannot_revive(self):
        ref = self.candidate()
        self.decide(ref)
        backup = Path(self.temp.name) / 'backup.json'
        self.call('backup', path=str(backup))
        self.decide(ref, 'revoke')
        self.call('restore', path=str(backup))
        self.assertFalse(self.query()['items'])
        orphan = self.root / 'lessons' / 'orphan' / '1.md'
        orphan.parent.mkdir()
        orphan.write_text('orphan', encoding='utf-8')
        (self.root / 'INDEX.md').write_text('active forged index', encoding='utf-8')
        self.assertEqual(self.call('rebuild')['orphans'], ['lessons/orphan/1.md'])
        self.assertTrue(orphan.exists())

    def test_delete_managed_text_and_reimport_block(self):
        ref = self.candidate()
        self.decide(ref)
        self.decide(ref, 'delete')
        self.assertFalse(list((self.root / 'lessons').glob('*/*.md')))
        self.assertNotIn('Synthetic original observation', (self.root / 'registry.json').read_text(encoding='utf-8'))
        self.assertFalse(self.query()['items'])
        with self.assertRaises(m.MemoryError):
            self.candidate(id='new-name')

    def test_env_resolved_each_entry_and_off_does_not_touch_root(self):
        other = Path(self.temp.name) / 'other'
        with patch.dict(os.environ, {'LAB_REPORT_MEMORY_HOME': str(other)}):
            self.assertFalse(m.execute({'action': 'init', 'mode': 'off'})['loaded'])
            self.assertFalse(other.exists())
            identity = m.execute({'action': 'init'})['root_id']
        with patch.dict(os.environ, {'LAB_REPORT_MEMORY_HOME': str(self.root)}):
            self.assertNotEqual(m.execute({'action': 'init'})['root_id'], identity)
        with m.Store(self.root).transaction() as store:
            with patch.dict(os.environ, {'LAB_REPORT_MEMORY_HOME': str(other)}):
                self.assertEqual(store.root, self.root)

    def test_transaction_failure_leaves_registry_and_orphan_inactive(self):
        before = (self.root / 'registry.json').read_bytes()
        with self.assertRaises(RuntimeError):
            with m.Store(self.root).transaction() as store:
                store.registry['heads']['fake'] = 1
                raise RuntimeError('synthetic crash')
        self.assertEqual(before, (self.root / 'registry.json').read_bytes())
        with self.assertRaises(m.MemoryError):
            self.call('rebuild', expected_generation=-1)

    def test_cross_process_same_session_collection(self):
        script = Path(m.__file__)
        requests = []
        for i in range(6):
            p = Path(self.temp.name) / ('request-' + str(i) + '.json')
            m.atomic(p, dict(action='collect', invocation_id=self.inv['invocation_id'], source={'provider': 'p', 'namespace': 'n', 'record_id': str(i)},
                             event_type='decision', payload={'value': i}, occurred_at='2026-10-24T00:00:00+08:00'))
            requests.append(p)
        procs = [subprocess.Popen([sys.executable, '-B', str(script), '--root', str(self.root), '--request', str(p)], stdout=subprocess.PIPE, stderr=subprocess.PIPE) for p in requests]
        for proc in procs:
            out, err = proc.communicate(timeout=15)
            self.assertEqual(proc.returncode, 0, (out, err))
        self.assertEqual(self.call('consolidate', invocation_id=self.inv['invocation_id'])['new_events'], 6)


if __name__ == '__main__':
    unittest.main()
