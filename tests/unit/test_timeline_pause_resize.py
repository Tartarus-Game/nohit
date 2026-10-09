"""Timeline pauses consume real world ticks until the native resize callback."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from nohit.engine.compact_wave import compile_wave
from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.resumable_wave import initialize,advance_one_tick,advance_with_dialogue_input


@pytest.mark.parametrize('backend',['reference','resumable'])
def test_native_bonestab3_prefix_waits_for_resize_without_slam(tmp_path,backend):
    fixture=json.loads((Path(__file__).resolve().parents[1]/'fixtures/native_bonestab3_resize_pause_prefix.json').read_text())
    path=tmp_path/'bonestab3.csv';path.write_bytes(fixture['csv'].encode('utf-8'))
    assert hashlib.sha256(path.read_bytes()).hexdigest()==fixture['csv_sha256']
    rows=fixture['rows'];schedule=[row['dt'] for row in rows]
    settings=dict(seed=fixture['seed'],initial_environment=fixture['initial_environment'],
        initial_arena=fixture['initial_arena'],dt_schedule=schedule,max_ticks=len(rows),capture_state_keys=True)
    wave=ParametricEnvironment(path,backend=backend,**settings).bind().wave
    assert not wave.complete and wave.termination_reason=='tick_budget'
    assert [event[1] for event in wave.source_events]==[
        'combatzoneresize','heartteleport','heartmode','tlpause']
    assert not wave.env_schedule[:,6].any()
    assert wave.terminal_details['executed_callbacks']==[]
    np.testing.assert_array_equal(wave.env_schedule[0,:4],fixture['initial_arena_observed'])
    np.testing.assert_array_equal(wave.env_schedule[-1,:4],fixture['final_arena_observed'])
    state=np.array(fixture['initial'],dtype=float)
    for tick,row in enumerate(rows):
        assert row['running']==0 and row['T']==0 and row['line']==5
        assert row['HP']==92 and row['KR']==0
        if tick:step_mask_into(state,row['mask'],wave.env_schedule[tick],wave.platform_table[tick],state)
        assert state.tobytes()==np.asarray(row['state'],dtype=float).tobytes(),tick
    direct=compile_wave(path,**settings)
    assert wave.environment_state_keys==direct.environment_state_keys


@pytest.mark.parametrize('settled,callback_tick,resume_tick,slam_tick',[
    (False,1,2,3),(True,0,1,2),
])
@pytest.mark.parametrize('backend',['reference','resumable'])
def test_pause_and_post_world_resize_resume_do_not_retroactively_advance_timeline(
        tmp_path,backend,settled,callback_tick,resume_tick,slam_tick):
    path=tmp_path/'pause.csv'
    path.write_text('0,CombatZoneResize,116,200,500,400,TLResume\n0,TLPause\n'
                    '0,SET,resumed,1\n0.016666666666666666,SansSlam,2\n0,EndAttack\n')
    left=116. if settled else 100.
    initial=[left,200.,500.,400.,0.,1.,0.,1/60,750.,0.,0.,0.,0.]
    settings=dict(initial_environment=initial,dt_schedule=[1/60]*10,max_ticks=10,capture_state_keys=True)
    wave=ParametricEnvironment(path,backend=backend,**settings).bind().wave
    assert wave.complete
    events={cmd:tick for tick,cmd,args in wave.source_events}
    assert events['set']==resume_tick
    assert events['sansslam']==slam_tick
    calls=wave.terminal_details['executed_callbacks']
    assert len(calls)==1 and calls[0]['executed_tick']==callback_tick
    assert calls[0]['phase']=='post_timeline_combatzonetick'
    assert wave.environment_state_keys==compile_wave(path,**settings).environment_state_keys


@pytest.mark.parametrize('coupled',[False,True])
def test_pause_timer_stays_zero_through_the_settling_tick(tmp_path,coupled):
    path=tmp_path/'pause.csv'
    path.write_text('0,CombatZoneResize,116,200,500,400,TLResume\n0,TLPause\n0.1,EndAttack\n')
    initial=[100.,200.,500.,400.,0.,1.,0.,1/60,750.,0.,0.,0.,0.]
    state=initialize(path,initial_environment=initial,dt_schedule=[1/60]*20,max_ticks=20)
    for tick in range(3):
        result=(advance_with_dialogue_input(state,confirm=False,cancel=False,
                    previous_confirm=False,previous_cancel=False) if coupled and tick==0 else
                advance_with_dialogue_input(state,confirm=False,cancel=False) if coupled else
                advance_one_tick(state))
        state=result.state
        assert state.data['running']==(tick>=1)
        assert state.data['time_acc']==(0. if tick<2 else 1/60)


@pytest.mark.parametrize('backend',['reference','resumable'])
def test_paused_timeline_cannot_reach_its_own_later_resume_without_callback(tmp_path,backend):
    path=tmp_path/'blocked.csv';path.write_text('0,TLPause\n0,TLResume\n0,EndAttack\n')
    wave=ParametricEnvironment(path,backend=backend,dt_schedule=[1/60]*4,max_ticks=4).bind().wave
    assert not wave.complete and wave.termination_reason=='tick_budget'
    assert [cmd for tick,cmd,args in wave.source_events]==['tlpause']
