"""Backtracking through actual source target reads, with exact replay checking."""
import numpy as np
import pytest
from nohit.engine.parametric_dag import ParametricRouteIterator,solve_parametric
from nohit.engine.compact_wave import compile_wave
from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.cspace import bake_cspace,collision_query


@pytest.mark.parametrize('policy',['navigation','coast','coast_support'])
def test_zero_weight_backtracks_across_target_and_returns_only_complete_witness(tmp_path,policy):
    path=tmp_path/'target_escape.csv'
    path.write_text('0.008333,GetHeartPos,x,y\n'
                    '0.008333,BoneH,0,30,19,0,0\n0.008333,EndAttack\n')
    env=[0,0,100,100,0,1,0,1/240,750,0,20,35,0,0,0,0,100,100]
    initial=np.array([20.,35.,0.,0.,0.,0.,0.,1.,750.,0.,0.])
    result=solve_parametric(path,initial,initial_environment=env,weights=[0,0,0,0],max_nodes=5000,
                            lookahead_policy=policy)
    assert result['status']=='candidate_found'
    assert result['target_history'] and result['actions'][0]!=0
    # A separate whole-wave binding replays the returned witness through every
    # microtick, rather than trusting the branch search's intermediate data.
    samples={(t,line):(x,y) for t,line,x,y in result['target_history']}
    wave=compile_wave(path,initial_environment=env,heart_samples=samples)
    space=bake_cspace(wave);state=initial.copy()
    for frame,mask in enumerate(result['actions']):
        for micro in range(1,5):
            tick=frame*4+micro
            if tick>=len(wave.env_schedule):break
            step_mask_into(state,mask,wave.env_schedule[tick],wave.platform_table[tick],state)
            assert not collision_query(wave.geometry_white,wave.geometry_blue,tick,state,0.,space.payload)
    assert wave.complete


def test_resource_limit_never_claims_unsatisfiable(tmp_path):
    path=tmp_path/'limit.csv';path.write_text('0.1,GetHeartPos,x,y\n0.1,EndAttack\n')
    result=solve_parametric(path,[320,304,0,0,0,0,0,1,750,0,0],max_nodes=1)
    assert result['status']=='resource_limit'
    assert not result['deadlock_proven']


@pytest.mark.parametrize('target', ['', '0.004167,GetHeartPos,x,y\n',
                                  '0.1,GetHeartPos,x,y\n'])
@pytest.mark.parametrize('ending,reason,status', [
    ('0.2,EndAttack\n','tick_budget','resource_limit'),
    ('0.008333,SansText,hello\n0,EndAttack\n','dialogue_boundary','model_incomplete'),
])
def test_public_solver_never_promotes_safe_incomplete_prefix_to_candidate(tmp_path,target,ending,reason,status):
    from nohit.engine.canonical_solver import solve_attack
    policy='eof_hazards_drained' if reason=='dialogue_boundary' else 'endattack'
    # A target after the budget stops before dialogue is ever reached.
    if target.startswith('0.1'):
        reason,status='tick_budget','resource_limit'
    path=tmp_path/'incomplete.csv';path.write_text(target+ending)
    result=solve_attack(path,[320,304,0,0,0,0,0,1,750,0,0],max_ticks=8,
                        termination_policy=policy,
                        weights=dict(clearance=0,lookahead=0,center=0,switches=0))
    assert result['status']==status
    assert result['model_termination_reason']==reason
    assert result['actions']==[]
    assert not result['complete_in_original_game']
    assert not result['deadlock_proven']


def test_incomplete_target_extension_keeps_action_available(tmp_path):
    path=tmp_path/'extend_limit.csv'
    path.write_text('0.004167,GetHeartPos,x,y\n0.2,EndAttack\n')
    search=ParametricRouteIterator(path,[320,304,0,0,0,0,0,1,750,0,0],
                                   weights=[0,0,0,0],max_ticks=8)
    with pytest.raises(StopIteration):next(search)
    assert search.status=='resource_limit'
    assert search.model_termination_reason=='tick_budget'
    assert search.stack[-1].cursor==0
    assert not search.dead


def test_iterator_keeps_other_complete_routes_after_first_witness(tmp_path):
    path=tmp_path/'alternatives.csv';path.write_text('0.008333,GetHeartPos,x,y\n0.008333,EndAttack\n')
    search=ParametricRouteIterator(path,[320,304,0,0,0,0,0,1,750,0,0],weights=[0,0,0,0])
    a=next(search);b=next(search)
    assert a['status']==b['status']=='candidate_found'
    assert a['actions']!=b['actions']


def test_deepest_diagnostic_path_survives_backtracking_and_budget_resume(tmp_path):
    path=tmp_path/'diagnostic_path.csv'
    path.write_text('0.008333,GetHeartPos,x,y\n0.008333,EndAttack\n')
    search=ParametricRouteIterator(path,[320,304,0,0,0,0,0,1,750,0,0],weights=[0,0,0,0])
    first=next(search)
    search.max_nodes=search.nodes
    with pytest.raises(StopIteration):next(search)
    assert search.status=='resource_limit'
    assert len(search.stack)-1<len(first['actions'])
    assert search.best_prefix==first['actions']
    np.testing.assert_array_equal(search.best_state,first['trajectory'][-1])
    search.max_nodes+=100
    second=next(search)
    assert second['status']=='candidate_found'
    assert second['actions']!=first['actions']


def test_support_coast_without_platforms_matches_held_coast_across_target(tmp_path):
    from nohit.engine.canonical_solver import solve_attack
    path=tmp_path/'no_support.csv'
    path.write_text('0.016666,GetHeartPos,x,y\n0.033333,EndAttack\n')
    initial=[320,304,0,0,0,0,0,1,750,0,0]
    coast=solve_parametric(path,initial,lookahead_policy='coast',allow_cancel=False)
    support=solve_attack(path,initial,lookahead_policy='coast_support',allow_cancel=False)
    assert coast['status']==support['status']=='candidate_found'
    assert coast['actions']==support['actions']
    assert coast['target_history']==support['target_history']
    assert support['planner']=='canonical-dag-dp'
    assert support['environment_solver']==coast['planner']=='parametric-demand-dag-dp'
    assert support['lookahead_policy']=='coast_support'
    np.testing.assert_array_equal(coast['trajectory'],support['trajectory'])


@pytest.mark.parametrize('nodes,status',[(1,'resource_limit'),(1000,'candidate_found')])
def test_public_parametric_results_keep_the_canonical_tas_identity(tmp_path,nodes,status):
    from nohit.engine.canonical_solver import solve_attack
    path=tmp_path/'public_identity.csv'
    path.write_text('0.016666,GetHeartPos,x,y\n0.033333,EndAttack\n')
    result=solve_attack(path,[320,304,0,0,0,0,0,1,750,0,0],max_nodes=nodes)
    assert result['status']==status
    assert result['planner']=='canonical-dag-dp'
    assert result['environment_solver']=='parametric-demand-dag-dp'


def test_support_forecast_stops_before_unbound_target_and_uses_legal_controls(tmp_path,monkeypatch):
    import nohit.engine.parametric_dag as module
    path=tmp_path/'support_target.csv'
    path.write_text('0,Platform,20,50,30,0,15\n0.008333,GetHeartPos,x,y\n0.033333,EndAttack\n')
    env=[0,0,100,100,1,1,0,1/240,750,0,40,41.95,0,0,0,0,100,100]
    initial=np.array([40.,41.95,0,0,0,0,1,1,750,0,0])
    calls=[];original=module._support_coast_survival
    def checked(state,mask,start,stop,env,platforms,white,blue,payload,allowed):
        assert stop==len(env)-1==len(platforms)-1
        assert allowed==16 and mask<16
        calls.append((start,stop))
        before=state.copy()
        value=original(state,mask,start,stop,env,platforms,white,blue,payload,allowed)
        np.testing.assert_array_equal(state,before)
        return value
    monkeypatch.setattr(module,'_support_coast_survival',checked)
    result=solve_parametric(path,initial,initial_environment=env,lookahead_policy='coast_support',
                            allow_cancel=False,max_nodes=1000)
    assert result['status']=='candidate_found'
    assert calls and calls[0]==(0,1)
    assert all(mask<16 for mask in result['actions'])
    wave=compile_wave(path,initial_environment=env,
        heart_samples={(t,line):(x,y) for t,line,x,y in result['target_history']})
    space=bake_cspace(wave);state=initial.copy()
    for frame,mask in enumerate(result['actions']):
        for micro in range(1,5):
            tick=frame*4+micro
            if tick>=len(wave.env_schedule):break
            step_mask_into(state,mask,wave.env_schedule[tick],wave.platform_table[tick],state)
            assert not collision_query(wave.geometry_white,wave.geometry_blue,tick,state,0.,space.payload)
