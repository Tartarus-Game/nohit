"""Differential checks for owned sampling and linear known-history replay."""
import pickle
import time
import numpy as np
import pytest

from nohit.engine import resumable_wave as world
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.source_oracle import scalar_module
from nohit.engine.native_dynamic import _world, _certify


def test_minimal_sampling_matches_full_preview_without_mutating_suspension(tmp_path):
    path=tmp_path/'sampling.csv'
    path.write_text('0,CombatZoneResizeInstant,100,100,500,400\n'
        '0,Platform,110,350,50,0,120,1\n0,Platform,450,300,50,0,120,1\n'
        '0,GetHeartPos,x,y\n0.1,GetHeartPos,x,y\n'
        '0,BlackScreen,1\n0,GetHeartPos,x,y\n0.1,EndAttack\n')
    state=world.initialize(path,dt_schedule=[1/60]*200)
    player=scalar_module('discrete_operator');reads=0
    while True:
        result=world.advance_one_tick(state)
        if isinstance(result,world.NeedTarget):
            before=pickle.dumps(result.state.data)
            env,platforms=world._observation_sampling_arrays(result)
            full=world.preview_observation_frame(result)
            for direction in range(4):
                for x,y,vx,vy in [(110,340,150,300),(490,310,-150,400),(320,380,0,300),(320,300,30,-30)]:
                    physical=np.array([x,y,vx,vy,0,1,1,direction,750,1,0],dtype=float)
                    assert player.sample_position(physical,env,platforms)==player.sample_position(physical,full.env,full.platforms)
            assert pickle.dumps(result.state.data)==before
            state=world.supply_target(result,(320.,304.));reads+=1
        elif isinstance(result,world.TickCommitted):state=result.state
        else:
            assert isinstance(result,world.Terminal);break
    assert reads==3


def test_known_history_matches_persistent_bindings_and_reference(tmp_path):
    path=tmp_path/'linear.csv'
    path.write_text('0,Platform,200,350,60,0,80,1\n'+
        ''.join('0.003,GetHeartPos,x,y\n0,BoneV,$x,100,12,0,10\n' for _ in range(40))+
        '0.1,EndAttack\n')
    settings=dict(dt_schedule=[1/60]*100,max_ticks=100)
    persistent=ParametricEnvironment(path,**settings);binding=persistent.bind()
    while binding.pending_target is not None:binding=persistent.extend(binding,320.,304.)
    once=ParametricEnvironment(path,**settings);actual=once.bind_history_once(binding.history)
    reference=ParametricEnvironment(path,backend='reference',**settings).bind(binding.history)
    assert actual.identity==binding.identity and actual.complete
    assert once.stats['bindings_compiled']==1 and len(once._bindings)==1
    for name in ('env_schedule','platform_table','geometry_white','geometry_blue','geometry_polygons'):
        assert getattr(actual.wave,name).tobytes()==getattr(binding.wave,name).tobytes()
        assert getattr(actual.wave,name).tobytes()==getattr(reference.wave,name).tobytes()
    with pytest.raises(ValueError,match='source program'):
        ParametricEnvironment(path,**settings).bind_history_once(((0,999,320.,304.),))


def test_linear_dialogue_certificate_checks_dense_prefix_and_rejects_tampering(tmp_path):
    path=tmp_path/'dialogue.csv'
    path.write_text('0,HeartMode,0\n'+''.join('0.003,GetHeartPos,x,y\n' for _ in range(96))+
        '0.05,SansText,Hi.,\n0.1,EndAttack\n')
    settings=dict(dt_schedule=[1/60]*1000,max_ticks=1000)
    initial=np.array([320,304,0,0,0,0,0,1,750,0,0],dtype=float)
    built=_world(path,initial,settings,[],False,False,None,time.perf_counter()+5)
    assert built is not None
    _,_,expected,confirms,safe,word=built;assert safe
    certificate=_certify(path,initial,settings,word,expected,confirms,False,False,None,True)
    assert certificate is not None and len(certificate[1])==96
    altered=expected.copy();altered[3,0]+=1
    assert _certify(path,initial,settings,word,altered,confirms,False,False,None,True) is None


@pytest.mark.parametrize('delay',[0.,0.05])
def test_streaming_certificate_identity_matches_pure_product_replay(tmp_path,delay):
    from nohit.engine.joint_transition import JointState,step_joint
    path=tmp_path/'controls.csv'
    path.write_text(f'0,HeartMode,0\n{delay},SansText,Hi.,\n'+
        ''.join('0.05,GetHeartPos,x,y\n' for _ in range(4))+'0.1,EndAttack\n')
    settings=dict(dt_schedule=[1/60]*1000,max_ticks=1000)
    initial=np.array([320,304,0,0,0,0,0,1,750,0,0],dtype=float)
    built=_world(path,initial,settings,[],False,False,None,time.perf_counter()+5)
    _,_,expected,confirms,safe,word=built;assert safe
    certificate=_certify(path,initial,settings,word,expected,confirms,False,False,None,True)
    assert certificate is not None
    base,history,terminal,identity,start,primed=certificate
    template=ParametricEnvironment(path,**settings);binding=template.bind_history_once(base.history)
    previous=int(expected[start,4])|(32 if start and confirms[start-1] else 0)
    env=template.begin_controlled(binding,previous_input_code=previous)
    if primed:env=template.step_controlled(env,int(expected[0,4]))
    node=JointState(tuple(expected[start]),env)
    for tick in range(start+1,len(expected)):
        edge=step_joint(template,node,int(word[tick-1])|(32 if confirms[tick-1] else 0))
        assert edge.state is not None;node=edge.state
    assert node.environment.status=='terminal' and node.environment.identity==identity
    assert np.asarray(node.player).tobytes()==expected[-1].tobytes()


def test_coupled_segments_sample_committed_inputs_and_pass_source_replay(tmp_path):
    from nohit.engine.native_dynamic import _segmented_coupled
    path=tmp_path/'segments.csv'
    path.write_text('0,HeartMode,0\n0,SansText,Hi.,\n'+
        ''.join('0.05,GetHeartPos,x,y\n' for _ in range(6))+'0.1,EndAttack\n')
    settings=dict(dt_schedule=[1/60]*1000,max_ticks=1000)
    initial=np.array([320,304,0,0,0,0,0,1,750,0,0],dtype=float)
    result=_segmented_coupled(path,initial,settings,128,4,8,42,False,False,None,time.perf_counter()+5)
    assert result is not None and result.verified and result.status=='candidate_found'
    assert len(result.target_history)==6 and result.stats['committed_observation_segments']>1
    built=_world(path,initial,settings,result.actions,False,False,None,time.perf_counter()+5)
    _,binding,actual,confirms,safe,word=built
    assert safe and binding.history==result.target_history
    assert actual.tobytes()==result.trajectory.tobytes() and word==result.actions


def test_dense_geometry_pack_matches_monolithic_source_bit_for_bit(tmp_path):
    from nohit.engine.compact_wave import compile_wave
    path=tmp_path/'dense.csv'
    path.write_text('0,BoneVRepeat,20,10,30,0,100,9,80,1\n'
        '0,BoneHRepeat,30,400,25,2,120,-8,80,0\n0.1,EndAttack\n')
    settings=dict(dt_schedule=[1/60]*100,max_ticks=100)
    reference=compile_wave(path,**settings)
    actual=ParametricEnvironment(path,**settings).bind_history_once().wave
    for name in ('env_schedule','platform_table','geometry_white','geometry_blue','geometry_polygons'):
        assert getattr(actual,name).tobytes()==getattr(reference,name).tobytes()


def test_target_free_dialogue_builds_one_world_and_matches_full_replay(tmp_path):
    from nohit.engine.native_dynamic import _static_coupled_candidate
    path=tmp_path/'static.csv';path.write_text('0,HeartMode,0\n0,SansText,Hi.,\n0.3,EndAttack\n')
    settings=dict(dt_schedule=[1/60]*1000,max_ticks=1000)
    initial=np.array([320,304,0,0,0,0,0,1,750,0,0],dtype=float)
    result=_static_coupled_candidate(path,initial,settings,128,4,8,42,False,True,None,time.perf_counter()+5)
    assert result is not None and result.verified and result.stats['observation_iterations']==0
    built=_world(path,initial,settings,result.actions,False,True,None,time.perf_counter()+5)
    assert built[4] and built[2].tobytes()==result.trajectory.tobytes()
    path.write_text('0,SansText,Hi.,\n0.05,GetHeartPos,x,y\n0.1,EndAttack\n')
    assert _static_coupled_candidate(path,initial,settings,128,4,8,42,False,True,None,time.perf_counter()+5) is None


@pytest.mark.parametrize('preview_ticks,chunk_ticks',[(60,0),(60,8)])
def test_speculative_preview_commits_only_actual_observations(tmp_path,preview_ticks,chunk_ticks):
    from nohit.engine.native_dynamic import _segmented_coupled
    path=tmp_path/'preview.csv'
    path.write_text('0,HeartMode,0\n0,SansText,Hi.,\n'
        '0.3,GetHeartPos,x,y\n0,BoneV,$x,80,20,1,10\n'
        '0.3,GetHeartPos,x,y\n0.3,EndAttack\n')
    settings=dict(dt_schedule=[1/60]*1000,max_ticks=1000)
    initial=np.array([320,304,0,0,0,0,0,1,750,0,0],dtype=float)
    result=_segmented_coupled(path,initial,settings,128,4,8,42,False,False,None,
        time.perf_counter()+5,_goal_style=1,_preview_ticks=preview_ticks,_chunk_ticks=chunk_ticks)
    assert result is not None and result.verified
    actual=_world(path,initial,settings,result.actions,False,False,None,time.perf_counter()+5)
    assert actual[4] and actual[1].history==result.target_history
    assert actual[2].tobytes()==result.trajectory.tobytes()
    assert len(result.actions)==len(result.trajectory)-1
