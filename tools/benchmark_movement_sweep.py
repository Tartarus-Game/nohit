"""Exact native player operator, stress sweep and wall fallback; not a wave solve."""
import argparse,hashlib,json,tempfile,time
from pathlib import Path
import numpy as np
from nohit.engine import native_backend as backend
from nohit.engine.source_oracle import scalar_module


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--states',type=int,default=100000);p.add_argument('--repeats',type=int,default=3);a=p.parse_args()
    rng=np.random.default_rng(888)
    states=np.tile(np.array([320.,304.,750.,750.,0.,1.,1.,1.,750.,1.,0.]),(a.states,1))
    states[:,:2]+=rng.uniform(-20.,20.,(a.states,2));states[:a.states//5,1]=378.
    masks=rng.integers(0,32,a.states,dtype=np.int64)
    env=np.array([33.,251.,608.,391.,1.,1.,0.,1/30,750.,0.,320.,304.,1.,0.,33.,251.,608.,391.,33.,251.,608.,391.])
    platforms=np.empty((0,9));original=backend._SOURCE;expected=None;records=[]
    try:
        for reference,source in [(True,Path(__file__).parent/'reference/round7_native_frontier.cpp'),(False,original)]:
            backend._SOURCE=source;backend.load_backend.cache_clear();_,code=backend.load_backend()
            for repeat in range(a.repeats):
                began=time.perf_counter();output=backend.step_batch(states,masks,env,platforms);elapsed=time.perf_counter()-began
                if expected is None:expected=output.copy()
                assert output.tobytes()==expected.tobytes()
                record=dict(reference=reference,repeat=repeat,seconds=elapsed,source_sha256=code['source_sha256'],output_sha256=hashlib.sha256(output.tobytes()).hexdigest())
                records.append(record);print(json.dumps(record),flush=True)
        player=scalar_module('discrete_operator')
        for i in rng.choice(a.states,size=min(512,a.states),replace=False):
            state=states[i].copy();player.step_mask_into(state,int(masks[i]),env,platforms,state)
            assert state.tobytes()==expected[i].tobytes()
    finally:backend._SOURCE=original;backend.load_backend.cache_clear()
    old=float(np.median([r['seconds'] for r in records if r['reference']]));new=float(np.median([r['seconds'] for r in records if not r['reference']]))
    report=dict(scope=__doc__,states=a.states,wall_fallback_fraction=.2,reference_median_seconds=old,optimized_median_seconds=new,speedup=old/new,
        exact_all_outputs_equal=True,scalar_samples=min(512,a.states),records=records)
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
