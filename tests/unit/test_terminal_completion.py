"""Public EOF candidates carry a checked bridge and infinite-tail certificate."""
import numpy as np
import pytest
from types import SimpleNamespace

from nohit.engine.compact_wave import native_fixed_dt
from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.terminal_completion import complete_eof_tail
from nohit.engine.execution_schedule import execution_schedule


ZERO=dict(clearance=0,lookahead=0,center=0,switches=0)
INITIAL=[320,304,0,0,0,0,1,1,750,0,0]


def empty_wave(count):
    bounds=[0.,0.,200.,200.]
    env=np.array([*bounds,0.,1.,0.,1/240,750.,0.,0.,0.,0.,0.,*bounds,*bounds])
    details=dict(active_bones=0,active_stabs=0,active_blasters=0,active_platforms=0,
                 arena_settled=True,timeline_exhausted=True,pending_callbacks=[],pending_dialogue=None)
    return SimpleNamespace(termination_reason='eof_hazards_drained',complete=True,
                           env_schedule=np.tile(env,(count,1)),terminal_details=details)


@pytest.mark.parametrize('current_tick',[4,5,6,7])
def test_partial_last_control_block_holds_input_until_next_grid_point(current_tick):
    wave=empty_wave(current_tick+1)
    s=np.array([100.,100.,150.,0.,2.,0.,0.,1.,750.,0.,0.])
    clock=81808.33333333702
    result=complete_eof_tail(wave,s,last_mask=2,clock_start_ms=clock,max_ticks=100)
    carry=(-current_tick)%4
    assert result['status']=='proven'
    assert result['carry_ticks']==carry
    assert result['actions'][:carry]==[2]*carry
    assert result['actions'][carry:]==[0]
    assert result['release_after_tick']%4==0
    expected=native_fixed_dt(clock,current_tick+1+len(result['actions']),wave.env_schedule[0,7])[current_tick+1:]
    np.testing.assert_array_equal(result['dt_sequence'],expected)
    env=np.array(result['static_environment']);q=s.copy()
    for i,(mask,dt) in enumerate(zip(result['actions'],expected)):
        env[7]=dt;step_mask_into(q,mask,env,np.zeros((0,9)),q)
        np.testing.assert_array_equal(q,result['states'][i+1])


def test_control_grid_alignment_fails_closed_on_missing_budget_or_environment_proof():
    wave=empty_wave(6)
    s=np.array([100.,100.,150.,0.,2.,0.,0.,1.,750.,0.,0.])
    assert complete_eof_tail(wave,s,last_mask=2,max_ticks=8)['status']=='unknown'
    assert complete_eof_tail(wave,s,last_mask=0)['reasons']==['last_mask_state_disagreement']
    wave.terminal_details['pending_callbacks']=['spawn']
    result=complete_eof_tail(wave,s,last_mask=2)
    assert result['status']=='unknown' and result['actions']==[]
