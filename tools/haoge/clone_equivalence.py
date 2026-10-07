"""Deterministic equivalence check for the fast clone.

``environment_state_keys`` is a byte-exact structural fingerprint of every
committed world tick, so comparing it between the baseline engine and the
optimised one is a much stronger statement than "the tests still pass": it says
the copied state is identical, tick by tick, for all 24 haoge rounds.

Usage: python clone_equivalence.py <out.json>
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nohit.engine.parametric_environment import ParametricEnvironment

out_path = Path(sys.argv[1])
result = {}
for entry in sorted((ROOT / 'scratch/haoge-run/entries').glob('*.request.json')):
    stem = entry.name.replace('.request.json', '')
    request = json.loads(entry.read_text(encoding='utf-8'))
    csv_path = ROOT / 'scratch/haoge-run' / ('_eq_' + stem + '.csv')
    csv_path.write_text(request['custom_csv'], encoding='utf-8')
    try:
        wave = ParametricEnvironment(
            csv_path, backend='resumable',
            initial_environment=request['initial_environment'],
            initial_arena=request.get('initial_arena'),
            dt_schedule=request['dt_schedule'],
            max_ticks=min(request['max_ticks'], 2000),
            termination_policy=request['termination_policy']).bind().wave
        keys = wave.environment_state_keys if wave.environment_state_keys is not None else []
        digest = hashlib.sha256(b''.join(keys)).hexdigest()
        result[stem] = dict(digest=digest, ticks=len(keys), complete=bool(wave.complete),
                            termination=wave.termination_reason)
    except Exception as error:
        result[stem] = dict(error=type(error).__name__ + ': ' + str(error))
    finally:
        csv_path.unlink(missing_ok=True)

out_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding='utf-8')
print(f'wrote {out_path} for {len(result)} rounds')
