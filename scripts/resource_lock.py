#!/usr/bin/env python3
"""Exclusive-resource lock with lease, heartbeat and fencing token.

Usage (JSON on stdout):
  python -B resource_lock.py acquire --lock WORK/locks/vm.lock --owner agent-a \
      --pid 4242 [--lease 120]
  python -B resource_lock.py renew   --lock WORK/locks/vm.lock --owner agent-a [--lease 120]
  python -B resource_lock.py release --lock WORK/locks/vm.lock --owner agent-a
  python -B resource_lock.py status  --lock WORK/locks/vm.lock [--owner agent-a]
  python -B resource_lock.py break-stale --lock WORK/locks/vm.lock --owner agent-a \
      --reason "pid 4242 gone; heartbeat expired" [--force]

One lock file per exclusive resource (VM, device, license). The record holds
owner, pid, host, timestamps, lease_seconds and a monotonically increasing
fencing_token. Creation is atomic and never overwrites an existing lock. Only
the recorded owner may renew or release. A lock is stale only when its
heartbeat is older than the lease or its pid no longer exists on the recorded
host; break-stale requires a reason, writes an audit entry to <lock>.log and
keeps the fencing token from going backwards (<lock>.fence).

Carry the fencing token into the work product (file name, manifest or result
record) so a stale holder that wakes up late is detectable instead of silently
overwriting newer output. Hosts with the same hostname and different machines
cannot be distinguished here; use per-host lock paths or unique host labels.

Standard library only, Python 3.9+. Same-permission writers can race between
the final check and the write; keep leases well above one operation and treat
a changed lock as a signal to re-read status, never to force through.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import uuid
from datetime import datetime, timezone

SCHEMA = 1
DEFAULT_LEASE = 120
TOKEN_FIELDS = ('schema', 'owner', 'pid', 'host', 'acquired_at', 'heartbeat_at',
                'lease_seconds', 'fencing_token')


class LockError(RuntimeError):
    """Lock operation refused or lock state unusable."""


class LockHeld(LockError):
    """Another live lock already occupies this resource."""


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def parse_time(value):
    if not nonempty(value):
        raise LockError('Timestamp must be a nonempty ISO 8601 string')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise LockError('Unreadable timestamp: ' + value) from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def local_host():
    return socket.gethostname()


def same_host(left, right):
    return left.strip().casefold() == right.strip().casefold()


def windows_pid_alive(pid):
    """OpenProcess with query-only rights: invalid parameter means no such pid."""
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    process_query_limited_information = 0x1000
    still_active = 259
    error_invalid_parameter = 87
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        # Access denied means the pid exists but is protected; only 87 proves absence.
        return ctypes.get_last_error() != error_invalid_parameter
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def pid_alive(pid):
    """True/False for the local host. Never sends a signal on Windows."""
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == 'nt':
        return windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def atomic_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def exclusive_create(path, text):
    """Create path with full content, never overwriting. True if this call won."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temp, path)
            return True
        except FileExistsError:
            return False
        except OSError:
            # Filesystems without hard links: exclusive open still prevents overwrite.
            try:
                raw = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                return False
            with os.fdopen(raw, 'w', encoding='utf-8', newline='\n') as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            return True
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def validate_record(record):
    if not isinstance(record, dict) or record.get('schema') != SCHEMA:
        raise LockError('Unsupported lock schema')
    if not nonempty(record.get('owner')):
        raise LockError('Lock needs a nonempty owner')
    if isinstance(record.get('pid'), bool) or not isinstance(record.get('pid'), int) or record['pid'] <= 0:
        raise LockError('Lock needs a positive integer pid')
    if not nonempty(record.get('host')):
        raise LockError('Lock needs a nonempty host')
    parse_time(record.get('acquired_at'))
    parse_time(record.get('heartbeat_at'))
    lease = record.get('lease_seconds')
    if isinstance(lease, bool) or not isinstance(lease, (int, float)) or lease <= 0:
        raise LockError('Lock needs positive lease_seconds')
    token = record.get('fencing_token')
    if isinstance(token, bool) or not isinstance(token, int) or token < 1:
        raise LockError('Lock needs a positive integer fencing_token')
    return record


def read_lock(path):
    """Return the record, None when absent; LockError when unreadable."""
    path = Path(path)
    try:
        text = path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return None
    try:
        record = json.loads(text)
    except json.JSONDecodeError as error:
        raise LockError('Lock file is not valid JSON: ' + str(path)) from error
    return validate_record(record)


def stale_reasons(record, now=None):
    """Only two causes count: expired heartbeat, or a local pid that is gone."""
    now = now or datetime.now(timezone.utc)
    heartbeat = parse_time(record['heartbeat_at'])
    age = (now - heartbeat).total_seconds()
    reasons = []
    if age > record['lease_seconds']:
        reasons.append('heartbeat age %.0fs exceeds lease %ss' % (age, record['lease_seconds']))
    if same_host(record['host'], local_host()) and not pid_alive(record['pid']):
        reasons.append('pid %d is not running on %s' % (record['pid'], record['host']))
    return reasons


def fence_path(path):
    return Path(path).with_name(Path(path).name + '.fence')


def log_path(path):
    return Path(path).with_name(Path(path).name + '.log')


def read_fence(path):
    fence = fence_path(path)
    if not fence.exists():
        return 0
    try:
        value = json.loads(fence.read_text(encoding='utf-8'))
        token = value['fencing_token']
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise LockError('Fencing counter is corrupt: ' + str(fence)
                        + '; inspect it before removing it, removing resets the sequence') from error
    if isinstance(token, bool) or not isinstance(token, int) or token < 0:
        raise LockError('Fencing counter is not a nonnegative integer: ' + str(fence))
    return token


def next_fencing_token(path):
    token = read_fence(path) + 1
    atomic_write(fence_path(path), {'fencing_token': token})
    return token


def keep_fencing_token(path, token):
    if read_fence(path) < token:
        atomic_write(fence_path(path), {'fencing_token': token})


def append_log(path, entry):
    target = log_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, 'a', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    return target


def acquire(lock_path, owner, pid=None, lease_seconds=DEFAULT_LEASE, host=None):
    """Create a new lock. Raises LockHeld if any record already exists."""
    if not nonempty(owner):
        raise LockError('owner must be nonempty')
    if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or lease_seconds <= 0:
        raise LockError('lease_seconds must be a positive integer')
    pid = os.getpid() if pid is None else pid
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise LockError('pid must be a positive integer')
    host = local_host() if host is None else host
    if not nonempty(host):
        raise LockError('host must be nonempty')
    path = Path(lock_path)
    existing = read_lock(path)
    if existing is not None:
        raise LockHeld('Lock is held by %s (pid %d on %s, fencing_token %d)'
                       % (existing['owner'], existing['pid'], existing['host'],
                          existing['fencing_token']))
    now = utc_now()
    record = {'schema': SCHEMA, 'owner': owner, 'pid': pid, 'host': host,
              'acquired_at': now, 'heartbeat_at': now, 'lease_seconds': lease_seconds,
              'fencing_token': next_fencing_token(path)}
    if not exclusive_create(path, encode(record)):
        current = read_lock(path)
        if current is None:
            raise LockError('Lock vanished during concurrent acquire; retry')
        raise LockHeld('Lock is held by %s (pid %d on %s, fencing_token %d)'
                       % (current['owner'], current['pid'], current['host'],
                          current['fencing_token']))
    return record


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _replace_unchanged(path, expected_digest, record):
    if _digest(path) != expected_digest:
        raise LockError('Lock changed during the update; read status again before retrying')
    atomic_write(path, record)


def renew(lock_path, owner, lease_seconds=None):
    """Refresh heartbeat for the recorded owner. Stale locks are not renewable."""
    path = Path(lock_path)
    record = read_lock(path)
    if record is None:
        raise LockError('No lock at ' + str(path))
    if record['owner'] != owner:
        raise LockError('Only the recorded owner may renew; held by ' + record['owner'])
    reasons = stale_reasons(record)
    if reasons:
        raise LockError('Lock is stale (%s); break-stale and re-acquire instead of renewing'
                        % '; '.join(reasons))
    if lease_seconds is not None:
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or lease_seconds <= 0:
            raise LockError('lease_seconds must be a positive integer')
        record['lease_seconds'] = lease_seconds
    record['heartbeat_at'] = utc_now()
    _replace_unchanged(path, _digest(path), record)
    return record


def release(lock_path, owner):
    """Remove the lock. Only the recorded owner may release."""
    path = Path(lock_path)
    record = read_lock(path)
    if record is None:
        raise LockError('No lock at ' + str(path))
    if record['owner'] != owner:
        raise LockError('Only the recorded owner may release; held by ' + record['owner'])
    expected = _digest(path)
    if _digest(path) != expected:
        raise LockError('Lock changed during release; read status before retrying')
    path.unlink()
    return record


def status(lock_path, owner=None, now=None):
    """Report held/staleness without changing anything."""
    path = Path(lock_path)
    record = read_lock(path)
    if record is None:
        return {'held': False, 'stale': False, 'stale_reasons': [], 'record': None,
                'owner_matches': None}
    reasons = stale_reasons(record, now)
    now = now or datetime.now(timezone.utc)
    age = (now - parse_time(record['heartbeat_at'])).total_seconds()
    local = same_host(record['host'], local_host())
    return {'held': True, 'stale': bool(reasons), 'stale_reasons': reasons,
            'heartbeat_age_seconds': round(age, 3),
            'lease_seconds': record['lease_seconds'],
            'pid_alive': pid_alive(record['pid']) if local else None,
            'owner_matches': None if owner is None else record['owner'] == owner,
            'record': record}


def _restore(path, tomb):
    try:
        os.link(tomb, path)
    except OSError:
        raise LockError('Lock changed while being broken; the newer lock is at ' + str(tomb))
    os.unlink(tomb)


def break_stale(lock_path, actor, reason, force=False):
    """Move a stale (or forced) lock aside, log why, keep the fencing sequence."""
    if not nonempty(actor) or not nonempty(reason):
        raise LockError('break-stale needs an actor and a concrete reason')
    path = Path(lock_path)
    if not path.exists():
        raise LockError('No lock at ' + str(path))
    before = _digest(path)
    unreadable = None
    try:
        record = read_lock(path)
    except LockError as error:
        if not force:
            raise LockError(str(error) + '; use --force with a reason to move it aside')
        record = None
        unreadable = str(error)
    if record is None and unreadable is None:
        raise LockError('No lock at ' + str(path))
    reasons = stale_reasons(record) if record is not None else []
    if not reasons and not force:
        raise LockError('Lock is live (heartbeat fresh, pid running); use --force only for a '
                        'known hung holder and record why')
    if force and not reasons:
        reasons = ['forced break: ' + reason]
    if record is not None:
        read_fence(path)  # Fail before moving the lock if the counter is corrupt.
    tomb = path.with_name(path.name + '.broken-' + uuid.uuid4().hex)
    try:
        os.rename(path, tomb)
    except FileNotFoundError as error:
        raise LockError('Lock disappeared while being broken; nothing to do') from error
    if _digest(tomb) != before:
        _restore(path, tomb)
        raise LockError('Lock changed while being broken; the newer lock was restored')
    if record is not None:
        keep_fencing_token(path, record['fencing_token'])
    append_log(path, {'at': utc_now(), 'action': 'break-stale', 'actor': actor,
                      'reason': reason, 'lock': str(path), 'forced': bool(force),
                      'stale_reasons': reasons, 'record': record,
                      'unreadable': unreadable})
    tomb.unlink()
    return {'record': record, 'stale_reasons': reasons, 'forced': bool(force),
            'reason': reason, 'actor': actor, 'log': str(log_path(path)),
            'unreadable': unreadable}


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='action', required=True)

    def command(name, help_text):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument('--lock', required=True, help='Lock file path')
        return sub

    for name, help_text in (('acquire', 'Acquire an exclusive resource'),
                            ('renew', 'Refresh the heartbeat of an owned lock'),
                            ('release', 'Remove an owned lock')):
        sub = command(name, help_text)
        sub.add_argument('--owner', required=True, help='Session/agent identity')
        if name == 'acquire':
            sub.add_argument('--pid', type=int, required=True,
                             help='Native PID of the long-lived holder (PowerShell $PID, POSIX $$); '
                                  'MSYS/Git Bash $$ is a pseudo-pid and is rejected as dead')
            sub.add_argument('--lease', type=int, default=DEFAULT_LEASE,
                             help='Lease seconds (default %d)' % DEFAULT_LEASE)
            sub.add_argument('--host', help='Override host label (default: hostname)')
        if name == 'renew':
            sub.add_argument('--lease', type=int,
                             help='Replace the lease with this many seconds')
    sub = command('status', 'Show holder, heartbeat age and staleness')
    sub.add_argument('--owner', help='Also report whether this caller is the owner')
    sub = command('break-stale', 'Move a stale or unreadable lock aside with a reason')
    sub.add_argument('--owner', required=True, help='Acting session/agent identity')
    sub.add_argument('--reason', required=True, help='Why the holder is considered gone')
    sub.add_argument('--force', action='store_true',
                     help='Also break a live or unreadable lock; use only for a known hung holder')
    return parser.parse_args(argv)


def run(args):
    if args.action == 'acquire':
        record = acquire(args.lock, args.owner, pid=args.pid,
                         lease_seconds=args.lease, host=args.host)
        return {'ok': True, 'action': 'acquire', 'lock': str(Path(args.lock)), 'record': record}
    if args.action == 'renew':
        record = renew(args.lock, args.owner, lease_seconds=args.lease)
        return {'ok': True, 'action': 'renew', 'lock': str(Path(args.lock)), 'record': record}
    if args.action == 'release':
        record = release(args.lock, args.owner)
        return {'ok': True, 'action': 'release', 'lock': str(Path(args.lock)), 'record': record}
    if args.action == 'status':
        return {'ok': True, 'action': 'status', 'lock': str(Path(args.lock)),
                **status(args.lock, owner=args.owner)}
    if args.action == 'break-stale':
        result = break_stale(args.lock, args.owner, args.reason, force=args.force)
        return {'ok': True, 'action': 'break-stale', 'lock': str(Path(args.lock)), **result}
    raise LockError('Unknown action')


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    args = parse_args(argv)
    try:
        print(json.dumps(run(args), ensure_ascii=False))
        return 0
    except LockHeld as error:
        print(json.dumps({'ok': False, 'error': str(error), 'reason': 'held'}, ensure_ascii=False))
        return 3
    except (LockError, OSError, ValueError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
