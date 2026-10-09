"""Pathological integer-lattice frontier, same exact source world and witness.

This synthetic whole native search benchmark excludes compilation and source
world preparation. It is not a speedup claim for every original attack.
"""
import argparse,hashlib,json,tempfile,time
from pathlib import Path
import numpy as np
from nohit.engine import native_backend as backend
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.source_oracle import scalar_module


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--width',type=int,default=1024);parser.add_argument('--repeats',type=int,default=2)
    args=parser.parse_args();original=backend._SOURCE;records=[];expected=None
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'integer-lattice.csv';path.write_text('0,HeartMode,0\n1,EndAttack\n')
        wave=ParametricEnvironment(path,dt_schedule=[1/30]*100,max_ticks=100).bind().wave
        initial=np.array([320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.])
        table=np.tile(np.arange(16,dtype=np.int64),(len(wave.env_schedule)-1,1));counts=np.full(len(table),16,np.int64)
        try:
            for source in (Path(__file__).parent/'reference/round6_native_frontier.cpp',original):
                backend._SOURCE=source;backend.load_backend.cache_clear();backend.load_backend()
                for repeat in range(args.repeats):
                    began=time.perf_counter();winner,actions,trace,stats,code=backend.search(initial,wave,table,counts,
                        [args.width],[42],1,60,terminal_target=[320.,300.]);elapsed=time.perf_counter()-began
                    assert winner==0
                    witness=actions.tobytes()+trace.tobytes()
                    if expected is None:expected=witness
                    assert expected==witness,'hash layout changed exact retained witness'
                    player=scalar_module('discrete_operator');state=initial.copy()
                    for tick,mask in enumerate(actions,1):
                        player.step_mask_into(state,int(mask),wave.env_schedule[tick],wave.platform_table[tick],state)
                        assert state.tobytes()==trace[tick].tobytes()
                    records.append(dict(source_sha256=code['source_sha256'],reference=source!=original,repeat=repeat,
                        seconds=elapsed,states_expanded=stats[0]['expanded'],unique=stats[0]['unique'],
                        hash_rebuilds=code.get('state_hash_rebuilds'),witness_sha256=hashlib.sha256(witness).hexdigest()))
                    print(json.dumps(records[-1]),flush=True)
        finally:backend._SOURCE=original;backend.load_backend.cache_clear()
    old=float(np.median([r['seconds'] for r in records if r['reference']]))
    new=float(np.median([r['seconds'] for r in records if not r['reference']]))
    report=dict(scope=__doc__,width=args.width,ticks=len(table),records=records,
        baseline_median_seconds=old,optimized_median_seconds=new,speedup=old/new,exact_witness_equal=True)
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
