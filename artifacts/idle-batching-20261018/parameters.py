import gzip,hashlib,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
OUT=ROOT/'build/one-second-20261018'
if len(sys.argv)>1:
    options=json.loads(sys.argv[1]);name=options.pop('name')
    from nohit import _configure_solver_process
    _configure_solver_process()
    from nohit.engine.csv_solver import solve_csv
    entry=json.loads((ROOT/'build/realhell-final-20261018/native-declared-1800000/sans_bonegap1-entry.json').read_text())
    from tools.benchmark_samples import implementations
    before=implementations()
    began=time.perf_counter()
    r=solve_csv(ROOT/'build/realhell-final-20261018/source.csv',entry['initial'],
        initial_environment=entry['initial_environment'],initial_arena=entry['initial_arena'],
        initial_confirm=entry['initial_confirm'],previous_confirm=entry['previous_confirm'],
        initial_target_history=entry['initial_target_history'],dt_schedule=entry['dt_schedule'],
        max_ticks=40000,seconds=15,memory_mb=1024,termination_policy='eof_hazards_drained',**options)
    elapsed=time.perf_counter()-began
    assert before==implementations(), "implementation changed during solve"
    (OUT/(name+'.json.gz')).write_bytes(gzip.compress(json.dumps(r).encode(),mtime=0))
    s=r.get('search_stats',{})
    print(json.dumps(dict(name=name,options=options,status=r['status'],verified=r['verified'],
        reached=r.get('reached_tick'),seconds=elapsed,search_seconds=s.get('search_seconds'),
        implementation_sha256=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),
        source_sha256=hashlib.sha256((ROOT/'build/realhell-final-20261018/source.csv').read_bytes()).hexdigest(),
        entry_sha256=hashlib.sha256((ROOT/'build/realhell-final-20261018/native-declared-1800000/sans_bonegap1-entry.json').read_bytes()).hexdigest(),
        verify_seconds=s.get('verification_seconds'),expanded=s.get('expanded_states'))),flush=True)
else:
    configs=[(1024,4,240,0),(1024,4,240,60),(1024,4,240,120),(1024,4,480,120),
             (128,1,240,60),(128,4,240,120)]
    rows=[]
    for width,workers,chunk,preview in configs:
        options=dict(name=f'w{width}-p{workers}-c{chunk}-v{preview}',width=width,workers=workers,
            observation_chunk_ticks=chunk,observation_preview_ticks=preview,observation_goal_style=16)
        child=subprocess.run([sys.executable,__file__,json.dumps(options)],cwd=ROOT,capture_output=True,text=True,timeout=60)
        print(child.stdout[-1000:]+child.stderr[-1500:],flush=True)
        if child.returncode:raise RuntimeError('child failed')
        rows.append(json.loads(child.stdout));(OUT/'parameters.json').write_text(json.dumps(rows,indent=2))
