"""Fixed collision corpus: native kernels only, excludes code loading and solving."""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
from nohit.engine import native_backend as backend
from nohit.engine.source_oracle import scalar_module


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--states',type=int,default=100000);parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args();rng=np.random.default_rng(901)
    # Offscreen repeat bodies remain genuine hazards, as in BlueBone. The
    # oracle must also handle mixed occupied cells and moving blue contacts.
    white=np.empty((4096,4));white[:,:2]=rng.uniform(-50000,-1000,(4096,2));white[:,2:]=white[:,:2]+rng.uniform(5,40,(4096,2))
    white[-32:,:2]=rng.uniform(0,600,(32,2));white[-32:,2:]=white[-32:,:2]+rng.uniform(4,25,(32,2))
    blue=np.array([[200,200,220,270],[400,100,430,400]],np.float64);quads=np.array([[60,60,180,80,130,100,40,80]],np.float64)
    states=np.zeros((args.states,11));states[:,:2]=rng.uniform(0,640,(args.states,2));states[:,1]*=.75;states[:,2]=rng.integers(0,2,args.states)
    original=backend._SOURCE;results=[];expected=None
    try:
        for source in (Path(__file__).parent/'reference/round5_native_frontier.cpp',original):
            backend._SOURCE=source;backend.load_backend.cache_clear();backend.load_backend()
            backend.collision_batch(states[:1000],white,blue,quads)
            for repeat in range(args.repeats):
                st=time.perf_counter();hits=backend.collision_batch(states,white,blue,quads);elapsed=time.perf_counter()-st
                if expected is None:expected=hits.copy()
                assert np.array_equal(hits,expected)
                results.append(dict(source=str(source),repeat=repeat,seconds=elapsed,states=len(states),white_rectangles=len(white),
                    collision_sha256=hashlib.sha256(hits.tobytes()).hexdigest()))
        oracle=scalar_module('cspace');payload=(np.empty((1,2,0,0),np.uint8),quads[None],0.,0.,1.)
        for index in np.linspace(0,len(states)-1,128,dtype=int):
            assert bool(expected[index])==oracle.collision_query(white[None],blue[None],0,states[index],0.,payload)
    finally:backend._SOURCE=original;backend.load_backend.cache_clear()
    record=dict(scope=__doc__,records=results,scalar_samples_checked=128,
        baseline_median_seconds=float(np.median([v['seconds'] for v in results[:args.repeats]])),
        optimized_median_seconds=float(np.median([v['seconds'] for v in results[args.repeats:]])))
    record['speedup']=record['baseline_median_seconds']/record['optimized_median_seconds']
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(record,indent=2));print(json.dumps(record))

if __name__=='__main__':main()
