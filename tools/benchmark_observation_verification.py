"""Compare previous prefix replay with linear certification, identical source VM."""
import argparse
import json
from pathlib import Path
import tempfile
import time

from nohit.engine.native_dynamic import _world
from nohit.engine.source_verification import certify_observed
from tools.reference.previous_observation_certifier import certify_previous


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observations',type=int,default=800)
    parser.add_argument('--out',type=Path,default=Path('tools/optimization-results/round3-observation-scaling.json'))
    args=parser.parse_args();n=args.observations
    if not 1<=n<=2000:parser.error('observations must be in [1,2000]')
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'observed.csv'
        path.write_text('0,HeartMode,0\n'+('0.004166666666666667,GetHeartPos,x,y\n'*n)+'0,EndAttack\n')
        settings=dict(dt_schedule=[1/240]*(n+20),max_ticks=n+20,seed=42)
        initial=[320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.]
        _,_,trace,confirms,safe,word=_world(path,initial,settings,[],False,False,None,time.perf_counter()+30)
        assert safe
        start=time.perf_counter();old=certify_previous(path,initial,settings,word,trace,confirms,False,False,None,False)
        previous=time.perf_counter()-start;assert old is not None
        start=time.perf_counter();new=certify_observed(path,initial,settings,word,trace,None)
        optimized=time.perf_counter()-start
        assert new is not None and old[1]==new[1] and old[0].identity==new[0].identity
        report=dict(observations=n,ticks=len(trace),previous_seconds=previous,optimized_seconds=optimized,
            speedup=previous/optimized,scope='certification only; synthetic source; warm imports; same current source VM; no JIT or route cache',
            identical_history=True,identical_binding=True)
        args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2))
        print(json.dumps(report))


if __name__=='__main__':main()
