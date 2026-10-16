"""Solve an unchanged CSV from a captured initial state at an explicit clock."""
import argparse
import json
import math
from pathlib import Path

from nohit import _configure_solver_process
_configure_solver_process()
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
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--search-strategy', choices=('auto','native'), default='auto')
    parser.add_argument('--workers', type=int)
    parser.add_argument('--memory-mb', type=int, default=64)
    parser.add_argument('--allow-scripted-healing', action='store_true',
                        help='opt in to physical-only literal healing; native HP/KR replay is still required')
    parser.add_argument('--allow-scripted-damage',action='store_true',
        help='physical projection only; original runtime must audit script effects and survival')
    parser.add_argument('--observation-chunk-ticks', type=int, default=0,
                        help='commit source observations in bounded chunks; 480 is useful for long CSVs')
    parser.add_argument('--observation-preview-ticks', type=int, default=0,
                        help='rank chunk boundaries using speculative future frames (for example 480)')
    parser.add_argument('--observation-preview-reads', type=int, default=128)
    parser.add_argument('--observation-goal-style', type=int)
    parser.add_argument('--observation-goal-retries', action='store_true')
    parser.add_argument('--fixed-prefix', type=Path,
                        help='JSON with source hash, actions, Confirm sequence and trajectory to preserve')
    parser.add_argument('--termination-policy', choices=('endattack','eof_hazards_drained'), default='endattack')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not math.isfinite(args.fps) or args.fps <= 0:
        parser.error('--fps must be finite and positive')
    captured = json.loads(args.entry.read_text(encoding='utf-8-sig')) if args.entry else {}
    result = solve_csv(args.csv, captured.get('initial', args.initial),
        initial_environment=captured.get('initial_environment'),
        dt_schedule=captured.get('dt_schedule',[1/args.fps]*args.max_ticks), max_ticks=args.max_ticks,
        width=args.width, seconds=args.seconds,
        seed=args.seed, search_strategy=args.search_strategy, workers=args.workers, memory_mb=args.memory_mb,
        allow_scripted_healing=args.allow_scripted_healing,allow_scripted_damage=args.allow_scripted_damage,
        initial_arena=captured.get('initial_arena',captured.get('arena')),
        initial_confirm=captured.get('initial_confirm',False), previous_confirm=captured.get('previous_confirm',False),
        initial_target_history=captured.get('initial_target_history'),
        termination_policy=args.termination_policy,
        observation_chunk_ticks=args.observation_chunk_ticks,
        observation_preview_ticks=args.observation_preview_ticks,
        observation_preview_reads=args.observation_preview_reads,
        observation_goal_style=args.observation_goal_style,
        observation_goal_retries=args.observation_goal_retries,
        fixed_prefix=json.loads(args.fixed_prefix.read_text(encoding='utf-8-sig')) if args.fixed_prefix else None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    keys = ('status', 'reason', 'reached_tick', 'verified', 'wall_seconds',
            'game_seconds', 'physics_hz', 'original_replay_passed')
    print(json.dumps({key: result[key] for key in keys if key in result}, indent=2))
    return 0 if result['status'] == 'candidate_found' else 2


if __name__ == '__main__':
    raise SystemExit(main())
