"""Public EOF candidates carry a checked bridge and infinite-tail certificate."""
import numpy as np
import pytest
from types import SimpleNamespace

from nohit.engine.canonical_solver import solve_attack
from nohit.engine.compact_wave import native_fixed_dt
from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.parametric_dag import ParametricRouteIterator
from nohit.engine.terminal_completion import complete_eof_tail
from nohit.engine.execution_schedule import execution_schedule


ZERO=dict(clearance=0,lookahead=0,center=0,switches=0)
INITIAL=[320,304,0,0,0,0,1,1,750,0,0]


@pytest.mark.parametrize('target',['','0,GetHeartPos,x,y\n'])
def test_eof_candidate_has_exact_safe_settling_and_fixed_point(tmp_path,target):
    path=tmp_path/'tail.csv'
    path.write_text('0,HeartMode,1\n'+target+'0.02,CombatZoneSpeed,480\n')
    clock=81808.33333333702
    result=solve_attack(path,INITIAL,weights=ZERO,clock_start_ms=clock,
                        termination_policy='eof_hazards_drained',max_ticks=1000)
    assert result['status']=='candidate_found'
    tail=result['terminal_tail']
    assert tail['status']=='proven' and tail['actions']
    assert tail['control_ticks']==1
    playback=execution_schedule(result)
    assert playback['has_terminal_tail'] and playback['control_ticks']==1
    assert len(playback['actions'])==tail['start_tick']+len(tail['actions'])
    assert playback['actions'][tail['start_tick']:]==tail['actions']
    assert not result['original_replay_passed'] and not tail['original_replay_passed']
    first=tail['start_tick']+1
    expected=native_fixed_dt(clock,first+len(tail['actions']))[first:]
    np.testing.assert_array_equal(tail['dt_sequence'],expected)
    state=np.array(tail['states'][0]);env=np.array(tail['static_environment'])
    for index,(dt,mask) in enumerate(zip(expected,tail['actions'])):
        env[7]=dt
        step_mask_into(state,mask,env,np.zeros((0,9)),state)
        np.testing.assert_array_equal(state,tail['states'][index+1])
        assert state[10]==0
    np.testing.assert_array_equal(state,tail['certificate']['invariant_state'])


@pytest.mark.parametrize('target',['','0,GetHeartPos,x,y\n'])
def test_unproven_callback_never_becomes_complete_candidate(tmp_path,target):
    path=tmp_path/'callback.csv'
    path.write_text('0,HeartMode,0\n'+target+'0,CombatZoneResize,133,251,508,391,spawn\n')
    result=solve_attack(path,INITIAL,weights=ZERO,
                        termination_policy='eof_hazards_drained',max_ticks=100)
    assert result['status']=='model_incomplete'
    assert result['model_termination_reason']=='terminal_invariant_unproven'
    assert result['actions']==[] and not result['deadlock_proven']


def test_unknown_tail_keeps_parametric_branch_out_of_dead_memo(tmp_path):
    path=tmp_path/'budget.csv'
    path.write_text('0,GetHeartPos,x,y\n')
    search=ParametricRouteIterator(path,INITIAL,weights=[0,0,0,0],
                                   termination_policy='eof_hazards_drained',max_ticks=1)
    with pytest.raises(StopIteration):next(search)
    assert search.model_termination_reason=='terminal_invariant_unproven'
    assert search.stack and not search.dead


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
