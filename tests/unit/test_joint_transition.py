import numpy as np
import pytest
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.joint_transition import (begin_joint,step_joint,joint_key,
    joint_reachable,verify_joint_witness,JointState,frame_collision)
from nohit.engine.resumable_wave import Frame


def setup(tmp_path,source,dx=0.):
    path=tmp_path/'joint.csv';path.write_text(source)
    template=ParametricEnvironment(path,termination_policy='eof_hazards_drained',max_ticks=100)
    binding=template.bind()
    player=[320.,304.,dx,0.,0.,0.,0.,1.,750.,0.,0.]
    return template,begin_joint(template,binding,player,previous_input_code=0)


def test_two_dialogues_product_graph_and_exact_replay(tmp_path):
    template,start=setup(tmp_path,'0,HeartMode,0\n0,SansText,a,\n0,SansText,b,\n0,EndAttack\n')
    key=joint_key(start)
    status,word,end=joint_reachable(template,start,max_ticks=25)
    assert status=='terminal' and len(word)==17
    verified=verify_joint_witness(template,start,word)
    assert verified.status=='terminal' and joint_key(verified.state)==joint_key(end)
    assert joint_key(start)==key
    assert end.player[0:2]==(320.,304.)
    assert end.player[4]==0 # Confirm never leaks into physics mask.


def test_target_uses_incoming_movement_not_old_position(tmp_path):
    template,start=setup(tmp_path,'0,HeartMode,0\n0,SansText,a,\n0,GetHeartPos,x,y\n0,EndAttack\n',dx=150.)
    node=start
    for _ in range(7):node=step_joint(template,node,2).state
    node=step_joint(template,node,34).state
    before=np.array(node.player)
    edge=step_joint(template,node,0)
    assert edge.status=='terminal'
    sample=edge.state.environment.frame.target_history[0]
    assert sample[2]>before[0]
    assert sample[2]==edge.state.player[0]
    assert sample[3]==edge.state.player[1]


def test_cancel_mismatch_and_illegal_domain(tmp_path):
    template,start=setup(tmp_path,'0,SansText,a\n0,EndAttack\n')
    player=list(start.player);player[4]=16
    with pytest.raises(ValueError,match='Cancel'):joint_key(JointState(tuple(player),start.environment))
    with pytest.raises(ValueError,match='Cancel'):step_joint(template,start,16)
    edge=step_joint(template,start,16,allow_cancel=True)
    assert edge.state.player[4]==16
    assert edge.state.environment.state.dialogue_last_input==(False,True)


def test_two_same_tick_targets_respect_preceding_teleport(tmp_path):
    template,start=setup(tmp_path,'0,HeartMode,0\n0,SansText,a,\n0,GetHeartPos,x,y\n'
        '0,HeartTeleport,250,300\n0,GetHeartPos,u,v\n0,EndAttack\n',dx=150.)
    node=start
    for _ in range(7):node=step_joint(template,node,2).state
    node=step_joint(template,node,34).state
    before=node.player
    edge=step_joint(template,node,0)
    assert edge.status=='terminal'
    samples=edge.state.environment.frame.target_history
    assert len(samples)==2 and samples[0][2]>before[0]
    assert samples[1][2:]==(250.,300.)
    assert edge.state.player[:2]==(250.,300.)


def test_key_distinguishes_player_and_confirm(tmp_path):
    template,start=setup(tmp_path,'0,HeartMode,0\n0,SansText,abc\n0,EndAttack\n')
    a=step_joint(template,start,0).state;b=step_joint(template,start,32).state
    assert a.player==b.player and joint_key(a)!=joint_key(b)
    player=list(a.player);player[2]=1.
    assert joint_key(a)!=joint_key(JointState(tuple(player),a.environment))


def test_per_tick_collision_and_unknown_budget(tmp_path):
    template,start=setup(tmp_path,'0,HeartMode,0\n0,BoneV,320,294,20,0,0\n0,SansText,a\n0,EndAttack\n')
    assert step_joint(template,start,0).status=='collision'
    # Independently exercise all native damage components of a local frame.
    empty=np.empty((0,4));quads=np.empty((0,8))
    frame=Frame(0,np.zeros(22),np.empty((0,8)),empty,empty,quads,(),())
    p=np.array(start.player)
    assert not frame_collision(frame,p)
    p[10]=1;assert frame_collision(frame,p);p[10]=0
    frame.white=np.array([[319.,303.,321.,305.]])
    assert frame_collision(frame,p)
    frame.white=empty;frame.blue=np.array([[319.,303.,321.,305.]])
    assert not frame_collision(frame,p)
    p[2]=1;assert frame_collision(frame,p)
    frame.blue=empty;frame.polygons=np.array([[319.,303.,321.,303.,321.,305.,319.,305.]])
    assert frame_collision(frame,p)
    template,start=setup(tmp_path,'0,SansText,abc\n0,EndAttack\n')
    assert joint_reachable(template,start,max_ticks=1)[0]=='unknown'


def test_unknown_callback_does_not_publish_safe_edge(tmp_path):
    template,start=setup(tmp_path,'0,SansText,a,UnknownCallback\n0,EndAttack\n')
    node=start
    for _ in range(7):node=step_joint(template,node,0).state
    edge=step_joint(template,node,32)
    assert edge.status=='unknown' and edge.state is None
    assert edge.reason=='unsupported_dialogue_callback:UnknownCallback'


def test_state_budget_and_clock_identity(tmp_path):
    template,start=setup(tmp_path,'0,SansText,abc\n0,EndAttack\n')
    assert joint_reachable(template,start,controls=(0,32,2),max_states=1)[0]=='unknown'
    a=step_joint(template,start,0).state
    from dataclasses import replace
    changed=a.environment.state.clone();changed.clock_timestamp=100.
    b=JointState(a.player,replace(a.environment,state=changed))
    assert joint_key(a)!=joint_key(b)
