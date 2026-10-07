"""Join fresh solver, original replay and real-time evidence after verification."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def finalize(solver_path, offline_path, live_path, screenshot_path=None):
    solver = json.loads(solver_path.read_text(encoding='utf-8'))
    offline = json.loads(offline_path.read_text(encoding='utf-8'))
    live = json.loads(live_path.read_text(encoding='utf-8'))
    if solver['status'] != 'candidate_found':
        raise ValueError('Solver did not produce a complete witness')
    actions = solver['actions']
    if not (offline['clock'] == 'original-runtime-fixed-240hz' and
            offline['original_replay_passed'] and offline['plan']['actions'] == actions and
            offline['result']['frames'] == len(actions) and
            len(offline['microtick_records']) == 4 * len(actions) and
            all(r['HP'] == 92 and r['KR'] == 0 for r in offline['microtick_records']) and
            offline['trajectory'][-1]['ended']):
        raise ValueError('Original fixed-step evidence is incomplete or mismatched')
    if not (live['clock'] == 'original-runtime-realtime' and live['seed'] == 42 and
            live['wave'] == solver['wave'] and live['result']['passed'] and
            live['plan']['actions'] == actions and len(live['trace']['runs']) == 3):
        raise ValueError('Real-time evidence is incomplete or mismatched')
    rounds = []
    for run in live['trace']['runs']:
        rows = run['rows']
        if not (run['end']['endAttackObserved'] and not run['hits'] and
                run['startHP'] == 92 and rows and
                all(row['HP'] == 92 and row['KR'] == 0 for row in rows)):
            raise ValueError('A real-time round failed')
        rounds.append({'ticks': len(rows), 'min_hp': min(r['HP'] for r in rows),
                       'max_kr': max(r['KR'] for r in rows), 'hits': 0,
                       'end_attack_observed': True,
                       'min_dt': min(r['dt'] for r in rows),
                       'max_dt': max(r['dt'] for r in rows)})
    candidate_path = ROOT / 'tools/oracle-plans' / (
        solver['wave'].removesuffix('.csv') + '-42-candidate-' + live['candidate_id'] + '.json')
    candidate = json.loads(candidate_path.read_text(encoding='utf-8'))
    if candidate['result']['actions'] != actions:
        raise ValueError('Registered candidate differs from verified solver output')
    for key, path in [('csv_sha256', ROOT / 'c2-sans-fight' / solver['wave']),
                      ('runtime_sha256', ROOT / 'c2-sans-fight/c2runtime.js'),
                      ('data_sha256', ROOT / 'c2-sans-fight/data.js')]:
        if candidate[key] != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError('Original game source changed: ' + key)
    if solver['kernel_sha256'] != hashlib.sha256((ROOT / 'nohit/engine/compact_lattice.py').read_bytes()).hexdigest():
        raise ValueError('Solver kernel changed after generation')
    actions_hash = hashlib.sha256(json.dumps(actions, separators=(',', ':')).encode()).hexdigest()
    ux_changes = sum(a[0] != b[0] for a, b in zip(actions, actions[1:]))
    up_changes = sum(a[1] != b[1] for a, b in zip(actions, actions[1:]))
    evidence = {'candidate_id': live['candidate_id'], 'actions_sha256': actions_hash,
                'browser': 'Codex in-app browser (visible)', 'offline_trace': str(offline_path.resolve()),
                'realtime_trace': str(live_path.resolve()), 'rounds': rounds,
                'screenshot': str(screenshot_path.resolve()) if screenshot_path else None,
                'horizontal_action_changes': ux_changes, 'jump_action_changes': up_changes,
                'min_frame_boundary_clearance_px': offline['result']['min_frame_boundary_clearance_px'],
                'complete_search_configuration': solver['complete_search_configuration']}
    solver.update(original_replay_passed=True, realtime_passed_three=True, acceptance=evidence)
    solver_path.write_text(json.dumps(solver, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    receipt = ROOT / 'tools/real-game/frs-iab-acceptance-20261005.json'
    receipt.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('solver', type=Path)
    parser.add_argument('offline', type=Path)
    parser.add_argument('live', type=Path)
    parser.add_argument('--screenshot', type=Path)
    args = parser.parse_args()
    print(json.dumps(finalize(args.solver, args.offline, args.live, args.screenshot),
                     ensure_ascii=False, indent=2))
