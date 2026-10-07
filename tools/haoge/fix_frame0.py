"""Publish the correct frame-0 environment for every route plan.

The in-game validator compares `plan.visualization.frames[0].env` against the
environment the real game produced at that round's entry, so the plan must carry
the model's *frame 0* environment -- the one after the source's first tick, not
the pre-TLPlay `initial_environment` the request carries.

`visualization` is added by the dashboard's /api/solve-csv, so a route produced by
the standalone process entry has none, and such plans were rejected with
"frame0 environment differs" purely because the field was missing. Rebuilding the
wave from the captured entry request is deterministic and needs no search:
`wave.env_schedule[0]` is that frame.

Plans that DO carry a dashboard-produced frame are used as the control: if the
rebuilt value disagrees with them, this script reports it instead of overwriting.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nohit.engine.parametric_environment import ParametricEnvironment

DIR = ROOT / 'scratch/haoge-run'
PLANS = ROOT / 'haoge-runtime/routes'

rebuilt = {}
requests = {}
for entry in sorted((DIR / 'entries').glob('*.request.json')):
    stem = entry.name.replace('.request.json', '')
    request = json.loads(entry.read_text(encoding='utf-8'))
    requests[stem] = request
    csv_path = DIR / ('_f0_' + stem + '.csv')
    csv_path.write_text(request['custom_csv'], encoding='utf-8')
    try:
        wave = ParametricEnvironment(
            csv_path, backend='resumable',
            initial_environment=request['initial_environment'],
            initial_arena=request.get('initial_arena'),
            dt_schedule=request['dt_schedule'],
            max_ticks=min(request['max_ticks'], 200),
            termination_policy=request['termination_policy']).bind().wave
        rebuilt[stem] = [float(x) for x in wave.env_schedule[0]]
    finally:
        csv_path.unlink(missing_ok=True)

agreed = disagreed = published = missing = 0
for stem, env in sorted(rebuilt.items()):
    plan_path = PLANS / (stem + '.plan.json')
    if not plan_path.exists():
        missing += 1
        continue
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    frames = (plan.get('visualization') or {}).get('frames') or []
    current = frames[0].get('env') if frames else None
    # The pre-TLPlay environment from the request is NOT the model's frame 0. A
    # published value equal to it is provably the wrong substitution, so it is
    # safe to replace; anything else that disagrees is reported, never overwritten.
    fallback = [float(x) for x in requests[stem]['initial_environment']]
    if current is not None and [float(x) for x in current] == fallback:
        plan.setdefault('visualization', {})['frames'] = [{'env': env}]
        plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding='utf-8')
        published += 1
        print(f'  FIXED {stem}: {[round(x,3) for x in current[:4]]} -> {[round(x,3) for x in env[:4]]}')
        continue
    if current is not None and len(current) == 22:
        # Control: the dashboard's own frame must equal the rebuilt one.
        if [float(x) for x in current] == env:
            agreed += 1
        else:
            disagreed += 1
            print(f'  DISAGREE {stem}: published={current[:9]} rebuilt={[round(x,3) for x in env[:9]]}')
    else:
        plan.setdefault('visualization', {})['frames'] = [{'env': env}]
        plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding='utf-8')
        published += 1
        print(f'  PUBLISHED frame0 for {stem}: {[round(x,3) for x in env[:9]]}')

print(f'\ncontrol agreed={agreed} disagreed={disagreed} | published={published} | no plan={missing}')
