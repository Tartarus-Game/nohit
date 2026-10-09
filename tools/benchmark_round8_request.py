"""Fresh-process Round 7 C++ comparison and optional stage wall-time profile.

Profile sums wall time across concurrent probes; it is neither process CPU time
nor additive request latency. No route or world cache is used.
"""
import argparse,ctypes,hashlib,json,os,resource,subprocess,sys,tempfile,time
from pathlib import Path


def profiled_source(source):
    text=source.read_text()
    text=text.replace('using Clock=std::chrono::steady_clock;', '''using Clock=std::chrono::steady_clock;
static std::atomic<uint64_t> phase_ns[3];
extern "C" uint64_t nohit_profile_phase(int i){return phase_ns[i].load();}
static void phase_add(int i,Clock::time_point began){phase_ns[i].fetch_add(std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-began).count());}''')
    text=text.replace('edges.clear();std::fill(table.begin(),table.end(),-1);','auto phase_begin=Clock::now();edges.clear();std::fill(table.begin(),table.end(),-1);')
    text=text.replace('        edges.clear();\n        size_t active_capacity', '        auto phase_begin=Clock::now();edges.clear();\n        size_t active_capacity')
    text=text.replace('stats.expanded+=count;stats.unique+=edges.size();','stats.expanded+=count;stats.unique+=edges.size();phase_add(0,phase_begin);')
    text=text.replace('        order.resize(edges.size());\n        for(size_t i=0;i<order.size();i++)','        phase_begin=Clock::now();order.resize(edges.size());\n        for(size_t i=0;i<order.size();i++)')
    text=text.replace('        auto less=[&](int a,int b)', '        phase_add(1,phase_begin);phase_begin=Clock::now();\n        auto less=[&](int a,int b)')
    text=text.replace('        capture(tick,current,costs,count);\n    }','        capture(tick,current,costs,count);phase_add(2,phase_begin);\n    }')
    text=text.replace('        capture(tick,current,costs,count);account_history();\n    }', '        capture(tick,current,costs,count);account_history();phase_add(2,phase_begin);\n    }')
    return text


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('csv',type=Path);p.add_argument('--entry',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--source',type=Path);p.add_argument('--baseline',action='store_true');p.add_argument('--profile',action='store_true');p.add_argument('--healing',action='store_true')
    p.add_argument('--workers',type=int,default=8);p.add_argument('--width',type=int,default=8192);p.add_argument('--seconds',type=float,default=45)
    p.add_argument('--compare',action='store_true');p.add_argument('--empty-code-cache',action='store_true');p.add_argument('--repeats',type=int,default=3);p.add_argument('--child',action='store_true');a=p.parse_args()
    if a.child:
        from nohit import _configure_solver_process
        _configure_solver_process()
        import numpy as np
        from nohit.engine import native_backend as backend
        source=Path(__file__).parent/'reference/round7_native_frontier.cpp' if a.baseline else backend._SOURCE
        if a.source:source=a.source
        original_sha=hashlib.sha256(source.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory(prefix='nohit-profile-source-') as d:
            if a.profile:
                prof=Path(d)/'profile.cpp';prof.write_text(profiled_source(source));source=prof
            backend._SOURCE=source;backend.load_backend.cache_clear();library,code=backend.load_backend()
            from nohit.engine.csv_solver import solve_csv
            entry=json.loads(a.entry.read_text());began=time.perf_counter();cpu=time.process_time()
            r=solve_csv(a.csv,entry['initial'],initial_environment=entry['initial_environment'],initial_arena=entry.get('initial_arena'),
                initial_confirm=entry.get('initial_confirm',False),previous_confirm=entry.get('previous_confirm',False),
                initial_target_history=entry.get('initial_target_history'),dt_schedule=entry['dt_schedule'],max_ticks=40000,
                search_strategy='native',workers=a.workers,width=a.width,memory_mb=256,seconds=a.seconds,allow_scripted_healing=a.healing)
            elapsed=time.perf_counter()-began;cpu=time.process_time()-cpu
            phases=None
            if a.profile:
                library.nohit_profile_phase.argtypes=[ctypes.c_int];library.nohit_profile_phase.restype=ctypes.c_uint64
                phases=dict(zip(('expand_and_dedup','rank_and_preview','selection_and_copy'),[library.nohit_profile_phase(i)/1e9 for i in range(3)]))
            witness=np.asarray(r['actions'],dtype='<i8').tobytes()+np.asarray(r['trajectory'],dtype='<f8').tobytes()
            print(json.dumps(dict(status=r['status'],verified=r['verified'],solve_seconds=elapsed,solve_cpu_seconds=cpu,
                effective_solve_cores=cpu/elapsed,search_stats=r.get('search_stats'),source_sha256=original_sha,
                compiled_source_sha256=code['source_sha256'],compiler_flags=code['compiler_flags'],code_was_compiled=code['compiled'],profile=phases,
                peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,fingerprint=hashlib.sha256(witness).hexdigest(),
                csv_sha256=r['csv_sha256'],entry_sha256=hashlib.sha256(a.entry.read_bytes()).hexdigest(),
                baseline=a.baseline,numba_imported='numba' in sys.modules,route_cache=False,environment_cache=False)))
        return
    command=[sys.executable,'-m','tools.benchmark_round8_request',str(a.csv),'--entry',str(a.entry),'--out',str(a.out),
        '--workers',str(a.workers),'--width',str(a.width),'--seconds',str(a.seconds),'--child']
    if a.source:command+=['--source',str(a.source)]
    for flag in ('baseline','profile','healing'):
        if getattr(a,flag):command.append('--'+flag)
    records=[]
    for i in range(a.repeats):
        for baseline in ([True,False] if a.compare else [a.baseline]):
            invoke=[item for item in command if item!='--baseline']+(['--baseline'] if baseline else [])
            with tempfile.TemporaryDirectory(prefix='nohit-request-code-') as cache:
                environment=dict(os.environ)
                if a.empty_code_cache:environment['NOHIT_NATIVE_CACHE']=cache
                began=time.perf_counter();r=subprocess.run(invoke,capture_output=True,text=True,env=environment)
                if r.returncode:raise RuntimeError(r.stdout+'\n'+r.stderr)
                record=json.loads(r.stdout);record.update(repeat=i,external_wall_seconds=time.perf_counter()-began,workers=a.workers,width=a.width,empty_code_cache=a.empty_code_cache)
            records.append(record);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(records,indent=2)+'\n')
            print(json.dumps({k:record[k] for k in ('repeat','baseline','status','solve_seconds','external_wall_seconds','solve_cpu_seconds','peak_rss_bytes','profile')}),flush=True)

if __name__=='__main__':main()
