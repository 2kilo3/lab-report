"""Synthetic state-machine tests only; not a real report/Agent quality evaluation."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'workflow_state.py'
spec = importlib.util.spec_from_file_location('workflow_state', SCRIPT)
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='报告 测试 ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / 'state.json'
        for name in ('source.txt', '意图.md', 'report.docx', 'screen.png'):
            (self.root / name).write_text('synthetic fixture ' + name, encoding='utf-8')
        self.call('init', maker='maker-session', sources=['source.txt'])

    def call(self, action, **kwargs):
        return w.transact(self.state, dict(action=action, **kwargs))

    def ready(self):
        self.call('submit_intention', path='意图.md')
        self.call('confirm', message_ref='synthetic-test-only:user-confirmation')
        return self.call('submit_draft', paths=['report.docx'], evidence=['screen.png'])

    def receipt(self):
        state = self.call('status')
        value = dict(reviewer='reviewer-session', context_ref='synthetic-test-only:separate-context',
                     basis=w.basis(state), verdict='pass',
                     checks={k: {'status': 'pass', 'reason': 'Synthetic fixture check'} for k in w.CHECKS})
        (self.root / 'review.json').write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        return value

    def finish(self):
        self.ready()
        self.receipt()
        self.call('record_review', path='review.json')
        return self.call('finish')

    def test_requires_actual_confirmation_reference(self):
        self.call('submit_intention', path='意图.md')
        for request in ({'action': 'confirm'}, {'action': 'submit_draft', 'paths': ['report.docx']},
                        {'action': 'rollback', 'to': 'produce', 'reason': 'skip'}):
            with self.assertRaises(w.GuardError):
                w.transact(self.state, request)
        self.assertEqual(self.call('status')['phase'], 'awaiting_confirmation')

    def test_happy_path_and_no_reset(self):
        self.assertEqual(self.finish()['phase'], 'done')
        with self.assertRaises(w.GuardError):
            self.call('init', maker='new', sources=[])

    def test_fresh_review_required(self):
        self.ready()
        with self.assertRaises(w.GuardError):
            self.call('finish')

    def test_changed_done_draft_invalidates_review(self):
        self.finish()
        (self.root / 'report.docx').write_text('new candidate', encoding='utf-8')
        with self.assertRaises(w.GuardError):
            self.call('finish')
        state = self.call('status')
        self.assertEqual(state['phase'], 'review')
        self.assertIsNone(state['review'])
        with self.assertRaises(w.GuardError):
            self.call('record_review', path='review.json')

    def test_changed_intention_requires_new_confirmation(self):
        self.finish()
        (self.root / '意图.md').write_text('new requirements', encoding='utf-8')
        state = self.call('status')
        self.assertEqual(state['phase'], 'awaiting_confirmation')
        self.assertIsNone(state['approval'])

    def test_changed_source_blocks_until_impact_assessed(self):
        self.finish()
        (self.root / 'source.txt').write_text('changed material', encoding='utf-8')
        state = self.call('status')
        self.assertEqual(state['phase'], 'blocked')
        with self.assertRaises(w.GuardError):
            self.call('resume', reason='skip')
        state = self.call('reassess', requirements_changed=False, reason='Only irrelevant metadata changed, checked actual requirement text')
        self.assertEqual(state['phase'], 'produce')
        self.assertIsNotNone(state['approval'])
        self.assertIsNone(state['review'])

    def test_material_new_requirements_return_to_intake(self):
        self.finish()
        (self.root / 'source.txt').write_text('new requirement', encoding='utf-8')
        self.call('status')
        state = self.call('reassess', requirements_changed=True, reason='Task definition changed')
        self.assertEqual(state['phase'], 'intake')
        self.assertIsNone(state['approval'])

    def test_local_rollback_and_resume_preserve_files(self):
        self.finish()
        state = self.call('rollback', to='produce', reason='Fix figure caption only')
        self.assertIsNone(state['review'])
        self.call('pause', kind='failed', reason='Renderer failed')
        state = self.call('resume', reason='Renderer restored; inspected existing candidate')
        self.assertEqual(state['phase'], 'produce')
        self.assertTrue((self.root / 'report.docx').exists())
        self.assertIsNotNone(state['approval'])

    def test_corrupt_state_does_not_advance(self):
        self.state.write_text('{invalid', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.call('finish')
        self.state.write_text(json.dumps({'schema': 1, 'phase': 'done', 'maker': 'x'}), encoding='utf-8')
        with self.assertRaises(w.GuardError):
            self.call('status')

    def test_unresolved_review_and_same_maker_rejected(self):
        self.ready()
        value = self.receipt()
        for change in ('reviewer', 'check', 'basis'):
            trial = json.loads(json.dumps(value))
            if change == 'reviewer':
                trial['reviewer'] = 'maker-session'
            elif change == 'check':
                trial['checks']['render']['status'] = 'unverified'
            else:
                trial['basis']['draft'][0]['sha256'] = '0' * 64
            (self.root / 'review.json').write_text(json.dumps(trial), encoding='utf-8')
            with self.assertRaises(w.GuardError):
                self.call('record_review', path='review.json')

    def test_new_sources_and_changed_evidence_invalidate(self):
        self.finish()
        (self.root / 'screen.png').write_text('different synthetic evidence', encoding='utf-8')
        self.assertEqual(self.call('status')['phase'], 'produce')
        self.assertIsNone(self.call('status')['review'])
        state = self.call('set_sources', paths=['source.txt', '意图.md'], reason='Additional user material')
        self.assertEqual(state['phase'], 'blocked')
        self.assertTrue(state['impact_pending'])

    def test_blocked_is_distinct_from_failure(self):
        self.call('pause', kind='blocked', reason='Awaiting permitted environment access')
        self.assertEqual(self.call('status')['phase'], 'blocked')
        self.assertEqual(self.call('resume', reason='Access available')['phase'], 'intake')

    def test_artifact_change_cannot_release_external_hold(self):
        self.ready()
        self.call('pause', kind='blocked', reason='Permission is missing')
        (self.root / 'report.docx').write_text('changed', encoding='utf-8')
        state = self.call('status')
        self.assertEqual(state['phase'], 'blocked')
        self.assertEqual(state['waiting_reason'], 'Permission is missing')
        with self.assertRaises(w.GuardError):
            self.call('rollback', to='review', reason='bypass hold')
        (self.root / 'source.txt').write_text('changed source', encoding='utf-8')
        self.call('status')
        self.assertEqual(self.call('reassess', requirements_changed=False, reason='No intent impact')['phase'], 'blocked')
        self.assertEqual(self.call('resume', reason='Permission now granted')['phase'], 'produce')

    def test_new_intention_during_pending_source_impact_stays_blocked(self):
        self.ready()
        self.call('set_sources', paths=['source.txt'], reason='Refresh inventory')
        (self.root / '意图.md').write_text('changed intent', encoding='utf-8')
        state = self.call('status')
        self.assertEqual(state['phase'], 'blocked')
        self.assertIsNone(state['approval'])
        self.assertTrue(state['impact_pending'])
        self.assertEqual(self.call('reassess', requirements_changed=True, reason='New intent required')['phase'], 'intake')

    def test_explicit_inventory_repair_removes_missing_source(self):
        self.ready()
        (self.root / 'source.txt').unlink()
        state = self.call('set_sources', paths=[], reason='User withdrew obsolete source')
        self.assertEqual(state['phase'], 'blocked')
        self.assertTrue(state['impact_pending'])

    def test_mandatory_checks_cannot_be_na(self):
        self.ready()
        value = self.receipt()
        value['checks']['requirements']['status'] = 'not_applicable'
        (self.root / 'review.json').write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaises(w.GuardError):
            self.call('record_review', path='review.json')

    def test_missing_artifact_fails_closed(self):
        self.finish()
        (self.root / 'report.docx').unlink()
        with self.assertRaises(w.GuardError):
            self.call('status')

    def test_changed_receipt_invalidates_done(self):
        self.finish()
        (self.root / 'review.json').write_text('{}', encoding='utf-8')
        state = self.call('status')
        self.assertEqual(state['phase'], 'review')
        self.assertIsNone(state['review'])

    def test_utf8_cli_space_paths_and_error_json(self):
        request = self.root / '请求.json'
        request.write_text(json.dumps({'action': 'submit_intention', 'path': '意图.md'}, ensure_ascii=False), encoding='utf-8')
        env = dict(os.environ)
        env.pop('PYTHONUTF8', None)
        result = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(SCRIPT), '--state', str(self.state), '--request', str(request)],
                                capture_output=True, text=True, encoding='utf-8', env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('意图.md', json.loads(result.stdout)['basis']['intention']['path'])
        request.write_text('{invalid', encoding='utf-8')
        result = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(SCRIPT), '--state', str(self.state), '--request', str(request)],
                                capture_output=True, text=True, encoding='utf-8', env=env)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(json.loads(result.stdout)['ok'])


if __name__ == '__main__':
    unittest.main()
