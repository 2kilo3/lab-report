"""Synthetic integration: dependency lifecycle, migration and finalization ordering."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_experience_store as memory_tests
import test_workflow_state as original

m = memory_tests.m
w = original.w


class MemoryWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.protocol = memory_tests.MemoryTests()
        self.protocol.setUp()
        self.addCleanup(self.protocol.doCleanups)
        self.files = original.WorkflowTests()
        self.files.setUp()
        self.addCleanup(self.files.doCleanups)
        self.state = self.files.state
        self.root = self.protocol.root
        self.ref = self.protocol.candidate()
        self.protocol.decide(self.ref)
        self.files.ready()
        self.call('memory_mode', mode='on')
        self.begin()

    def call(self, action, **extra):
        return w.transact(self.state, dict(action=action, **extra), self.root)

    def begin(self):
        return self.call('memory_begin', host='synthetic', native_session_id='report-session',
                         explicit_use_ref='synthetic:lab-report-explicit',
                         materials_read={'refs': ['synthetic:current-materials'], 'constraints': {'template': 'v1'}})

    def adopt(self, ref=None):
        state = self.call('adopt_lesson', lesson=ref or self.ref, application={'action': 'Synthetic caption method', 'affected': ['report.docx:page1']})
        app = state['lessons_used'][-1]['applications'][-1]
        return self.call('record_application', application_id=app['application_id'], result='Synthetic applied and locally checked')

    def review(self):
        state = self.call('status')
        receipt = dict(reviewer='independent', context_ref='synthetic:independent-context', basis=w.basis(state),
                       lessons_basis=w.lessons_basis(state), verdict='pass',
                       checks={k: {'status': 'pass', 'reason': 'Synthetic check'} for k in w.CHECKS})
        p = self.state.parent / 'memory-review.json'
        m.atomic(p, receipt)
        return self.call('record_review', path=str(p))

    def detach(self):
        state = self.call('status')
        receipt = dict(reviewer='independent', context_ref='synthetic:clean-current-material-context',
                       basis=w.basis(state), lessons_basis=w.lessons_basis(state), verdict='pass',
                       reason='Synthetic local revalidation of affected page without historical method',
                       revalidated_from_current_materials=True,
                       applications_digest=m.sha([a for x in state['lessons_used'] for a in x['applications']]))
        p = self.state.parent / 'detach.json'
        m.atomic(p, receipt)
        return self.call('detach_lessons', path=str(p), lessons=[self.ref])

    def test_adoption_invalidates_even_without_artifact_change(self):
        self.files.receipt()
        self.call('record_review', path='review.json')
        old = self.call('status')
        state = self.adopt()
        self.assertEqual(w.basis(old), w.basis(state))
        self.assertNotEqual(w.lessons_basis(old), w.lessons_basis(state))
        self.assertEqual(old['approval'], state['approval'])
        with self.assertRaises(w.GuardError):
            self.call('record_review', path='review.json')
        self.review()
        self.assertEqual(self.call('finish')['phase'], 'done')

    def test_revoked_authority_detected_with_unchanged_task_receipt(self):
        self.adopt()
        self.review()
        before = self.state.read_bytes()
        self.protocol.decide(self.ref, 'revoke')
        self.assertEqual(before, self.state.read_bytes())
        with self.assertRaises(w.GuardError):
            self.call('finish')
        state = self.call('status')
        generation = state['adoption_generation']
        self.assertTrue(state['memory_impact_pending'])
        self.assertEqual(self.call('status')['adoption_generation'], generation)
        self.assertIsNone(state['review'])

    def test_off_does_not_remove_dependency_or_restore_old_review(self):
        self.adopt()
        self.review()
        self.protocol.decide(self.ref, 'revoke')
        state = self.call('memory_mode', mode='off')
        self.assertTrue(state['lessons_used'])
        self.assertGreater(state['adoption_generation'], 0)
        with self.assertRaises(w.GuardError):
            self.call('finish')
        state = self.detach()
        self.assertFalse(state['lessons_used'])
        self.assertTrue(state['lessons_history'])
        with self.assertRaises(w.GuardError):
            self.call('record_review', path='review.json')
        self.review()
        self.assertEqual(self.call('finish')['phase'], 'done')

    def test_unrelated_update_and_receipt_refresh_keep_review(self):
        self.adopt()
        self.review()
        before = self.call('status')
        self.protocol.candidate('unrelated')
        state = self.call('refresh_lessons')
        self.assertEqual(before['review'], state['review'])
        self.assertEqual(w.lessons_basis(before), w.lessons_basis(state))
        state['lessons_receipt'] = {'corrupt': True}
        m.atomic(self.state, state)
        self.assertEqual(self.call('finish')['phase'], 'done')

    def test_root_identity_or_unavailability_denies_finish_but_detach_works(self):
        self.adopt()
        self.review()
        other = self.root.parent / 'different-root'
        m.execute({'action': 'init'}, other)
        with self.assertRaises(w.GuardError):
            w.transact(self.state, {'action': 'finish'}, other)
        moved = self.root.with_name('temporarily-offline')
        self.root.rename(moved)
        state = self.call('status')
        self.assertTrue(state['memory_impact_pending'])
        self.assertFalse(self.detach()['lessons_used'])
        self.review()
        self.assertEqual(self.call('finish')['phase'], 'done')

    def test_post_delivery_revocation_records_later_impact(self):
        self.adopt()
        self.review()
        self.call('finish')
        self.protocol.decide(self.ref, 'revoke')
        state = self.call('status')
        self.assertEqual(state['phase'], 'review')
        self.assertTrue(any(e['action'] == 'memory_impact' and e['detail']['after_delivery'] for e in state['events']))
        self.assertTrue((self.state.parent / 'report.docx').exists())

    def test_finish_holds_same_root_lock_through_done_write(self):
        self.adopt()
        self.review()
        original_write = w.atomic_write
        seen = []
        def checked_write(path, value):
            if value['phase'] == 'done':
                with self.assertRaisesRegex(m.MemoryError, 'lock timeout'):
                    with m.Store(self.root, timeout=0.05).transaction():
                        pass
                seen.append('locked')
            original_write(path, value)
        with patch.object(w, 'atomic_write', checked_write):
            self.call('finish')
        self.assertEqual(seen, ['locked'])

    def test_migration_preserves_legacy_done_approval_and_receipt(self):
        self.files.receipt()
        self.call('record_review', path='review.json')
        self.call('finish')
        state = m.read(self.state)
        legacy_fields = {'task_id', 'session_ref', 'invocation_id', 'memory_mode', 'lessons_used', 'lessons_receipt',
                         'adoption_generation', 'memory_impact_pending', 'lessons_history', 'memory_checkpoint'}
        legacy = {k: v for k, v in state.items() if k not in legacy_fields}
        legacy['schema'] = 1
        m.atomic(self.state, legacy)
        before = self.state.read_bytes()
        upgraded = self.call('status')
        self.assertEqual(upgraded['schema'], 2)
        self.assertEqual(upgraded['phase'], 'done')
        for name in ('approval', 'review', 'sources', 'intention', 'draft', 'evidence'):
            self.assertEqual(legacy[name], upgraded[name])
        self.assertEqual(self.state.with_suffix('.json.schema1.bak').read_bytes(), before)
        w.validate(upgraded)

    def test_invalid_unknown_or_missing_legacy_cannot_be_migrated(self):
        for state in ({'schema': 1, 'phase': 'done'}, {'schema': 999}, ['invalid-state-object']):
            m.atomic(self.state, state)
            before = self.state.read_bytes()
            with self.assertRaises(w.GuardError):
                self.call('migrate')
            self.assertEqual(self.state.read_bytes(), before)

    def test_off_without_adoption_never_opens_memory_root(self):
        self.call('memory_mode', mode='off')
        with patch.object(w.memory, 'Store', side_effect=AssertionError('Must not access memory')):
            self.call('status')
            self.files.receipt()
            self.call('record_review', path='review.json')
            self.assertEqual(self.call('finish')['phase'], 'done')

    def test_new_material_scope_rechecks_existing_adoption(self):
        self.adopt()
        self.call('memory_begin', host='synthetic', native_session_id='report-session',
                  explicit_use_ref='synthetic:changed-template',
                  materials_read={'refs': ['synthetic:new-template'], 'constraints': {'template': 'v2'}})
        state = self.call('status')
        self.assertTrue(state['memory_impact_pending'])
        with self.assertRaises(w.GuardError):
            self.call('finish')


if __name__ == '__main__':
    unittest.main()
