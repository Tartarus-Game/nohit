"""Dialogue continuation must bind each reachable player's actual observations."""
import numpy as np
import pytest

from nohit.engine.dialogue_frontier import solve_dialogue_frontier
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.joint_transition import begin_joint, step_joint


STATE=np.array([320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.])


def fixture(tmp_path, tail, *, at_zero=False):
    path=tmp_path/'target-after-dialogue.csv'
    path.write_text('0,HeartMode,0\n'+('0' if at_zero else '0.033333')+',SansText,a,\n'+tail)
    template=ParametricEnvironment(path,dt_schedule=(1/30,)*100,max_ticks=100,
                                   termination_policy='eof_hazards_drained')
    return template,template.bind()


def replay(template,binding,initial,result):
    fresh=ParametricEnvironment(template.path,dt_schedule=template.dt_schedule,max_ticks=100,
                               termination_policy='eof_hazards_drained')
    origin=np.asarray(initial).reshape(-1,11)[result.origin_index]
    node=begin_joint(fresh,fresh.bind(binding.history),origin,previous_input_code=int(origin[4]))
    targets=list(binding.history)
    for index,control in enumerate(result.controls,1):
        edge=step_joint(fresh,node,control)
        assert edge.state is not None
        node=edge.state;targets.extend(node.environment.frame.target_history)
        assert np.asarray(node.player).tobytes()==result.trajectory[index].tobytes()
    assert node.environment.status=='terminal'
    assert tuple(targets)==result.target_history
    assert node.environment.identity==result.controlled_binding_identity


def test_dialogue_then_target_reaches_known_safe_terminal(tmp_path):
    template,binding=fixture(tmp_path,'0,GetHeartPos,x,y\n0,EndAttack\n')
    result=solve_dialogue_frontier(template,binding,STATE,controls=(0,))
    assert result.status=='candidate_found' and result.verified
    assert result.target_history==((3,3,320.,304.),)
    assert result.controls==[0,32,0]
    replay(template,binding,STATE,result)


def test_each_player_owns_target_even_after_players_converge(tmp_path):
    template,binding=fixture(tmp_path,'0,GetHeartPos,x,y\n0,BoneV,$x,280,10,0,0\n'
                            '0,HeartTeleport,320,304\n0.066667,EndAttack\n')
    initial=np.tile(STATE,(2,1));initial[:,0]=[280.,360.]
    result=solve_dialogue_frontier(template,binding,initial,controls=(0,))
    assert result.verified
    assert np.array_equal(result.layers[-1][0],result.layers[-1][1])
    assert result.stats['world_group_counts']==[(3,2),(4,2),(5,2)]
    assert len(result.layers[-1])==2
    assert result.target_history[0][2]==initial[result.origin_index,0]
    replay(template,binding,initial,result)


def test_later_origin_survives_its_own_target_world(tmp_path):
    template,binding=fixture(tmp_path,'0,GetHeartPos,x,y\n0,Add,bx,$x,40\n'
                            '0,BoneV,$bx,300,10,0,0\n0,HeartTeleport,320,304\n0.066667,EndAttack\n')
    initial=np.tile(STATE,(2,1));initial[:,0]=[280.,360.]
    result=solve_dialogue_frontier(template,binding,initial,controls=(0,))
    assert result.verified and result.origin_index==1
    assert result.target_history[0][2:]==(360.,304.)
    replay(template,binding,initial,result)


def test_same_tick_targets_use_incoming_movement_then_teleport(tmp_path):
    template,binding=fixture(tmp_path,'0,GetHeartPos,x,y\n0,HeartTeleport,250,300\n'
                            '0,GetHeartPos,u,v\n0,EndAttack\n')
    result=solve_dialogue_frontier(template,binding,STATE,controls=(2,))
    assert result.verified
    assert result.target_history==((3,3,330.,304.),(3,5,250.,300.))
    assert len(result.actions)==3
    replay(template,binding,STATE,result)


def test_target_world_expands_arrows_without_cloning_for_each_mask(tmp_path):
    template,binding=fixture(tmp_path,'0,GetHeartPos,x,y\n0,EndAttack\n')
    result=solve_dialogue_frontier(template,binding,STATE,max_states=10000)
    assert result.verified
    assert set(result.layers[-1][:,4])==set(range(16))
    assert result.stats['target_player_transactions']==len(result.layers[-2])
    replay(template,binding,STATE,result)


def test_future_equal_worlds_keep_distinct_unconsumed_frames(tmp_path):
    from nohit.engine.dialogue_target_frontier import _WorldScope
    from nohit.engine.resumable_wave import state_environment_key
    template,binding=fixture(tmp_path,'0,GetHeartPos,x,y\n0,JmpG,7,$x,300\n'
                            '0,HeartTeleport,320,304\n0,:skip\n0,GetHeartPos,x,y\n0.066667,EndAttack\n')
    worlds=[]
    for x in (280.,320.):
        player=STATE.copy();player[0]=x
        node=begin_joint(template,binding,player,previous_input_code=0)
        for control in (0,32,0):node=step_joint(template,node,control).state
        worlds.append(node.environment)
    assert state_environment_key(worlds[0].state)==state_environment_key(worlds[1].state)
    assert [world.frame.env[9] for world in worlds]==[1.,0.]
    scope=_WorldScope(worlds[0])
    assert scope.key(worlds[0])!=scope.key(worlds[1])
    initial=np.tile(STATE,(2,1));initial[:,0]=[280.,320.]
    result=solve_dialogue_frontier(template,binding,initial,controls=(0,))
    assert result.verified
    assert result.stats['world_group_counts'][0]==(3,2)
    replay(template,binding,initial,result)


@pytest.mark.parametrize('tail,reason',[
    ('0,GetHeartPos,x,y\n','verified_eof_hazards_drained'),
    ('0,GetHeartPos,x,y\n0,SansText,b,UnknownCallback\n0,EndAttack\n','unknown_world_transition'),
])
def test_eof_and_unknown_callbacks_keep_their_meanings(tmp_path,tail,reason):
    template,binding=fixture(tmp_path,tail)
    result=solve_dialogue_frontier(template,binding,STATE,controls=(0,))
    assert result.reason==reason
    if reason.startswith('verified'):
        assert result.verified;replay(template,binding,STATE,result)
    else:
        assert result.status=='unknown' and not result.verified
        assert result.stats['unknown_world_branches']>0


@pytest.mark.parametrize('prime',[False,True])
def test_tick_zero_target_continuation_does_not_repeat_movement(tmp_path,prime):
    from nohit.engine.joint_transition import JointState
    template,binding=fixture(tmp_path,'0,GetHeartPos,x,y\n0,EndAttack\n',at_zero=True)
    initial=STATE.copy();initial[2]=75.
    options={'initial_frame_control':0} if prime else {}
    result=solve_dialogue_frontier(template,binding,initial,controls=(0,),**options)
    assert result.verified and result.start_tick==(0 if prime else -1)
    node=begin_joint(template,binding,initial,previous_input_code=0)
    if prime:node=JointState(node.player,template.step_controlled(node.environment,0))
    for i,control in enumerate(result.controls,1):
        node=step_joint(template,node,control).state
        assert np.asarray(node.player).tobytes()==result.trajectory[i].tobytes()


def test_public_csv_reports_full_history_and_base_provenance(tmp_path):
    from nohit.engine.csv_solver import solve_csv
    template,_=fixture(tmp_path,'0,GetHeartPos,x,y\n0,EndAttack\n')
    result=solve_csv(template.path,STATE,dt_schedule=template.dt_schedule,max_ticks=100,width=10)
    assert result['status']=='candidate_found' and result['verified']
    assert len(result['target_history'])==1
    provenance=result['environment_provenance']
    assert provenance['kind']=='controlled' and provenance['base_target_history']==[]
    assert provenance['base_binding_identity']==result['environment_binding_identity']
    assert provenance['final_binding_identity']==result['controlled_environment_binding_identity']
    assert provenance['base_binding_identity']!=provenance['final_binding_identity']


def test_inflight_target_before_dialogue_is_not_published_twice(tmp_path):
    from nohit.engine.csv_solver import solve_csv
    path=tmp_path/'inflight.csv'
    path.write_text('0,HeartMode,0\n0.033333,GetHeartPos,x,y\n0,SansText,a,\n'
                    '0,GetHeartPos,u,v\n0,EndAttack\n')
    template=ParametricEnvironment(path,dt_schedule=(1/30,)*100,max_ticks=100,
                                   termination_policy='eof_hazards_drained')
    binding=template.extend(template.bind(),320.,304.)
    result=solve_dialogue_frontier(template,binding,STATE,controls=(0,))
    assert result.verified
    assert result.target_history==((1,2,320.,304.),(3,4,320.,304.))
    public=solve_csv(path,STATE,dt_schedule=template.dt_schedule,max_ticks=100,width=10,max_bindings=2)
    assert public['verified'] and len(public['target_history'])==2
    assert [(row[0],row[1]) for row in public['target_history']]==[(1,2),(3,4)]
    assert len(public['environment_provenance']['base_target_history'])==1


def test_target_expansion_budget_keeps_preceding_complete_layer(tmp_path):
    template,binding=fixture(tmp_path,'0,GetHeartPos,x,y\n0,EndAttack\n')
    result=solve_dialogue_frontier(template,binding,STATE,controls=(0,2),max_states=4)
    assert result.status=='unknown' and result.reason=='state_budget'
    assert result.stats['target_dependent'] and not result.verified
    assert result.end_tick==2 and len(result.layers)==3
    assert len(result.layers[-1])==4 and len(result.parents)==2


def test_width_selection_counts_discarded_world_player_alternatives(tmp_path):
    template,binding=fixture(tmp_path,'0,GetHeartPos,x,y\n0.1,EndAttack\n')
    result=solve_dialogue_frontier(template,binding,STATE,width=3,selection_seed=17)
    assert result.verified and result.stats['motion_states_discarded_by_width']>0
    assert all(len(layer)<=3 for layer in result.layers)
    replay(template,binding,STATE,result)


def test_scope_rejects_other_clock_and_preserves_dynamic_clock(tmp_path):
    from dataclasses import replace
    from nohit.engine.dialogue_target_frontier import _WorldScope
    template,binding=fixture(tmp_path,'0,GetHeartPos,x,y\n0,EndAttack\n')
    node=begin_joint(template,binding,STATE,previous_input_code=0)
    node=step_joint(template,node,0).state
    scope=_WorldScope(node.environment)
    other=ParametricEnvironment(template.path,dt_schedule=(1/30,)*99+(1/60,),max_ticks=100,
                                termination_policy='eof_hazards_drained')
    peer=step_joint(other,begin_joint(other,other.bind(),STATE,previous_input_code=0),0).state
    with pytest.raises(ValueError,match='source/clock scope'):scope.key(peer.environment)
    changed=node.environment.state.clone();changed.clock_timestamp=100.
    assert scope.key(node.environment)!=scope.key(replace(node.environment,state=changed))


def test_tick_zero_known_target_prefix_is_verified_and_counted_once(tmp_path):
    from nohit.engine.csv_solver import solve_csv
    path=tmp_path/'tick-zero-history.csv'
    path.write_text('0,HeartMode,0\n0,GetHeartPos,x,y\n0,SansText,a,\n'
                    '0,GetHeartPos,u,v\n0,EndAttack\n')
    result=solve_csv(path,STATE,dt_schedule=(1/30,)*100,max_ticks=100,width=1,
                     initial_target_history=[[0,2,320.,304.]])
    assert result['verified'] and result['primed_initial_frame']
    assert [(row[0],row[1]) for row in result['target_history']]==[(0,2),(3,4)]
    assert result['target_history'][0]==[0,2,320.,304.]
    assert result['target_history'][1][2:]==result['trajectory'][3][:2]
    assert result['environment_provenance']['base_target_history']==[[0,2,320.,304.]]
