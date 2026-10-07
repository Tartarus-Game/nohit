"""Candidate discovery never converts discarded alternatives into dead facts."""
import numpy as np
import pytest

import nohit.engine.bounded_frontier as module
from nohit.engine.discrete_operator import step_mask_into, sample_position
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.cspace import bake_cspace, collision_query


INITIAL=np.array([320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.])


def source(tmp_path,text):
    path=tmp_path/'candidate.csv';path.write_text(text)
    return path


def run(path,**kwargs):
    return module.find_bounded_candidate(path,INITIAL,dt_schedule=(1/30,)*100,
        max_ticks=100,seconds=5.,**kwargs)


def independently_replay(result,path):
    template=ParametricEnvironment(path,dt_schedule=(1/30,)*100,max_ticks=100)
    binding=template.bind();state=INITIAL.copy();cache={}
    while binding.pending_target is not None and binding.pending_target['tick']==0:
        binding=template.extend(binding,state[0],state[1])
    for tick in range(len(result.actions)+1):
        if tick:
            if binding.pending_target is not None and binding.pending_target['tick']==tick:
                x,y=sample_position(state,binding.wave.env_schedule[tick],binding.wave.platform_table[tick])
                while binding.pending_target is not None and binding.pending_target['tick']==tick:
                    binding=template.extend(binding,x,y)
            step_mask_into(state,result.actions[tick-1],binding.wave.env_schedule[tick],binding.wave.platform_table[tick],state)
        if binding.identity not in cache:cache[binding.identity]=bake_cspace(binding.wave,cell_size=8.)
        assert not collision_query(binding.wave.geometry_white,binding.wave.geometry_blue,tick,state,0.,cache[binding.identity].payload)
        assert state.tobytes()==result.trajectory[tick].tobytes()
    assert binding.history==result.target_history
    assert binding.complete and len(result.actions)==len(binding.wave.env_schedule)-1


def test_complete_safe_candidate_is_scalar_verified_from_real_initial(tmp_path):
    path=source(tmp_path,'0,HeartMode,0\n0.1,BoneV,400,200,100,0,0\n0.1,EndAttack\n')
    original=INITIAL.copy()
    result=run(path,width=40)
    assert result.status=='candidate_found' and result.verified
    assert result.reason=='verified_endattack'
    assert result.clock['original_replay_passed'] is False
    assert result.stats['verification_seconds']>0 and result.reached_tick>0
    assert result.actions==result.witness()[0]
    assert INITIAL.tobytes()==original.tobytes()
    independently_replay(result,path)


def test_width_losing_a_real_witness_returns_unknown(tmp_path):
    path=source(tmp_path,'0,HeartMode,0\n0.133333,BoneH,310,304,330,0,0\n0.033333,EndAttack\n')
    known=run(path,controls=(1,),width=1)
    assert known.status=='candidate_found'
    limited=run(path,width=1,selection_seed=1,recovery_lookback=0)
    assert limited.status=='unknown' and not limited.verified
    assert limited.reason=='frontier_empty'
    assert limited.stats['discarded_states']>0
    assert not hasattr(limited,'dead')


def test_recovery_restores_a_pruned_safe_path_from_the_original_initial(tmp_path):
    path=source(tmp_path,'0,HeartMode,0\n0.133333,BoneH,310,304,330,0,0\n0.033333,EndAttack\n')
    result=run(path,width=1,selection_seed=1)
    assert result.status=='candidate_found' and result.verified
    assert result.stats['recovery_count']>0
    assert result.stats['recovery_macro_edges']>0
    assert result.stats['layer_counts_scope']=='expansion_history'
    assert any(row.get('kind')=='recovery' for row in result.stats['layer_counts'])
    assert result.actions==result.witness()[0]
    independently_replay(result,path)


def test_observation_branches_keep_their_own_history_and_parent_chains(tmp_path):
    path=source(tmp_path,'0,HeartMode,0\n0.1,GetHeartPos,x,y\n'
        '0,BoneV,$x,100,12,0,0\n0.066667,GetHeartPos,x,y\n0.066667,EndAttack\n')
    result=run(path,width=60,max_bindings=3)
    assert result.status=='candidate_found' and result.stats['observation_branches']>1
    assert result.stats['observation_discarded_states']>0
    assert max(row['bindings'] for row in result.stats['layer_counts'])<=3
    for layer,previous in zip(result.layers[1:],result.layers):
        for index,parent in enumerate(layer.parents):
            child=result.bindings[int(layer.binding_ids[index])]
            prior=result.bindings[int(previous.binding_ids[parent])]
            assert child.history[:len(prior.history)]==prior.history
            if child.history!=prior.history:
                wave=prior.wave;x,y=sample_position(previous.states[parent],wave.env_schedule[layer.tick],wave.platform_table[layer.tick])
                assert child.history[-1][2:]==(x,y)
    independently_replay(result,path)


@pytest.mark.parametrize('boundary',['dialogue','clock','eof'])
def test_incomplete_boundaries_are_unknown_not_terminal_candidates(tmp_path,boundary):
    text='0,SansText,waiting\n0.1,EndAttack\n' if boundary=='dialogue' else '10,EndAttack\n' if boundary=='clock' else '0,Platform,200,300,60,0,0\n'
    path=source(tmp_path,text)
    result=module.find_bounded_candidate(path,INITIAL,dt_schedule=(1/30,)*3,max_ticks=100,
        seconds=5.,termination_policy='eof_hazards_drained' if boundary=='eof' else 'endattack')
    assert result.status=='unknown' and not result.verified
    assert result.reason in ('dialogue_boundary','tick_budget','terminal_invariant_unproven')
    if boundary=='clock':
        assert result.reached_tick==2 and len(result.actions)==2


def test_initial_collision_is_unknown_and_never_expanded(tmp_path):
    path=source(tmp_path,'0,BoneH,0,304,640,0,0\n0.1,EndAttack\n')
    result=run(path)
    assert result.status=='unknown' and result.reason=='initial_collision'
    assert result.stats['expanded_states']==0 and result.actions==[]


def test_zero_search_budget_returns_unknown_and_records_separate_timing(tmp_path):
    path=source(tmp_path,'0,HeartMode,0\n0.1,EndAttack\n')
    result=module.find_bounded_candidate(path,INITIAL,seconds=0,max_ticks=100)
    assert result.status=='unknown' and result.reason=='wall_budget'
    assert result.actions==[] and result.stats['expanded_states']==0
    assert result.stats['kernel_materialization_seconds']>=0
    assert result.stats['environment_setup_seconds']>=0


def test_verification_failure_cannot_be_reported_as_a_candidate(tmp_path,monkeypatch):
    path=source(tmp_path,'0,HeartMode,0\n0.1,EndAttack\n')
    monkeypatch.setattr(module,'_scalar_verify',lambda *args,**kwargs:(False,None,'replay_state_mismatch'))
    result=run(path,width=1)
    assert result.status=='unknown' and not result.verified
    assert result.reason=='replay_state_mismatch'


def test_terminal_eof_uses_existing_certificate_and_cannot_bypass_unknown(tmp_path,monkeypatch):
    path=source(tmp_path,'0,HeartMode,0\n')
    unknown={'status':'unknown','reasons':['unproved_test_boundary']}
    monkeypatch.setattr(module,'complete_eof_tail',lambda *args,**kwargs:unknown)
    result=run(path,width=1,termination_policy='eof_hazards_drained')
    assert result.status=='unknown' and result.reason=='terminal_invariant_unproven'
    assert not result.verified


def test_different_explicit_clocks_remain_distinct_in_result_scope(tmp_path):
    path=source(tmp_path,'0.1,EndAttack\n')
    results=[module.find_bounded_candidate(path,INITIAL,dt_schedule=(dt,)*100,
        max_ticks=100,width=1) for dt in (1/30,1/60)]
    assert all(result.verified for result in results)
    assert results[0].clock['schedule_sha256']!=results[1].clock['schedule_sha256']
    assert results[0].bindings[0].identity!=results[1].bindings[0].identity


@pytest.mark.parametrize('kwargs',[
    {'width':0},{'width':True},{'max_bindings':0},{'seconds':-1},
    {'seconds':float('inf')},{'seconds':True},{'controls':()},
    {'recovery_lookback':-1},{'recovery_lookback':True},{'recovery_lookback':1.5},
    {'controls':(32,)},{'controls':(True,)},{'controls':(1.5,)},
    {'dt_schedule':[1/30],'clock_start_ms':100.},
])
def test_invalid_configuration_rejected(tmp_path,kwargs):
    path=source(tmp_path,'0.1,EndAttack\n')
    with pytest.raises(ValueError):module.find_bounded_candidate(path,INITIAL,**kwargs)
