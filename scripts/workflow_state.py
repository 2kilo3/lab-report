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
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

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


def validate(state):
    require(isinstance(state, dict) and state.get('schema') == 1, 'Unsupported state schema')
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
    require(receipt.get('verdict') == 'pass', 'Review did not pass; revise affected work')
    checks = receipt.get('checks')
    require(isinstance(checks, dict) and CHECKS <= checks.keys(), 'Missing required review checks')
    for key in CHECKS:
        item = checks[key]
        require(isinstance(item, dict) and item.get('status') in {'pass', 'not_applicable'}
                and nonempty(item.get('reason')), 'Unresolved/unsupported review check: ' + key)
        require(key not in {'requirements', 'writing', 'final_file'} or item['status'] == 'pass', 'Required check cannot be not_applicable: ' + key)
    return {'receipt': record, 'basis': basis(state)}


def apply(state, request, base):
    action = request.get('action')
    phase = state['phase']
    if action == 'status':
        return
    if action == 'submit_intention':
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
        state['review'] = review_record(base, state, request.get('path'))
    elif action == 'finish':
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


def transact(path, request):
    path = Path(path).resolve()
    require(isinstance(request, dict), 'Request must be an object')
    if request.get('action') == 'init':
        require(not path.exists(), 'State already exists; never silently reset')
        require(nonempty(request.get('maker')), 'Maker identity required')
        state = dict(schema=1, phase='intake', maker=request['maker'], sources=artifacts(path.parent, request.get('sources', [])),
                     intention=None, draft=[], evidence=[], approval=None, review=None, impact_pending=False,
                     waiting_reason=None, resume_phase=None, hold=None, events=[])
        event(state, 'init', 'Initialized; no user approval implied')
    else:
        state = read_json(path)
        validate(state)
        # Explicit inventory repair can remove missing sources; it never advances.
        changed = [] if request.get('action') == 'set_sources' else reconcile(state)
        if changed:
            atomic_write(path, state)
            require(request.get('action') in {'status', 'reassess', 'rollback'}, 'Artifacts changed; inspect status and affected work first')
        apply(state, request, path.parent)
    validate(state)
    atomic_write(path, state)
    return state


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', required=True)
    parser.add_argument('--request', required=True, help='UTF-8 JSON action file')
    args = parser.parse_args()
    try:
        state = transact(args.state, read_json(args.request))
        print(json.dumps({'ok': True, 'phase': state['phase'], 'waiting_reason': state['waiting_reason'], 'basis': basis(state)}, ensure_ascii=False))
        return 0
    except (GuardError, OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
