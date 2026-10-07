import pytest

from nohit.engine.dialogue_operator import CHAR_PERIOD, DialogueState, step_dialogue, utf16_length


def test_one_character_per_event_even_with_accumulated_time():
    s=DialogueState('abc',t=1.)
    result=step_dialogue(s,1/240)
    assert result.state.current_char==1
    assert result.state.t==(1.+1/240)-CHAR_PERIOD
    assert s.current_char==0


def test_new_text_ticks_in_its_creation_ticks_rpgtext_phase():
    s=DialogueState('a')
    for _ in range(7):s=step_dialogue(s,1/240).state
    assert s.current_char==0
    result=step_dialogue(s,1/240,confirm=True)
    assert result.state.current_char==1
    assert result.destroyed and result.callback=='EndSansText'


def test_held_confirm_does_not_close_and_a_new_edge_does():
    s=DialogueState('x',current_char=1)
    assert not step_dialogue(s,1/240,confirm=True,previous_confirm=True).destroyed
    result=step_dialogue(s,1/240,confirm=True)
    assert result.destroyed
    assert step_dialogue(result.state,1/240,confirm=True).callback is None


def test_simultaneous_confirm_cancel_only_skips_an_incomplete_line():
    result=step_dialogue(DialogueState('abc'),1/240,confirm=True,cancel=True)
    assert not result.destroyed and result.state.current_char==3 and result.state.t==0.
    held=step_dialogue(result.state,1/240,confirm=True,previous_confirm=True,cancel=True,previous_cancel=True)
    assert not held.destroyed
    assert step_dialogue(held.state,1/240,confirm=True).destroyed


def test_confirm_can_close_on_the_tick_that_reveals_last_character():
    result=step_dialogue(DialogueState('abc',current_char=2,t=CHAR_PERIOD-1/240),1/240,confirm=True)
    assert result.destroyed


def test_utf16_units_and_literal_spaces_match_javascript_len_left():
    assert utf16_length('😀')==2
    one=step_dialogue(DialogueState('😀'),CHAR_PERIOD).state
    assert one.current_char==1 and one.displayed_text=='\ud83d'
    two=step_dialogue(one,CHAR_PERIOD).state
    assert two.displayed_text=='😀'
    assert DialogueState('You have no other way             out of this!').length==46


def test_empty_line_requires_confirm_edge_and_opaque_callback_is_not_executed():
    s=DialogueState('',end_func='SomeCallback')
    assert not step_dialogue(s,1/240).destroyed
    assert step_dialogue(s,1/240,confirm=True).callback=='SomeCallback'
    assert step_dialogue(DialogueState('',end_func=''),0.,confirm=True).callback is None


def test_noninteractive_timeout_starts_on_same_phase_as_final_character():
    s=DialogueState('a',t=CHAR_PERIOD,interactive=False,timeout=.01,end_func='Expire')
    one=step_dialogue(s,.004)
    assert one.state.timeout==.006 and not one.destroyed
    two=step_dialogue(one.state,.01)
    assert two.destroyed and two.callback=='Expire'
    assert not step_dialogue(DialogueState('',interactive=False,timeout=0.),1.).destroyed


@pytest.mark.parametrize('dt',[-1.,float('nan'),float('inf')])
def test_invalid_time_rejected(dt):
    with pytest.raises(ValueError):step_dialogue(DialogueState('x'),dt)
