"""Run every indexed CSV in a fresh process with a captured original entry.

No routes or worlds are reused. Captured entry clocks and compiled code may be
reused. Missing files, model gaps and timeouts remain explicit failed cases.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def implementations():
    return {p.name: digest(p) for p in (ROOT / 'nohit/engine').iterdir()
            if p.suffix in ('.py', '.cpp', '.so', '.pyd', '.dylib')}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def child(args):
    from nohit import _configure_solver_process
    _configure_solver_process()
    from nohit.engine.csv_solver import solve_csv
    from nohit.engine.native_backend import load_backend
    from tools.benchmark_round8_request import peak_rss_bytes
    entry = json.loads(args.entry.read_text())
    before = implementations()
    began = time.perf_counter()
    settings = dict(initial_environment=entry['initial_environment'],
        initial_arena=entry.get('initial_arena', entry.get('arena')),
        initial_confirm=entry.get('initial_confirm', False),
        previous_confirm=entry.get('previous_confirm', False),
        initial_target_history=entry.get('initial_target_history'),
        dt_schedule=entry['dt_schedule'], max_ticks=len(entry['dt_schedule']),
        search_strategy='native', workers=args.workers, width=args.width,
        memory_mb=args.memory_mb, seconds=args.seconds,
        termination_policy=args.termination_policy)
    if args.profile:
        import cProfile
        profiler = cProfile.Profile()
        result = profiler.runcall(solve_csv, args.csv, entry['initial'], **settings)
        profiler.dump_stats(str(args.out / 'profile.pstats'))
    else:
        result = solve_csv(args.csv, entry['initial'], **settings)
    elapsed = time.perf_counter() - began
    if before != implementations():
        raise RuntimeError('Implementation changed during measurement')
    with gzip.open(args.out / 'witness.json.gz', 'wt', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False)
    record = {key: result.get(key) for key in ('status', 'reason', 'verified',
        'reached_tick', 'game_seconds', 'warnings', 'issues', 'terminal_reasons', 'completion', 'search_stats')}
    record.update(solve_seconds=elapsed, peak_rss_bytes=peak_rss_bytes(),
        source_sha256=digest(args.csv), entry_sha256=digest(args.entry),
        implementation_sha256=hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
        route_cache=False, environment_cache=False, original_replay_passed=False,
        numba_imported='numba' in sys.modules,
        installed_code_images=sorted(p.name for p in (ROOT/'nohit/engine').iterdir()
            if p.suffix in ('.so','.pyd','.dylib')),
        native_load=None if not load_backend.cache_info().currsize else dict(load_backend()[1]))
    write_json(args.out / 'result.json', record)
    print(json.dumps({k: record[k] for k in ('status', 'reason', 'verified', 'solve_seconds')}))


def run(args):
    from nohit.engine.csv_preparation import prepare_csv_bytes
    samples = json.loads((ROOT / 'data/samples.json').read_text())['samples']
    samples.append(dict(id='regression/realhell-weakened',
        path='artifacts/realhell-weakened-20261017/source.csv',
        entry='artifacts/realhell-weakened-20261017/entry.json'))
    indexed = {item['path'] for item in samples}
    for folder in ('c2-sans-fight', 'hrzq'):
        for path in sorted((ROOT / folder).glob('*.csv')):
            relative = path.relative_to(ROOT).as_posix()
            if relative not in indexed:
                samples.append(dict(id=relative.removesuffix('.csv'), path=relative))
    if args.case:
        samples = [s for s in samples if any(q in s['id'] or q in s['path'] for q in args.case)]
    args.out.mkdir(parents=True, exist_ok=True)
    game = args.out / 'capture-game'
    if not game.exists():
        shutil.copytree(ROOT / 'c2-sans-fight', game)
    records = []
    for sample in samples:
        name = sample['id'].replace('/', '__')
        folder = args.out / name
        folder.mkdir(parents=True, exist_ok=True)
        path = ROOT / sample['path']
        record = dict(id=sample['id'], path=sample['path'])
        if not path.exists():
            record.update(status='missing', verified=False)
        else:
            prepared = prepare_csv_bytes(path.read_bytes())
            source = folder / 'source.csv'
            source.write_bytes(prepared['raw'])
            write_json(folder / 'preparation.json', prepared['preparation'])
            entry = folder / 'entry.json'
            capture_identity = dict(source_sha256=digest(source), fps=args.fps)
            capture_receipt = folder / 'capture.json'
            if args.entries_from and not entry.exists():
                previous = args.entries_from / name
                if ((previous / 'entry.json').exists() and (previous / 'source.csv').exists()
                        and digest(previous / 'source.csv') == digest(source)):
                    shutil.copyfile(previous / 'entry.json', entry)
                    if (previous / 'capture.json').exists():
                        shutil.copyfile(previous / 'capture.json', capture_receipt)
            if 'entry' in sample:
                shutil.copyfile(ROOT / sample['entry'], entry)
            elif not (entry.exists() and capture_receipt.exists()
                      and json.loads(capture_receipt.read_text()) == capture_identity):
                shutil.copyfile(source, game / 'sans_bonegap1.csv')
                environment = dict(os.environ, NOHIT_CAPTURE_ONLY='1',
                    NOHIT_GAME_DIR=str(game.resolve()), NOHIT_BENCH_OUT=str(folder.resolve()),
                    NOHIT_FPS=str(args.fps))
                try:
                    capture = subprocess.run(['node', 'tools/native_optimized_replay.mjs', 'sans_bonegap1'],
                        cwd=ROOT, env=environment, text=True, capture_output=True, timeout=15)
                    if capture.returncode:
                        raise RuntimeError(capture.stderr[-3000:])
                    shutil.move(folder / 'sans_bonegap1-entry.json', entry)
                    write_json(capture_receipt, capture_identity)
                except (subprocess.TimeoutExpired, RuntimeError) as error:
                    record.update(status='capture_failed', verified=False, error=str(error))
            if 'status' not in record:
                rows = prepared['text'].splitlines()
                has_end = any(len(parts := row.split(',')) > 1 and parts[1].strip().lower() == 'endattack' for row in rows)
                policy = 'endattack' if has_end else 'eof_hazards_drained'
                command = [sys.executable, '-m', 'tools.benchmark_samples', '--child',
                    '--csv', str(source.resolve()), '--entry', str(entry.resolve()),
                    '--out', str(folder.resolve()), '--seconds', str(args.seconds),
                    '--width', str(args.width), '--workers', str(args.workers),
                    '--memory-mb', str(args.memory_mb), '--termination-policy', policy]
                if args.profile:
                    command.append('--profile')
                began = time.perf_counter()
                try:
                    solved = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=args.timeout)
                    external = time.perf_counter() - began
                    if solved.returncode:
                        record.update(status='error', verified=False, error=solved.stderr[-5000:])
                    else:
                        record.update(json.loads((folder / 'result.json').read_text()))
                    record.update(external_wall_seconds=external, termination_policy=policy,
                        source_preparation=prepared['preparation'])
                except subprocess.TimeoutExpired:
                    record.update(status='timeout', verified=False, external_wall_seconds=time.perf_counter()-began)
        records.append(record)
        write_json(args.out / 'summary.json', records)
        print(json.dumps({k: record[k] for k in ('id', 'status', 'reason', 'verified',
            'solve_seconds', 'external_wall_seconds') if k in record}, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--case', action='append')
    parser.add_argument('--entries-from', type=Path, help='Reuse only captured entries from an earlier suite')
    parser.add_argument('--fps', type=float, default=60)
    parser.add_argument('--seconds', type=float, default=5)
    parser.add_argument('--timeout', type=float, default=30)
    parser.add_argument('--width', type=int, default=1024)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--memory-mb', type=int, default=512)
    parser.add_argument('--profile', action='store_true')
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--csv', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--entry', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--termination-policy', default='endattack', help=argparse.SUPPRESS)
    args = parser.parse_args()
    (child if args.child else run)(args)


if __name__ == '__main__':
    main()
