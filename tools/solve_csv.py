"""Solve an unchanged CSV from a captured initial state at an explicit clock."""
import argparse
import json
import math
from pathlib import Path

from nohit.engine.csv_solver import solve_csv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    entry = parser.add_mutually_exclusive_group(required=True)
    entry.add_argument('--initial', nargs=11, type=float,
                       help='complete player state observed at model tick 0')
    entry.add_argument('--entry', type=Path,
                       help='JSON containing initial and optional initial_environment')
    parser.add_argument('--fps', type=float, default=30,
                        help='declared fixed simulation clock, default 30 Hz')
    parser.add_argument('--width', type=int, default=3000)
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--max-ticks', type=int, default=40000)
    parser.add_argument('--max-bindings', type=int, default=1)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not math.isfinite(args.fps) or args.fps <= 0:
        parser.error('--fps must be finite and positive')
    captured = json.loads(args.entry.read_text(encoding='utf-8-sig')) if args.entry else {}
    result = solve_csv(args.csv, captured.get('initial', args.initial),
        initial_environment=captured.get('initial_environment'),
        dt_schedule=[1/args.fps]*args.max_ticks, max_ticks=args.max_ticks,
        width=args.width, seconds=args.seconds, max_bindings=args.max_bindings,
        seed=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    keys = ('status', 'reason', 'reached_tick', 'verified', 'wall_seconds',
            'game_seconds', 'physics_hz', 'original_replay_passed')
    print(json.dumps({key: result[key] for key in keys if key in result}, indent=2))
    return 0 if result['status'] == 'candidate_found' else 2


if __name__ == '__main__':
    raise SystemExit(main())
