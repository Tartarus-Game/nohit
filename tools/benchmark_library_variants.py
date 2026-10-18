"""Fresh-process full-solver comparison, with interleaved library variants.

Each child freshly executes the source and independently verifies its result.
Only compiled code and captured input clocks are reused. Unknown results are
retained and never counted as speedups.
"""
import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = dict(scalar=('off', 'std'), highway=('highway', 'std'),
                pdqsort=('off', 'pdqsort'), combined=('highway', 'pdqsort'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', type=Path, required=True)
    parser.add_argument('--entry', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--width', type=int, default=8192)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--memory-mb', type=int, default=1024)
    parser.add_argument('--termination-policy', default='eof_hazards_drained')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    records = []
    for repetition in range(args.repeats):
        names = list(VARIANTS)
        names = names[repetition % len(names):] + names[:repetition % len(names)]
        for name in names:
            simd, sorter = VARIANTS[name]
            environment = dict(os.environ, NOHIT_NATIVE_SIMD=simd, NOHIT_NATIVE_SORT=sorter)
            folder = (args.out / f'{name}-{repetition+1}').resolve()
            folder.mkdir(parents=True, exist_ok=True)
            command = [sys.executable, '-m', 'tools.benchmark_samples', '--child',
                '--csv', str(args.csv.resolve()), '--entry', str(args.entry.resolve()), '--out', str(folder),
                '--seconds', str(args.seconds), '--width', str(args.width), '--workers', str(args.workers),
                '--memory-mb', str(args.memory_mb), '--termination-policy', args.termination_policy]
            began = time.perf_counter()
            child = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True,
                                   text=True, timeout=max(90, args.seconds+60))
            external = time.perf_counter()-began
            (folder/'child.log').write_text(child.stdout+child.stderr)
            if child.returncode:
                raise RuntimeError(f'{name}: {child.stderr[-3000:]}')
            result = json.loads((folder/'result.json').read_text())
            metadata = result['native_load']
            assert metadata['highway'] == (simd == 'highway') and metadata['pdqsort'] == (sorter == 'pdqsort')
            assert not metadata['compiled'], 'Warm the selected compiled code before this benchmark'
            record = dict(variant=name, repetition=repetition+1,
                status=result['status'], verified=result['verified'], reason=result['reason'],
                reached_tick=result.get('reached_tick'), solve_seconds=result['solve_seconds'],
                external_seconds=external, peak_rss_bytes=result['peak_rss_bytes'],
                original_replay_passed=False, binary_sha256=metadata['binary_sha256'],
                implementation_sha256=result['implementation_sha256'],
                source_sha256=result['source_sha256'], entry_sha256=result['entry_sha256'])
            records.append(record)
            (args.out/'runs.json').write_text(json.dumps(records, indent=2)+'\n')
            print(json.dumps(record), flush=True)
    summary = {}
    for name in VARIANTS:
        rows = [r for r in records if r['variant'] == name]
        successes = [r for r in rows if r['status'] == 'candidate_found' and r['verified']]
        summary[name] = dict(attempts=len(rows), successes=len(successes),
            median_success_seconds=statistics.median(r['solve_seconds'] for r in successes) if successes else None,
            all_runs_verified=len(successes) == len(rows))
    (args.out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
