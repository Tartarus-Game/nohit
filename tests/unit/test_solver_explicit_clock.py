"""Public search and EOF continuation use the declared clock throughout."""
from types import SimpleNamespace

import numpy as np
import pytest

from nohit.engine.canonical_solver import solve_attack
from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.execution_schedule import execution_schedule
from nohit.engine.parametric_dag import ParametricRouteIterator, _Node
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.terminal_completion import complete_eof_tail

INITIAL = [320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.]
ZERO = dict(clearance=0,lookahead=0,center=0,switches=0)


@pytest.mark.parametrize('targeted', [False, True])
@pytest.mark.parametrize('hold', [1, 4])
def test_public_route_preserves_clock_and_reports_actual_rate(tmp_path, targeted, hold):
    path=tmp_path/'clock.csv'
    path.write_text('0,HeartMode,0\n'+('0.1,GetHeartPos,x,y\n' if targeted else '')+'0.2,EndAttack\n')
    schedule=np.full(100,1/30)
    result=solve_attack(path,INITIAL,weights=ZERO,allow_cancel=False,
                        decision_ticks=hold,dt_schedule=schedule,max_ticks=100)
    assert result['status']=='candidate_found'
    assert result['clock_protocol']=='explicit_dt_schedule'
    assert result['physics_hz']==30
    assert result['control_hz']==30/hold
    assert result['dt_schedule_count']==100
    assert set(result['dt_sequence'])=={1/30}
    assert not result['original_replay_passed']
    playback=execution_schedule(result)
    assert playback['control_hz']==30/hold
    assert playback['dt_sequence']==result['dt_sequence']
    # This is substantially shorter than the former silent 240 Hz bake.
    assert len(result['actions'])*hold < 20


def test_variable_clock_has_no_invented_fixed_rate_and_does_not_fill_missing_ticks(tmp_path):
    path=tmp_path/'short.csv'
    path.write_text('1,EndAttack\n')
    result=solve_attack(path,INITIAL,weights=ZERO,allow_cancel=False,
                        decision_ticks=1,dt_schedule=[1/30,1/60,1/30],max_ticks=100)
    assert result['status']=='resource_limit'
    assert result['physics_hz'] is None and result['control_hz'] is None
    assert result['model_termination_reason']=='tick_budget'
    assert not result['deadlock_proven']
    assert execution_schedule(result)['control_hz'] is None


def test_explicit_clock_cannot_be_combined_with_implicit_timestamp_protocol(tmp_path):
    path=tmp_path/'clock.csv'
    path.write_text('0.1,EndAttack\n')
    with pytest.raises(ValueError,match='either'):
        solve_attack(path,INITIAL,weights=ZERO,dt_schedule=[1/30]*20,clock_start_ms=1000)


def test_foreign_clock_binding_cannot_join_future_history_keys(tmp_path):
    path=tmp_path/'history.csv'
    path.write_text('0.1,GetHeartPos,x,y\n0.1,EndAttack\n')
    search=ParametricRouteIterator(path,INITIAL,weights=[0]*4,history_quotient=True,
                                  dt_schedule=[1/30]*100)
    a=search.stack[0]
    foreign=ParametricEnvironment(path,dt_schedule=[1/60]*100).bind()
    b=_Node(a.tick,a.state.copy(),foreign,a.mask)
    assert search._key(a)!=search._key(b)


def test_eof_bridge_consumes_explicit_future_and_never_nominal_240():
    bounds=[0.,0.,200.,200.]
    row=np.array([*bounds,0.,1.,0.,1/30,750.,0.,0.,0.,0.,0.,*bounds,*bounds])
    details=dict(active_bones=0,active_stabs=0,active_blasters=0,active_platforms=0,
                 arena_settled=True,timeline_exhausted=True,pending_callbacks=[],pending_dialogue=None)
    wave=SimpleNamespace(termination_reason='eof_hazards_drained',complete=True,
                         env_schedule=np.tile(row,(6,1)),terminal_details=details)
    state=np.array([100.,100.,150.,0.,2.,0.,0.,1.,750.,0.,0.])
    schedule=[1/30]*6+[1/60,1/30,1/120,1/60,1/30]
    result=complete_eof_tail(wave,state,last_mask=2,dt_schedule=schedule,max_ticks=100)
    assert result['status']=='proven'
    assert result['dt_sequence']==schedule[6:6+len(result['actions'])]
    q=state.copy()
    for index,(mask,dt) in enumerate(zip(result['actions'],result['dt_sequence'])):
        row[7]=dt
        step_mask_into(q,mask,row,np.empty((0,9)),q)
        assert q.tobytes()==np.asarray(result['states'][index+1]).tobytes()
    short=complete_eof_tail(wave,state,last_mask=2,dt_schedule=schedule[:7],max_ticks=100)
    assert short['status']=='unknown'
    assert short['actions']==[]
