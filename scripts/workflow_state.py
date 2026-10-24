#!/usr/bin/env python3
"""Small local workflow ledger (Python 3.9+, standard library only).

Usage: python -B workflow_state.py --state WORK/state.json --request action.json
Requests and output use UTF-8 JSON. Run status before resuming work. Paths in
requests resolve relative to the state file's directory. This tool NEVER runs
experiments, invokes agents, grants permission, or certifies review quality.
Confirmation/context references are assertions to be verified by the host;
a same-permission writer can tamper with this ledger. See --help and notes.
"""
import argparse
from contextlib import nullcontext
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid

_memory_spec = importlib.util.spec_from_file_location('lab_report_experience', Path(__file__).with_name('experience_store.py'))
memory = importlib.util.module_from_spec(_memory_spec)
_memory_spec.loader.exec_module(memory)

PHASES = {'intake', 'awaiting_confirmation', 'produce', 'review', 'done', 'failed', 'blocked'}
CHECKS = {'requirements', 'evidence', 'writing', 'format', 'render', 'final_file'}


class GuardError(ValueError):
    pass


def require(test, message):
    if not test:
        raise GuardError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def read_json(path):
    with open(path, encoding='utf-8') as stream:
        return json.load(stream)


def digest(path):
    require(path.is_file(), 'Missing artifact: ' + str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def artifact(base, name):
    require(nonempty(name), 'Artifact path must be nonempty')
    path = (base / name).resolve()
    return {'path': str(path), 'sha256': digest(path)}


def artifacts(base, values):
    require(isinstance(values, list), 'Expected artifact path list')
    result = [artifact(base, name) for name in values]
    require(len({v['path'] for v in result}) == len(result), 'Duplicate artifact')
    return result


def basis(state):
    return {key: state[key] for key in ('sources', 'intention', 'draft', 'evidence')}


def validate_base(state, schema):
    require(isinstance(state, dict) and state.get('schema') == schema, 'Unsupported state schema')
    require(state.get('phase') in PHASES and nonempty(state.get('maker')), 'Invalid phase/maker')
    for key in ('sources', 'draft', 'evidence'):
        require(isinstance(state.get(key), list), 'Invalid artifact collection: ' + key)
    require(state.get('intention') is None or isinstance(state['intention'], dict), 'Invalid intention')
    for item in state['sources'] + state['draft'] + state['evidence'] + ([state['intention']] if state['intention'] else []):
        require(isinstance(item, dict) and nonempty(item.get('path')) and isinstance(item.get('sha256'), str)
                and len(item['sha256']) == 64 and all(c in '0123456789abcdef' for c in item['sha256']), 'Invalid artifact record')
    require(isinstance(state.get('events'), list), 'Invalid events')
    require(isinstance(state.get('impact_pending'), bool), 'Invalid impact marker')
    require(state.get('approval') is None or (isinstance(state['approval'], dict)
            and nonempty(state['approval'].get('message_ref')) and nonempty(state['approval'].get('intention_sha256'))), 'Invalid approval')
    require(state.get('review') is None or (isinstance(state['review'], dict) and 'receipt' in state['review']
            and 'basis' in state['review']), 'Invalid review')
    require(not state['impact_pending'] or state['phase'] in {'blocked', 'failed', 'intake'}, 'Unresolved source impact')
    hold = state.get('hold')
    require(hold is None or (isinstance(hold, dict) and hold.get('kind') in {'blocked', 'failed'}
            and nonempty(hold.get('reason')) and state['phase'] == hold['kind']), 'Invalid execution hold')
    if state['phase'] in {'produce', 'review', 'done'}:
        require(approved(state), 'No approval for current intention')
    if state['phase'] in {'review', 'done'}:
        require(bool(state['draft']), 'No candidate artifact')
    if state['phase'] == 'done':
        require(state['review'] is not None and state['review']['basis'] == basis(state), 'No current review')
    if state['phase'] in {'blocked', 'failed'}:
        require(nonempty(state.get('waiting_reason')) and state.get('resume_phase') in PHASES - {'blocked', 'failed'}, 'Invalid paused state')


def lessons_basis(state):
    return memory.sha({'used': state['lessons_used'], 'adoption_generation': state['adoption_generation']})


def validate(state):
    validate_base(state, 2)
    require(nonempty(state.get('task_id')) and state.get('memory_mode') in {'on', 'off'}, 'Invalid task identity/memory mode')
    require(state.get('session_ref') is None or nonempty(state['session_ref']), 'Invalid session_ref')
    require(state.get('invocation_id') is None or nonempty(state['invocation_id']), 'Invalid invocation_id')
    require(type(state.get('adoption_generation')) is int and state['adoption_generation'] >= 0, 'Invalid adoption generation')
    require(isinstance(state.get('lessons_used'), list) and isinstance(state.get('lessons_history'), list)
            and isinstance(state.get('memory_impact_pending'), list), 'Invalid memory adoption/impact list')
    require(not state['lessons_used'] or state['adoption_generation'] > 0, 'Unversioned memory adoption')
    require(state.get('lessons_receipt') is None or isinstance(state['lessons_receipt'], dict), 'Invalid lessons receipt')
    for used in state['lessons_used']:
        memory.key(used)
        require(all(nonempty(used.get(k)) for k in ('root_id', 'content_digest', 'invocation_id'))
                and isinstance(used.get('context'), dict) and isinstance(used.get('applications'), list)
                and bool(used['applications']), 'Invalid actual adoption')
        for app in used['applications']:
            require(all(nonempty(app.get(k)) for k in ('application_id', 'action', 'result'))
                    and isinstance(app.get('affected'), list) and app['affected'], 'Invalid application record')
    if state['phase'] == 'done':
        require(not state['memory_impact_pending'], 'Unresolved memory impact')
        require(review_lessons_match(state['review'], state), 'No review for current memory adoption')


def memory_defaults(state):
    state.update(schema=2, task_id='task-' + uuid.uuid4().hex, session_ref=None, invocation_id=None,
                 memory_mode='off', lessons_used=[], lessons_receipt=None, adoption_generation=0,
                 memory_impact_pending=[], lessons_history=[], memory_checkpoint=None)


def review_lessons_match(receipt, state):
    if 'lessons_basis' not in receipt:
        return not state['lessons_used'] and state['adoption_generation'] == 0
    return receipt['lessons_basis'] == lessons_basis(state)


def adoption_changed(state, reason):
    state['adoption_generation'] += 1
    state['review'] = None
    state['lessons_receipt'] = None
    if state['phase'] == 'done':
        state['phase'] = 'review'
    event(state, 'memory_invalidate', reason)


def check_used(state, store):
    """Online check at controlled entry, never a task-local receipt permission."""
    receipt = store.check_used(state)
    receipt['lessons_basis'] = lessons_basis(state)
    receipt['digest'] = memory.sha(receipt)
    state['lessons_receipt'] = receipt
    return receipt


def memory_problem(state, error):
    message = str(error)
    if not state['memory_impact_pending']:
        adoption_changed(state, message)
        state['memory_impact_pending'] = [{'reason': message, 'detected_at': memory.now(),
                                           'affected': [app['affected'] for used in state['lessons_used'] for app in used['applications']]}]
        event(state, 'memory_impact', {'reason': message, 'after_delivery': any(e['action'] == 'finish' for e in state['events'])})
    state['lessons_receipt'] = None


def approved(state):
    return bool(state['intention'] and state['approval'] and
                state['approval']['intention_sha256'] == state['intention']['sha256'])


def event(state, action, detail):
    state['events'].append({'action': action, 'detail': detail})


def reconcile(state):
    changed = []
    for key in ('sources', 'intention', 'draft', 'evidence'):
        items = [state[key]] if key == 'intention' and state[key] else ([] if key == 'intention' else state[key])
        for item in items:
            current = digest(Path(item['path']))
            if current != item['sha256']:
                changed.append(key)
                item['sha256'] = current
    if changed:
        state['review'] = None
        if 'intention' in changed:
            state['approval'] = None
        if 'sources' in changed or state['impact_pending']:
            state.update(phase='blocked', resume_phase='produce' if approved(state) else 'awaiting_confirmation',
                         waiting_reason='Source files changed; assess impact before proceeding', impact_pending=True)
        else:
            state.update(phase='review' if approved(state) and state['draft'] and 'evidence' not in changed else
                         ('produce' if approved(state) else 'awaiting_confirmation'), waiting_reason=None, resume_phase=None)
        event(state, 'invalidate', sorted(set(changed)))
    if state['review'] and digest(Path(state['review']['receipt']['path'])) != state['review']['receipt']['sha256']:
        state.update(review=None, phase='review', waiting_reason=None, resume_phase=None)
        changed.append('review_receipt')
        event(state, 'invalidate', ['review_receipt'])
    if changed and state.get('hold'):
        preserve_hold(state)
    return changed


def preserve_hold(state):
    if state.get('hold'):
        if state['phase'] not in {'blocked', 'failed'}:
            state['resume_phase'] = state['phase']
        state.update(phase=state['hold']['kind'], waiting_reason=state['hold']['reason'])


def review_record(base, state, name):
    record = artifact(base, name)
    receipt = read_json(record['path'])
    require(isinstance(receipt, dict), 'Invalid review receipt')
    require(nonempty(receipt.get('reviewer')) and receipt['reviewer'] != state['maker'], 'Independent reviewer identity required')
    require(nonempty(receipt.get('context_ref')), 'Independent context/session reference required')
    require(receipt.get('basis') == basis(state), 'Review is not bound to current files')
    require(review_lessons_match(receipt, state), 'Review is not bound to current lessons basis')
    require(receipt.get('verdict') == 'pass', 'Review did not pass; revise affected work')
    checks = receipt.get('checks')
    require(isinstance(checks, dict) and CHECKS <= checks.keys(), 'Missing required review checks')
    for key in CHECKS:
        item = checks[key]
        require(isinstance(item, dict) and item.get('status') in {'pass', 'not_applicable'}
                and nonempty(item.get('reason')), 'Unresolved/unsupported review check: ' + key)
        require(key not in {'requirements', 'writing', 'final_file'} or item['status'] == 'pass', 'Required check cannot be not_applicable: ' + key)
    result = {'receipt': record, 'basis': basis(state)}
    if 'lessons_basis' in receipt:
        result['lessons_basis'] = receipt['lessons_basis']
    return result


def apply(state, request, base, store=None):
    action = request.get('action')
    phase = state['phase']
    if action in {'status', 'migrate'}:
        return
    if action == 'memory_mode':
        require(request.get('mode') in {'on', 'off'}, 'Mode must be on/off')
        state['memory_mode'] = request['mode']
    elif action == 'memory_begin':
        require(state['memory_mode'] == 'on' and store is not None, 'Enable memory before explicit begin')
        inv = store.begin(dict(request, task_id=state['task_id']))
        state.update(session_ref=inv['session_ref'], invocation_id=inv['invocation_id'])
    elif action == 'memory_checkpoint':
        require(request.get('status') in {'saved', 'unavailable', 'disabled'} and nonempty(request.get('source_ref')), 'Checkpoint needs recovery reference/status')
        state['memory_checkpoint'] = {k: request[k] for k in ('status', 'source_ref')}
    elif action == 'adopt_lesson':
        require(state['memory_mode'] == 'on' and store is not None and state['invocation_id']
                and approved(state) and phase in {'produce', 'review', 'done'}, 'Adoption requires confirmed intention and explicit memory begin')
        require(not state['memory_impact_pending'], 'Resolve previous memory impact before new adoption')
        ref = request['lesson']
        record = store.get(ref)
        inv = store.invocation(state['invocation_id'])
        require(inv['task_id'] == state['task_id'], 'Invocation task mismatch')
        context = inv['materials_read']['constraints']
        store.check(ref, context, state['invocation_id'])
        app = request['application']
        require(nonempty(app.get('action')) and isinstance(app.get('affected'), list) and app['affected'], 'Application needs concrete action and affected objects/pages')
        app = dict(application_id='app-' + uuid.uuid4().hex, action=app['action'], affected=app['affected'], result='pending')
        existing = next((x for x in state['lessons_used'] if x['id'] == ref['id'] and x['revision'] == ref['revision']), None)
        if existing:
            existing['applications'].append(app)
        else:
            state['lessons_used'].append(dict(id=record['id'], revision=record['revision'], root_id=store.registry['root_id'],
                                             content_digest=record['content_digest'], context=context,
                                             invocation_id=state['invocation_id'], applications=[app]))
        record['last_used_at'] = memory.now()
        adoption_changed(state, 'Registered actual application at controlled entry')
        check_used(state, store)
    elif action == 'record_application':
        require(nonempty(request.get('result')) and request['result'] != 'pending', 'Record actual application result')
        apps = [a for x in state['lessons_used'] for a in x['applications'] if a['application_id'] == request.get('application_id')]
        require(len(apps) == 1, 'Unknown application')
        apps[0]['result'] = request['result']
        adoption_changed(state, 'Application result changed')
    elif action == 'detach_lessons':
        receipt = read_json(artifact(base, request.get('path'))['path'])
        require(receipt.get('lessons_basis') == lessons_basis(state) and receipt.get('basis') == basis(state), 'De-adoption review must bind current dependencies and artifacts')
        require(nonempty(receipt.get('reviewer')) and receipt['reviewer'] != state['maker'] and nonempty(receipt.get('context_ref'))
                and receipt.get('verdict') == 'pass' and nonempty(receipt.get('reason')) and receipt.get('revalidated_from_current_materials') is True,
                'Independent local revalidation needed to detach')
        targets = request.get('lessons')
        require(isinstance(targets, list) and targets, 'Explicit detach targets required')
        target_keys = {memory.key(x) for x in targets}
        require(target_keys <= {memory.key(x) for x in state['lessons_used']}, 'Unknown detach dependency')
        affected = [a for x in state['lessons_used'] if memory.key(x) in target_keys for a in x['applications']]
        require(receipt.get('applications_digest') == memory.sha(affected), 'De-adoption must cover affected actions/pages')
        removed = [x for x in state['lessons_used'] if memory.key(x) in target_keys]
        state['lessons_history'].append({'detached': removed, 'receipt': artifact(base, request['path'])})
        state['lessons_used'] = [x for x in state['lessons_used'] if memory.key(x) not in target_keys]
        adoption_changed(state, 'Detached after current-material revalidation; fresh report review required')
        state['memory_impact_pending'] = []
        if state['phase'] in {'review', 'done'}:
            state['phase'] = 'review'
    elif action == 'acknowledge_memory_recovery':
        require(store is not None and nonempty(request.get('reason')), 'Recheck authority and give recovery reason')
        check_used(state, store)
        state['memory_impact_pending'] = []
    elif action == 'refresh_lessons':
        require(store is not None, 'Online memory check required')
        check_used(state, store)
    elif action == 'submit_intention':
        require(phase in {'intake', 'awaiting_confirmation'}, 'Return to intake to change scope')
        state.update(intention=artifact(base, request.get('path')), approval=None, review=None, phase='awaiting_confirmation')
    elif action == 'confirm':
        require(phase == 'awaiting_confirmation' and state['intention'] and not state['impact_pending'], 'No ready intention to confirm')
        require(nonempty(request.get('message_ref')), 'Supply actual user confirmation reference; do not invent one')
        state.update(approval={'message_ref': request['message_ref'], 'intention_sha256': state['intention']['sha256']}, phase='produce')
    elif action == 'submit_draft':
        require(phase == 'produce' and approved(state), 'Production requires confirmed intention')
        candidate = artifacts(base, request.get('paths'))
        require(bool(candidate), 'Candidate cannot be empty')
        state.update(draft=candidate, evidence=artifacts(base, request.get('evidence', [])), review=None, phase='review')
    elif action == 'record_review':
        require(phase == 'review', 'Not ready for review')
        require(not state['memory_impact_pending'], 'Unresolved memory impact requires local revalidation')
        require(all(a['result'] != 'pending' for x in state['lessons_used'] for a in x['applications']), 'Unrecorded memory application')
        state['review'] = review_record(base, state, request.get('path'))
    elif action == 'finish':
        require(not state['memory_impact_pending'] and review_lessons_match(state.get('review') or {}, state), 'Fresh memory-bound independent review required')
        require(phase == 'review' and state['review'] and state['review']['basis'] == basis(state), 'Fresh independent review required')
        # Re-read semantics as well as checking the stored artifact digest.
        state['review'] = review_record(base, state, state['review']['receipt']['path'])
        state['phase'] = 'done'
    elif action == 'rollback':
        require(not state.get('hold'), 'Resolve existing execution hold before rollback')
        require(request.get('to') in {'intake', 'produce', 'review'} and nonempty(request.get('reason')), 'Rollback needs target and affected scope/reason')
        target = request['to']
        require(target == 'intake' or approved(state), 'Cannot bypass confirmation by rollback')
        require(target != 'review' or state['draft'], 'No draft to review')
        require(not state['impact_pending'] or target == 'intake', 'Assess source impact first')
        state.update(phase=target, review=None, waiting_reason=None, resume_phase=None)
        if target == 'intake':
            state['approval'] = None
    elif action == 'pause':
        require(phase not in {'blocked', 'failed', 'done'} and request.get('kind') in {'blocked', 'failed'} and nonempty(request.get('reason')), 'Invalid pause')
        state.update(phase=request['kind'], resume_phase=phase, waiting_reason=request['reason'],
                     hold={'kind': request['kind'], 'reason': request['reason']})
    elif action == 'resume':
        require(phase in {'blocked', 'failed'} and not state['impact_pending'] and nonempty(request.get('reason')), 'Resume needs resolved blocker/failure; reassess changed sources first')
        state.update(phase=state['resume_phase'], resume_phase=None, waiting_reason=None, hold=None)
    elif action == 'set_sources':
        require(nonempty(request.get('reason')), 'Source list change needs a reason')
        state.update(sources=artifacts(base, request.get('paths')), review=None, impact_pending=True,
                     phase='blocked', resume_phase='produce' if approved(state) else 'awaiting_confirmation',
                     waiting_reason='Source inventory changed; assess impact before proceeding')
        preserve_hold(state)
    elif action == 'reassess':
        require(state['impact_pending'] and isinstance(request.get('requirements_changed'), bool)
                and nonempty(request.get('reason')), 'Source reassessment needs impact and evidence-based reason')
        state.update(impact_pending=False, review=None, waiting_reason=None, resume_phase=None)
        if request['requirements_changed']:
            state.update(phase='intake', approval=None)
        else:
            state['phase'] = 'produce' if approved(state) else 'awaiting_confirmation'
        preserve_hold(state)
    else:
        raise GuardError('Unknown action')
    event(state, action, {k: v for k, v in request.items() if k != 'action'})


def transact(path, request, memory_root=None):
    path = Path(path).resolve()
    require(isinstance(request, dict), 'Request must be an object')
    if request.get('action') == 'init':
        require(not path.exists(), 'State already exists; never silently reset')
        require(nonempty(request.get('maker')), 'Maker identity required')
        state = dict(schema=1, phase='intake', maker=request['maker'], sources=artifacts(path.parent, request.get('sources', [])),
                     intention=None, draft=[], evidence=[], approval=None, review=None, impact_pending=False,
                     waiting_reason=None, resume_phase=None, hold=None, events=[])
        memory_defaults(state)
        event(state, 'init', 'Initialized; no user approval implied')
    else:
        state = read_json(path)
        require(isinstance(state, dict), 'State must be an object')
        if state.get('schema') == 1:
            validate_base(state, 1)
            # Check old artifacts before changing schema or writing any backup/state.
            reconcile(state)
            backup = path.with_suffix(path.suffix + '.schema1.bak')
            if not backup.exists():
                with open(backup, 'xb') as stream:
                    stream.write(path.read_bytes())
                    stream.flush()
                    os.fsync(stream.fileno())
            memory_defaults(state)
        validate(state)
        # Explicit inventory repair can remove missing sources; it never advances.
        changed = [] if request.get('action') == 'set_sources' else reconcile(state)
        if changed:
            atomic_write(path, state)
            require(request.get('action') in {'status', 'reassess', 'rollback'}, 'Artifacts changed; inspect status and affected work first')
    needs_store = bool(state['lessons_used']) or request.get('action') in {'adopt_lesson', 'memory_begin', 'refresh_lessons', 'acknowledge_memory_recovery'}
    try:
        manager = memory.Store(memory_root, create=request.get('action') == 'memory_begin').transaction() if needs_store else nullcontext(None)
        with manager as store:
            if state['lessons_used']:
                try:
                    check_used(state, store)
                except (ValueError, OSError, KeyError) as error:
                    memory_problem(state, error)
                    atomic_write(path, state)
                    require(request.get('action') in {'status', 'memory_mode', 'detach_lessons', 'rollback', 'memory_checkpoint'}, 'Adopted memory invalid/unavailable; inspect status and revalidate affected work')
            if request.get('action') != 'init':
                apply(state, request, path.parent, store)
            validate(state)
            # finish and task done write share the root lock with revocation.
            atomic_write(path, state)
    except (memory.MemoryError, OSError, KeyError) as error:
        if state['lessons_used']:
            memory_problem(state, error)
            if request.get('action') in {'status', 'memory_mode', 'detach_lessons', 'rollback', 'memory_checkpoint'}:
                apply(state, request, path.parent)
                validate(state)
                atomic_write(path, state)
            else:
                atomic_write(path, state)
                raise GuardError('Adopted memory unavailable: ' + str(error)) from error
        else:
            raise
    return state


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', required=True)
    parser.add_argument('--request', required=True, help='UTF-8 JSON action file')
    parser.add_argument('--memory-root', help='Private root override for this call (normally environment/default)')
    args = parser.parse_args()
    try:
        state = transact(args.state, read_json(args.request), args.memory_root)
        print(json.dumps({'ok': True, 'phase': state['phase'], 'waiting_reason': state['waiting_reason'], 'basis': basis(state),
                          'task_id': state['task_id'], 'session_ref': state['session_ref'], 'invocation_id': state['invocation_id'],
                          'lessons_basis': lessons_basis(state), 'adoption_generation': state['adoption_generation'],
                          'lessons_used': state['lessons_used'], 'lessons_receipt': state['lessons_receipt'],
                          'memory_impact_pending': state['memory_impact_pending']}, ensure_ascii=False))
        return 0
    except (GuardError, OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
