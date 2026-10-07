"""Cold/load and warm calls of the single core; not original-game acceptance."""
import argparse
import time
import json
from pathlib import Path
import numpy as np
from nohit.engine.compact_wave import compile_wave,ROOT
from nohit.engine.adaptive_dag import search
from nohit.engine.canonical_solver import solve_attack,warm_kernel,ranking_weights

p=argparse.ArgumentParser()
p.add_argument('waves',nargs='*',default=['sans_bonegap1','sans_bonegap1fast','sans_bonegap2','sans_boneslideh','sans_boneslidev','sans_bluebone'])
p.add_argument('--lookahead',type=int,default=60)
p.add_argument('--nodes',type=int,default=300000)
p.add_argument('--margin',type=float,default=4.)
p.add_argument('--weights',type=json.loads,help='JSON object of soft ranking weights')
p.add_argument('--out',type=Path)
a=p.parse_args()
weights=ranking_weights(a.weights)
records=[]
kernel_load_ms=warm_kernel()
print(json.dumps(dict(kernel_load_ms=kernel_load_ms,route_cache=False)),flush=True)
for name in a.waves:
    t=time.perf_counter();w=compile_wave(ROOT/'c2-sans-fight'/f'{name}.csv');bake_ms=(time.perf_counter()-t)*1000
    initial=np.array([320.,304. if w.env_schedule[0,4]==0 else 377.81875,0.,0.,0.])
    args=(w.geometry_white,w.geometry_blue,w.env_schedule,w.platform_table,initial)
    for label,fn,kw in [('deferred-dag',search,dict(max_nodes=a.nodes,max_expansions=5000000,
            lookahead=a.lookahead,margin=a.margin,initial_capacity=4096,
            weights=np.array(list(weights.values()),dtype=np.float64)))]:
        for run in range(2):
            t=time.perf_counter();s,f,expanded,visits,actions=fn(*args,**kw);elapsed=(time.perf_counter()-t)*1000
            record=dict(wave=name,algorithm=label,run=run,bake_ms=round(bake_ms,3),ms=round(elapsed,3),
                status=int(s),frame=int(f),expanded=int(expanded),generated=int(visits.sum()),peak_layer=int(visits.max()))
            records.append(record)
            print(json.dumps(record,ensure_ascii=False),flush=True)
    result=solve_attack(ROOT/'c2-sans-fight'/f'{name}.csv',initial,lookahead=a.lookahead,max_nodes=a.nodes,margin=a.margin,weights=weights)
    record=dict(wave=name,algorithm='full_fresh_solve',status=result['status'],timing_ms=result['timing_ms'],
        kernel_sha256=result['kernel_sha256'],route_cache_hit=result['route_cache_hit'],environment_cache_hit=result['environment_cache_hit'])
    records.append(record)
    print(json.dumps(record),flush=True)
if a.out:
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(dict(seed=42,preferred_margin=a.margin,margin_is_pruning=False,ranking_weights=weights,lookahead=a.lookahead,max_nodes=a.nodes,kernel_load_ms=kernel_load_ms,
        original_game_acceptance=False,process_startup_excluded=True,records=records),indent=2),encoding='utf-8')
