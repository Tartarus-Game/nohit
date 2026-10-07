"""Fresh routes, identical physics/beam/margins; JIT startup reported separately.

Run: .venv/Scripts/python.exe tools/benchmark_operators.py --repeats 5
This measures candidate generation, never game acceptance or completeness.
"""
import argparse
import hashlib
import json
import platform
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
import numpy as np
import numba

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nohit.baker.dilator import bake_cspace
from nohit.engine.source_compiled import solve_source_compiled

WAVES = ['bluebone', 'bonegap1', 'bonegap1fast', 'bonegap2', 'boneslideh', 'platforms3', 'platforms4hard']


def options(wave):
    diverse = wave in ('bonegap1', 'bonegap2') or wave.startswith('platforms')
    result = dict(max_states=3600 if diverse else 512, phase_diversity=diverse)
    if wave in ('bluebone', 'boneslideh'):
        # Use the existing production fallback beam to measure full candidates.
        result['max_states'] = 3600
    if diverse:
        result.update(spatial_margin=1, timing_margin_frames=1, landing_wait_frames=3)
    if wave == 'platforms4hard':
        result['initial_vy'] = 60.048
    return result


def digest(result):
    return hashlib.sha256(json.dumps([result.is_deadlock, result.deadlock_frame,
        result.action_sequence, result.trajectory, result.stats.alive_states_history],
        separators=(',', ':')).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--waves', nargs='+', default=WAVES, choices=WAVES)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('repeats must be positive')
    destination = ROOT / 'tools' / 'operator-results'
    destination.mkdir(exist_ok=True)
    report = dict(created_at=datetime.now().astimezone().isoformat(), seed=42,
        route_cache=False, acceptance=False, exact_original_model=False,
        python=platform.python_version(), numpy=np.__version__, numba=numba.__version__,
        machine=platform.platform(), cpu=platform.processor(), parallel_workers=8,
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [ROOT/'nohit/engine/source_compiled.py', ROOT/'c2-sans-fight/c2runtime.js', ROOT/'c2-sans-fight/data.js']},
        results=[])
    for wave in args.waves:
        path = ROOT / 'c2-sans-fight' / f'sans_{wave}.csv'
        bake_args = dict(auto_size=True, soul_w=4, soul_h=4, physics_mode='c2', attack_seed=42)
        # Compile each actual dtype signature using real data. No cached route.
        bake = bake_cspace(path, **bake_args)
        startup = {}
        expected = None
        for operator in ('baseline', 'a', 'b'):
            first = time.perf_counter()
            result = solve_source_compiled(bake, operator=operator, **options(wave))
            startup[operator] = (time.perf_counter()-first)*1000
            signature = digest(result)
            if expected is None:
                expected = signature
            if signature != expected:
                raise RuntimeError(f'{wave}/{operator}: differential mismatch')
        samples = {op: [] for op in startup}
        for iteration in range(args.repeats):
            # Rotate order to reduce thermal/order bias; every run rebakes.
            order = ('baseline', 'a', 'b')
            order = order[iteration % 3:] + order[:iteration % 3]
            for operator in order:
                begin = time.perf_counter()
                bake = bake_cspace(path, **bake_args)
                baked = time.perf_counter()
                result = solve_source_compiled(bake, operator=operator, **options(wave))
                end = time.perf_counter()
                if digest(result) != expected:
                    raise RuntimeError(f'{wave}/{operator}: unstable result')
                samples[operator].append(dict(bake_ms=(baked-begin)*1000,
                    prepare_ms=result.stats.operator_prepare_ms, search_ms=result.stats.operator_search_ms,
                    reconstruct_ms=result.stats.operator_reconstruct_ms,
                    candidate_ms=result.stats.dp_solve_time_ms, total_ms=(end-begin)*1000))
                if iteration == 0:
                    route = dict(wave=path.name, seed=42, operator=operator, candidate_found=not result.is_deadlock,
                        deadlock_proven=False, realtime_accepted=False, actions=result.action_sequence,
                        trajectory=result.trajectory, fingerprint=expected, options=options(wave))
                    (destination/f'{wave}-{operator}.json').write_text(json.dumps(route), encoding='utf-8', newline='\n')
        entry = dict(wave=path.name, T=bake.T, W=bake.W, H=bake.H, options=options(wave),
            candidate_found=not result.is_deadlock, exhausted_frame=result.deadlock_frame,
            parity=True, fingerprint=expected, csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            first_call_ms=startup, samples=samples, summary={})
        for operator, values in samples.items():
            entry['summary'][operator] = {key:dict(median=statistics.median(v[key] for v in values),
                max=max(v[key] for v in values), min=min(v[key] for v in values)) for key in values[0]}
        report['results'].append(entry)
        (destination/'latest.json').write_text(json.dumps(report, indent=2), encoding='utf-8', newline='\n')
        print(wave, 'candidate', entry['candidate_found'], 'total ms',
              {op:round(v['total_ms']['median'],2) for op,v in entry['summary'].items()}, flush=True)
    rows = ['# 两版算子实测', '', 'seed=42；每次重新烘焙并求解，未复用路线。JIT 首次调用单列于 JSON。',
        '动作、轨迹、前沿数量和终止帧与 baseline 完全一致；此处不代表原版游戏验收。', '',
        '| 回合 | 结果 | baseline 端到端 | A 端到端 | B 端到端 | B 搜索 |',
        '|---|---|---:|---:|---:|---:|']
    for e in report['results']:
        s=e['summary']
        rows.append(f"| {e['wave']} | {'候选' if e['candidate_found'] else '无候选'} | " +
            ' | '.join(f"{s[op]['total_ms']['median']:.2f}ms" for op in ('baseline','a','b'))+
            f" | {s['b']['search_ms']['median']:.2f}ms |")
    rows += ['', '完整样本、阶段耗时、源码哈希和运行环境见 latest.json。无候选不等于死局。']
    (destination/'RESULTS.md').write_text('\n'.join(rows)+'\n',encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()
