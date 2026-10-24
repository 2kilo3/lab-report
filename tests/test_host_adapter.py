"""Offline synthetic samples of pinned upstream exports, not a real host run."""
import unittest

import test_experience_store as fixtures
import host_adapter as adapter

m = fixtures.m


class HostAdapterTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.MemoryTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root

    def test_end_only_saves_candidate_and_is_bounded(self):
        self.fixture.collect()
        result = adapter.execute({'action': 'end', 'invocation_id': self.fixture.inv['invocation_id']}, self.root)
        self.assertEqual(result['new_events'], 1)
        self.assertEqual(len(result['candidates']), 1)
        registry = self.fixture.registry()
        self.assertEqual(next(iter(registry['records'].values()))['kind'], 'hypothesis')
        self.assertFalse(registry['displays'])
        self.assertFalse(self.fixture.query()['items'])

    def test_export_requires_clean_context_and_deduplicates(self):
        path = self.root.parent / 'synthetic-export.json'
        m.atomic(path, {'exportedAt': m.now(), 'observations': [dict(id=1, memory_session_id='source-session', project='synthetic-project',
                 type='discovery', title='Synthetic observation', narrative='Synthetic unverified text', created_at='2026-10-24T10:00:00+08:00', created_at_epoch=0)], 'summaries': []})
        request = dict(action='claude_mem_export', path=str(path), invocation_id=self.fixture.inv['invocation_id'],
                       source_namespace='synthetic-installation', project='synthetic-project')
        with self.assertRaisesRegex(m.MemoryError, 'isolation'):
            adapter.execute(request, self.root)
        request['isolation'] = dict(mode='clean_context', verified_by='synthetic-host', evidence_ref='synthetic:disabled-plugin-context')
        first = adapter.execute(request, self.root)
        second = adapter.execute(request, self.root)
        self.assertEqual(first['events'][0]['event_id'], second['events'][0]['event_id'])
        self.assertTrue(second['events'][0]['duplicate'])
        result = adapter.execute(dict(action='checkpoint', invocation_id=self.fixture.inv['invocation_id']), self.root)
        self.assertEqual(result['new_events'], 1)
        self.assertFalse(self.fixture.query()['items'])


if __name__ == '__main__':
    unittest.main()
