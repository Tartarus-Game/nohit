"""Full fresh-process requests, including optional empty native code caches."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv',type=Path);parser.add_argument('--entry',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--child',action='store_true')
    parser.add_argument('--reuse-code',action='store_true');parser.add_argument('--healing',action='store_true')
    parser.add_argument('--repeats',type=int,default=3);args=parser.parse_args()
    if args.child:
        from nohit import _configure_solver_process
        _configure_solver_process()
        started=time.perf_counter()
        from nohit.engine.csv_solver import solve_csv
        imported=time.perf_counter();entry=json.loads(args.entry.read_text())
        result=solve_csv(args.csv,entry['initial'],initial_environment=entry.get('initial_environment'),
            initial_arena=entry.get('initial_arena'),initial_confirm=entry.get('initial_confirm',False),
            previous_confirm=entry.get('previous_confirm',False),initial_target_history=entry.get('initial_target_history'),
            dt_schedule=entry['dt_schedule'],max_ticks=40000,search_strategy='native',seconds=8,
            workers=8,width=3000,memory_mb=64,allow_scripted_healing=args.healing)
        fields={k:result.get(k) for k in ('actions','confirm_sequence','trajectory','target_history')}
        own=resource.getrusage(resource.RUSAGE_SELF);compiler=resource.getrusage(resource.RUSAGE_CHILDREN)
        record=dict(status=result['status'],model_verified=result['verified'],inside_seconds=time.perf_counter()-started,
            import_seconds=imported-started,solve_seconds=result['wall_seconds'],search_stats=result.get('search_stats'),
            process_peak_rss_bytes=own.ru_maxrss*1024,compiler_peak_rss_bytes=compiler.ru_maxrss*1024,
            fingerprint=hashlib.sha256(json.dumps(fields,sort_keys=True).encode()).hexdigest(),
            numba_imported='numba' in sys.modules,route_cache=False,environment_cache=False)
        print(json.dumps(record));return 0 if result['verified'] else 2
    records=[];fingerprint=None
    for repeat in range(args.repeats):
        with tempfile.TemporaryDirectory(prefix='nohit-code-only-') as cache:
            environment=dict(os.environ)
            if not args.reuse_code:environment['NOHIT_NATIVE_CACHE']=cache
            command=[sys.executable,'-m','tools.benchmark_solver_request',str(args.csv),'--entry',str(args.entry),
                '--out',str(args.out),'--child']+(['--healing'] if args.healing else [])
            started=time.perf_counter();child=subprocess.run(command,env=environment,capture_output=True,text=True,timeout=40)
            elapsed=time.perf_counter()-started
            if child.returncode:raise RuntimeError(child.stdout+'\n'+child.stderr)
            record=json.loads(child.stdout);record.update(repeat=repeat,external_wall_seconds=elapsed,empty_code_cache=not args.reuse_code)
            assert not record['numba_imported']
            if fingerprint is None:fingerprint=record['fingerprint']
            assert record['fingerprint']==fingerprint,'different verified input word'
            records.append(record);args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(records,indent=2))
            print(json.dumps({k:record[k] for k in ('external_wall_seconds','solve_seconds','empty_code_cache','process_peak_rss_bytes')}),flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
