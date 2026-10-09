"""Fresh process requests: wall time, CPU use and RSS with fixed native entry."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,os,resource,subprocess,sys,time
from pathlib import Path


def install_round6_reference():
    from nohit.engine import native_backend, resumable_wave
    folder=Path(__file__).parent/'reference'
    native_backend._SOURCE=folder/'round6_native_frontier.cpp'
    native_backend.load_backend.cache_clear()
    source=(folder/'round6_resumable_wave.py').read_text()
    namespace=dict(resumable_wave.__dict__)
    exec(source[source.index('class _BoneArrays:'):source.index('def _enable_bone_arrays')],namespace)
    resumable_wave._BoneArrays=namespace['_BoneArrays']
    def enable(state,*,native=False):
        if not isinstance(state.data['active_bones'],resumable_wave._BoneArrays):
            state.data['active_bones']=resumable_wave._BoneArrays(state.data['active_bones'])
        return state
    resumable_wave._enable_bone_arrays=enable
    for name in ('native_candidate','native_dynamic'):
        spec=importlib.util.spec_from_file_location('nohit.engine.'+name,folder/('round6_'+name+'.py'))
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv',type=Path);parser.add_argument('--entry',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--workers',type=int,default=8)
    parser.add_argument('--width',type=int,default=8192);parser.add_argument('--seconds',type=float,default=45.)
    parser.add_argument('--repeats',type=int,default=3);parser.add_argument('--baseline',action='store_true')
    parser.add_argument('--opt-level',choices=['2','3']);parser.add_argument('--healing',action='store_true');parser.add_argument('--child',action='store_true')
    args=parser.parse_args()
    if args.child:
        from nohit import _configure_solver_process
        _configure_solver_process()
        import numpy as np
        if args.baseline:install_round6_reference()
        if args.opt_level:
            from nohit.engine import native_backend
            native_backend._FLAGS=tuple("-O"+args.opt_level if flag in ("-O2","-O3") else flag for flag in native_backend._FLAGS)
        from nohit.engine.native_backend import load_backend
        from nohit.engine.csv_solver import solve_csv
        _,code=load_backend()
        entry=json.loads(args.entry.read_text());began=time.perf_counter();cpu=time.process_time()
        r=solve_csv(args.csv,entry['initial'],initial_environment=entry['initial_environment'],
            initial_arena=entry.get('initial_arena'),dt_schedule=entry['dt_schedule'],max_ticks=40000,
            initial_confirm=entry.get('initial_confirm',False),previous_confirm=entry.get('previous_confirm',False),
            initial_target_history=entry.get('initial_target_history'),search_strategy='native',workers=args.workers,
            width=args.width,memory_mb=256,seconds=args.seconds,allow_scripted_healing=args.healing)
        elapsed=time.perf_counter()-began;cpu=time.process_time()-cpu
        fingerprint=hashlib.sha256(np.asarray(r['actions'],dtype='<i8').tobytes()+np.asarray(r['trajectory'],dtype='<f8').tobytes()).hexdigest()
        print(json.dumps(dict(status=r['status'],verified=r.get('verified'),solve_seconds=elapsed,
            solve_cpu_seconds=cpu,effective_solve_cores=cpu/elapsed,search_stats=r['search_stats'],
            source_sha256=code['source_sha256'],compiler_flags=code['compiler_flags'],code_was_compiled=code['compiled'],
            peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,fingerprint=fingerprint,
            csv_sha256=r['csv_sha256'],entry_sha256=hashlib.sha256(args.entry.read_bytes()).hexdigest(),
            numba_imported='numba' in sys.modules,route_cache=False,environment_cache=False)))
        return
    command=[sys.executable,'-m','tools.benchmark_cpu_request',str(args.csv),'--entry',str(args.entry),
        '--out',str(args.out),'--workers',str(args.workers),'--width',str(args.width),'--seconds',str(args.seconds),'--child']
    if args.opt_level:command += ["--opt-level",args.opt_level]
    if args.baseline:command+=['--baseline']
    if args.healing:command+=['--healing']
    records=[]
    for repeat in range(args.repeats):
        began=time.perf_counter();result=subprocess.run(command,check=True,capture_output=True,text=True)
        external=time.perf_counter()-began;r=json.loads(result.stdout)
        r.update(repeat=repeat,external_wall_seconds=external,workers=args.workers,baseline=args.baseline)
        records.append(r)
        print(json.dumps({k:r[k] for k in ('repeat','status','solve_seconds','solve_cpu_seconds','effective_solve_cores','peak_rss_bytes')}),flush=True)
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(records,indent=2)+'\n')

if __name__=='__main__':main()
