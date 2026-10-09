"""Compare full sorting with partial selection on one identical fixed world."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from nohit.engine import native_backend as backend
from nohit.engine.control_quotient import control_classes
from nohit.engine.initial_target_history import bind_initial_target_history
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.source_oracle import scalar_module


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv',type=Path);parser.add_argument('--entry',type=Path,required=True)
    parser.add_argument('--width',type=int,default=8192);parser.add_argument('--repeats',type=int,default=2)
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    entry=json.loads(args.entry.read_text())
    template=ParametricEnvironment(args.csv,initial_environment=entry.get('initial_environment'),
        initial_arena=entry.get('initial_arena'),dt_schedule=entry.get('dt_schedule'),max_ticks=40000)
    plan=json.loads(args.entry.with_name(args.entry.name.replace('-entry.json','-plan.json')).read_text())
    binding=template.bind_history_once(plan.get('target_history',()))
    assert binding.complete
    wave=binding.wave;env=wave.env_schedule
    state=scalar_module('discrete_operator').initial_state(entry['initial'],env[0])
    table=np.zeros((len(env)-1,16),np.int64);counts=np.empty(len(table),np.int64)
    for tick in range(len(table)):
        following=env[tick+2] if tick+2<len(env) else None
        masks=[group[0] for group in control_classes(env[tick+1:tick+2],tuple(range(16)),next_environment=following)]
        counts[tick]=len(masks);table[tick,:len(masks)]=masks
    production=backend._SOURCE;reference=Path(__file__).parent/'reference/round4_native_frontier.cpp'
    records=[];fingerprint=None
    try:
        for source in (reference,production):
            backend._SOURCE=source;backend.load_backend.cache_clear();backend.load_backend()
            for repeat in range(args.repeats):
                winner,actions,trace,attempts,metadata=backend.search(state,wave,table,counts,[args.width],[42],1,60)
                assert winner>=0,attempts
                word_hash=hashlib.sha256(actions.tobytes()+trace.tobytes()).hexdigest()
                if fingerprint is None:fingerprint=word_hash
                assert word_hash==fingerprint,'selection changed the deterministic witness'
                record=dict(source=str(source),repeat=repeat,seconds=metadata['search_seconds'],
                    workspace_bytes=sum(row['workspace_bytes'] for row in attempts),
                    expanded=sum(row['expanded'] for row in attempts),witness_sha256=word_hash)
                records.append(record);print(json.dumps(record),flush=True)
                args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(records,indent=2))
    finally:backend._SOURCE=production;backend.load_backend.cache_clear()

if __name__=='__main__':main()
