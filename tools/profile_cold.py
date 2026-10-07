"""Time a genuinely new process, including imports and first kernel invocation.

Compiler cache and route cache are different: all runs bake and search afresh.
An empty compiler cache measures installation/source-change compilation too.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--operator', choices=['baseline', 'a', 'b'], default='b')
    parser.add_argument('--empty-compiler-cache', action='store_true')
    parser.add_argument('--built-runtime', action='store_true')
    args = parser.parse_args()
    if args.child:
        start = time.perf_counter()
        sys.path.insert(0, str(ROOT))
        if args.built_runtime:
            from nohit.native_runtime import select_built_runtime
            select_built_runtime(required=True)
        from nohit.baker.dilator import bake_cspace
        from nohit.engine.source_compiled import solve_source_compiled, _search, _clearance, _clearance_anchors
        imported = time.perf_counter()
        bake = bake_cspace(ROOT/'c2-sans-fight/sans_bonegap1.csv', auto_size=True,
            soul_w=4, soul_h=4, physics_mode='c2', attack_seed=42)
        baked = time.perf_counter()
        result = solve_source_compiled(bake, operator=args.operator, max_states=3600,
            phase_diversity=True, spatial_margin=1, timing_margin_frames=1, landing_wait_frames=3)
        end = time.perf_counter()
        dispatchers = [_search, _clearance, _clearance_anchors]
        code_hits = sum(sum(d._cache_hits.values()) for d in dispatchers)
        code_misses = sum(sum(d._cache_misses.values()) for d in dispatchers)
        if args.built_runtime and code_misses:
            raise RuntimeError('Built-runtime trial unexpectedly compiled code')
        print(json.dumps(dict(operator=args.operator, import_ms=(imported-start)*1000,
            bake_ms=(baked-imported)*1000, first_prepare_ms=result.stats.operator_prepare_ms,
            first_search_ms=result.stats.operator_search_ms, candidate_ms=(end-baked)*1000,
            process_work_ms=(end-start)*1000, candidate_found=not result.is_deadlock,
            route_cache=False, compiled_code_hits=code_hits, compiled_code_misses=code_misses)))
        return
    env = dict(os.environ)
    if args.empty_compiler_cache and args.built_runtime:
        parser.error('empty compiler cache and built runtime are distinct experiments')
    if args.empty_compiler_cache:
        cache = ROOT / '.cold-cache' / str(time.time_ns())
        cache.mkdir(parents=True)
        env['NUMBA_CACHE_DIR'] = str(cache)
    begin = time.perf_counter()
    command = [sys.executable, str(Path(__file__).resolve()), '--child', '--operator', args.operator]
    if args.built_runtime:
        command.append('--built-runtime')
    completed = subprocess.run(command, env=env, cwd=ROOT, capture_output=True, text=True, check=True)
    elapsed = (time.perf_counter()-begin)*1000
    result = json.loads(completed.stdout)
    result.update(new_process=True, empty_compiler_cache=args.empty_compiler_cache,
                  built_runtime=args.built_runtime, wall_ms=elapsed, startup_and_exit_ms=elapsed-result['process_work_ms'])
    state = 'built' if args.built_runtime else 'empty' if args.empty_compiler_cache else 'installed'
    destination = ROOT/'tools/operator-results'/f'cold-{args.operator}-{state}.json'
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(result, indent=2), encoding='utf-8', newline='\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
