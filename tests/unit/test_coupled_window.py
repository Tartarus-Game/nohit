"""Batch commitment must use the proposed controls' own source observations."""
import pickle
import time
import numpy as np
from nohit.engine import resumable_wave as world
from nohit.engine.native_dynamic import _segmented_coupled,_world,_validate_coupled_window

INITIAL=np.array([320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.])


def test_coupled_window_keeps_exact_midpoint_state_and_actual_targets(tmp_path):
    path=tmp_path/'target.csv'
    path.write_text('0,HeartMode,0\n'+''.join('0.1,GetHeartPos,x,y\n0,BoneV,$x,80,10,0,0\n' for _ in range(20))+'0.2,EndAttack\n')
    settings=dict(dt_schedule=[1/60]*300,max_ticks=300)
    full=_world(path,INITIAL,settings,[2]*100,False,False,None,time.perf_counter()+5)
    assert full is not None and full[4]
    state=world._enable_bone_arrays(world.initialize(path,**settings),native=True)
    while True:
        tick=state.data['tick']
        result=world._advance_with_dialogue_input_owned(state,confirm=tick%2==0 if tick else False,cancel=False,
            **(dict(previous_confirm=False,previous_cancel=False) if tick==0 else {}))
        if isinstance(result,world.NeedTarget):break
        state=result.state
    start=result.state.data['tick']-1;before=pickle.dumps(result.state)
    checked=_validate_coupled_window(result,full[2][start],[2]*100,start,0,False)
    assert checked is not None and pickle.dumps(result.state)==before
    midpoint,trace,frames,middle=checked
    assert trace.tobytes()==full[2][start+1:101].tobytes()
    assert midpoint.data['tick']==middle+1 and frames[-1].tick==middle
    actual=tuple(row for frame in frames for row in frame.target_history)
    assert actual==tuple(row for row in full[1].history if start<row[0]<=middle)
    assert len(set(row[2] for row in actual))>1


def test_segmented_solver_commits_validated_observations_and_certifies_whole_source(tmp_path):
    path=tmp_path/'segment.csv'
    path.write_text('0,HeartMode,0\n'+''.join('0.1,GetHeartPos,x,y\n' for _ in range(20))+'0.2,EndAttack\n')
    settings=dict(dt_schedule=[1/60]*300,max_ticks=300)
    result=_segmented_coupled(path,INITIAL,settings,32,1,16,42,False,False,None,
        time.perf_counter()+5,_chunk_ticks=12,_preview_ticks=120)
    assert result is not None and result.verified
    assert sum(part.get('coupled_validated_ticks',0) for part in result.stats['segments'])>0
    actual=_world(path,INITIAL,settings,result.actions,False,False,None,time.perf_counter()+5)
    assert actual[4] and actual[2].tobytes()==result.trajectory.tobytes()
    assert actual[1].history==result.target_history and actual[3]==result.confirm_sequence
