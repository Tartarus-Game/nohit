"""Solve one captured round in its own process.

Concurrent HTTP requests to the dashboard all land in one Python process, where
the dialogue relation phase is Python-level and therefore GIL-serialised: four
"parallel" solves shared ~1.09 cores and starved each other. This entry calls
the solver directly so each round gets its own interpreter and its own core, and
adds the same provenance block the dashboard would have attached, so the result
is a drop-in plan for the in-game replay path.

Usage: python solve_entry.py --entry <request.json> --out <route.json>
                             [--width 1200] [--seconds 2400] [--bindings 1]
"""
import argparse
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nohit.engine.csv_solver import solve_csv
from nohit.dashboard.csv_api import implementation_hashes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--entry', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--width', type=int, default=1200)
    parser.add_argument('--seconds', type=float, default=2400)
    parser.add_argument('--bindings', type=int, default=1)
    parser.add_argument('--max-ticks', type=int, default=None)
    parser.add_argument('--selection-seed', type=int, default=42)
    parser.add_argument('--dialogue-max-states', type=int, default=None,
                        help='override csv_solver dialogue_max_states (default 100000); the '
                             'API never exposed it and it silently caps the dialogue relation')
    parser.add_argument('--dialogue-max-ticks', type=int, default=None)
    parser.add_argument('--work', type=Path, default=ROOT / 'scratch' / 'haoge-run')
    args = parser.parse_args()

    request = json.loads(args.entry.read_text(encoding='utf-8'))
    csv_path = args.work / ('_proc_' + args.entry.stem.replace('.request', '') + '.csv')
    csv_path.write_text(request['custom_csv'], encoding='utf-8')

    started = time.perf_counter()
    extra = {}
    if args.dialogue_max_states is not None:
        extra['dialogue_max_states'] = args.dialogue_max_states
    if args.dialogue_max_ticks is not None:
        extra['dialogue_max_ticks'] = args.dialogue_max_ticks
    result = solve_csv(
        csv_path, request['initial'],
        initial_environment=request['initial_environment'],
        initial_arena=request.get('initial_arena'),
        initial_target_history=request.get('initial_target_history'),
        initial_confirm=request.get('initial_confirm', False),
        previous_confirm=request.get('previous_confirm', False),
        dt_schedule=request['dt_schedule'],
        max_ticks=args.max_ticks or request['max_ticks'],
        seed=request['seed'],
        termination_policy=request['termination_policy'],
        width=args.width, seconds=args.seconds, max_bindings=args.bindings,
        selection_seed=args.selection_seed, **extra)
    result['initial'] = list(request['initial'])
    result['initial_environment'] = list(request['initial_environment'])
    result['request_seconds'] = time.perf_counter() - started
    result['provenance'] = dict(fresh_computation=True, route_cache_hit=False,
                                request_id=str(uuid.uuid4()),
                                implementation_sha256=implementation_hashes())
    # The in-game controller hashes the native AJAX text: UTF-8 decoded with the
    # BOM stripped and CRLF folded to LF. Hashing the raw temp bytes instead makes
    # the plan look like it belongs to a different CSV, and the validator refuses
    # it -- correctly. Match the dashboard's text identity exactly.
    result['csv_sha256'] = hashlib.sha256(
        csv_path.read_bytes().decode('utf-8-sig').replace('\r\n', '\n').encode('utf-8')).hexdigest()
    result['process_solver'] = dict(width=args.width, seconds=args.seconds,
                                    max_bindings=args.bindings)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    csv_path.unlink(missing_ok=True)

    print(f"{args.entry.stem.replace('.request',''):<24} {result['status']:<16} "
          f"actions={len(result['actions'])} reached={result.get('reached_tick')} "
          f"reason={result.get('reason')} wall={result['request_seconds']:.0f}s "
          f"width={args.width} seconds={args.seconds:.0f}", flush=True)
    return 0 if result['status'] == 'candidate_found' else 2


if __name__ == '__main__':
    raise SystemExit(main())
