"""Opt-in environment edges carry explicit Confirm, never infer text skipping."""
import pickle

import numpy as np
import pytest

from nohit.engine.dialogue_operator import split_control
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.discrete_operator import step_mask_into


def setup(tmp_path,source):
    path=tmp_path/'controlled.csv';path.write_text(source)
    template=ParametricEnvironment(path,termination_policy='eof_hazards_drained',max_ticks=100)
    baked=template.bind()
    assert baked.wave.termination_reason=='dialogue_boundary'
    return template,baked,template.begin_controlled(baked,previous_input_code=0)


def test_confirm_has_an_independent_bit_and_does_not_move_player(tmp_path):
    template,baked,parent=setup(tmp_path,'0,HeartMode,0\n0,SansText,a,\n0,EndAttack\n')
    state=np.array([320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.])
    for tick in range(8):
        control=32 if tick==7 else 0
        movement,confirm,cancel=split_control(control)
        assert movement==0 and confirm==(tick==7) and not cancel
        child=template.step_controlled(parent,control)
        assert child.frame is not None and child.status=='ready'
        step_mask_into(state,movement,child.frame.env,child.frame.platforms,state)
        parent=child
    assert not parent.state.dialogue.alive
    assert state[0]==320. and state[1]==304.
    assert template.step_controlled(parent,0).status=='terminal'


def test_controlled_siblings_preserve_checkpoint_and_cache_distinct_inputs(tmp_path):
    template,baked,parent=setup(tmp_path,'0,SansText,abc\n0,EndAttack\n')
    snapshot=pickle.dumps((baked,parent))
    skip=template.step_controlled(parent,16,allow_cancel=True)
    wait=template.step_controlled(parent,0)
    assert skip.state.dialogue.current_char==3 and skip.state.dialogue.alive
    assert wait.state.dialogue.current_char==0
    assert pickle.dumps((baked,parent))==snapshot
    assert skip.identity!=wait.identity
    assert template.step_controlled(parent,0) is wait
    with pytest.raises(ValueError,match='Cancel'):
        template.step_controlled(parent,16) # domain check also applies to a cached edge


def test_target_observation_after_dialogue_keeps_confirm_transaction(tmp_path):
    template,baked,parent=setup(tmp_path,'0,SansText,a,\n0,GetHeartPos,x,y\n0,SansText,b,\n0,EndAttack\n')
    for _ in range(7):parent=template.step_controlled(parent,0)
    parent=template.step_controlled(parent,32)
    pending=template.step_controlled(parent,32)
    assert pending.status=='need_target'
    assert pending.frame is None
    with pytest.raises(ValueError,match='supply pending target'):
        template.step_controlled(pending,0)
    child=template.supply_controlled_target(pending,250.,300.)
    assert child.frame.target_history==((8,2,250.,300.),)
    assert child.state.dialogue.text=='b' and child.state.dialogue.alive
    assert child.state.dialogue_last_input==(True,False)
    assert template.supply_controlled_target(pending,250.,300.) is child


def test_tiny_graph_search_uses_confirm_edges_and_advances_every_wait_tick(tmp_path):
    template,baked,start=setup(tmp_path,'0,SansText,a,\n0,SansText,b,\n0,EndAttack\n')
    # Exact-state memoization on this fixture discards only bit-identical
    # worlds; scores or dialogue length never stand in for state equality.
    from nohit.engine.resumable_wave import state_environment_key
    frontier=[(start,[])];seen=set();answer=None
    for _ in range(20):
        next_frontier=[]
        for parent,path in frontier:
            for control in (0,32):
                child=template.step_controlled(parent,control)
                assert child.frame is not None
                if child.status=='terminal':answer=path+[control];break
                key=state_environment_key(child.state)
                if key not in seen:
                    seen.add(key);next_frontier.append((child,path+[control]))
            if answer is not None:break
        if answer is not None:break
        frontier=next_frontier
    assert answer is not None and len(answer)==17
    assert answer.count(32)>=2
    # Replay all 17 source ticks, including all 16 text ticks; no virtual
    # macro-edge jumps directly from the first SansText to EndAttack.
    node=start;events=[]
    for tick,control in enumerate(answer):
        node=template.step_controlled(node,control)
        assert node.frame.tick==tick
        events.extend(node.frame.events)
    assert [e[1] for e in events]==['sanstext','sanstext','endattack']


@pytest.mark.parametrize('control',[-1,64,True,1.5])
def test_invalid_unified_controls_rejected(control):
    with pytest.raises(ValueError):split_control(control)
