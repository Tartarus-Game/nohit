"""Black-box native search and fresh-process replay; no physics approximation.

Import the prepared project first. Workers read the imported project but never
edit it. Each candidate starts a new native world. This deliberately does not
claim to restore Godot coroutines/Tweens by copying a property dictionary.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_nohit(d):
    if d.get('status') != 'native_nohit' or not d.get('attack_completed'):
        raise ValueError('attack did not finish without damage')
    if d.get('ticks') != 300 or len(d.get('route', [])) != 300 or len(d.get('states', [])) != 300:
        raise ValueError('incomplete trace')
    if d.get('damage_calls') != 0 or d.get('heal_calls') != 0 or d.get('hp_drop_ticks') != 0:
        raise ValueError('damage or healing event')
    if d.get('special_bullet_mode') != 2 or d.get('observed_bullets') != d.get('expected_bullets'):
        raise ValueError('wrong native scene settings / incomplete spawn')
    hp = d['entry']['hp']
    if d.get('hp') != hp or d.get('kr') != 0:
        raise ValueError('terminal health changed')
    for i, s in enumerate(d['states'], 1):
        if s['tick'] != i or s['hp'] != hp or s['kr'] != 0:
            raise ValueError('health/tick trace changed')
        if s['invulnerable'] or not s['monitoring'] or not s['monitorable'] or s['body_shape_disabled']:
            raise ValueError('native damage detection was disabled')
    if any(type(mask) is not int or not 0 <= mask < 16 for mask in d['route']):
        raise ValueError('invalid input mask')


def validate_replay(candidate, replay):
    validate_nohit(candidate)
    validate_nohit(replay)
    if not replay.get('replay'):
        raise ValueError('result is not an input replay')
    # Exact native floating-point states; no epsilon-based acceptance.
    for key in ('scenario', 'seed', 'engine', 'upstream', 'entry', 'route', 'states',
                'damage_calls', 'heal_calls', 'native_overlap_ticks', 'observed_bullets'):
        if candidate[key] != replay[key]:
            raise ValueError('fresh-process replay mismatch: ' + key)


class Runner:
    def __init__(self, godot, project, out):
        self.godot, self.project, self.out = godot, project, out

    def run(self, label, scenario, strategy='idle', seed=1, route=None, replay=None, bake=False):
        target = self.out / (label + '.json')
        # Never accept a stale result from an earlier invocation.
        target.unlink(missing_ok=True)
        args = [str(self.godot), '--headless', '--path', str(self.project), '--fixed-fps', '60',
                '--quit-after', '4300' if scenario == 'default_attack' else '600', '--',
                '--scenario=' + scenario, '--strategy=' + strategy, '--seed=' + str(seed),
                '--bake=' + str(int(bake)), '--out=' + str(target)]
        if route is not None:
            plan = self.out / (label + '-input.json')
            plan.write_text(json.dumps({'route': route}))
            args.append('--plan=' + str(plan))
        if replay:
            args.append('--replay=' + str(replay))
        start = time.perf_counter()
        p = subprocess.run(args, capture_output=True, text=True, timeout=30)
        wall = time.perf_counter() - start
        log = p.stdout + p.stderr
        (self.out / (label + '.log')).write_text(log)
        if re.search(r'SCRIPT ERROR|Parse Error|Failed to load script|Error calling', log):
            raise RuntimeError('native script error: ' + label)
        if not target.exists():
            raise RuntimeError('native result missing: ' + label)
        d = json.loads(target.read_text())
        if p.returncode != (0 if d['status'] == 'native_nohit' else 2):
            raise RuntimeError('unexpected process termination: ' + label)
        return d, {'label': label, 'status': d['status'], 'ticks': d['ticks'],
                   'wall_seconds_with_startup': wall, 'native_segment_ms': d['elapsed_ms'],
                   'exit_code': p.returncode, 'logged_error_lines': sum(line.startswith('ERROR:') for line in log.splitlines())}


def portfolio(scenario):
    if scenario == 'circle_white_blue':
        # Short launch phases, then native jump input; includes both directions.
        return [(f'phase-{delay}-{a}-{b}', 'idle', 1, [a]*delay + [b]*(300-delay))
                for delay in (10, 20, 30, 40) for a,b in ((1,5),(2,6),(0,4),(5,1),(6,2),(0,5),(0,6),(1,4),(2,4))]
    return [(f'{s}-{seed}', s, seed, None) for s,seed in
            [('idle',1),('up',1),('left',1),('right',1),('orbit',1),('diagonal',0),('diagonal',1),('down',1)]]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--godot', type=Path, required=True)
    p.add_argument('--project', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--workers', type=int, default=6)
    p.add_argument('--skip-import', action='store_true')
    a = p.parse_args()
    if not 1 <= a.workers <= 16: p.error('workers must be in [1,16]')
    a.godot, a.project, a.out = a.godot.resolve(), a.project.resolve(), a.out.resolve()
    a.out.mkdir(parents=True, exist_ok=True)
    all_start = time.perf_counter()
    import_wall = None
    if not a.skip_import:
        start = time.perf_counter()
        proc = subprocess.run([str(a.godot),'--headless','--editor','--path',str(a.project),'--import'], capture_output=True, text=True, timeout=120)
        (a.out/'import.log').write_text(proc.stdout+proc.stderr)
        import_wall = time.perf_counter()-start
        if proc.returncode or 'SCRIPT ERROR' in proc.stdout+proc.stderr:
            raise RuntimeError('project import failed')
    r = Runner(a.godot, a.project, a.out)
    report = {'schema': 'nohit-native-meow-suite-v1', 'import_seconds': import_wall,
              'workers': a.workers, 'godot_binary_sha256': hashlib.sha256(a.godot.read_bytes()).hexdigest(),
              'cases': [], 'negative_controls': [], 'full_attack_attempts': [],
              'scope': 'Four isolated upstream circular-wave components; not the full default_attack sequence.'}
    for scenario in ('circle_white_red','circle_white_blue','circle_blue_red','circle_orange_red'):
        specs = portfolio(scenario)
        attempts, winner = [], None
        for start in range(0,len(specs),a.workers):
            batch = specs[start:start+a.workers]
            def attempt(spec):
                name,strategy,seed,route = spec
                return r.run(scenario+'-search-'+name, scenario, strategy, seed, route, bake=True)
            with ThreadPoolExecutor(max_workers=a.workers) as ex:
                runs = list(ex.map(attempt, batch))
            for d, rec in runs:
                attempts.append(rec)
                if d['status'] == 'native_nohit' and winner is None:
                    validate_nohit(d)
                    winner = d, rec
            if winner: break
        if not winner: raise RuntimeError('no candidate found within portfolio: ' + scenario)
        d, rec = winner
        replay, replay_rec = r.run(scenario+'-replay', scenario, seed=d['seed'], replay=a.out/(rec['label']+'.json'))
        validate_replay(d, replay)
        nonempty = sum(any(int(layer['bits_hex'] or '0',16) for layer in f['layers'].values()) for f in d['baked_frames'])
        if not nonempty: raise ValueError('baking never observed a hazard')
        report['cases'].append({'scenario': scenario, 'verdict': 'native_nohit_fresh_process',
             'candidate': rec['label']+'.json', 'replay': replay_rec['label']+'.json',
             'route_sha256': digest(d['route']), 'states_sha256': digest(d['states']),
             'attempts': attempts, 'replay_timing': replay_rec, 'damage_calls': d['damage_calls'],
             'hp': d['hp'], 'kr': d['kr'], 'spawned': d['observed_bullets'],
             'native_overlap_ticks': d['native_overlap_ticks'], 'nonempty_baked_frames': nonempty})
        print(scenario, 'PASS', 'attempts',len(attempts),flush=True)
    for scenario, strategy in [('circle_white_red','idle'),('circle_blue_red','orbit'),('circle_orange_red','idle')]:
        d, rec = r.run(scenario+'-negative', scenario, strategy)
        if d['status'] != 'hit' or d['damage_calls'] < 1 or d['hp'] >= d['entry']['hp']:
            raise ValueError('negative control did not take native damage: ' + scenario)
        report['negative_controls'].append({**rec,'damage_calls': d['damage_calls'], 'hp': d['hp']})
        print(scenario,'negative control HIT',flush=True)
    for strategy,seed in [('diagonal',0),('orbit',1),('idle',1),('diagonal',1)]:
        d, rec = r.run('full-'+strategy+'-'+str(seed),'default_attack',strategy,seed)
        report['full_attack_attempts'].append({**rec,'damage_calls':d['damage_calls'],'hp':d['hp'],'attack_completed':d['attack_completed']})
        print('default_attack',strategy,seed,d['status'],d['ticks'],flush=True)
    report['total_seconds_with_import_search_replay_controls'] = time.perf_counter()-all_start
    (a.out/'suite.json').write_text(json.dumps(report,indent=2))
    print('PASS four native components + three native damage controls; full attack is reported separately.',flush=True)


if __name__ == '__main__': main()
