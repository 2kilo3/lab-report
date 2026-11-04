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

    def confirmed(self):
        self.call('submit_intention', path='意图.md')
        return self.call('confirm', message_ref='synthetic-test-only:user-confirmation')

    def plan_step(self, step_id='S1', screenshot=True, **overrides):
        step = dict(id=step_id, source='synthetic guide section', goal='synthetic step goal',
                    modality='gui', action='synthetic visible action', screenshot_required=screenshot,
                    must_include=['filename visible'] if screenshot else [],
                    forbidden_shortcuts=['synthetic CLI substitution'], verify='filename visible',
                    on_fail='retry_once', evidence_ids=['E1'])
        step.update(overrides)
        return step

    def write_plan(self, steps=None, frozen=True, name='steps.json', goal='synthetic step goal'):
        value = {'version': '1.0', 'frozen': frozen,
                 'steps': steps if steps is not None else [self.plan_step(goal=goal)]}
        (self.root / name).write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        return name

    def freeze(self, name='steps.json', **kwargs):
        return self.call('freeze_plan', path=name,
                         message_ref='synthetic-test-only:card-confirmation', **kwargs)

    def complete(self, step_id='S1', evidence=None, marks=None):
        request = dict(id=step_id, evidence=['screen.png'] if evidence is None else evidence)
        if marks is not None:
            request['must_include'] = marks
        return self.call('complete_step', **request)

    def test_execution_card_must_be_approved_and_frozen(self):
        self.write_plan(frozen=False)
        with self.assertRaises(w.GuardError):
            self.freeze()  # intention is not confirmed yet
        self.confirmed()
        with self.assertRaises(w.GuardError):
            self.freeze()
        self.write_plan(frozen=True)
        with self.assertRaises(w.GuardError):
            self.call('freeze_plan', path='steps.json')
        state = self.freeze()
        self.assertTrue(state['plan']['frozen'])
        self.assertEqual(state['plan']['steps'][0]['id'], 'S1')

    def test_optional_tool_and_objects_are_kept(self):
        self.write_plan([self.plan_step('S1', tool='Postman', objects=['c0', 's1', 'h1'])])
        self.confirmed()
        state = self.freeze()
        step = state['plan']['steps'][0]
        self.assertEqual(step['tool'], 'Postman')
        self.assertEqual(step['objects'], ['c0', 's1', 'h1'])
        self.complete(marks={'filename visible': 'pass'})
        self.call('bind_evidence')

    def test_invalid_tool_and_duplicate_objects_rejected(self):
        self.confirmed()
        self.write_plan([self.plan_step('S1', tool='')])
        with self.assertRaises(w.GuardError):
            self.freeze()
        self.write_plan([self.plan_step('S1', objects=['c0', 'c0'])])
        with self.assertRaises(w.GuardError):
            self.freeze()
        self.write_plan([self.plan_step('S1', objects=['c0', ''])])
        with self.assertRaises(w.GuardError):
            self.freeze()

    def test_complete_step_requires_frozen_card(self):
        self.confirmed()
        with self.assertRaises(w.GuardError):
            self.complete()
        self.write_plan()
        self.freeze()
        with self.assertRaises(w.GuardError):
            self.complete(step_id='S9')
        with self.assertRaises(w.GuardError):
            self.complete(evidence=[])
        with self.assertRaises(w.GuardError):
            self.complete(evidence=['source.txt'])
        (self.root / 'empty.png').write_bytes(b'')
        with self.assertRaises(w.GuardError):
            self.complete(evidence=['empty.png'])
        with self.assertRaises(w.GuardError):
            self.complete(marks={})
        with self.assertRaises(w.GuardError):
            self.complete(marks={'filename visible': 'unknown'})
        state = self.complete(marks={'filename visible': 'pass'})
        self.assertIn('S1', state['step_records'])
        with self.assertRaises(w.GuardError):
            self.complete(marks={'filename visible': 'pass'})

    def test_bind_and_submit_wait_for_all_steps(self):
        self.write_plan([self.plan_step('S1'), self.plan_step('S2', must_include=['output visible'])])
        self.confirmed()
        self.freeze()
        with self.assertRaises(w.GuardError):
            self.call('bind_evidence')
        self.complete('S1', marks={'filename visible': 'pass'})
        with self.assertRaises(w.GuardError):
            self.call('bind_evidence')
        with self.assertRaises(w.GuardError):
            self.call('submit_draft', paths=['report.docx'], evidence=['screen.png'])
        self.complete('S2', marks={'output visible': 'pass'})
        with self.assertRaises(w.GuardError):
            self.call('submit_draft', paths=['report.docx'], evidence=['screen.png'])
        self.call('bind_evidence')
        state = self.call('submit_draft', paths=['report.docx'], evidence=['screen.png'])
        self.assertEqual(state['phase'], 'review')

    def test_non_screenshot_step_can_omit_must_include(self):
        step = self.plan_step('S1', screenshot=False)
        del step['must_include']
        self.write_plan([step])
        self.confirmed()
        self.freeze()
        state = self.complete('S1', evidence=['source.txt'])
        self.assertEqual(state['step_records']['S1']['must_include'], {})
        self.call('bind_evidence')

    def test_frozen_plan_flow_reaches_done_with_fresh_review(self):
        self.write_plan()
        self.confirmed()
        self.freeze()
        self.complete(marks={'filename visible': 'pass'})
        self.call('bind_evidence')
        self.call('submit_draft', paths=['report.docx'], evidence=['screen.png'])
        self.receipt()
        self.call('record_review', path='review.json')
        self.assertEqual(self.call('finish')['phase'], 'done')

    def test_new_intention_invalidates_frozen_card(self):
        self.write_plan()
        self.confirmed()
        self.freeze()
        self.complete(marks={'filename visible': 'pass'})
        self.call('rollback', to='intake', reason='User changed the task scope')
        (self.root / '意图.md').write_text('new synthetic scope', encoding='utf-8')
        self.call('status')
        self.call('submit_intention', path='意图.md')
        self.call('confirm', message_ref='synthetic-test-only:new-confirmation')
        with self.assertRaises(w.GuardError):
            self.call('submit_draft', paths=['report.docx'], evidence=['screen.png'])
        with self.assertRaises(w.GuardError):
            self.freeze()
        state = self.freeze(reason='Rebuilt card for the newly confirmed scope')
        self.assertEqual(state['step_records'], {})
        self.assertFalse(state['plan_invalidated'])

    def test_changed_plan_needs_reason_and_restarts_steps(self):
        self.write_plan()
        self.confirmed()
        self.freeze()
        self.complete(marks={'filename visible': 'pass'})
        self.write_plan(goal='changed synthetic step goal')
        state = self.call('status')
        self.assertIsNone(state['plan'])
        self.assertEqual(state['phase'], 'produce')
        with self.assertRaises(w.GuardError):
            self.freeze()
        state = self.freeze(reason='Guide wording clarified; recapture affected step')
        self.assertEqual(state['step_records'], {})
        self.assertFalse(state['plan_invalidated'])
        with self.assertRaises(w.GuardError):
            self.freeze()
        state = self.freeze(reason='second re-freeze applied')
        self.assertEqual(state['step_records'], {})

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
