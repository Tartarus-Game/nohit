"""A fixed Confirm policy preserves moving hazards and exact motion ancestry."""
import numpy as np
import pytest

from nohit.engine.dialogue_frontier import solve_dialogue_frontier, _padded
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.joint_transition import begin_joint, step_joint


STATE=np.array([320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.])


def fixture(tmp_path,tail='0,EndAttack\n',text='abcdef',hazard=True):
    path=tmp_path/'dialogue.csv'
    path.write_text('0,HeartMode,0\n'+('0,BoneH,0,320,640,0,0\n' if hazard else '')+
        '0.033333,SansText,'+text+',\n'+tail)
    template=ParametricEnvironment(path,dt_schedule=(1/30,)*100,max_ticks=100,
        termination_policy='eof_hazards_drained')
    binding=template.bind()
    assert binding.wave.termination_reason=='dialogue_boundary'
    return template,binding


def test_real_dialogue_ticks_and_hazards_are_not_skipped(tmp_path):
    template,binding=fixture(tmp_path)
    safe=solve_dialogue_frontier(template,binding,STATE,controls=(0,),max_states=1000)
    assert safe.status=='candidate_found' and safe.verified
    assert len(safe.actions)>=7 and safe.end_tick==safe.start_tick+len(safe.actions)
    assert safe.origin_index==0 and safe.confirm==[bool(i%2) for i in range(len(safe.actions))]
    node=begin_joint(template,binding,STATE,previous_input_code=0)
    for index,control in enumerate(safe.controls,1):
        edge=step_joint(template,node,control);assert edge.state is not None
        node=edge.state
        assert np.asarray(node.player).tobytes()==safe.trajectory[index].tobytes()
    assert edge.status=='terminal' and edge.reason=='endattack'
    # Moving toward the still-active floor dies before the text can finish.
    failed=solve_dialogue_frontier(template,binding,STATE,controls=(8,),max_states=1000)
    assert failed.status=='unknown' and failed.reason=='empty_fixed_policy_relation'
    assert failed.end_tick<safe.end_tick


def test_origin_and_parents_refer_to_actual_supplied_states(tmp_path):
    template,binding=fixture(tmp_path,text='a')
    bad=STATE.copy();bad[1]=320.
    initial=np.asarray([bad,STATE]);before=initial.tobytes()
    result=solve_dialogue_frontier(template,binding,initial,controls=(0,),max_states=1000)
    assert result.verified and result.origin_index==1
    assert result.initial_indices.tolist()==[1]
    assert result.trajectory[0].tobytes()==initial[1].tobytes()
    assert initial.tobytes()==before
    index=0
    for pp,mm in zip(reversed(result.parents),reversed(result.masks)):
        assert 0<=index<len(pp) and int(mm[index]) in (0,)
        index=int(pp[index])
    assert result.initial_indices[index]==result.origin_index


@pytest.mark.parametrize('kwargs,reason',[
    ({'max_ticks':0},'tick_budget'),({'max_states':0},'state_budget'),
    ({'seconds':0},'wall_budget'),({'confirm_policy':()},'confirm_policy_exhausted'),
    ({'confirm_policy':(True,)*20,'max_ticks':20},'tick_budget'),
])
def test_limits_and_missing_confirm_edges_are_unknown(tmp_path,kwargs,reason):
    template,binding=fixture(tmp_path,text='abcdef')
    result=solve_dialogue_frontier(template,binding,STATE,**kwargs)
    assert result.status=='unknown' and not result.verified and result.reason==reason


def test_layer_budget_preserves_preceding_complete_relation(tmp_path):
    template,binding=fixture(tmp_path,text='abcdef',hazard=False)
    result=solve_dialogue_frontier(template,binding,STATE,max_states=1)
    assert result.status=='unknown' and result.reason=='state_budget'
    assert len(result.layers)==1 and not result.parents
    assert result.layers[0].tobytes()==STATE.reshape(1,11).tobytes()


@pytest.mark.parametrize('tail,text,reason',[
    ('0,EndAttack\n','a,ArbitraryCallback','unknown'),
])
def test_unknown_world_effects_never_become_endattack(tmp_path,tail,text,reason):
    template,binding=fixture(tmp_path,tail=tail,text=text,hazard=False)
    result=solve_dialogue_frontier(template,binding,STATE)
    assert result.status=='unknown' and not result.verified
    assert result.reason==reason or (reason=='unknown' and 'callback' in result.reason.lower())


def test_explicit_eof_policy_returns_its_real_source_terminal(tmp_path):
    template,binding=fixture(tmp_path,tail='',text='a',hazard=False)
    result=solve_dialogue_frontier(template,binding,STATE)
    assert result.status=='candidate_found' and result.verified
    assert result.reason=='verified_eof_hazards_drained'
    assert result.source_terminal['reason']=='eof_hazards_drained'
    assert not result.original_replay_passed and not result.complete_in_original_game


def test_platform_padding_cannot_create_phantom_active_platforms():
    rows=[np.array([[200.,320.,60.,0.,0.,0.,1.,1.,0.]]),np.empty((0,9))]
    padded=_padded(rows,9,platforms=True)
    assert padded.shape==(2,1,9) and padded[1].tobytes()==np.zeros((1,9)).tobytes()


def test_tick_zero_dialogue_starts_from_pre_tick_zero_and_replays_that_tick(tmp_path):
    path=tmp_path/'at-zero.csv';path.write_text('0,SansText,a,\n0,EndAttack\n')
    template=ParametricEnvironment(path,dt_schedule=(1/30,)*100,max_ticks=100)
    binding=template.bind();assert binding.resume_state.request['tick']==0
    result=solve_dialogue_frontier(template,binding,STATE,controls=(0,))
    assert result.verified and result.start_tick==-1
    assert len(result.actions)==result.end_tick+1
    node=begin_joint(template,binding,STATE,previous_input_code=0)
    for index,control in enumerate(result.controls):
        edge=step_joint(template,node,control);assert edge.state is not None
        node=edge.state
        assert node.environment.frame.tick==index
        assert np.asarray(node.player).tobytes()==result.trajectory[index+1].tobytes()


@pytest.mark.parametrize('kwargs',[
    {'max_ticks':-1},{'max_states':True},{'previous_confirm':1},
    {'controls':(16,)},{'controls':()},{'seconds':-1},
    {'confirm_policy':'skip'},{'confirm_policy':(0,1)},
])
def test_invalid_configuration_is_rejected(tmp_path,kwargs):
    template,binding=fixture(tmp_path)
    with pytest.raises(ValueError):solve_dialogue_frontier(template,binding,STATE,**kwargs)
