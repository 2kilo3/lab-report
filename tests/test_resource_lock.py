"""Synthetic resource-lock tests only; no real VM/device/license is involved."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'resource_lock.py'
spec = importlib.util.spec_from_file_location('resource_lock', SCRIPT)
rl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rl)

# Above every supported platform's pid ceiling, so it is never a live process.
DEAD_PID = 2147483647


class ResourceLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='锁 测试 ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.lock = self.root / 'locks' / 'resource.lock'
        self.host = socket.gethostname()

    def old_time(self, seconds=600):
        return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(timespec='milliseconds')

    def write_record(self, **overrides):
        record = {'schema': 1, 'owner': 'agent-a', 'pid': os.getpid(), 'host': self.host,
                  'acquired_at': rl.utc_now(), 'heartbeat_at': rl.utc_now(),
                  'lease_seconds': 120, 'fencing_token': 1}
        record.update(overrides)
        self.lock.parent.mkdir(parents=True, exist_ok=True)
        self.lock.write_text(rl.encode(record), encoding='utf-8')
        return record

    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', '-X', 'utf8', str(SCRIPT)] + list(args),
                              capture_output=True, text=True, encoding='utf-8')

    def test_acquire_status_and_owner_only_release(self):
        record = rl.acquire(self.lock, 'agent-a', pid=os.getpid(), lease_seconds=60)
        self.assertEqual(record['fencing_token'], 1)
        for key in ('owner', 'pid', 'host', 'acquired_at', 'heartbeat_at',
                    'lease_seconds', 'fencing_token'):
            self.assertIn(key, record)
        state = rl.status(self.lock, owner='agent-a')
        self.assertTrue(state['held'])
        self.assertFalse(state['stale'])
        self.assertTrue(state['owner_matches'])
        with self.assertRaises(rl.LockHeld):
            rl.acquire(self.lock, 'agent-b', pid=os.getpid())
        with self.assertRaises(rl.LockError):
            rl.renew(self.lock, 'agent-b')
        with self.assertRaises(rl.LockError):
            rl.release(self.lock, 'agent-b')
        rl.release(self.lock, 'agent-a')
        self.assertFalse(rl.status(self.lock)['held'])
        self.assertFalse(self.lock.exists())

    def test_fencing_token_increases_across_acquire_release_and_break(self):
        tokens = []
        for _ in range(3):
            tokens.append(rl.acquire(self.lock, 'agent-a', pid=os.getpid())['fencing_token'])
            rl.release(self.lock, 'agent-a')
        self.assertEqual(tokens, [1, 2, 3])
        fourth = rl.acquire(self.lock, 'agent-a', pid=DEAD_PID)
        self.assertEqual(fourth['fencing_token'], 4)
        rl.break_stale(self.lock, 'agent-b', 'pid is gone')
        fifth = rl.acquire(self.lock, 'agent-a', pid=os.getpid())
        self.assertEqual(fifth['fencing_token'], 5)
        self.assertGreaterEqual(json.loads(rl.fence_path(self.lock).read_text())['fencing_token'], 5)

    def test_acquire_never_overwrites_existing_file(self):
        self.write_record(owner='agent-a')
        with self.assertRaises(rl.LockHeld):
            rl.acquire(self.lock, 'agent-b', pid=os.getpid())
        self.assertEqual(rl.read_lock(self.lock)['owner'], 'agent-a')
        self.lock.write_text('not json', encoding='utf-8')
        with self.assertRaises(rl.LockError):
            rl.acquire(self.lock, 'agent-b', pid=os.getpid())
        self.assertEqual(self.lock.read_text(encoding='utf-8'), 'not json')

    def test_renew_refreshes_heartbeat_and_lease(self):
        record = self.write_record(heartbeat_at=self.old_time(30), lease_seconds=120)
        renewed = rl.renew(self.lock, 'agent-a', lease_seconds=300)
        self.assertEqual(renewed['lease_seconds'], 300)
        self.assertGreater(rl.parse_time(renewed['heartbeat_at']),
                           rl.parse_time(record['heartbeat_at']))
        with self.assertRaises(rl.LockError):
            rl.renew(self.lock, 'agent-b')

    def test_renew_refuses_stale_lock(self):
        self.write_record(heartbeat_at=self.old_time(600), lease_seconds=120)
        with self.assertRaises(rl.LockError):
            rl.renew(self.lock, 'agent-a')

    def test_dead_pid_is_stale_and_break_records_reason(self):
        broken = self.write_record(pid=DEAD_PID, fencing_token=7)
        state = rl.status(self.lock)
        self.assertTrue(state['stale'])
        self.assertIn('not running', ' '.join(state['stale_reasons']))
        with self.assertRaises(rl.LockError):
            rl.break_stale(self.lock, 'agent-b', '')
        with self.assertRaises(rl.LockError):
            rl.break_stale(self.lock, '', 'pid is gone')
        result = rl.break_stale(self.lock, 'agent-b', 'holder crashed, pid gone')
        self.assertTrue(result['stale_reasons'])
        self.assertFalse(self.lock.exists())
        lines = rl.log_path(self.lock).read_text(encoding='utf-8').splitlines()
        entry = json.loads(lines[-1])
        self.assertEqual(entry['reason'], 'holder crashed, pid gone')
        self.assertEqual(entry['record']['fencing_token'], broken['fencing_token'])
        next_record = rl.acquire(self.lock, 'agent-c', pid=os.getpid())
        self.assertGreater(next_record['fencing_token'], broken['fencing_token'])

    def test_expired_heartbeat_alone_is_stale(self):
        self.write_record(heartbeat_at=self.old_time(600), lease_seconds=120)
        state = rl.status(self.lock)
        self.assertTrue(state['stale'])
        self.assertIn('heartbeat age', ' '.join(state['stale_reasons']))
        self.assertNotIn('not running', ' '.join(state['stale_reasons']))
        rl.break_stale(self.lock, 'agent-b', 'lease expired while holder was suspended')
        self.assertFalse(self.lock.exists())

    def test_remote_host_pid_is_not_checked(self):
        self.write_record(host='another-machine', pid=DEAD_PID)
        state = rl.status(self.lock)
        self.assertFalse(state['stale'])
        self.assertIsNone(state['pid_alive'])
        with self.assertRaises(rl.LockError):
            rl.break_stale(self.lock, 'agent-b', 'pid looks dead')
        self.write_record(host='another-machine', pid=DEAD_PID, heartbeat_at=self.old_time(600))
        self.assertTrue(rl.status(self.lock)['stale'])

    def test_live_lock_needs_force_to_break(self):
        self.write_record()
        with self.assertRaises(rl.LockError):
            rl.break_stale(self.lock, 'agent-b', 'looks stuck')
        result = rl.break_stale(self.lock, 'agent-b', 'holder known hung', force=True)
        self.assertTrue(result['forced'])
        self.assertIn('forced break', result['stale_reasons'][0])
        entry = json.loads(rl.log_path(self.lock).read_text(encoding='utf-8').splitlines()[-1])
        self.assertTrue(entry['forced'])
        self.assertFalse(self.lock.exists())

    def test_corrupt_lock_requires_force(self):
        self.lock.parent.mkdir(parents=True, exist_ok=True)
        self.lock.write_text('{invalid', encoding='utf-8')
        with self.assertRaises(rl.LockError):
            rl.status(self.lock)
        with self.assertRaises(rl.LockError):
            rl.break_stale(self.lock, 'agent-b', 'corrupt')
        result = rl.break_stale(self.lock, 'agent-b', 'half-written by a crashed writer', force=True)
        self.assertIn('not valid JSON', result['unreadable'])
        self.assertFalse(self.lock.exists())
        self.assertEqual(rl.acquire(self.lock, 'agent-c', pid=os.getpid())['fencing_token'], 1)

    def test_corrupt_fence_blocks_break_without_moving_lock(self):
        self.write_record(pid=DEAD_PID)
        rl.fence_path(self.lock).write_text('{bad', encoding='utf-8')
        with self.assertRaises(rl.LockError):
            rl.break_stale(self.lock, 'agent-b', 'pid gone')
        self.assertTrue(self.lock.exists())

    def test_acquire_rejects_invalid_identity_without_writing(self):
        for kwargs in ({'pid': 0}, {'pid': 'not-a-pid'}, {'host': ''}, {'lease_seconds': 0}):
            with self.assertRaises(rl.LockError):
                rl.acquire(self.lock, 'agent-a', **kwargs)
            self.assertFalse(self.lock.exists())

    def test_record_validation_rejects_bad_fields(self):
        for overrides in ({'owner': ''}, {'pid': 0}, {'host': ''}, {'lease_seconds': 0},
                          {'fencing_token': 0}, {'heartbeat_at': 'not-a-date'}, {'schema': 9}):
            self.write_record(**overrides)
            with self.assertRaises(rl.LockError):
                rl.read_lock(self.lock)

    def test_pid_alive_local_processes(self):
        self.assertTrue(rl.pid_alive(os.getpid()))
        self.assertFalse(rl.pid_alive(DEAD_PID))
        self.assertFalse(rl.pid_alive(0))
        self.assertFalse(rl.pid_alive(True))

    def test_pid_alive_tracks_a_real_process(self):
        proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        try:
            self.assertTrue(rl.pid_alive(proc.pid))
        finally:
            proc.terminate()
            proc.wait()
        self.assertFalse(rl.pid_alive(proc.pid))

    def test_cli_roundtrip_and_exit_codes(self):
        args = ['acquire', '--lock', str(self.lock), '--owner', 'agent-a',
                '--pid', str(os.getpid()), '--lease', '60']
        result = self.cli(*args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['record']['fencing_token'], 1)
        result = self.cli(*args)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['reason'], 'held')
        result = self.cli('status', '--lock', str(self.lock), '--owner', 'agent-a')
        self.assertEqual(result.returncode, 0)
        self.assertTrue(json.loads(result.stdout)['held'])
        result = self.cli('release', '--lock', str(self.lock), '--owner', 'agent-b')
        self.assertEqual(result.returncode, 2)
        result = self.cli('release', '--lock', str(self.lock), '--owner', 'agent-a')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(json.loads(self.cli('status', '--lock', str(self.lock)).stdout)['held'])

    def test_cli_break_stale_requires_reason(self):
        rl.acquire(self.lock, 'agent-a', pid=DEAD_PID)
        result = self.cli('break-stale', '--lock', str(self.lock), '--owner', 'agent-b')
        self.assertEqual(result.returncode, 2)
        result = self.cli('break-stale', '--lock', str(self.lock), '--owner', 'agent-b',
                          '--reason', 'pid no longer exists')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok'])
        self.assertFalse(self.lock.exists())

    def test_status_of_missing_lock_is_empty(self):
        state = rl.status(self.lock)
        self.assertFalse(state['held'])
        self.assertFalse(state['stale'])
        self.assertIsNone(state['record'])


if __name__ == '__main__':
    unittest.main()
