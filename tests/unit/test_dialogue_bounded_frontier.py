"""Width-limited dialogue candidates retain honest failure and exact ancestry."""
import numpy as np
import pytest

from nohit.engine.dialogue_frontier import solve_dialogue_frontier
from nohit.engine.joint_transition import begin_joint, step_joint
from nohit.engine.parametric_environment import ParametricEnvironment


STATE=np.array([320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.])


def fixture(tmp_path,tail='0,EndAttack\n',text='abcdef'):
    path=tmp_path/'bounded-dialogue.csv'
    path.write_text('0.03333333333333333,SansText,'+text+',\n'+tail,encoding='utf-8')
    template=ParametricEnvironment(path,dt_schedule=(1/30,)*100,max_ticks=100)
    return template,template.bind()


def test_width_keeps_exact_parent_origin_and_joint_replay(tmp_path):
    template,binding=fixture(tmp_path)
    other=STATE.copy();other[0]=400.
    initial=np.array([STATE,other]);before=initial.tobytes()
    result=solve_dialogue_frontier(template,binding,initial,controls=(0,2),
        width=2,selection_seed=42)
    assert result.status=='candidate_found' and result.verified
    assert result.stats['motion_states_discarded_by_width']>0
    assert all(len(layer)<=2 for layer in result.layers[1:])
    assert result.origin_index in (0,1)
    assert result.trajectory[0].tobytes()==initial[result.origin_index].tobytes()
    assert initial.tobytes()==before
    node=begin_joint(template,binding,initial[result.origin_index],previous_input_code=0)
    for i,control in enumerate(result.controls,1):
        edge=step_joint(template,node,control);assert edge.state is not None
        node=edge.state
        assert np.asarray(node.player).tobytes()==result.trajectory[i].tobytes()
    assert edge.status=='terminal' and edge.reason=='endattack'
    repeated=solve_dialogue_frontier(template,binding,initial,controls=(0,2),width=2,selection_seed=42)
    assert repeated.actions==result.actions and repeated.origin_index==result.origin_index
    assert repeated.trajectory.tobytes()==result.trajectory.tobytes()


def test_losing_a_feasible_branch_never_proves_the_full_relation_empty(tmp_path):
    template,binding=fixture(tmp_path,text='a',
        tail='0.06666666666666667,BoneH,300,304,40,0,0\n0.06666666666666667,EndAttack\n')
    safe=STATE.copy();safe[0]=400.
    initial=np.array([STATE,safe])
    complete=solve_dialogue_frontier(template,binding,initial,controls=(0,))
    assert complete.verified and complete.origin_index==1
    assert complete.stats['motion_states_discarded_by_width']==0
    outcomes=[solve_dialogue_frontier(template,binding,initial,controls=(0,),width=1,selection_seed=seed)
              for seed in range(8)]
    failures=[result for result in outcomes if not result.verified]
    assert failures
    for result in failures:
        assert result.status=='unknown' and result.reason=='empty_fixed_policy_relation'
        assert result.stats['motion_states_discarded_by_width']>0
        assert not result.actions and not result.complete_in_original_game


def test_state_resource_limit_is_checked_before_width_selection(tmp_path):
    template,binding=fixture(tmp_path)
    result=solve_dialogue_frontier(template,binding,STATE,controls=(0,2),width=1,max_states=1)
    assert result.reason=='state_budget' and not result.verified
    assert result.stats['motion_states_discarded_by_width']==0
    assert len(result.layers)==1 and not result.parents


@pytest.mark.parametrize('width',[True,0,-1,1.5])
def test_invalid_width_is_rejected(tmp_path,width):
    template,binding=fixture(tmp_path)
    with pytest.raises(ValueError,match='width'):
        solve_dialogue_frontier(template,binding,STATE,width=width)
