"""Source-phase tests for explicit dialogue input plus continuing world ticks."""
import pickle
from dataclasses import replace

import numpy as np
import pytest

from nohit.engine.resumable_wave import (
    initialize,advance_one_tick,advance_with_dialogue_input,supply_target,
    state_environment_key,TickCommitted,NeedDialogue,NeedTarget,Terminal,ResourceLimit,
)
from nohit.engine.discrete_operator import step_mask_into


def make_state(tmp_path,text,dt=1/30,max_ticks=100):
    path=tmp_path/'dialogue.csv';path.write_text(text)
    return initialize(path,termination_policy='eof_hazards_drained',
        dt_schedule=[dt]*max_ticks,max_ticks=max_ticks)


def step(state,confirm=False,cancel=False):
    options={} if state.dialogue_coupled else dict(previous_confirm=False,previous_cancel=False)
    return advance_with_dialogue_input(state,confirm=confirm,cancel=cancel,**options)


def test_two_source_lines_require_fresh_edges_and_never_freeze_world(tmp_path):
    state=make_state(tmp_path,'0,BoneV,100,100,20,0,30\n0,SansText,ab,\n'
                     '0,SansText,c,\n0,Set,after,1\n0,EndAttack\n')
    expected_chars=[1,2,1,1,1]
    expected_running=[False,True,False,False,True]
    snapshots=[]
    for tick,confirm in enumerate([False,True,True,False,True]):
        before=pickle.dumps(state)
        result=step(state,confirm)
        assert pickle.dumps(state)==before
        assert isinstance(result,TickCommitted)
        state=result.state;snapshots.append(state)
        assert state.dialogue.current_char==expected_chars[tick]
        assert state.data['running']==expected_running[tick]
        assert state.data['time_acc']==0. # TLResume cannot advance this tick's Timeline T
        assert state.data['active_bones'][0].x==101.+tick
        assert 'after' not in state.vm.vars
        assert result.frame.dialogue_input==(confirm,False)
    result=step(state)
    assert isinstance(result,Terminal)
    assert result.state.vm.vars['after']=='1'
    assert [event[1] for event in result.frame.events]==['set','endattack']
    assert snapshots[0].dialogue.current_char==1
    assert snapshots[0].data['active_bones'][0].x==101.


def test_default_boundary_can_be_entered_without_reexecuting_prior_commands(tmp_path):
    state=make_state(tmp_path,'0,Set,count,1\n0,SansText,x,\n0,Add,count,$count,1\n0,EndAttack\n')
    boundary=advance_one_tick(state)
    assert isinstance(boundary,NeedDialogue)
    assert boundary.state.stats['commands_executed']==1
    snapshot=pickle.dumps(boundary.state)
    closed=step(boundary.state,True)
    assert closed.state.stats['commands_executed']==2
    assert closed.state.data['running'] and not closed.state.dialogue.alive
    assert pickle.dumps(boundary.state)==snapshot
    complete=step(closed.state,False)
    assert isinstance(complete,Terminal)
    assert complete.state.vm.vars['count']==2.


def test_input_required_never_invents_a_confirm_or_advances_clock(tmp_path):
    state=make_state(tmp_path,'0,SansText,ab\n0,EndAttack\n')
    with pytest.raises(ValueError,match='previous Confirm'):
        advance_with_dialogue_input(state,confirm=False,cancel=False)
    state=step(state).state
    before=pickle.dumps(state)
    waiting=advance_one_tick(state)
    assert isinstance(waiting,NeedDialogue) and waiting.request['kind']=='input_required'
    assert waiting.state.data['tick']==state.data['tick']
    assert pickle.dumps(state)==before


def test_confirm_held_before_first_dialogue_is_not_a_false_edge(tmp_path):
    state=make_state(tmp_path,'0,SansText,x\n0,EndAttack\n')
    result=advance_with_dialogue_input(state,confirm=True,cancel=False,previous_confirm=True,previous_cancel=False)
    assert result.state.dialogue.alive
    assert result.state.dialogue.current_char==1
    assert step(step(result.state,False).state,True).state.dialogue.alive is False


def test_simultaneous_skip_and_confirm_does_not_dismiss_partial_text(tmp_path):
    state=make_state(tmp_path,'0,SansText,long text\n0,EndAttack\n',dt=1/240)
    result=step(state,True,True)
    assert result.state.dialogue.alive
    assert result.state.dialogue.current_char==9
    held=step(result.state,True,True)
    assert held.state.dialogue.alive
    released=step(held.state)
    assert not step(released.state,True).state.dialogue.alive


def test_target_suspension_retains_same_tick_dialogue_inputs(tmp_path):
    state=make_state(tmp_path,'0,GetHeartPos,x,y\n0,SansText,x,\n0,EndAttack\n')
    pending=step(state,True)
    assert isinstance(pending,NeedTarget)
    resumed=supply_target(pending,(200.,300.))
    with pytest.raises(ValueError,match='cannot change input'):
        step(resumed,False)
    result=step(resumed,True)
    assert result.frame.target_history==((0,1,200.,300.),)
    assert not result.state.dialogue.alive


def test_exact_keys_include_text_progress_and_previous_input(tmp_path):
    state=step(make_state(tmp_path,'0,SansText,abc\n0,EndAttack\n')).state
    a=state.clone();a.dialogue=replace(a.dialogue,current_char=2)
    b=state.clone();b.dialogue_last_input=(True,False)
    assert len({state_environment_key(s) for s in (state,a,b)})==3


def test_eof_does_not_complete_while_text_is_alive(tmp_path):
    state=make_state(tmp_path,'0,SansText,x,\n')
    result=step(state)
    assert isinstance(result,TickCommitted)
    assert not result.state.data['ended']
    closed=step(result.state,True)
    assert isinstance(closed,TickCommitted) and not closed.state.dialogue.alive
    # Native newline tokenization retains the trailing empty source line;
    # it can only be consumed by Timeline after the dialogue callback.
    ended=step(closed.state)
    assert isinstance(ended,Terminal) and ended.reason=='eof_hazards_drained'


def test_unknown_callback_blocks_instead_of_faking_tlresume(tmp_path):
    state=make_state(tmp_path,'0,SansText,x,ArbitraryCallback\n0,EndAttack\n')
    result=step(state,True)
    assert isinstance(result,ResourceLimit)
    assert not result.state.data['running']
    assert result.state.phase=='await_dialogue_callback'
    assert result.state.data['callback_events']==[]
    assert result.state.data['unproven_callbacks'][0]['function']=='ArbitraryCallback'
    stopped=advance_one_tick(result.state)
    assert isinstance(stopped,ResourceLimit)
    assert stopped.reason=='unsupported_dialogue_callback:ArbitraryCallback'


def test_player_and_bones_continue_during_timeline_pause(tmp_path):
    initial=[0,0,640,480,0,1,0,1/240,750,0,320,304,0,0,0,0,640,480,0,0,640,480]
    path=tmp_path/'moving.csv';path.write_text('0,BoneV,100,100,20,0,120\n0,SansText,long text\n0,EndAttack\n')
    state=initialize(path,initial_environment=initial,termination_policy='eof_hazards_drained')
    player=np.array([320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.])
    for _ in range(8):
        result=step(state);state=result.state
        step_mask_into(player,2,result.frame.env,result.frame.platforms,player)
    assert state.data['running'] is False
    assert state.data['active_bones'][0].x==104.
    assert player[0]>320. and player[2]==150.
    assert state.dialogue.current_char==1
