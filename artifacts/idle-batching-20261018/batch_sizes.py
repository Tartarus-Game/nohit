import json,statistics,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from nohit.engine import resumable_wave as world
from nohit.engine.native_backend import load_backend
load_backend()
rows=[]
for inventory in (0,100,900):
    source=[['0','HeartMode','0']]+[['0','BoneV',str(i%20*30),str(i%7*60),'20',str(i%4),'100',str(i%2)] for i in range(inventory)]+[['100','EndAttack']]
    initial=world._enable_bone_arrays(world.initialize(source,dt_schedule=[1/60]*1000,max_ticks=1000),native=True)
    world._advance_with_dialogue_input_owned(initial,confirm=False,cancel=False,previous_confirm=False,previous_cancel=False)
    for n in (2,4,8,16,32,64):
        samples=[[],[]]
        for repeat in range(50):
            for batch in (0,1):
                state=initial.clone();began=time.perf_counter()
                if batch:
                    frames=world._advance_idle_world_owned(state,n)
                    assert len(frames)==n
                else:
                    for _ in range(n):world._advance_with_dialogue_input_owned(state,confirm=state.data['tick']%2==0,cancel=False)
                samples[batch].append(time.perf_counter()-began)
        row=dict(inventory=inventory,ticks=n,scalar_seconds=statistics.median(samples[0]),batch_seconds=statistics.median(samples[1]))
        row['speedup']=row['scalar_seconds']/row['batch_seconds'];rows.append(row);print(json.dumps(row),flush=True)
(ROOT/'build/one-second-20261018/batch-sizes.json').write_text(json.dumps(rows,indent=2))
