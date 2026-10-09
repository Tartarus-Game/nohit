"""Whole-process cold timings; fresh native and Numba caches, no saved routes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
WAVES=['sans_bonegap1','sans_bonegap1fast','sans_bluebone','sans_platforms3','sans_platforms4hard']


def rss_tree(pid):
    """Linux sampled sum RSS, including compiler descendants; shared pages count twice."""
    pending=[pid];seen=set();total=0
    while pending:
        current=pending.pop()
        if current in seen:continue
        seen.add(current)
        try:
            status=Path(f'/proc/{current}/status').read_text()
            line=next((line for line in status.splitlines() if line.startswith('VmRSS:')),None)
            if line:total+=int(line.split()[1])*1024
            pending += [int(value) for value in Path(f'/proc/{current}/task/{current}/children').read_text().split()]
        except (OSError,ValueError):pass
    return total


def child(args):
    started=time.perf_counter()
    from nohit.engine.csv_solver import solve_csv
    imported=time.perf_counter()
    entry=json.loads((args.entry_dir/(args.wave+'-entry.json')).read_text())
    before_cpu=time.process_time()
    result=solve_csv(ROOT/'c2-sans-fight'/(args.wave+'.csv'),entry['initial'],
        initial_environment=entry['initial_environment'],initial_arena=entry['initial_arena'],
        initial_confirm=entry['initial_confirm'],previous_confirm=entry['previous_confirm'],
        dt_schedule=entry.get('dt_schedule',[1/30]*40000),max_ticks=40000,width=3000,seconds=8,
        initial_target_history=entry.get('initial_target_history'),
        search_strategy='native',workers=args.workers)
    try:
        import resource
        own=resource.getrusage(resource.RUSAGE_SELF);compiler=resource.getrusage(resource.RUSAGE_CHILDREN)
        resources=dict(process_peak_rss_bytes=own.ru_maxrss*1024,compiler_peak_rss_bytes=compiler.ru_maxrss*1024,
            process_cpu_seconds=own.ru_utime+own.ru_stime,compiler_cpu_seconds=compiler.ru_utime+compiler.ru_stime)
    except ImportError:resources={}
    fields={name:result.get(name) for name in ('status','reason','actions','confirm_sequence','trajectory','dt_sequence','completion')}
    fingerprint=hashlib.sha256(json.dumps(fields,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    record=dict(wave=args.wave,workers=args.workers,status=result['status'],verified=result['verified'],
        import_seconds=imported-started,inside_seconds=time.perf_counter()-started,
        solve_seconds=result['wall_seconds'],solve_cpu_seconds=time.process_time()-before_cpu,
        fingerprint=fingerprint,numba_imported='numba' in sys.modules,llvmlite_imported='llvmlite' in sys.modules,
        search_stats=result.get('search_stats'),**resources)
    print(json.dumps(record),flush=True)
    return 0 if result['status']=='candidate_found' else 2


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child',action='store_true');parser.add_argument('--wave',default=WAVES[0])
    parser.add_argument('--waves',nargs='+',default=WAVES);parser.add_argument('--workers',type=int,default=8)
    parser.add_argument('--repeats',type=int,default=3);parser.add_argument('--reuse-code',action='store_true')
    parser.add_argument('--entry-dir',type=Path,default=ROOT/'tools/optimization-results')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.child:return child(args)
    if args.repeats<1:parser.error('repeats must be positive')
    records=[]
    for wave in args.waves:
        expected=None
        for repeat in range(args.repeats):
            with tempfile.TemporaryDirectory(prefix='nohit-empty-code-') as cache:
                environment=dict(os.environ)
                environment['NUMBA_CACHE_DIR']=str(Path(cache)/'numba')
                if not args.reuse_code:environment['NOHIT_NATIVE_CACHE']=str(Path(cache)/'native')
                started=time.perf_counter()
                process=subprocess.Popen([sys.executable,'-m','tools.benchmark_cold_native','--child','--wave',wave,'--workers',str(args.workers),'--entry-dir',str(args.entry_dir.resolve())],
                    cwd=ROOT,env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                # /proc may expose host PIDs while Popen uses a nested PID namespace.
                proc_pid=process.pid
                try:
                    host=int(os.readlink('/proc/self'))
                    children=Path(f'/proc/{host}/task/{host}/children').read_text().split()
                    if len(children)==1:proc_pid=int(children[0])
                except (OSError,ValueError):pass
                stop=threading.Event();samples=[]
                def sample():
                    while not stop.is_set():samples.append(rss_tree(proc_pid));stop.wait(.005)
                sampler=threading.Thread(target=sample,daemon=True);sampler.start()
                stdout,stderr=process.communicate(timeout=30)
                wall=time.perf_counter()-started;stop.set();sampler.join()
                if process.returncode:raise RuntimeError(stdout+'\n'+stderr)
                record=json.loads(stdout)
                assert record['verified'] and not record['numba_imported'] and not record['llvmlite_imported']
                if expected is None:expected=record['fingerprint']
                assert record['fingerprint']==expected,'nondeterministic witness'
                if not args.reuse_code:
                    code=record['search_stats']['native_code']
                    assert code['compiled'] or code.get('scalar_preflight'), 'neither fresh compilation nor compilation-free scalar proof'
                record.update(external_wall_seconds=wall,empty_code_cache=not args.reuse_code,
                    repeated_process=True,route_cache=False,environment_cache=False,
                    sampled_tree_peak_rss_bytes=(max(samples,default=0) if max(samples,default=0)>=record.get('process_peak_rss_bytes',1) else None),rss_sample_interval_seconds=.005,
                    recorded_rss_peaks_sum_bytes=record.get('process_peak_rss_bytes',0)+record.get('compiler_peak_rss_bytes',0))
                records.append(record)
                suffix='process' if args.reuse_code else 'empty'
                destination=args.output or ROOT/'tools/optimization-results'/f'cold-native-{suffix}-w{args.workers}.json'
                destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_text(json.dumps(records,indent=2))
                print(json.dumps({k:record[k] for k in ('wave','external_wall_seconds','sampled_tree_peak_rss_bytes','status')}),flush=True)
                if wall>=10:raise RuntimeError('whole cold process exceeded 10 seconds')
    return 0


if __name__=='__main__':raise SystemExit(main())
