"""The native one-tick input lattice strictly contains four-tick hold routes."""
import numpy as np
import pytest

from nohit.engine.parametric_dag import ParametricRouteIterator, solve_parametric
from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.cspace import bake_cspace, collision_query
from nohit.engine.terminal_completion import complete_eof_tail


def gap_script(tmp_path):
    path=tmp_path/'microtick_gap.csv'
    # Tick 2 creates a one-pixel safe center interval (320,321). Initial
    # velocity is zero; movement uses the previous tick's chosen velocity.
    # A right hold can enter, but must brake before four ticks are complete.
    path.write_text('0,HeartMode,0\n'
                    '0.00833333,BoneV,308,0,480,0,0\n'
                    '0,BoneV,323,0,480,0,0\n'
                    '0.0125,EndAttack\n')
    return path


INITIAL=[319.55,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.]


def test_real_csv_has_a_one_tick_witness_but_no_four_tick_hold_witness(tmp_path):
    path=gap_script(tmp_path)
    common=dict(weights=np.zeros(4),max_ticks=20,max_nodes=10000,max_expansions=10000)
    coarse=solve_parametric(path,INITIAL,decision_ticks=4,**common)
    fine=solve_parametric(path,INITIAL,decision_ticks=1,**common)
    assert coarse['status']=='exhausted_in_declared_model'
    assert fine['status']=='candidate_found'
    assert fine['control_ticks']==1 and fine['control_hz']==240
    assert not fine['four_tick_pruning_enabled']
    assert len(set(fine['actions'][:4]))>1
    # Re-evaluate every physical step against source dynamics and C-space;
    # no fake graph edges, monkeypatched physics, or native branch replay.
    search=ParametricRouteIterator(path,INITIAL,decision_ticks=1,**common)
    wave=search.stack[0].binding.wave;space=bake_cspace(wave)
    state=np.array(INITIAL)
    for tick,mask in enumerate(fine['actions'],1):
        step_mask_into(state,mask,wave.env_schedule[tick],wave.platform_table[tick],state)
        assert not collision_query(wave.geometry_white,wave.geometry_blue,tick,state,0.,space.payload)
        np.testing.assert_array_equal(state,fine['trajectory'][tick])


@pytest.mark.parametrize('policy',['navigation','coast','coast_support'])
def test_microtick_search_never_invokes_four_tick_pruning_or_quotients(tmp_path,monkeypatch,policy):
    import nohit.engine.parametric_dag as module
    def forbidden(*args,**kwargs):raise AssertionError('four-tick-only optimization used')
    for name in ('equivalent_controls','forced_vertical_collision','make_vertical_cache',
                 'preferred_axis_jump','_support_coast_survival'):
        monkeypatch.setattr(module,name,forbidden)
    path=tmp_path/'blue.csv'
    path.write_text('0,HeartMode,1\n0.02,GetHeartPos,x,y\n0.02,EndAttack\n')
    result=solve_parametric(path,[320.,304.,0.,0.,0.,0.,1.,1.,750.,0.,0.],
                            decision_ticks=1,weights=np.ones(4),lookahead=4,
                            lookahead_policy=policy,max_ticks=30,max_expansions=1000)
    assert result['status']=='candidate_found'
    assert len(result['target_history'])==1


def test_microtick_eof_tail_releases_on_next_tick_without_four_tick_carry(tmp_path):
    path=tmp_path/'eof.csv';path.write_text('0,HeartMode,0\n0.00833333,CombatZoneSpeed,480\n')
    search=ParametricRouteIterator(path,INITIAL,decision_ticks=1,termination_policy='eof_hazards_drained')
    wave=search.stack[0].binding.wave
    assert (len(wave.env_schedule)-1)%4!=0
    state=np.array(INITIAL);state[2]=150.;state[4]=2.
    tail=complete_eof_tail(wave,state,last_mask=2,decision_ticks=1,max_ticks=100)
    assert tail['status']=='proven' and tail['carry_ticks']==0
    assert tail['control_grid_ticks']==1 and tail['actions']==[0]


@pytest.mark.parametrize('value',[0,2,3,True,1.0])
def test_invalid_decision_granularity_rejected_before_compilation(tmp_path,value):
    with pytest.raises(ValueError,match='decision_ticks'):
        ParametricRouteIterator(tmp_path/'absent.csv',INITIAL,decision_ticks=value)
