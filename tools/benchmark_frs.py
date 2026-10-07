"""Measure import, kernel compilation/loading, preparation, search and witness separately."""
import_start = __import__('time').perf_counter()
import argparse
import hashlib
import json
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from nohit.engine.compact_wave import compile_wave, prepare_collision_native
from nohit.engine.compact_lattice import search_frs_dp_bellman, reconstruct_native
from nohit.engine.compact_solver import _cache_state, _load_mode
import_ms = (time.perf_counter() - import_start) * 1000


def timed(call):
    start = time.perf_counter()
    value = call()
    return value, (time.perf_counter() - start) * 1000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='tools/operator-results/frs-phase-timing-20261005.json')
    args = parser.parse_args()
    (schedule, geometry, initial), csv_ms = timed(lambda: compile_wave(ROOT / 'c2-sans-fight/sans_platforms4hard.csv'))
    starts = np.tile(initial, 9)
    for group in range(3):
        starts[group * 15 + 8] = .75
        starts[group * 15 + 13] = 0.
    collision_before = _cache_state(prepare_collision_native)
    _, collision_load_ms = timed(lambda: prepare_collision_native(geometry[:1], margin_x=1., margin_y=2.))
    collision_mode = _load_mode(prepare_collision_native, collision_before)
    mask, preparation_ms = timed(lambda: prepare_collision_native(geometry, margin_x=1., margin_y=2.))
    kwargs = dict(max_states=30000, max_beam=1000, deadband=6., h_toggle_weight=.01,
                  anticipation=12, exact=True, max_expansions=10000000)
    search_before = _cache_state(search_frs_dp_bellman)
    _, search_load_ms = timed(lambda: search_frs_dp_bellman(mask[:5], schedule[:5], starts, **kwargs))
    search_mode = _load_mode(search_frs_dp_bellman, search_before)
    result, hot_search_ms = timed(lambda: search_frs_dp_bellman(mask, schedule, starts, **kwargs))
    status, frame, expansions, visits, actions = result
    reconstruction_before = _cache_state(reconstruct_native)
    _, reconstruction_load_ms = timed(lambda: reconstruct_native(initial, np.empty((0, 2), np.int8), schedule))
    reconstruction_mode = _load_mode(reconstruct_native, reconstruction_before)
    _, reconstruction_ms = timed(lambda: reconstruct_native(initial, actions, schedule))
    report = {'status':int(status), 'frame':int(frame), 'expansions':int(expansions),
              'exact_state_folding':True, 'max_beam':1000, 'complete_search_configuration':False,
              'actions_sha256':hashlib.sha256(json.dumps(actions.tolist(), separators=(',', ':')).encode()).hexdigest(),
              'kernel_sha256':hashlib.sha256((ROOT / 'nohit/engine/compact_lattice.py').read_bytes()).hexdigest(),
              'kernel_load':{'collision':collision_mode, 'search':search_mode, 'reconstruction':reconstruction_mode},
              'timing_ms':{'python_import':import_ms, 'csv_compile':csv_ms,
                           'collision_compile_or_load':collision_load_ms, 'collision_prepare_hot':preparation_ms,
                           'search_compile_or_load':search_load_ms, 'search_hot':hot_search_ms,
                           'reconstruction_compile_or_load':reconstruction_load_ms, 'reconstruction_hot':reconstruction_ms},
              'scope':'Process import through hot witness; excludes OS process launch and browser startup. Warmup uses one-frame native input, never a saved route.'}
    Path(args.output).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    if status != 0:
        raise SystemExit('No complete witness')


if __name__ == '__main__':
    main()
