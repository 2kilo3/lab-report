#!/usr/bin/env python3
"""Executable synthetic replay. Writes no real conversations or production memory."""
import argparse
import json
from pathlib import Path
import time

from test_memory_workflow import MemoryWorkflowTests, m, w


def replay(output):
    start = time.monotonic()
    scenario = MemoryWorkflowTests()
    scenario.setUp()
    try:
        p = scenario.protocol
        trace = []
        r = p.registry()
        candidate = r['records'][m.key(scenario.ref)]
        trace.append({'step': '1 input event and candidate recap', 'source_events': list(r['sources'].values()),
                      'candidate': candidate, 'recaps': [x.read_text(encoding='utf-8') for x in (p.root / 'sessions').glob('*/recap-*.md')]})
        # The first sample was explicitly managed in setup. Add a fresh, unapproved sample
        # to demonstrate the ordinary next-use path with a new session and task material read.
        ref = p.candidate('replay-next-use', id='replay-method')
        p.inv = p.begin('replay-next-explicit-session')
        display = p.display(ref, management=False)
        confirmation = p.confirm(display)
        consumed = p.call('consume', **confirmation)
        assert not consumed['errors']
        trace.append({'step': '2 next explicit use reads current materials and freezes display',
                      'invocation': p.inv, 'display': display, 'confirmation': p.call('query', context={'template': 'v1'})['root_id'],
                      'confirmation_record': m.read(p.root / 'reviews' / (confirmation['confirmation_id'] + '.json'))})
        context = p.query()
        assert any(x['id'] == ref['id'] for x in context['items'])
        trace.append({'step': '3 approved retrieval', 'context': context})
        scenario.adopt(ref)
        reviewed = scenario.review()
        trace.append({'step': '4 actual application and independent review binding',
                      'adopted': reviewed['lessons_used'], 'lessons_basis': w.lessons_basis(reviewed), 'review': reviewed['review']})
        done = scenario.call('finish')
        assert done['phase'] == 'done'
        p.decide(ref, 'revoke')
        invalid = scenario.call('status')
        assert invalid['memory_impact_pending'] and invalid['phase'] == 'review'
        denied = False
        try:
            scenario.call('finish')
        except w.GuardError:
            denied = True
        assert denied
        trace.append({'step': '5 later revocation refuses old review', 'phase': invalid['phase'],
                      'impact': invalid['memory_impact_pending'], 'finish_denied': denied})
        scenario.ref = ref
        detached = scenario.detach()
        assert not detached['lessons_used'] and detached['adoption_generation'] > 0
        scenario.review()
        final = scenario.call('finish')
        assert final['phase'] == 'done'
        trace.append({'step': '6 local current-material revalidation then fresh review',
                      'phase': final['phase'], 'generation': final['adoption_generation'], 'history': final['lessons_history']})
        result = dict(label='SYNTHETIC HOST AND USER CONFIRMATION; NOT A REAL REPORT', trace=trace,
                      metrics={'wrong_candidate_adoptions': 0, 'revocation_delivery_bypasses': 0,
                               'stale_review_reuses': 0, 'elapsed_seconds': round(time.monotonic() - start, 3),
                               'evidence_omissions_real_report': None, 'template_drift_real_report': None,
                               'page_errors_real_report': None, 'rework_real_report': None,
                               'human_review_seconds': None, 'model_cost': None, 'efficiency_gain': None})
        output.mkdir(parents=True, exist_ok=True)
        m.atomic(output / 'synthetic-memory-replay.json', result)
        return result
    finally:
        scenario.doCleanups()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = replay(args.output.resolve())
    print(json.dumps({'ok': True, 'steps': len(result['trace']), 'metrics': result['metrics']}, ensure_ascii=False))
