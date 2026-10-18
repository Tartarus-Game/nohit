"""Measure the current native CSV solver in fresh processes.

Only compiled code may be reused. Each request rebuilds its world and route;
model verification does not imply original-game acceptance.
"""
import argparse
import ctypes
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

try:
    import resource
except ImportError:
    resource = None

ROOT = Path(__file__).resolve().parents[1]


def peak_rss_bytes():
    """Peak RSS of the solver process; compiler children are excluded."""
    if resource is not None:
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return value if sys.platform == 'darwin' else value * 1024

    class Counters(ctypes.Structure):
        _fields_ = [('cb', ctypes.c_ulong), ('PageFaultCount', ctypes.c_ulong),
                    ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                    ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                    ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]

    counters = Counters()
    counters.cb = ctypes.sizeof(Counters)
    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    query = getattr(kernel32, 'K32GetProcessMemoryInfo', None) or ctypes.windll.psapi.GetProcessMemoryInfo
    query.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong]
    query.restype = ctypes.c_int
    if not query(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        return 0
    return int(counters.PeakWorkingSetSize)


def child(args):
    from nohit import _configure_solver_process
    _configure_solver_process()
    from nohit.engine.csv_solver import solve_csv
    from nohit.engine import native_backend

    entry = json.loads(args.entry.read_text(encoding='utf-8-sig'))
    implementation = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (ROOT / 'nohit/engine').iterdir() if p.suffix in ('.py', '.cpp')}
    accelerator_files={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (ROOT/'nohit/engine').iterdir() if p.suffix in ('.so','.pyd','.dylib')}
    accelerator_manifest=ROOT/'build/accelerated/manifest.json'
    accelerator_metadata=json.loads(accelerator_manifest.read_text()) if accelerator_files and accelerator_manifest.exists() else None
    began, cpu = time.perf_counter(), time.process_time()
    result = solve_csv(args.csv, entry['initial'],
        initial_environment=entry.get('initial_environment'),
        initial_arena=entry.get('initial_arena', entry.get('arena')),
        initial_confirm=entry.get('initial_confirm', False),
        previous_confirm=entry.get('previous_confirm', False),
        initial_target_history=entry.get('initial_target_history'),
        dt_schedule=entry.get('dt_schedule', [1 / 30] * args.max_ticks),
        max_ticks=args.max_ticks, search_strategy='native', workers=args.workers,
        width=args.width, memory_mb=args.memory_mb, seconds=args.seconds,
        allow_scripted_healing=args.allow_scripted_healing,
        allow_scripted_damage=args.allow_scripted_damage,
        termination_policy=args.termination_policy,
        observation_chunk_ticks=args.observation_chunk_ticks,
        observation_preview_ticks=args.observation_preview_ticks,
        observation_preview_reads=args.observation_preview_reads,
        observation_goal_style=args.observation_goal_style,
        observation_goal_retries=args.observation_goal_retries)
    elapsed, cpu = time.perf_counter() - began, time.process_time() - cpu
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (ROOT / 'nohit/engine').iterdir() if p.suffix in ('.py', '.cpp')}
    if after != implementation:
        raise RuntimeError('Solver sources changed during benchmark; discard this measurement')
    if accelerator_files!={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT/'nohit/engine').iterdir() if p.suffix in ('.so','.pyd','.dylib')}:
        raise RuntimeError('Compiled VM changed during benchmark; discard this measurement')
    witness = {key: result.get(key) for key in
               ('actions', 'confirm_sequence', 'trajectory', 'dt_sequence', 'target_history', 'completion')}
    record = dict(status=result['status'], reason=result.get('reason'),
        verified=result['verified'], solve_seconds=elapsed, solve_cpu_seconds=cpu,
        effective_solve_cores=cpu / elapsed, peak_rss_bytes=peak_rss_bytes(),
        search_stats=result.get('search_stats'),
        source_sha256=implementation['native_frontier.cpp'],
        implementation_sha256=hashlib.sha256(json.dumps(implementation, sort_keys=True).encode()).hexdigest(),
        fingerprint=hashlib.sha256(json.dumps(witness, sort_keys=True).encode()).hexdigest(),
        csv_sha256=result['csv_sha256'], entry_sha256=hashlib.sha256(args.entry.read_bytes()).hexdigest(),
        original_replay_passed=result['original_replay_passed'],
        python_accelerators=accelerator_metadata,accelerator_binary_sha256=accelerator_files,
        numba_imported='numba' in sys.modules, route_cache=False, environment_cache=False)
    if args.witness_out is not None:
        args.witness_out.parent.mkdir(parents=True,exist_ok=True)
        with gzip.open(args.witness_out,'wt',encoding='utf-8') as output:
            json.dump(result,output)
    print(json.dumps(record))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('--entry', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--witness-out', type=Path, help='Save the resulting witness after the timed solve')
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--width', type=int, default=8192)
    parser.add_argument('--seconds', type=float, default=45)
    parser.add_argument('--memory-mb', type=int, default=256)
    parser.add_argument('--max-ticks', type=int, default=40000)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--empty-code-cache', action='store_true')
    parser.add_argument('--allow-scripted-healing', action='store_true')
    parser.add_argument('--allow-scripted-damage', action='store_true')
    parser.add_argument('--termination-policy', choices=('endattack', 'eof_hazards_drained'), default='endattack')
    parser.add_argument('--observation-chunk-ticks', type=int, default=0)
    parser.add_argument('--observation-preview-ticks', type=int, default=0)
    parser.add_argument('--observation-preview-reads', type=int, default=128)
    parser.add_argument('--observation-goal-style', type=int)
    parser.add_argument('--observation-goal-retries', action='store_true')
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not (1 <= args.workers <= 32 and min(args.width, args.memory_mb, args.max_ticks, args.repeats) > 0
            and math.isfinite(args.seconds) and args.seconds > 0):
        parser.error('require 1..32 workers and positive width, budget, horizon and repeats')
    if args.child:
        child(args)
        return
    command = [sys.executable, '-m', 'tools.benchmark_round8_request', str(args.csv.resolve()),
        '--entry', str(args.entry.resolve()), '--out', str(args.out.resolve()),
        '--termination-policy', args.termination_policy, '--child']
    for name in ('workers', 'width', 'seconds', 'memory_mb', 'max_ticks',
                 'observation_chunk_ticks', 'observation_preview_ticks', 'observation_preview_reads'):
        command += ['--' + name.replace('_', '-'), str(getattr(args, name))]
    if args.observation_goal_style is not None:
        command += ['--observation-goal-style', str(args.observation_goal_style)]
    if args.witness_out is not None:
        command += ['--witness-out',str(args.witness_out.resolve())]
    for name in ('allow_scripted_healing', 'allow_scripted_damage', 'observation_goal_retries'):
        if getattr(args, name):
            command.append('--' + name.replace('_', '-'))
    records = []
    for repeat in range(args.repeats):
        with tempfile.TemporaryDirectory(prefix='nohit-request-code-') as cache:
            environment = dict(os.environ)
            if args.empty_code_cache:
                environment['NOHIT_NATIVE_CACHE'] = cache
            began = time.perf_counter()
            run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, env=environment)
            if run.returncode:
                raise RuntimeError(run.stdout + '\n' + run.stderr)
            record = json.loads(run.stdout)
            record.update(repeat=repeat, external_wall_seconds=time.perf_counter() - began,
                workers=args.workers, width=args.width, empty_code_cache=args.empty_code_cache)
        records.append(record)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({key: record[key] for key in
            ('repeat', 'status', 'verified', 'solve_seconds', 'external_wall_seconds', 'peak_rss_bytes')}), flush=True)


if __name__ == '__main__':
    main()
