"""Same entry and source in fresh processes; Round5 versus current solver."""
import argparse,hashlib,importlib.util,json,resource,sys,time
from pathlib import Path
from nohit.engine import native_backend as backend
from nohit.engine.csv_solver import solve_csv


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('csv',type=Path)
    parser.add_argument('--entry',type=Path,required=True);parser.add_argument('--baseline',action='store_true')
    parser.add_argument('--healing',action='store_true');parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--seconds',type=float,default=45);args=parser.parse_args()
    if args.baseline:
        reference=Path(__file__).parent/'reference/round5_native_dynamic.py'
        spec=importlib.util.spec_from_file_location('nohit.engine.native_dynamic',reference)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        sys.modules['nohit.engine.native_dynamic']=module
        backend._SOURCE=reference.with_name('round5_native_frontier.cpp');backend.load_backend.cache_clear()
    backend.load_backend() # code-only cache, excluded from solve timing
    entry=json.loads(args.entry.read_text());started=time.perf_counter()
    result=solve_csv(args.csv,entry['initial'],initial_environment=entry['initial_environment'],
        initial_arena=entry.get('initial_arena'),dt_schedule=entry['dt_schedule'],max_ticks=40000,
        initial_confirm=entry.get('initial_confirm',False),previous_confirm=entry.get('previous_confirm',False),
        initial_target_history=entry.get('initial_target_history'),search_strategy='native',workers=8,
        width=8192,memory_mb=256,seconds=args.seconds,allow_scripted_healing=args.healing)
    elapsed=time.perf_counter()-started
    record=dict(baseline=args.baseline,status=result['status'],verified=result['verified'],
        solve_seconds=elapsed,process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        search_stats=result['search_stats'],csv_sha256=result['csv_sha256'],
        entry_sha256=hashlib.sha256(args.entry.read_bytes()).hexdigest(),
        scope='whole solve and independent model verification, fixed actual entry; code preloaded, no route or world cache')
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(record,indent=2))
    print(json.dumps({key:record[key] for key in ('baseline','status','verified','solve_seconds','process_peak_rss_bytes')}))

if __name__=='__main__':main()
