"""Fresh pure-math solve. Initial state must come from the current original attack."""
import argparse
import json
from pathlib import Path
from nohit.engine.canonical_solver import solve_attack

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('attack')
parser.add_argument('--initial',type=float,nargs=5)
parser.add_argument('--max-nodes',type=int,default=500000,help='retained graph budget; no beam pruning')
parser.add_argument('--lookahead',type=int,default=60,help='ordering hint only; does not discard states')
parser.add_argument('--margin',type=float,default=2)
parser.add_argument('--out',type=Path,required=True)
args=parser.parse_args()
result=solve_attack(Path('c2-sans-fight')/(args.attack.removesuffix('.csv')+'.csv'),
    args.initial,max_nodes=args.max_nodes,lookahead=args.lookahead,margin=args.margin)
args.out.parent.mkdir(parents=True,exist_ok=True)
args.out.write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ('actions','trajectory')},indent=2))
raise SystemExit(0 if result['status']=='candidate_found' else 2)
