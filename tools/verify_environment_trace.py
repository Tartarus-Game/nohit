"""Compare a diagnostic native replay with the mathematical environment compiler.

Does not execute or mutate the game. Native snapshots must include hazard quads,
damage, typeSid and the actual initial arena (oracle_suite diagnostics).
"""
import argparse
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nohit.engine.compact_wave import compile_wave


def compare(path,attack='sans_intro',tolerance=2e-7,recorded_clock=False):
    data=json.loads(Path(path).read_text())
    initial=data['initial'];rows=data['replay']['micro_rows']
    arena=initial['arena'][0]['bbox']
    env=[arena[k] for k in ('left','top','right','bottom')]+[initial['mode']]
    dt=None
    if recorded_clock:
        dt=np.full(max(row['tick'] for row in rows)-initial['tick']+1,initial['dt'])
        for row in rows:dt[row['tick']-initial['tick']]=row['dt']
    wave=compile_wave(Path(__file__).resolve().parents[1]/'c2-sans-fight'/f'{attack}.csv',initial_environment=env,dt_schedule=dt)
    project=ET.parse(Path(__file__).resolve().parents[1]/'.capx_extract/Bad Time Simulator (Sans Fight).caproj').getroot()
    sids={e.get('name'):int(e.get('sid')) for e in project.iter('object-type')}
    rectangular={sids[n] for n in ('BoneV','BoneH','BoneStabV','BoneStabH')}
    errors=[];max_error=0.;compared=0;beam_ticks=0
    def check(tick,kind,a,b):
        nonlocal max_error
        if len(a)!=len(b):
            if len(errors)<20: errors.append(dict(tick=tick,kind=kind,native_count=len(a),model_count=len(b)))
            return
        if not len(a):return
        a=a[np.lexsort(a.T[::-1])];b=b[np.lexsort(b.T[::-1])]
        error=float(np.abs(a-b).max());max_error=max(error,max_error)
        if error>tolerance and len(errors)<20:errors.append(dict(tick=tick,kind=kind,max_error=error))
    for row in rows:
        if row['HP']<=0:
            break  # Native death cleanup destroys hazards; not an attack transition.
        tick=row['tick']-initial['tick']
        if tick>=len(wave.env_schedule):break
        for color,model in ((0,wave.geometry_white),(1,wave.geometry_blue)):
            a=np.asarray([[h['bbox'][k] for k in ('left','top','right','bottom')]
                for h in row['hazards'] if h['typeSid'] in rectangular and h['damage']>0 and h['color']==color]).reshape(-1,4)
            b=model[tick];b=b[np.isfinite(b[:,0])]
            check(tick,'rectangle-'+str(color),a,b)
        a=np.asarray([h['quad'] for h in row['hazards']
            if h['typeSid']==sids['GasterBlastHit'] and h['damage']>0]).reshape(-1,4,2)
        b=wave.geometry_polygons[tick].reshape(-1,4,2);b=b[np.isfinite(b[:,0,0])]
        if len(a):beam_ticks+=1
        # Winding/start vertex are representational, not geometric differences.
        a=np.asarray([q[np.lexsort(q.T[::-1])].ravel() for q in a]).reshape(-1,8)
        b=np.asarray([q[np.lexsort(q.T[::-1])].ravel() for q in b]).reshape(-1,8)
        check(tick,'beam',a,b)
        actual=np.array([row['arena'][0]['bbox'][k] for k in ('left','top','right','bottom')])
        check(tick,'arena',actual.reshape(1,4),wave.env_schedule[tick,:4].reshape(1,4))
        compared+=1
    return dict(trace=str(path),attack=attack,compared_ticks=compared,
        native_beam_ticks=beam_ticks,max_coordinate_error=max_error,tolerance=tolerance,
        recorded_clock=recorded_clock,passed=not errors,first_errors=errors)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('trace');parser.add_argument('--attack',default='sans_intro')
    parser.add_argument('--tolerance',type=float,default=2e-7)
    parser.add_argument('--recorded-clock',action='store_true');args=parser.parse_args()
    result=compare(args.trace,args.attack,args.tolerance,args.recorded_clock)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 1)
