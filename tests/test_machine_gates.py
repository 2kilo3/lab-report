"""Synthetic machine-gate contracts for 2.3; not real GUI/experiment validation."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'workflow_state.py'
spec = importlib.util.spec_from_file_location('workflow_state_gates', SCRIPT)
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


class MachineGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='机器门 测试 ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / 'state.json'
        for name in ('source.txt', '意图.md', 'report.docx', 'screen.png'):
            (self.root / name).write_text('synthetic fixture ' + name, encoding='utf-8')

    def init(self, **kwargs):
        options = dict(maker='maker-session', sources=['source.txt'])
        options.update(kwargs)
        return w.transact(self.state, dict(action='init', **options))

    def call(self, action, **kwargs):
        return w.transact(self.state, dict(action=action, **kwargs))

    def confirmed(self, path='意图.md', **kwargs):
        self.call('submit_intention', path=path, **kwargs)
        return self.call('confirm', message_ref='synthetic-test-only:user-confirmation')

    def step(self, step_id='S1', **overrides):
        value = dict(id=step_id, source='synthetic guide section', goal='synthetic step goal',
                     modality='gui', action='synthetic visible action', screenshot_required=True,
                     must_include=['filename visible'],
                     forbidden_shortcuts=['synthetic CLI substitution'], verify='filename visible',
                     on_fail='retry_once', evidence_ids=['E1'])
        value.update(overrides)
        return value

    def write_plan(self, steps=None, frozen=True, name='steps.json'):
        value = {'version': '1.1', 'frozen': frozen,
                 'steps': steps if steps is not None else [self.step()]}
        (self.root / name).write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        return name

    def freeze(self, name='steps.json', **kwargs):
        return self.call('freeze_plan', path=name,
                         message_ref='synthetic-test-only:card-confirmation', **kwargs)

    def complete(self, step_id='S1'):
        return self.call('complete_step', id=step_id, evidence=['screen.png'],
                         must_include={'filename visible': 'pass'})

    def submit(self, **kwargs):
        return self.call('submit_draft', paths=['report.docx'], evidence=['screen.png'], **kwargs)

    # M1: execution_required

    def test_new_state_defaults_to_execution_required(self):
        state = self.init()
        self.assertTrue(state['execution_required'])
        self.assertTrue(state['require_materials_map'])

    def test_execution_required_rejects_uncarded_draft(self):
        self.init(require_materials_map=False)
        self.confirmed()
        with self.assertRaises(w.GuardError) as caught:
            self.submit()
        self.assertIn('execution_required', str(caught.exception))
        self.write_plan()
        self.freeze()
        with self.assertRaises(w.GuardError):
            self.submit()
        self.complete()
        with self.assertRaises(w.GuardError):
            self.submit()
        self.call('bind_evidence')
        self.assertEqual(self.submit()['phase'], 'review')

    def test_execution_required_false_keeps_original_flow(self):
        self.init(execution_required=False, require_materials_map=False)
        self.confirmed()
        self.assertEqual(self.submit()['phase'], 'review')

    def test_legacy_state_without_gate_fields_keeps_bypass(self):
        self.init(execution_required=False, require_materials_map=False)
        value = json.loads(self.state.read_text(encoding='utf-8'))
        del value['execution_required']
        del value['require_materials_map']
        del value['materials_map']
        self.state.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        state = self.call('status')
        self.assertFalse(state['execution_required'])
        self.assertFalse(state['require_materials_map'])
        self.confirmed()
        self.assertEqual(self.submit()['phase'], 'review')

    # M3: tool/objects must_include contract

    def test_tool_must_appear_in_must_include(self):
        self.init(execution_required=False, require_materials_map=False)
        self.confirmed()
        self.write_plan([self.step(tool='Postman')])
        with self.assertRaises(w.GuardError) as caught:
            self.freeze()
        self.assertIn('Postman', str(caught.exception))
        self.write_plan([self.step(tool='Postman', must_include=['Postman request panel'])])
        state = self.freeze()
        self.assertEqual(state['plan']['steps'][0]['tool'], 'Postman')

    def test_objects_must_all_appear_in_must_include(self):
        self.init(execution_required=False, require_materials_map=False)
        self.confirmed()
        self.write_plan([self.step(objects=['c0', 's1', 'h1'], must_include=['c0', 's1'])])
        with self.assertRaises(w.GuardError) as caught:
            self.freeze()
        self.assertIn('h1', str(caught.exception))
        self.write_plan([self.step(objects=['c0', 's1', 'h1'], must_include=['c0', 's1', 'h1'])])
        state = self.freeze()
        self.assertEqual(state['plan']['steps'][0]['objects'], ['c0', 's1', 'h1'])

    def test_legacy_card_without_tool_or_objects_still_freezes(self):
        self.init(execution_required=False, require_materials_map=False)
        self.confirmed()
        self.write_plan([self.step()])
        self.assertTrue(self.freeze()['plan']['frozen'])


    # M2: materials map gate

    def write_map(self, name='MATERIALS_MAP.md', text='| M1 | guide | §1 | requirement | map gate | — | 意图 | main | indexed |\n'):
        (self.root / name).write_text(text, encoding='utf-8')
        return name

    def test_intention_requires_registered_materials_map(self):
        self.init(execution_required=False, require_materials_map=True)
        with self.assertRaises(w.GuardError) as caught:
            self.call('submit_intention', path='意图.md', map_ids=['M1'])
        self.assertIn('MATERIALS_MAP', str(caught.exception))
        with self.assertRaises(w.GuardError):
            self.call('register_materials_map', path='missing-map.md')

    def test_registered_map_and_map_ids_allow_intention(self):
        self.init(execution_required=False, require_materials_map=True)
        self.write_map()
        self.call('register_materials_map', path='MATERIALS_MAP.md')
        with self.assertRaises(w.GuardError) as caught:
            self.call('submit_intention', path='意图.md')
        self.assertIn('map_ids', str(caught.exception))
        with self.assertRaises(w.GuardError) as caught:
            self.call('submit_intention', path='意图.md', map_ids=['M9'])
        self.assertIn('M9', str(caught.exception))
        state = self.call('submit_intention', path='意图.md', map_ids=['M1'])
        self.assertEqual(state['phase'], 'awaiting_confirmation')

    def test_changed_materials_map_must_be_reregistered(self):
        self.init(execution_required=False, require_materials_map=True)
        self.write_map()
        self.call('register_materials_map', path='MATERIALS_MAP.md')
        self.write_map(text='| M1 | guide | §2 | requirement | changed | — | 意图 | main | indexed |\n')
        with self.assertRaises(w.GuardError) as caught:
            self.call('submit_intention', path='意图.md', map_ids=['M1'])
        self.assertIn('changed', str(caught.exception))
        self.call('register_materials_map', path='MATERIALS_MAP.md')
        self.assertEqual(self.call('submit_intention', path='意图.md', map_ids=['M1'])['phase'],
                         'awaiting_confirmation')

    def test_materials_map_gate_can_be_disabled_with_reason(self):
        self.init(execution_required=False, require_materials_map=False)
        with self.assertRaises(w.GuardError):
            self.call('set_require_materials_map', require_materials_map=True)
        self.call('set_require_materials_map', require_materials_map=True,
                  reason='Re-enable map gate for this intake')
        self.call('set_require_materials_map', require_materials_map=False,
                  reason='User supplied a single already-indexed task sheet')
        self.assertEqual(self.call('submit_intention', path='意图.md')['phase'], 'awaiting_confirmation')

    # M4: independent-review whitelist gate

    def ready_with_card_and_map(self):
        self.init(execution_required=True, require_materials_map=True)
        self.write_map()
        self.call('register_materials_map', path='MATERIALS_MAP.md')
        self.call('submit_intention', path='意图.md', map_ids=['M1'])
        self.call('confirm', message_ref='synthetic-test-only:user-confirmation')
        self.write_plan()
        self.freeze()
        self.complete()
        self.call('bind_evidence')
        return self.submit()

    def receipt(self):
        state = self.call('status')
        value = dict(reviewer='reviewer-session', context_ref='synthetic-test-only:separate-context',
                     basis=w.basis(state), verdict='pass',
                     checks={key: {'status': 'pass', 'reason': 'Synthetic fixture check'} for key in w.CHECKS})
        (self.root / 'review.json').write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def test_review_gate_accepts_complete_whitelist(self):
        self.ready_with_card_and_map()
        state = self.call('review_gate', required=['screen.png'])
        self.assertEqual(state['phase'], 'review')

    def test_review_gate_lists_missing_required_paths(self):
        self.ready_with_card_and_map()
        with self.assertRaises(w.GuardError) as caught:
            self.call('review_gate', required=['render.pdf'])
        self.assertIn('render.pdf', str(caught.exception))

    def test_review_gate_runs_before_draft(self):
        self.init(execution_required=False, require_materials_map=False)
        self.confirmed()
        with self.assertRaises(w.GuardError):
            self.call('review_gate')

    def test_record_review_rejects_missing_materials_map(self):
        self.ready_with_card_and_map()
        self.receipt()
        (self.root / 'MATERIALS_MAP.md').unlink()
        with self.assertRaises(w.GuardError) as caught:
            self.call('record_review', path='review.json')
        self.assertIn('materials map file', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
