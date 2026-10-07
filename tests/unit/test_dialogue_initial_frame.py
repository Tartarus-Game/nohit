"""Observed source tick zero is world-only bootstrap, never a player action."""
import numpy as np
import pytest

from nohit.engine.dialogue_frontier import solve_dialogue_frontier
from nohit.engine.joint_transition import JointState, step_joint
from nohit.engine.parametric_environment import ParametricEnvironment


STATE=np.array([320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.])


def fixture(tmp_path, text='a', before='', after='0,EndAttack\n', delay='0'):
    path=tmp_path/'initial-dialogue.csv'
    path.write_text(before+delay+',SansText,'+text+',\n'+after,encoding='utf-8')
    template=ParametricEnvironment(path,dt_schedule=(1/30,)*100,max_ticks=100)
    return template,template.bind()


def test_primed_world_keeps_observed_moving_player_and_next_tick_alignment(tmp_path):
    template,binding=fixture(tmp_path)
    observed=STATE.copy();observed[2]=150.;observed[4]=2.
    before=observed.tobytes()
    result=solve_dialogue_frontier(template,binding,observed,controls=(0,),initial_frame_control=2)
    assert result.verified and result.status=='candidate_found'
    assert result.primed_initial_frame and result.initial_frame.tick==0
    assert result.start_tick==0 and len(result.actions)==result.end_tick
    assert result.trajectory[0].tobytes()==before and observed.tobytes()==before
    assert result.trajectory[1,0]==325.  # One tick of retained velocity, not two.
    world=template.begin_controlled(binding,previous_input_code=2)
    world=template.step_controlled(world,2)
    node=JointState(tuple(observed),world)
    for index,control in enumerate(result.controls,1):
        edge=step_joint(template,node,control);assert edge.state is not None
        node=edge.state
        assert node.environment.frame.tick==index
        assert np.asarray(node.player).tobytes()==result.trajectory[index].tobytes()
    assert edge.status=='terminal' and edge.reason=='endattack'


def test_initial_confirm_edge_changes_the_world_before_the_first_action(tmp_path):
    template,binding=fixture(tmp_path)
    pressed=solve_dialogue_frontier(template,binding,STATE,controls=(0,),
        initial_frame_control=32,previous_confirm=False)
    held=solve_dialogue_frontier(template,binding,STATE,controls=(0,),
        initial_frame_control=32,previous_confirm=True)
    assert pressed.verified and held.verified
    assert pressed.end_tick==1 and pressed.actions==[0]
    assert held.end_tick==3 and len(held.actions)==3
    assert pressed.trajectory[0].tobytes()==STATE.tobytes()


def test_primed_frame_checks_hazards_at_the_observed_player(tmp_path):
    template,binding=fixture(tmp_path,before='0,BoneH,0,304,640,0,0\n')
    result=solve_dialogue_frontier(template,binding,STATE,controls=(0,),initial_frame_control=0)
    assert result.reason=='initial_collision' and not result.verified
    assert result.stats['expanded_states']==0


@pytest.mark.parametrize('text,after,reason',[
    ('a,UnknownCallback','0,EndAttack\n','unsupported_dialogue_callback'),
    ('a','0,GetHeartPos,x,y\n0,EndAttack\n','need_target'),
])
def test_prime_never_guesses_callback_or_target_effects(tmp_path,text,after,reason):
    template,binding=fixture(tmp_path,text=text,after=after)
    result=solve_dialogue_frontier(template,binding,STATE,controls=(0,),initial_frame_control=32)
    assert result.status=='unknown' and not result.verified
    assert reason in result.reason


def test_initial_frame_option_requires_tick_zero_boundary(tmp_path):
    template,binding=fixture(tmp_path,delay='0.03333333333333333')
    with pytest.raises(ValueError,match='tick zero'):
        solve_dialogue_frontier(template,binding,STATE,initial_frame_control=0)


@pytest.mark.parametrize('control',[True,-1,64,16,1])
def test_invalid_or_inconsistent_initial_frame_control_is_rejected(tmp_path,control):
    template,binding=fixture(tmp_path)
    with pytest.raises(ValueError):
        solve_dialogue_frontier(template,binding,STATE,initial_frame_control=control)
