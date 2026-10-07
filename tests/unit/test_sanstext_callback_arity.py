"""Missing Timeline cells are numeric zero; explicit empty cells are strings."""
import pytest

from nohit.engine.csv_solver import solve_csv
from nohit.engine.compact_wave import compile_wave
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.resumable_wave import (
    initialize,advance_with_dialogue_input,TickCommitted,Terminal,ResourceLimit,
)


PREFIX=('0,CombatZoneResizeInstant,32,240,608,384\n'
        '0,HeartTeleport,320,320\n0,HeartMode,0\n')
INITIAL=[320.,320.,0.,0.,0.,0.,0.,1.,750.,0.,0.]


@pytest.mark.parametrize('callback,expected',[('', 'EndSansText'),(None,'0'),('0','0'),('$missing','0')])
def test_callback_uses_native_missing_cell_value(tmp_path,callback,expected):
    row='0,SansText,a'+('' if callback is None else ','+callback)+'\n'
    path=tmp_path/'callback.csv';path.write_text(row+'0,EndAttack\n',encoding='utf-8')
    state=initialize(path,dt_schedule=(1/30,)*20,max_ticks=20)
    result=advance_with_dialogue_input(state,confirm=True,cancel=False,
        previous_confirm=False,previous_cancel=False)
    assert result.state.dialogue.end_func==expected
    if expected=='EndSansText':
        assert isinstance(result,TickCommitted) and result.state.data['running']
        after=advance_with_dialogue_input(result.state,confirm=False,cancel=False)
        assert isinstance(after,Terminal) and after.reason=='endattack'
    else:
        assert isinstance(result,TickCommitted)
        assert not result.state.data['running']
        assert result.state.phase=='committed'
        assert result.state.dialogue_blocked_callback is None
        assert not result.state.dialogue.alive
        assert result.frame.callback_events[0]['function']=='0'
        assert not result.state.data['ended']


def test_native_short_csv_without_callback_never_gets_a_false_candidate(tmp_path):
    path=tmp_path/'short-native.csv'
    path.write_text(PREFIX+'0.1,SansText,a\n0,EndAttack\n',encoding='utf-8')
    missing=solve_csv(path,INITIAL,dt_schedule=(1/30,)*100,max_ticks=100,width=10)
    assert missing['status']=='unknown' and not missing['verified']
    assert missing['reason']=='tick_budget'
    assert missing['actions']==[] and not missing['deadlock_proven']
    path.write_text(PREFIX+'0.1,SansText,a,\n0,EndAttack\n',encoding='utf-8')
    explicit=solve_csv(path,INITIAL,dt_schedule=(1/30,)*100,max_ticks=100,width=10)
    assert explicit['status']=='candidate_found' and explicit['verified']
    assert len(explicit['actions'])==5
    assert not explicit['original_replay_passed']


def test_quoted_empty_callback_is_literal_native_text_not_a_default_callback(tmp_path):
    path=tmp_path/'quoted-callback.csv'
    path.write_text(PREFIX+'0.1,SansText,a,""\n0,EndAttack\n',encoding='utf-8')
    result=solve_csv(path,INITIAL,dt_schedule=(1/30,)*100,max_ticks=100,width=10)
    assert result['status']=='unknown' and not result['verified']
    assert result['reason']=='unsupported_dialogue_callback:""'
    assert result['actions']==[]


def test_quoted_comma_does_not_merge_native_timeline_cells(tmp_path):
    path=tmp_path/'quoted-comma.csv'
    path.write_text('0,SansText,"a,b",\n0,EndAttack\n',encoding='utf-8')
    state=initialize(path,dt_schedule=(1/30,)*20,max_ticks=20)
    one=advance_with_dialogue_input(state,confirm=False,cancel=False,
        previous_confirm=False,previous_cancel=False)
    assert one.state.dialogue.text=='"a'
    assert one.state.dialogue.end_func=='b"'
    two=advance_with_dialogue_input(one.state,confirm=True,cancel=False)
    assert isinstance(two,ResourceLimit) and two.reason=='unsupported_dialogue_callback:b"'
    # Both world implementations must agree on the pending native text cell.
    for backend in ('reference','resumable'):
        wave=ParametricEnvironment(path,backend=backend,dt_schedule=(1/30,)*20,max_ticks=20).bind().wave
        assert wave.terminal_details['pending_dialogue']['text']=='"a'
    wave=compile_wave(path,allow_partial=True,dt_schedule=(1/30,)*20,max_ticks=20)
    assert wave.terminal_details['pending_dialogue']['text']=='"a'
