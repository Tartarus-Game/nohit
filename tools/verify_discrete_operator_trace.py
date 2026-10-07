"""Compare observed jcw transitions with the pure operator, isolating the baker.

This is linear diagnostic replay, never candidate checkpoint search. A passing
motion comparison says nothing about whether the recorded inputs were no-hit.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from nohit.engine.discrete_operator import initial_state, step_mask_into


def bounds(row):
    b=row['arena'][0]['bbox']
    return [b[k] for k in ('left','top','right','bottom')]


def expected(row):
    return [row[k] for k in ('x','y','dx','dy')]+[
        row['keymask'],row['heartVars'][1],row['mode'],
        round(row['angle']/(math.pi/2)),row['maxFall'],row['heartVars'][2],0.]


def make_fixture(data, source):
    before=data['initial']; samples=[]
    event_map={}
    for event in data['events']:
        event_map.setdefault(event['tick'],[]).append(event)
    for row in data['replay']['micro_rows']:
        events=event_map.get(row['tick']-1,[])
        # EndAttack deliberately disables movement and destroys attack objects;
        # the attack operator's domain ends at that native terminal event.
        if row['mode'] not in (0,1) or any(e['fn']=='endattack' for e in events): break
        old=bounds(before);mid=old.copy()
        for e in events:
            if e['fn']=='combatzoneresizeinstant':mid=list(map(float,e['args'][:4]))
        env=[*bounds(row),row['mode'],round(row['angle']/(math.pi/2)),
             int(any(e['fn']=='sansslam' for e in events)),row['dt'],row['maxFall'],
             int(any(e['fn']=='heartteleport' for e in events)),0.,0.,row['heartVars'][2],
             int(any(e['fn']=='heartmode' for e in events)),*old,*mid]
        for e in events:
            # HeartTeleport applies Construct's int() to both arguments. This
            # matters for Final's GetHeartPos -> HeartTeleport(40, HeartY).
            if e['fn']=='heartteleport':env[10:12]=[float(math.trunc(float(v))) for v in e['args'][:2]]
        platforms=[]
        previous_platforms={p['uid']:p for p in before['platforms']}
        for p in row['platforms']:
            previous=previous_platforms.get(p['uid'])
            platforms.append([p['bbox']['left'],p['bbox']['top'],p['w'],p['h'],p['dx'],p['dy'],1.,
                              float(previous is not None),previous['dy'] if previous else p['dy']])
        present={p['uid'] for p in row['platforms']}
        for uid,p in previous_platforms.items():
            if uid not in present:
                # BlackScreen(1) removes platforms in Timeline, after their
                # movement and the heart's behavior have already run.
                platforms.append([p['bbox']['left']+p['dx']*row['dt'],
                                  p['bbox']['top']+p['dy']*row['dt'],
                                  p['w'],p['h'],p['dx'],p['dy'],0.,1.,p['dy']])
        samples.append([row['tick'],row['keymask'],env,platforms,expected(row)])
        before=row
    return {'source_trace':str(source),'source_trace_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'description':'Observed original linear gameplay; checks player transitions against observed environment, not no-hit success.',
            'platform_width':9,'initial':expected(data['initial']),'samples':samples}


def verify(fixture):
    s=np.array(fixture['initial'],dtype=float);out=np.empty(11)
    maximum=0.
    for i,(tick,mask,env,platforms,wanted) in enumerate(fixture['samples']):
        ps=np.asarray(platforms,dtype=float).reshape((-1,fixture.get('platform_width',7)))
        step_mask_into(s,mask,np.array(env,dtype=float),ps,out)
        error=np.abs(out-np.asarray(wanted));maximum=max(maximum,float(error.max()))
        if error.max()!=0:
            return {'matched':False,'checked':i+1,'tick':tick,'max_error':maximum,
                    'error':error.tolist(),'actual':wanted,'predicted':out.tolist()}
        s,out=out,s
    return {'matched':True,'checked':len(fixture['samples']),'max_error':maximum}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('trace',type=Path);parser.add_argument('--fixture',type=Path)
    args=parser.parse_args();fixture=make_fixture(json.loads(args.trace.read_text()),args.trace)
    result=verify(fixture);print(json.dumps(result))
    if args.fixture and result['matched']:
        args.fixture.parent.mkdir(parents=True,exist_ok=True)
        args.fixture.write_text(json.dumps(fixture,separators=(',',':'))+'\n')
    return 0 if result['matched'] else 1


if __name__=='__main__':raise SystemExit(main())
