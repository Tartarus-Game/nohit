"""Fresh full-state operator/C-space/Boolean DAG-DP timing, never game acceptance."""
import argparse
import json
from pathlib import Path
from nohit.engine.canonical_solver import solve_attack,warm_kernel

parser=argparse.ArgumentParser()
parser.add_argument('waves',nargs='*',default=['sans_bonegap1','sans_bonegap1fast','sans_bonegap2','sans_boneslideh','sans_boneslidev','sans_bluebone'])
parser.add_argument('--nodes',type=int,default=150000)
parser.add_argument('--clock-start-ms',type=float)
parser.add_argument('--out',type=Path,default=Path('tools/operator-results/operator-dp-benchmark-20261006.json'))
args=parser.parse_args()
records=[]
warm=warm_kernel()
print(json.dumps({'warm_kernel_ms':warm}),flush=True)
for name in args.waves:
    initial=[320.,304. if name=='sans_boneslidev' else 377.96875,0.,0.,0.]
    result=solve_attack(Path('c2-sans-fight')/(name+'.csv'),initial,max_nodes=args.nodes,max_expansions=args.nodes,clock_start_ms=args.clock_start_ms)
    records.append({k:v for k,v in result.items() if k not in ('actions','trajectory')})
    print(json.dumps(dict(wave=name,status=result['status'],expansions=result.get('expansions'),timing_ms=result.get('timing_ms'))),flush=True)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(dict(original_game_acceptance=False,initial_state_origin='supplied solver fixture; observed normal-floor value for BoneGap1/2',warm_kernel_ms=warm,records=records),indent=2))
