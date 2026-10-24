#!/usr/bin/env python3
"""Private, supervised experience ledger. Python 3.9+, no network or models.

python -B scripts/experience_store.py --root PRIVATE_ROOT --request request.json
The host checks real user messages; this program checks their structural binding.
All callers, including workflow finalization, use Store's same OS lock.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import uuid

KINDS = {'preference', 'method', 'template_risk', 'hypothesis', 'playbook'}
STATUSES = {'candidate', 'active', 'needs_review', 'rejected', 'superseded', 'revoked'}
BODY_FIELDS = ('条件', '问题', '方法', '观察结果', '证据', '验证办法', '不适用情形')
RECAP_FIELDS = ('时间', '任务场景', '关键决策', '问题与解决', '可复用经验', '待优化项')
CONTENT_FIELDS = ('id', 'revision', 'kind', 'scope', 'source_refs', 'verification',
                  'depends_on', 'lineage', 'body_sha256', 'stages', 'replaces')


class MemoryError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise MemoryError(message)


def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def token(prefix):
    return prefix + '-' + uuid.uuid4().hex


def canonical(value):
    """Sorted compact JSON, UTF-8, LF in strings, no Unicode folding or NaN."""
    if isinstance(value, str):
        return value.replace('\r\n', '\n').replace('\r', '\n')
    if isinstance(value, list):
        return [canonical(x) for x in value]
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in value.items()}
    return value


def encoded(value):
    return json.dumps(canonical(value), sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def atomic(path, value, raw=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(value.encode('utf-8') if raw else encoded(value) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def immutable(path, value, raw=False):
    data = value if raw else encoded(value).decode('utf-8') + '\n'
    if path.exists():
        require(path.read_text(encoding='utf-8') == data, 'Immutable file conflict: ' + str(path))
    else:
        atomic(path, data, raw=True)


def resolve_root(root=None):
    if root is None:
        root = os.environ.get('LAB_REPORT_MEMORY_HOME')
    if not root:
        root = (Path.home() / '.lab-report' / 'memory' if os.name == 'nt' else
                Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local' / 'state') / 'lab-report' / 'memory')
    result = Path(root).expanduser().resolve()
    package = Path(__file__).resolve().parents[1]
    require(result != package and package not in result.parents, 'Memory root cannot be inside skill/repository')
    require(not any((p / '.git').exists() for p in (result,) + tuple(result.parents)),
            'Memory root cannot be inside a Git checkout')
    return result


@contextmanager
def lock(path, timeout=5):
    """Persistent lock inode, released by OS on process death; never age-unlinked."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                stream.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise MemoryError('Memory lock timeout; retry without deleting lock file')
                time.sleep(0.02)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def key(item):
    require(isinstance(item, dict) and re.fullmatch(r'[A-Za-z0-9_-]+', str(item.get('id', ''))) is not None
            and type(item.get('revision')) is int and item['revision'] > 0, 'Invalid ID/revision')
    return item['id'] + '@' + str(item['revision'])


def content_digest(record):
    return sha({k: record[k] for k in CONTENT_FIELDS})


def matches(scope, context):
    return all(k in context and context[k] == v for k, v in scope.items())


class Store:
    def __init__(self, root=None, create=False, timeout=5):
        self.root = resolve_root(root)
        self.create = create
        self.timeout = timeout
        self.registry = None

    @contextmanager
    def transaction(self):
        require(self.create or (self.root / 'registry.json').is_file(), 'Memory unavailable/uninitialized')
        with lock(self.root / '.lock', self.timeout):
            path = self.root / 'registry.json'
            if not path.exists():
                require(self.create, 'Memory unavailable')
                atomic(path, dict(schema=1, root_id=token('root'), generation=0, records={}, heads={},
                                  sources={}, sessions={}, invocations={}, displays={}, confirmations={},
                                  tombstones=[], history=[], cursors={}))
            self.registry = read(path)
            r = self.registry
            require(r.get('schema') == 1 and isinstance(r.get('root_id'), str)
                    and type(r.get('generation')) is int, 'Invalid memory registry')
            for field in ('records', 'heads', 'sources', 'sessions', 'invocations', 'displays', 'confirmations', 'cursors'):
                require(isinstance(r.get(field), dict), 'Invalid registry field: ' + field)
            require(isinstance(r.get('tombstones'), list) and isinstance(r.get('history'), list), 'Invalid governance history')
            before = sha(r)
            try:
                yield self
                if sha(r) != before:
                    r['generation'] += 1
                    atomic(path, r)
                    self.rebuild()
            finally:
                self.registry = None

    def savepoint(self):
        """Used only for explicit backup snapshots while the root lock is held."""
        return json.loads(encoded(self.registry))

    def body_path(self, record):
        key(record)
        return self.root / ('playbooks' if record['kind'] == 'playbook' else 'lessons') / record['id'] / (str(record['revision']) + '.md')

    def get(self, ref):
        k = key(ref)
        require(k in self.registry['records'], 'Unknown revision: ' + k)
        return self.registry['records'][k]

    def intact(self, record):
        require(record['status'] in STATUSES and content_digest(record) == record['content_digest'], 'Content metadata drift')
        require(file_sha(self.body_path(record)) == record['body_sha256'], 'Immutable body drift')

    def blocked(self, record):
        lineages = set(record['lineage'])
        return any(not t.get('reauthorized_by') and (t.get('id') == record['id'] or lineages.intersection(t.get('lineage', [])))
                   and (not t.get('scope') or matches(t['scope'], record['scope']))
                   for t in self.registry['tombstones'])

    def graph(self):
        records = self.registry['records']
        def visit(k, stack):
            require(k not in stack, 'Cyclic/self memory dependency')
            if k in records:
                for dep in records[k]['depends_on']:
                    visit(key(dep), stack | {k})
        for k in records:
            visit(k, set())

    def check(self, ref, context, invocation_id=None, stack=None):
        record = self.get(ref)
        self.intact(record)
        require(not self.blocked(record), 'Rejected/revoked lineage')
        require(record['status'] == 'active' and self.registry['heads'].get(record['id']) == record['revision'],
                'Revision is not active')
        require(record['kind'] != 'hypothesis', 'Hypothesis is not executable')
        require(matches(record['scope'], context), 'Scope unknown/mismatch')
        approval = record['memory_approval']
        require(isinstance(approval, dict) and approval.get('content_digest') == record['content_digest'], 'No bound memory approval')
        require(approval.get('mode') == 'long_term' or approval.get('invocation_id') == invocation_id,
                'Approval limited to another invocation')
        confirmation = self.confirmation(approval['confirmation_id'])
        require(self.registry['confirmations'][approval['confirmation_id']]['consumed']
                and any(key(d) == key(record) and d['content_digest'] == record['content_digest']
                        and d['operation'] in {'activate', 'use', 'resume'} for d in confirmation['decisions']),
                'Approval did not consume this displayed item')
        self.sources_ok(record)
        self.verified(record)
        k = key(ref)
        stack = stack or set()
        require(k not in stack, 'Cyclic memory dependency')
        checked = {k: record['state_version']}
        for dep in record['depends_on']:
            checked.update(self.check(dep, context, invocation_id, stack | {k}))
        return checked

    def verified(self, record):
        v = record['verification']
        require(v.get('status') == 'verified' and v.get('evidence_refs'), 'Verification evidence missing')
        require(record['kind'] == 'preference' or (v.get('verifier') and v.get('independent') is True),
                'Independent technical verification required')

    def sources_ok(self, record):
        require(record['source_refs'], 'No original sources')
        for ref in record['source_refs']:
            source = self.registry['sources'].get(ref)
            require(source and source.get('valid') is True, 'Source unavailable/invalid')
            for artifact in source.get('artifacts', []):
                require(file_sha(artifact['path']) == artifact['sha256'], 'Original source drift')

    def begin(self, request):
        require(request.get('explicit_use_ref') and request.get('materials_read') and request.get('task_id'),
                'Read current materials before explicit begin')
        materials = request['materials_read']
        require(isinstance(materials, dict) and materials.get('refs') and isinstance(materials.get('constraints'), dict),
                'Materials need references and independently extracted constraints')
        host = request.get('host', 'manual')
        native = request.get('native_session_id')
        fallback = request.get('session_token')
        require(native or fallback, 'Supply native_session_id or a retained begin session_token')
        session_ref = host + ':' + str(native or fallback)
        sid = sha(session_ref)[:32]
        self.registry['sessions'].setdefault(sid, {'session_ref': session_ref, 'created_at': now()})
        if request.get('resume'):
            inv = self.registry['invocations'].get(request.get('invocation_id'))
            require(inv and inv['session_ref'] == session_ref and inv['task_id'] == request['task_id']
                    and inv['materials_digest'] == sha(materials), 'Resume identity/materials mismatch')
            return inv
        for inv in self.registry['invocations'].values():
            if (inv['session_ref'], inv['task_id'], inv['materials_digest']) == (session_ref, request['task_id'], sha(materials)):
                return inv
        iid = token('inv')
        frozen = [k for k, v in self.registry['records'].items()
                  if v['status'] in {'candidate', 'needs_review', 'active'} and not v.get('deleted')
                  and matches(v['scope'], materials['constraints'])]
        inv = dict(invocation_id=iid, task_id=request['task_id'], session_ref=session_ref, session_id=sid,
                   materials_digest=sha(materials), materials_read=materials, explicit_use_ref=request['explicit_use_ref'],
                   frozen=frozen, displays=[], created_at=now())
        self.registry['invocations'][iid] = inv
        return inv

    def invocation(self, iid):
        require(iid in self.registry['invocations'], 'Unknown invocation; explicit begin/resume required')
        return self.registry['invocations'][iid]

    def collect(self, request):
        inv = self.invocation(request['invocation_id'])
        source = dict(request['source'])
        require(all(source.get(k) for k in ('provider', 'namespace', 'record_id')), 'Original source identity required; retain local token on retry')
        payload = request['payload']
        require(isinstance(payload, dict) and payload, 'Original business payload required')
        payload = {k: v for k, v in payload.items() if k not in {'received_at', 'retry_count', 'temp_path', 'adapter_summary'}}
        pd = sha(payload)
        source.setdefault('revision', pd)
        identity = {k: source[k] for k in ('provider', 'namespace', 'record_id', 'revision')}
        eid = sha({'protocol': 1, 'source': identity, 'event_type': request['event_type']})
        value = dict(event_id=eid, payload_digest=pd, source=identity, payload=payload,
                     event_type=request['event_type'], adapter=request.get('adapter', 'direct'),
                     occurred_at=request['occurred_at'], recorded_at=now(), invocation_id=inv['invocation_id'],
                     origin=request.get('origin'), source_lineage=request.get('source_lineage'),
                     verification_run_id=request.get('verification_run_id'), artifacts=request.get('artifacts', []),
                     classification=request.get('classification', 'fact'))
        require(value['classification'] in {'fact', 'user_requirement', 'inference', 'verified_result', 'hypothesis'}, 'Invalid event classification')
        require(datetime.fromisoformat(value['occurred_at']).utcoffset() is not None, 'Occurrence time needs timezone')
        journal = self.root / 'sessions' / inv['session_id'] / 'collection_events.jsonl'
        # Root lock also serializes writers to the same session shard.
        events = self.read_events(journal, repair=True)
        for prior in events:
            if prior['event_id'] == eid:
                require(prior['payload_digest'] == pd, 'Same event identity has conflicting payload')
                return {'event_id': eid, 'duplicate': True}
        indexed = self.registry['sources'].get(eid)
        require(not indexed or indexed['payload_digest'] == pd, 'Conflicting event across sessions')
        journal.parent.mkdir(parents=True, exist_ok=True)
        with open(journal, 'ab') as stream:
            stream.write(encoded(value) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        return {'event_id': eid, 'duplicate': bool(indexed)}

    def read_events(self, path, repair=False):
        if not path.exists():
            return []
        data = path.read_bytes()
        lines = data.splitlines(keepends=True)
        result = []
        good = 0
        for index, line in enumerate(lines):
            try:
                item = json.loads(line)
                require(isinstance(item, dict) and item.get('event_id') and item.get('payload_digest') == sha(item['payload']), 'Bad collection event')
            except (ValueError, KeyError, UnicodeError):
                require(index == len(lines) - 1 and not line.endswith(b'\n'), 'Corrupt interior journal record')
                if repair:
                    atomic(path.with_name('incomplete-' + uuid.uuid4().hex + '.bin'), line.decode('utf-8', errors='replace'), raw=True)
                    with open(path, 'r+b') as stream:
                        stream.truncate(good)
                break
            result.append(item)
            good += len(line)
        if repair and result and good == len(data) and not data.endswith(b'\n'):
            with open(path, 'ab') as stream:
                stream.write(b'\n')
        return result

    def consolidate(self, request):
        inv = self.invocation(request['invocation_id'])
        journal = self.root / 'sessions' / inv['session_id'] / 'collection_events.jsonl'
        events = self.read_events(journal, repair=True)
        cursor = self.registry['cursors'].get(inv['session_id'], 0)
        new = events[cursor:]
        for e in new:
            prior = self.registry['sources'].get(e['event_id'])
            require(not prior or prior['payload_digest'] == e['payload_digest'], 'Source conflict on replay')
            if not prior:
                self.registry['sources'][e['event_id']] = dict(e, valid=True)
        created = []
        for draft in request.get('candidates', []):
            require(set(draft['source_refs']) <= {e['event_id'] for e in new}, 'Candidate must use this unprocessed increment')
            created.append(self.candidate(draft, inv))
        self.registry['cursors'][inv['session_id']] = len(events)
        recap = dict(request.get('recap') or {})
        require(not recap or set(recap) == set(RECAP_FIELDS), 'Recap requires six named sections')
        if not recap:
            recap = dict(zip(RECAP_FIELDS, [now(), inv['task_id'], '无新增决策', '无新增问题',
                                          '无新经验' if not new else '新增事件待提炼：' + str(len(new)), '无新增待优化项']))
        rid = token('recap')
        text = '# Session 回顾\n\n' + '\n\n'.join('## ' + h + '\n\n' + str(recap[h]) for h in RECAP_FIELDS)
        immutable(journal.parent / (rid + '.md'), text + '\n', raw=True)
        self.registry['history'].append(dict(action='consolidate', session_id=inv['session_id'], recap_id=rid,
                                             event_ids=[e['event_id'] for e in new], created=created, at=now()))
        return dict(new_events=len(new), candidates=created, recap_id=rid)

    def candidate(self, draft, inv):
        require(draft.get('kind') in KINDS and isinstance(draft.get('scope'), dict), 'Invalid kind/scope')
        sections = draft['sections']
        require(set(sections) == set(BODY_FIELDS) and all(isinstance(v, str) and v.strip() for v in sections.values()), 'Seven nonempty body sections required')
        lid = draft.get('id') or token('lesson')
        revisions = [v['revision'] for v in self.registry['records'].values() if v['id'] == lid]
        revision = max(revisions, default=0) + 1
        refs = draft['source_refs']
        require(refs and all(x in self.registry['sources'] for x in refs), 'Unknown original source')
        lineage = sorted(set(sha({k: self.registry['sources'][x]['source'][k] for k in ('provider', 'namespace', 'record_id')}) for x in refs))
        for predecessor in draft.get('predecessors', []):
            lineage.extend(self.get(predecessor)['lineage'])
        body = '\n\n'.join('## ' + h + '\n\n' + sections[h] for h in BODY_FIELDS) + '\n'
        record = dict(id=lid, revision=revision, status='candidate', kind=draft['kind'], scope=draft['scope'],
                      source_refs=refs, verification=draft.get('verification', {'status': 'unverified'}),
                      depends_on=draft.get('depends_on', []), lineage=sorted(set(lineage)),
                      body_sha256=hashlib.sha256(body.encode('utf-8')).hexdigest(), stages=draft.get('stages', []),
                      replaces=draft.get('replaces'), memory_approval=None, created_at=now(), last_used_at=None,
                      last_verified_at=None, state_version=1, origin_invocation=inv['invocation_id'], pause_reason=None)
        k = key(record)
        record['content_digest'] = content_digest(record)
        require(not self.blocked(record), 'Rejected/revoked lineage; explicit reauthorization needed')
        self.registry['records'][k] = record
        self.graph()
        immutable(self.body_path(record), body, raw=True)
        return {'id': lid, 'revision': revision, 'content_digest': record['content_digest']}

    def revise(self, request):
        require(request.get('management_ref'), 'Revision/reproposal needs explicit user management reference')
        previous = self.get(request['previous'])
        draft = dict(request['candidate'], id=previous['id'], predecessors=[request['previous']])
        if self.registry['heads'].get(previous['id']):
            draft['replaces'] = {'id': previous['id'], 'revision': self.registry['heads'][previous['id']]}
        return self.candidate(draft, self.invocation(request['invocation_id']))

    def support_count(self, record):
        sources = [self.registry['sources'][x] for x in record['source_refs']]
        return len({(s['origin'], s['source_lineage'], s['verification_run_id']) for s in sources
                    if s.get('origin') and s.get('source_lineage') and s.get('verification_run_id')})

    def display(self, request):
        inv = self.invocation(request['invocation_id'])
        items = []
        for proposed in request['items']:
            record = self.get(proposed)
            k = key(record)
            require(k in inv['frozen'] or request.get('management_ref'), 'Candidate belongs to a later explicit invocation')
            op = proposed['operation']
            require(op in {'activate', 'use', 'defer', 'reject', 'pause', 'resume', 'revoke', 'delete', 'reauthorize'}, 'Invalid display operation')
            if not record.get('deleted'):
                self.intact(record)
            else:
                require(op in {'reauthorize', 'revoke', 'delete'}, 'Deleted revision has no executable content')
            items.append(dict(id=record['id'], revision=record['revision'], content_digest=record['content_digest'],
                              state_version=record['state_version'], operation=op, scope=record['scope'],
                              replaces=record['replaces'], difference=proposed.get('difference', ''),
                              body='[deleted]' if record.get('deleted') else self.body_path(record).read_text(encoding='utf-8'), source_refs=record['source_refs'],
                              verification=record['verification'], status=record['status']))
        require(items and len({key(x) for x in items}) == len(items), 'Empty/duplicate display')
        identity = sha(dict(invocation_id=inv['invocation_id'], items=items))
        for did in inv['displays']:
            old = self.registry['displays'][did]
            if old['items_digest'] == identity:
                return self.display_read(did)
        did = token('display')
        value = dict(root_id=self.registry['root_id'], display_id=did, invocation_id=inv['invocation_id'],
                     materials_digest=inv['materials_digest'], items=items, created_at=now(), items_digest=identity,
                     management_ref=request.get('management_ref'))
        value['display_digest'] = sha(value)
        immutable(self.root / 'reviews' / (did + '.json'), value)
        self.registry['displays'][did] = {'digest': value['display_digest'], 'items_digest': identity}
        inv['displays'].append(did)
        return value

    def display_read(self, did):
        value = read(self.root / 'reviews' / (did + '.json'))
        require(value['root_id'] == self.registry['root_id'] and value['display_digest'] == self.registry['displays'][did]['digest']
                and sha({k: v for k, v in value.items() if k != 'display_digest'}) == value['display_digest'], 'Display mismatch')
        return value

    def confirm(self, request):
        display = self.display_read(request['display_id'])
        check = request.get('host_check')
        require(isinstance(check, dict) and check.get('checked_by') and check.get('message_ref')
                and re.fullmatch(r'[0-9a-f]{64}', str(check.get('message_digest', '')))
                and check.get('matched_display_digest') == display['display_digest'], 'Host must check real response against this display')
        decisions = request.get('decisions')
        require(isinstance(decisions, list) and decisions and check.get('decisions_digest') == sha(decisions), 'Exact item decisions must be host checked')
        shown = {key(x): x for x in display['items']}
        require(len({key(x) for x in decisions}) == len(decisions), 'Duplicate decisions')
        for decision in decisions:
            item = shown.get(key(decision))
            require(item and decision.get('operation') == item['operation']
                    and decision.get('content_digest') == item['content_digest'], 'Unshown/changed item or operation')
        cid = token('confirmation')
        value = dict(root_id=self.registry['root_id'], confirmation_id=cid, display_id=display['display_id'],
                     display_digest=display['display_digest'], decisions=decisions, host_check=check, created_at=now())
        immutable(self.root / 'reviews' / (cid + '.json'), value)
        self.registry['confirmations'][cid] = {'digest': sha(value), 'consumed': False}
        return {'confirmation_id': cid}

    def confirmation(self, cid):
        value = read(self.root / 'reviews' / (cid + '.json'))
        require(value['root_id'] == self.registry['root_id'] and sha(value) == self.registry['confirmations'][cid]['digest'], 'Confirmation mismatch')
        display = self.display_read(value['display_id'])
        require(value['display_digest'] == display['display_digest'], 'Confirmation/display mismatch')
        return value

    def consume(self, request):
        cid = request['confirmation_id']
        value = self.confirmation(cid)
        require(not self.registry['confirmations'][cid]['consumed'], 'Confirmation already consumed')
        display = self.display_read(value['display_id'])
        inv = self.invocation(display['invocation_id'])
        shown = {key(x): x for x in display['items']}
        applied, errors = [], []
        for decision in value['decisions']:
            item = shown[key(decision)]
            try:
                record = self.get(item)
                if not record.get('deleted'):
                    self.intact(record)
                require(record['content_digest'] == item['content_digest'] and record['state_version'] == item['state_version'], 'Stale item; show current revision/state')
                op = decision['operation']
                self.transition(record, op, cid, inv, decision.get('reason', 'Explicit displayed decision'))
                applied.append(key(record))
            except (ValueError, OSError, KeyError) as error:
                errors.append({'item': key(item), 'error': str(error)})
        self.registry['confirmations'][cid]['consumed'] = True
        self.propagate()
        return dict(applied=applied, errors=errors)

    def transition(self, r, op, cid, inv, reason):
        status = r['status']
        if op == 'defer':
            return
        if op in {'activate', 'use', 'resume'}:
            require(status in {'candidate', 'needs_review', 'active'} and not self.blocked(r), 'Terminal/blocked revision cannot activate')
            require(r['kind'] != 'hypothesis', 'Hypothesis requires a new verified revision')
            self.sources_ok(r)
            self.verified(r)
            require(matches(r['scope'], inv['materials_read']['constraints']), 'Approval scope mismatch')
            for dep in r['depends_on']:
                self.check(dep, inv['materials_read']['constraints'], inv['invocation_id'])
            previous = self.registry['heads'].get(r['id'])
            if previous and previous != r['revision']:
                require(r['replaces'] == {'id': r['id'], 'revision': previous}, 'Replacement target must be explicitly displayed')
            require(not (r.get('pause_reason') or '').startswith('user:') or op == 'resume', 'User pause requires explicit resume')
            if op == 'resume':
                require(status == 'needs_review' and r['memory_approval'], 'Resume requires prior approval')
                self.confirmation(r['memory_approval']['confirmation_id'])
            else:
                r['memory_approval'] = dict(confirmation_id=cid, content_digest=r['content_digest'],
                                           mode='long_term' if op == 'activate' else 'invocation', invocation_id=inv['invocation_id'])
            if previous and previous != r['revision']:
                old = self.get(r['replaces'])
                old.update(status='superseded', state_version=old['state_version'] + 1)
            self.registry['heads'][r['id']] = r['revision']
            r.update(status='active', pause_reason=None, last_verified_at=now())
        elif op == 'reject':
            require(status in {'candidate', 'needs_review'} and not r['memory_approval'], 'Previously approved revision must pause/revoke')
            r['status'] = 'rejected'
            self.tombstone(r, 'reject', reason)
        elif op == 'pause':
            require(status in {'active', 'candidate', 'needs_review'}, 'Terminal revision cannot pause')
            r.update(status='needs_review', pause_reason='user: ' + reason)
        elif op in {'revoke', 'delete'}:
            r['status'] = 'revoked'
            self.tombstone(r, op, reason)
            if op == 'delete':
                self.delete_content(r)
        elif op == 'reauthorize':
            require(status in {'revoked', 'rejected'}, 'Only terminal lineage needs reauthorization')
            for t in self.registry['tombstones']:
                if t.get('id') == r['id'] or set(t.get('lineage', [])).intersection(r['lineage']):
                    t['reauthorized_by'] = cid
            # Keep the old terminal revision; a new linked candidate still needs approval.
        else:
            raise MemoryError('Unsupported transition')
        r['state_version'] += 1
        self.registry['history'].append(dict(action=op, item=key(r), reason=reason, confirmation_id=cid, at=now()))

    def tombstone(self, r, action, reason):
        self.registry['tombstones'].append(dict(id=r['id'], lineage=r['lineage'], scope=r['scope'],
                                                action=action, reason=reason, at=now()))

    def propagate(self):
        changed = True
        while changed:
            changed = False
            for r in self.registry['records'].values():
                if r['status'] == 'active' and any(self.get(d)['status'] != 'active' or self.blocked(self.get(d)) for d in r['depends_on']):
                    r.update(status='needs_review', pause_reason='dependency', state_version=r['state_version'] + 1)
                    changed = True

    def delete_content(self, r):
        """Remove managed text and derived audit copies; retain opaque lineage tombstones."""
        affected = {key(r)}
        while True:
            more = {k for k, v in self.registry['records'].items() if any(key(d) in affected for d in v['depends_on'])}
            if more <= affected:
                break
            affected |= more
        for k in affected:
            rec = self.registry['records'][k]
            self.body_path(rec).unlink(missing_ok=True)
            rec.update(deleted=True, status='revoked')
        # Displays and recaps can repeat text: remove affected managed copies conservatively.
        for did in list(self.registry['displays']):
            path = self.root / 'reviews' / (did + '.json')
            if path.exists() and any(key(x) in affected for x in read(path)['items']):
                path.unlink()
                self.registry['displays'][did]['deleted'] = True
        source_ids = {x for k in affected for x in self.registry['records'][k]['source_refs']}
        for eid in source_ids:
            s = self.registry['sources'].get(eid)
            if s:
                for field in ('payload', 'artifacts'):
                    s.pop(field, None)
                s['valid'] = False
        for journal in (self.root / 'sessions').glob('*/collection_events.jsonl'):
            events = self.read_events(journal)
            atomic(journal, ''.join(encoded(e).decode('utf-8') + '\n' for e in events if e['event_id'] not in source_ids), raw=True)
            self.registry['cursors'][journal.parent.name] = len([e for e in events if e['event_id'] not in source_ids])
            for recap in journal.parent.glob('recap-*.md'):
                recap.unlink()

    def query(self, request):
        context = request['context']
        results, clues = [], []
        for r in self.registry['records'].values():
            if request.get('stage') and r['stages'] and request['stage'] not in r['stages']:
                continue
            try:
                checked = self.check(r, context, request.get('invocation_id'))
                results.append(dict(id=r['id'], revision=r['revision'], content_digest=r['content_digest'], scope=r['scope'],
                                    source_refs=r['source_refs'], depends_on=r['depends_on'], checked=checked,
                                    independent_support_count=self.support_count(r),
                                    body=self.body_path(r).read_text(encoding='utf-8'), risk='Method advice only; current evidence and original gates remain required'))
            except (ValueError, OSError, KeyError) as error:
                clues.append({'id': r['id'], 'revision': r['revision'], 'reason': str(error)})
        results.sort(key=lambda r: (-len(r['scope']), r['id'], -r['revision']))
        limit = request.get('limit', 5)
        require(type(limit) is int and 0 < limit <= 20, 'Query limit must be 1..20')
        return dict(root_id=self.registry['root_id'], items=results[:limit], clues=clues)

    def check_used(self, state):
        checked = {}
        for used in state['lessons_used']:
            require(used['root_id'] == self.registry['root_id'], 'Configured memory root identity differs')
            r = self.get(used)
            require(r['content_digest'] == used['content_digest'], 'Adopted content mismatch')
            checked.update(self.check(r, used['context'], used['invocation_id']))
        return dict(task_id=state['task_id'], root_id=self.registry['root_id'], checked=checked,
                    result='valid', checked_at=now())

    def rebuild(self):
        r = self.registry
        lines = ['# 经验索引', '', '由 registry.json 重建；仅 query 输出可用于执行。', '']
        overview = ['# 长期经验总览', '', '总览不是有效规则上下文。', '']
        for rec in r['records'].values():
            lines.append(key(rec) + ' — ' + rec['status'] + ('（正文已删除）' if rec.get('deleted') else ''))
        for h in r['history']:
            if h['action'] == 'consolidate':
                p = self.root / 'sessions' / h['session_id'] / (h['recap_id'] + '.md')
                if p.exists():
                    overview.extend([p.read_text(encoding='utf-8'), '关联：' + ', '.join(key(x) for x in h['created']), ''])
            else:
                overview.append(h['at'] + ' ' + h['action'] + ' ' + h.get('item', ''))
        overview.extend(['', '## 当前修订与治理结果', ''] + lines[4:])
        atomic(self.root / 'INDEX.md', '\n'.join(lines) + '\n', raw=True)
        atomic(self.root / 'experience.md', '\n'.join(overview) + '\n', raw=True)
        registered = {self.body_path(v).resolve() for v in r['records'].values()}
        orphans = [p.relative_to(self.root).as_posix() for folder in ('lessons', 'playbooks')
                   for p in (self.root / folder).glob('*/*.md') if p.resolve() not in registered]
        return {'orphans': orphans, 'action': 'Listed only; never activated or deleted'}

    def backup(self, destination):
        require(not Path(destination).exists(), 'Backup destination exists')
        files = {p.relative_to(self.root).as_posix(): p.read_text(encoding='utf-8')
                 for folder in ('lessons', 'playbooks', 'reviews', 'sessions')
                 for p in (self.root / folder).rglob('*') if p.is_file() and p.suffix in {'.md', '.json', '.jsonl'}}
        snapshot = dict(protocol=1, registry=self.savepoint(), files=files, created_at=now())
        snapshot['digest'] = sha(snapshot)
        atomic(Path(destination), snapshot)
        return {'backup': str(destination), 'digest': snapshot['digest']}

    def restore(self, request):
        snapshot = read(request['path'])
        require(snapshot.get('protocol') == 1 and snapshot.get('digest') == sha({k: v for k, v in snapshot.items() if k != 'digest'}), 'Invalid snapshot')
        old = snapshot['registry']
        # Imports never inherit approval; current tombstones always win, even from older snapshots.
        for t in old.get('tombstones', []):
            if t not in self.registry['tombstones']:
                self.registry['tombstones'].append(t)
        imported = []
        for previous in old.get('records', {}).values():
            if previous.get('deleted') or self.blocked(previous):
                continue
            path = ('playbooks' if previous['kind'] == 'playbook' else 'lessons') + '/' + previous['id'] + '/' + str(previous['revision']) + '.md'
            body = snapshot['files'].get(path)
            require(body and hashlib.sha256(body.encode('utf-8')).hexdigest() == previous['body_sha256']
                    and content_digest(previous) == previous['content_digest'], 'Snapshot body/metadata mismatch')
            k = key(previous)
            if k in self.registry['records']:
                require(self.registry['records'][k]['content_digest'] == previous['content_digest'], 'Import revision conflict')
                continue
            rec = dict(previous, status='needs_review', memory_approval=None, pause_reason='import: verify source and revocation history', state_version=1)
            self.registry['records'][k] = rec
            immutable(self.body_path(rec), body, raw=True)
            imported.append(k)
        self.graph()
        self.propagate()
        self.registry['history'].append(dict(action='restore', at=now(), item=', '.join(imported)))
        return {'quarantined': imported, 'note': 'No active/approval restored; re-collect current sources before a new revision'}


def execute(request, root=None):
    require(isinstance(request, dict), 'Request must be an object')
    if request.get('mode') == 'off':
        return {'mode': 'off', 'loaded': False}
    action = request.get('action')
    if action == 'new_session_token':
        return {'session_token': token('session')}
    with Store(root, create=action in {'init', 'begin'}).transaction() as store:
        if 'expected_generation' in request:
            require(request['expected_generation'] == store.registry['generation'], 'Registry generation conflict')
        if action == 'init':
            return {'root_id': store.registry['root_id']}
        if action == 'rebuild':
            return store.rebuild()
        if action == 'backup':
            return store.backup(request['path'])
        if action == 'invalidate_source':
            require(request.get('reason'), 'Source invalidation needs evidence/reason')
            store.registry['sources'][request['event_id']]['valid'] = False
            for r in store.registry['records'].values():
                if request['event_id'] in r['source_refs'] and r['status'] == 'active':
                    r.update(status='needs_review', pause_reason='source: ' + request['reason'], state_version=r['state_version'] + 1)
            store.propagate()
            return {'invalidated': request['event_id']}
        method = {'begin': store.begin, 'collect': store.collect, 'consolidate': store.consolidate,
                  'display': store.display, 'confirm': store.confirm, 'consume': store.consume,
                  'query': store.query, 'restore': store.restore, 'revise': store.revise}.get(action)
        require(method is not None, 'Unknown memory action')
        return method(request)


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', help='Private root; otherwise resolve environment/default at this entry')
    parser.add_argument('--request', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps({'ok': True, 'result': execute(read(args.request), args.root)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
