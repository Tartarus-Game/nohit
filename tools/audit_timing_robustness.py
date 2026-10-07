"""Audit a saved fresh-math candidate against every allowed timing shift."""
import argparse
import json
import time
from pathlib import Path
from nohit.engine.compact_wave import compile_wave,ROOT
from nohit.engine.timing_robustness import certify_timing_radius

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('candidate',type=Path)
parser.add_argument('--max-states',type=int,default=100000)
parser.add_argument('--out',type=Path)
args=parser.parse_args()
if args.max_states<1:
    parser.error('--max-states must be positive')
candidate=json.loads(args.candidate.read_text(encoding='utf-8'))
result=candidate['result']
wave=compile_wave(ROOT/'c2-sans-fight'/candidate['wave'])
initial=result['computation']['initial']
layers=(len(wave.env_schedule)-1+3)//4
actions=result['actions'][:layers]
records=[]
for radius in (0,1,2):
    started=time.perf_counter()
    verdict=certify_timing_radius(wave,initial,actions,radius,args.max_states)
    record=dict(wave=candidate['wave'],candidate=candidate['candidate_id'],
        elapsed_ms=(time.perf_counter()-started)*1000,**verdict)
    records.append(record)
    print(json.dumps(record),flush=True)
if args.out:
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(dict(records=records,max_states=args.max_states,
        original_game_acceptance=False,optimality_proven=False),indent=2),encoding='utf-8')
