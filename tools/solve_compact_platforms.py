"""Fresh pure-kernel solve; calibration files contain clock, never actions."""
import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from nohit.engine.compact_wave import compile_wave, prepare_collision_native
from nohit.engine.compact_lattice import search, search_depth_first
from nohit.engine.compact_solver import solve_platforms4hard


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--operator',choices=['breadth','depth','frs_dp'],default='frs_dp')
    parser.add_argument('--states',type=int,default=100000)
    parser.add_argument('--nodes',type=int,default=2000000)
    parser.add_argument('--expansions',type=int,default=10000000)
    parser.add_argument('--dead',type=int,default=4000000)
    parser.add_argument('--margin-x',type=float,default=1.0)
    parser.add_argument('--margin-y',type=float,default=2.0)
    parser.add_argument('--anticipation',type=int,default=12)
    parser.add_argument('--beam',type=int,default=0,help='0 retains all distinct states; positive caps may lose routes')
    parser.add_argument('--approximate-folding',action='store_true',help='Explicitly enable lossy macro bins for candidate generation')
    parser.add_argument('--output',default='tools/operator-results/compact-platforms4hard.json')
    args=parser.parse_args()
    if min(args.states,args.nodes,args.expansions,args.dead)<1:
        parser.error('resource limits must be positive')
    if args.operator in ('depth', 'frs_dp'):
        result=solve_platforms4hard(max_expansions=args.expansions,max_dead=args.dead,
            margin_x=args.margin_x,margin_y=args.margin_y,anticipation=args.anticipation,
            max_states=args.states,max_beam=args.beam,exact=not args.approximate_folding)
        Path(args.output).write_text(json.dumps(result,indent=2))
        print(json.dumps({k:v for k,v in result.items() if k not in ('actions','trajectory','visits')},indent=2))
        return
    start=time.perf_counter()
    schedule,geometry,initial=compile_wave(ROOT/'c2-sans-fight/sans_platforms4hard.csv')
    compiled=time.perf_counter()
    mask=prepare_collision_native(geometry,margin_x=args.margin_x,margin_y=args.margin_y)
    prepared=time.perf_counter()
    route=[]
    if args.operator=='breadth':
        status,frame,history,parents,actions,end=search(mask,schedule,initial,args.states,args.nodes)
        node_count=len(parents)
        while end>0:
            route.append(actions[end].tolist())
            end=int(parents[end])
        route.reverse()
    else:
        status,frame,node_count,history,actions=search_depth_first(mask,schedule,initial,args.expansions,args.dead)
        route=actions.tolist()
    searched=time.perf_counter()
    result={'status':['candidate_found','exhausted_in_declared_model','resource_limit'][status],
        'kernel_id':'compact-float64-platforms-v1','wave':'sans_platforms4hard.csv','seed':42,
        'collision_model':'conservative_bbox_fractional_cell_cover','no_beam_pruning':True,'enumeration_exhausted':status==1,
        'frame':int(frame),'state_counts_or_visits':history.tolist(),'nodes':int(node_count),'operator':args.operator,
        'actions':route,'original_replay_passed':False,'realtime_passed_three':False,
        'route_cache_hit':False,'environment_cache_hit':False,
        'timing_ms':{'csv_compile':(compiled-start)*1000,'collision_prepare':(prepared-compiled)*1000,
                     'search_including_kernel_load_or_compile':(searched-prepared)*1000,
                     'first_route_wall':(searched-start)*1000},
        'python':platform.python_version(),'machine':platform.machine(),
        'kernel_sha256':hashlib.sha256((ROOT/'nohit/engine/compact_lattice.py').read_bytes()).hexdigest()}
    Path(args.output).write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k not in ('actions','state_counts_or_visits')},indent=2))


if __name__=='__main__':
    main()
