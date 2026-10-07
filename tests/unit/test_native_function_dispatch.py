"""Native TLLoadLine storage and nine typed Function arguments are distinct."""
import math

import numpy as np
import pytest

from nohit.engine.compact_wave import TimelineVM
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.resumable_wave import (
    initialize, advance_one_tick, advance_with_dialogue_input, supply_target,
    NeedTarget, NeedDialogue, TickCommitted, Terminal, ResourceLimit,
)
from nohit.engine.timeline_csv import parse_timeline_rows
from nohit.engine.native_function_dispatch import call_arguments


DT = 1 / 30
INITIAL = [100., 200., 500., 400., 0., 1., 0., DT, 750., 0., 320., 304., 0.]


def source(tmp_path, text):
    path = tmp_path / 'dispatch.csv'
    path.write_text(text, encoding='utf-8')
    return path


def compile_case(tmp_path, backend, text, ticks=12):
    return ParametricEnvironment(source(tmp_path, text), backend=backend,
        initial_environment=INITIAL, dt_schedule=(DT,) * ticks,
        max_ticks=ticks, capture_state_keys=True).bind().wave


@pytest.mark.parametrize('backend', ['reference', 'resumable'])
@pytest.mark.parametrize('command,expected', [('HeartMode', 0.), ('SET,key', 0.), ('ADD,key,1', 1.)])
def test_native_missing_scalar_parameters_execute(tmp_path, backend, command, expected):
    wave = compile_case(tmp_path, backend, '0,' + command + '\n0,HeartTeleport,$key,304\n0,EndAttack\n')
    assert wave.complete
    assert wave.env_schedule[0, 4 if command == 'HeartMode' else 10] == expected
    assert len(wave.source_events[0][2]) == 9


@pytest.mark.parametrize('backend', ['reference', 'resumable'])
def test_source_events_retain_nine_loaded_types_and_truncate_only_call(tmp_path, backend):
    text = '0,GasterBlaster,0,320,240,320,240,0,,,GasterBlaster,EXTRA,$not_present\n0.1,EndAttack\n'
    wave = compile_case(tmp_path, backend, text)
    events = [e for e in wave.source_events if e[1] == 'gasterblaster']
    assert len(events) == 1
    assert events[0][2] == ('0', '320', '240', '320', '240', '0', '', '', 'GasterBlaster')
    rows = parse_timeline_rows(text)
    assert rows[0][-2:] == ['EXTRA', '$not_present']


def test_loaded_delay_and_suspension_do_not_reload_or_pad_storage(tmp_path):
    state = initialize(source(tmp_path, '0,SET,key,17\n0.1,GetHeartPos,$key,y\n0,EndAttack\n'),
        initial_environment=INITIAL, dt_schedule=(DT,) * 12, max_ticks=12)
    state = advance_one_tick(state).state
    assert state.data['loaded_line'][2] == ('17', 'y')
    state.vm.vars['key'] = 99.  # Loader contract probe, not a native gameplay action.
    for _ in range(8):
        result = advance_one_tick(state)
        if isinstance(result, NeedTarget):
            break
        state = result.state
    assert isinstance(result, NeedTarget)
    assert result.request['variables'] == ('17', 'y')
    assert result.state.data['loaded_line'][2] == ('17', 'y')
    after = advance_one_tick(supply_target(result, (100., 200.)))
    assert isinstance(after, Terminal)
    assert after.state.vm.vars['17'] == 100.
    event = next(e for e in after.frame.events if e[1] == 'getheartpos')
    assert event[2] == ('17', 'y', 0., 0., 0., 0., 0., 0., 0.)


def test_short_target_call_normalizes_before_suspension(tmp_path):
    state = initialize(source(tmp_path, '0,GetHeartPos\n0,EndAttack\n'), dt_schedule=(DT,) * 4, max_ticks=4)
    result = advance_one_tick(state)
    assert isinstance(result, NeedTarget)
    assert result.request['variables'] == (0., 0.)
    assert result.state.data['loaded_line'][2] == ()
    after = advance_one_tick(supply_target(result, (100., 200.)))
    assert isinstance(after, Terminal)
    assert after.state.vm.vars['0'] == 200.  # Two native writes to the same key.


@pytest.mark.parametrize('backend', ['reference', 'resumable'])
@pytest.mark.parametrize('row,text', [('0,SansText', '0'), ('0,SansText,', ''), ('0,SansText,,', '')])
def test_uncoupled_dialogue_uses_native_text_and_boundary_arguments(tmp_path, backend, row, text):
    wave = compile_case(tmp_path, backend, row + '\n0,EndAttack\n')
    assert wave.termination_reason == 'dialogue_boundary'
    assert wave.terminal_details['pending_dialogue']['text'] == text
    event = next(e for e in wave.source_events if e[1] == 'sanstext')
    assert len(event[2]) == 9
    assert event[2][0] == (0. if row == '0,SansText' else '')


@pytest.mark.parametrize('row,text,callback', [('0,SansText', '0', '0'), ('0,SansText,', '', '0'), ('0,SansText,,', '', 'EndSansText')])
def test_coupled_missing_text_and_callback_zero_have_native_lifecycle(tmp_path, row, text, callback):
    state = initialize(source(tmp_path, row + '\n0,EndAttack\n'), dt_schedule=(DT,) * 6, max_ticks=6)
    one = advance_with_dialogue_input(state, confirm=False, cancel=False, previous_confirm=False, previous_cancel=False)
    assert one.state.dialogue.text == text
    assert one.state.dialogue.end_func == callback
    two = advance_with_dialogue_input(one.state, confirm=True, cancel=False)
    assert isinstance(two, TickCommitted)
    assert not two.state.dialogue.alive
    assert two.state.data['running'] == (callback == 'EndSansText')
    assert two.state.dialogue_blocked_callback is None
    assert two.frame.callback_events[0]['function'] == callback
    three = advance_with_dialogue_input(two.state, confirm=False, cancel=False)
    assert isinstance(three, Terminal if callback == 'EndSansText' else TickCommitted)


@pytest.mark.parametrize('backend', ['reference', 'resumable'])
def test_missing_resize_callback_calls_zero_at_settle_without_resuming(tmp_path, backend):
    wave = compile_case(tmp_path, backend,
        '0,CombatZoneSpeed,60\n0,CombatZoneResize,106,200,500,400\n'
        '0,TLPause\n0,SET,should_not_run,1\n0,EndAttack\n')
    assert not wave.complete and wave.termination_reason == 'tick_budget'
    assert not any(e[1] in ('set', 'endattack') for e in wave.source_events)
    calls = wave.terminal_details['executed_callbacks']
    assert len(calls) == 1 and calls[0]['function'] == '0'
    assert calls[0]['executed_tick'] == 2 and calls[0]['phase'] == 'post_timeline_combatzonetick'
    assert wave.terminal_details['end_resize'] is None
    assert wave.terminal_details['pending_callbacks'] == []


@pytest.mark.parametrize('backend', ['reference', 'resumable'])
@pytest.mark.parametrize('ending,phase', [('', 'post_timeline_combatzonetick'), ('0,CombatZoneResizeInstant,106,200,500,400\n', 'inline_combatzonetick')])
def test_resize_zero_pending_is_visible_and_fires_in_original_phase(tmp_path, backend, ending, phase):
    target = '100' if not ending else '106'
    wave = compile_case(tmp_path, backend, '0,CombatZoneResize,' + target + ',200,500,400\n' + ending + '1,EndAttack\n')
    calls = wave.terminal_details['executed_callbacks']
    assert len(calls) == 1 and calls[0]['function'] == '0'
    assert calls[0]['executed_tick'] == 0 and calls[0]['phase'] == phase
    pending = compile_case(tmp_path, backend, '0,CombatZoneSpeed,60\n0,CombatZoneResize,106,200,500,400\n1,EndAttack\n', ticks=1)
    assert pending.terminal_details['end_resize']['function'] == '0'
    assert pending.terminal_details['pending_callbacks'][0]['status'] == 'awaiting_arena_settle'


@pytest.mark.parametrize('backend', ['reference', 'resumable'])
def test_explicit_empty_resize_callback_replaces_pending_zero(tmp_path, backend):
    wave = compile_case(tmp_path, backend,
        '0,CombatZoneResize,106,200,500,400\n0,CombatZoneResize,106,200,500,400,\n0.2,EndAttack\n')
    assert wave.terminal_details['executed_callbacks'] == []
    assert wave.terminal_details['end_resize'] is None


@pytest.mark.parametrize('row', ['0,BoneVRepeat', '0,BoneHRepeat', '0,PlatformRepeat', '0,SineBones', '0,GasterBlaster'])
def test_missing_complex_command_slots_are_native_numeric_zero(tmp_path, row):
    state = initialize(source(tmp_path, row + '\n1,EndAttack\n'), dt_schedule=(DT,) * 2, max_ticks=2)
    one = advance_one_tick(state)
    assert isinstance(one, TickCommitted)
    assert one.frame.events[0][2] == (0.,) * 9


def test_repeat_missing_numeric_local_and_explicit_empty_remain_distinct(tmp_path):
    xs = []
    for row in ('0,BoneVRepeat', '0,BoneVRepeat,'):
        state = initialize(source(tmp_path, row + '\n1,EndAttack\n'), dt_schedule=(DT,) * 2, max_ticks=2)
        one = advance_one_tick(state)
        assert len(one.state.data['active_bones']) == 2  # Original descending inclusive For(0,-1).
        xs.append(one.state.data['active_bones'][0].x)
    assert xs[0] == 0. and math.isnan(xs[1])


def test_call_view_preserves_types_signed_zero_and_all_loaded_storage():
    vm = TimelineVM()
    vm.vars.update(zero=-0., literal='$other', extra=17.)
    tokens = ('$zero', '$literal', '', '0', 1., '5', '6', '7', '8', '$extra')
    # load_line's input is source tokens; present values after loading remain typed.
    tokens = tuple(str(x) if not isinstance(x, str) else x for x in tokens)
    loaded = vm.load_line(('0', None, 'GasterBlaster', 'gasterblaster', tokens))
    vm.vars.update(zero=99., other=123., extra=88.)
    args = call_arguments(loaded[2])
    assert len(loaded[2]) == 10 and loaded[2][-1] == 17.
    assert len(args) == 9 and type(args[0]) is float and np.signbit(args[0])
    assert args[1:4] == ('$other', '', '0')
    assert call_arguments(('', '0', 0, -0.))[:4] == ('', '0', 0, -0.)
    assert type(call_arguments(('', '0', 0, -0.))[2]) is int
    assert all(type(x) is float and not np.signbit(x) for x in call_arguments(())[0:])


def test_callback_zero_is_not_trusted_when_original_source_identity_is_unverified(tmp_path, monkeypatch):
    from nohit.engine import native_function_dispatch as dispatch
    monkeypatch.setattr(dispatch, '_original_registry_matches', lambda: False)
    assert not dispatch.audited_no_action_function('0')
    state = initialize(source(tmp_path, '0,SansText,a\n0,EndAttack\n'), dt_schedule=(DT,) * 4, max_ticks=4)
    result = advance_with_dialogue_input(state, confirm=True, cancel=False, previous_confirm=False, previous_cancel=False)
    assert isinstance(result, ResourceLimit) and result.reason == 'unsupported_dialogue_callback:0'
    assert not result.state.data['ended']


@pytest.mark.parametrize('backend', ['reference', 'resumable'])
def test_initial_native_zero_resize_callback_stays_pending_until_settle(tmp_path, backend):
    wave = ParametricEnvironment(source(tmp_path, '0,TLPause\n1,EndAttack\n'), backend=backend,
        initial_environment=INITIAL, initial_arena={'target': [106., 200., 500., 400.],
            'size': [400., 200.], 'speed': 60., 'callback': '0'},
        dt_schedule=(DT,) * 6, max_ticks=6).bind().wave
    assert not wave.complete and wave.termination_reason == 'tick_budget'
    calls = wave.terminal_details['executed_callbacks']
    assert len(calls) == 1 and calls[0]['function'] == '0' and calls[0]['source_line'] is None
    assert calls[0]['executed_tick'] == 2
    assert wave.terminal_details['pending_callbacks'] == []


def test_destroyed_last_dialogue_with_zero_callback_can_reach_real_eof(tmp_path):
    state = initialize(source(tmp_path, '0,SansText,a'), termination_policy='eof_hazards_drained',
        dt_schedule=(DT,) * 4, max_ticks=4)
    result = advance_with_dialogue_input(state, confirm=True, cancel=False, previous_confirm=False, previous_cancel=False)
    assert isinstance(result, Terminal) and result.reason == 'eof_hazards_drained'
    assert not result.state.data['running'] and not result.state.dialogue.alive
    assert result.state.dialogue_blocked_callback is None
