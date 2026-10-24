#!/usr/bin/env python3
"""Thin offline checkpoint/export adapter. Never installs hooks or fetches private data."""
import argparse
import json
from pathlib import Path
import sys

import experience_store as memory

CLAUDE_MEM_COMMIT = 'c12d2dd58b9188dbe705f59d0e02e945f68df466'


def import_claude_mem(request, root=None):
    isolation = request.get('isolation')
    memory.require(isinstance(isolation, dict) and isolation.get('mode') == 'clean_context'
                   and isolation.get('verified_by') and isolation.get('evidence_ref'),
                   'Claude Mem auto-injection isolation not established: use a confirmed clean execution context')
    export = memory.read(request['path'])
    memory.require(isinstance(export, dict) and isinstance(export.get('observations'), list)
                   and isinstance(export.get('summaries', []), list), 'Unsupported Claude Mem export shape')
    namespace = request.get('source_namespace')
    memory.require(namespace, 'Retain original installation/namespace identity across exports')
    results = []
    with memory.Store(root).transaction() as store:
        store.invocation(request['invocation_id'])
        for kind in ('observations', 'summaries'):
            for row in export.get(kind, []):
                memory.require(isinstance(row, dict) and row.get('memory_session_id') and row.get('project')
                               and row.get('created_at') and row.get('id') is not None, 'Export record lacks stable identity')
                if row['project'] != request['project']:
                    continue
                payload = {k: v for k, v in row.items() if k not in {'id', 'created_at_epoch'}}
                results.append(store.collect(dict(invocation_id=request['invocation_id'],
                                                  source=dict(provider='claude-mem', namespace=namespace,
                                                              record_id=kind + ':' + str(row['id']), revision=memory.sha(payload)),
                                                  event_type='external_' + kind, payload=payload,
                                                  occurred_at=row['created_at'], adapter='claude-mem-export@' + CLAUDE_MEM_COMMIT,
                                                  classification='inference')))
    return {'events': results, 'source_commit': CLAUDE_MEM_COMMIT,
            'note': 'External summaries are unverified input; no active rule or independent support inferred'}


def execute(request, root=None):
    if request.get('mode') == 'off':
        return {'loaded': False, 'mode': 'off'}
    if request.get('action') == 'claude_mem_export':
        return import_claude_mem(request, root)
    if request.get('action') in {'checkpoint', 'end'}:
        # No display/confirmation here. End is a bounded flush, never a human-review trigger.
        return memory.execute(dict(request, action='consolidate', max_events=min(request.get('max_events', 100), 100)), root)
    memory.require(request.get('action') in {'begin', 'collect'}, 'Use begin/collect/checkpoint/end or claude_mem_export')
    return memory.execute(request, root)


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root')
    parser.add_argument('--request', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps({'ok': True, 'result': execute(memory.read(args.request), args.root)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    sys.exit(main())
