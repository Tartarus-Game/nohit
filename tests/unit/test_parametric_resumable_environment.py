"""Consumer equivalence and measured elimination of executed source prefixes."""
import numpy as np
import pytest

from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.parametric_dag import solve_parametric
from nohit.engine.compact_wave import compile_wave
from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.cspace import bake_cspace,collision_query


def compare(a,b):
    for name in ('env_schedule','platform_table','num_platforms','geometry_white',
                 'geometry_blue','geometry_polygons','initial','schedule'):
        left,right=np.asarray(getattr(a,name)),np.asarray(getattr(b,name))
        assert left.shape==right.shape,name
        assert left.tobytes()==right.tobytes(),name
    for name in ('source_events','target_history','pending_target','complete','termination_reason',
                 'eof_tick','environment_state_keys','origin','dimensions'):
        assert getattr(a,name)==getattr(b,name),name
    if a.complete:assert a.terminal_details==b.terminal_details


@pytest.mark.parametrize('clock',[None,93108.33333335018])
def test_every_binding_and_same_tick_extension_matches_reference(tmp_path,clock):
    path=tmp_path/'bindings.csv'
    path.write_text('0,HeartMode,0\n0,Set,HeartY,17\n0,Platform,220,340,50,0,80,1\n'
                    '0.0125,GetHeartPos,HeartY,$HeartY\n0,BoneV,$17,$HeartY,10,0,0\n'
                    '0,HeartTeleport,250,300\n0,GetHeartPos,x,y\n0,GetHeartPos,x,y\n'
                    '0.025,BlackScreen,1\n0.0125,GetHeartPos,x,y\n'
                    '0,GasterBlaster,0,0,240,$x,$y,0,0.01,0.02\n0.05,EndAttack\n')
    templates=[ParametricEnvironment(path,max_ticks=100,capture_state_keys=True,
                clock_start_ms=clock,backend=backend) for backend in ('reference','resumable')]
    bindings=[template.bind() for template in templates]
    for _ in range(10):
        compare(bindings[0].wave,bindings[1].wave)
        if bindings[0].complete:break
        request=bindings[0].pending_target
        assert request
        bindings=[template.extend(binding,110.+request['line'],220.+request['tick'])
                  for template,binding in zip(templates,bindings)]
    else:raise AssertionError('fixture did not finish')
    assert templates[1].stats['executed_ticks']<templates[0].stats['executed_ticks']


def test_sibling_bindings_reuse_immutable_parent_continuation(tmp_path):
    path=tmp_path/'siblings.csv'
    path.write_text('0.025,GetHeartPos,x,y\n0,BoneV,$x,$y,10,0,0\n0.05,EndAttack\n')
    fast=ParametricEnvironment(path,max_ticks=100,backend='resumable')
    root=fast.bind();before=dict(root.resume_state.stats)
    for sample in ((100.,200.),(200.,300.),(300.,250.)):
        child=fast.extend(root,*sample)
        reference=ParametricEnvironment(path,max_ticks=100,backend='reference').bind(child.history)
        compare(reference.wave,child.wave)
        assert root.resume_state.stats==before
        assert child.committed_frames[:len(root.committed_frames)]==root.committed_frames
    assert root.history==()


def test_repeated_observations_execute_new_ticks_instead_of_prefixes(tmp_path):
    path=tmp_path/'many_targets.csv'
    rows=['0,HeartMode,0','0.05,GetHeartPos,x,y']
    for i in range(31):
        rows+=['0,BoneV,$x,100,10,0,0','0.0125,GetHeartPos,x,y']
    rows+=['0,BoneV,$x,100,10,0,0','0.025,EndAttack']
    path.write_text('\n'.join(rows)+'\n')
    templates=[ParametricEnvironment(path,max_ticks=500,backend=b) for b in ('reference','resumable')]
    last=[]
    for template in templates:
        binding=template.bind();index=0
        while binding.pending_target is not None:
            binding=template.extend(binding,200.+index,300.);index+=1
        assert index==32 and binding.complete
        last.append(binding)
    compare(last[0].wave,last[1].wave)
    slow,fast=(template.stats for template in templates)
    assert fast['committed_ticks']==len(last[1].wave.env_schedule)
    assert fast['preview_ticks']==32
    assert fast['executed_ticks']==fast['committed_ticks']+fast['preview_ticks']
    assert fast['executed_ticks']<slow['executed_ticks']/5
    assert fast['commands_executed']==len(last[1].wave.source_events)


@pytest.mark.parametrize('policy',['navigation','coast','coast_support'])
def test_tiny_solver_route_and_full_microtick_replay_are_backend_equivalent(tmp_path,policy):
    path=tmp_path/'escape.csv'
    path.write_text('0.008333,GetHeartPos,x,y\n0.008333,BoneH,0,30,19,0,0\n0.008333,EndAttack\n')
    env=[0,0,100,100,0,1,0,1/240,750,0,20,35,0,0,0,0,100,100]
    initial=np.array([20.,35.,0.,0.,0.,0.,0.,1.,750.,0.,0.])
    results=[solve_parametric(path,initial,initial_environment=env,weights=[0,0,0,0],
        max_nodes=5000,lookahead_policy=policy,environment_backend=b) for b in ('reference','resumable')]
    a,b=results
    assert a['status']==b['status']=='candidate_found'
    assert a['actions']==b['actions'] and a['target_history']==b['target_history']
    assert np.asarray(a['trajectory']).tobytes()==np.asarray(b['trajectory']).tobytes()
    wave=compile_wave(path,initial_environment=env,
        heart_samples={(t,line):(x,y) for t,line,x,y in b['target_history']})
    space=bake_cspace(wave);state=initial.copy()
    for frame,mask in enumerate(b['actions']):
        for micro in range(1,5):
            tick=frame*4+micro
            if tick>=len(wave.env_schedule):break
            step_mask_into(state,mask,wave.env_schedule[tick],wave.platform_table[tick],state)
            assert not collision_query(wave.geometry_white,wave.geometry_blue,tick,state,0.,space.payload)


@pytest.mark.parametrize('text,policy',[
    ('0,SansText,hello\n','eof_hazards_drained'),
    ('0,Platform,200,300,60,0,0\n','eof_hazards_drained'),
    ('0,CombatZoneResize,133,251,508,391,TLResume\n','eof_hazards_drained'),
])
def test_boundary_statuses_remain_explicit_in_compatibility_collector(tmp_path,text,policy):
    path=tmp_path/'boundary.csv';path.write_text(text)
    a,b=[ParametricEnvironment(path,max_ticks=100,backend=backend,
            termination_policy=policy).bind() for backend in ('reference','resumable')]
    compare(a.wave,b.wave)
