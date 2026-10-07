"""A CSV candidate must include dialogue, ancestry and the actual tick clock."""
import json

import numpy as np
import pytest

from nohit.engine.csv_solver import solve_csv
from nohit.engine.compact_wave import native_fixed_dt


INITIAL = [320., 304., 0., 0., 0., 0., 0., 1., 750., 0., 0.]


def source(tmp_path, text):
    path = tmp_path / 'wave.csv'
    path.write_text(text, encoding='utf-8')
    return path


def check_candidate(result):
    assert result['status'] == 'candidate_found' and result['verified']
    n = len(result['actions'])
    assert len(result['trajectory']) == n + 1
    assert len(result['confirm_sequence']) == n
    assert len(result['dt_sequence']) == n + 1
    assert result['unified_controls'] == [
        mask | (32 if confirm else 0)
        for mask, confirm in zip(result['actions'], result['confirm_sequence'])]
    assert not result['deadlock_proven'] and not result['optimality_proven']
    assert not result['original_replay_passed']
    assert not result['complete_in_original_game']
    json.dumps(result, allow_nan=False)


def test_complete_csv_without_dialogue(tmp_path):
    path = source(tmp_path, '0,HeartMode,0\n0.1,EndAttack\n')
    result = solve_csv(path, INITIAL, dt_schedule=(1/30,)*100,
                       max_ticks=100, width=10)
    check_candidate(result)
    assert not any(result['confirm_sequence'])
    assert result['physics_hz'] == 30


def test_observed_prefix_and_two_dialogues_form_one_route(tmp_path):
    path = source(tmp_path, '0,HeartMode,0\n0.1,GetHeartPos,x,y\n'
                  '0,BoneV,$x,100,12,0,0\n0.1,SansText,abc,\n'
                  '0,SansText,def,\n0,EndAttack\n')
    result = solve_csv(path, INITIAL, dt_schedule=(1/30,)*100,
                       max_ticks=100, width=10, max_bindings=2)
    check_candidate(result)
    assert len(result['target_history']) == 1
    assert any(result['confirm_sequence'])
    assert result['dialogue_start_tick'] < result['reached_tick']
    assert result['reached_tick'] == len(result['actions'])
    assert result['prefix_verification_seconds'] > 0


def test_target_read_on_dialogue_tick_keeps_its_real_origin(tmp_path):
    path = source(tmp_path, '0,HeartMode,0\n0.1,GetHeartPos,x,y\n'
                  '0,SansText,a,\n0,EndAttack\n')
    result = solve_csv(path, INITIAL, dt_schedule=(1/30,)*100,
                       max_ticks=100, width=10, max_bindings=2)
    check_candidate(result)
    assert result['target_history'][0][0] == result['dialogue_start_tick'] + 1


@pytest.mark.parametrize('options', [
    {'dialogue_max_ticks': 0}, {'dialogue_max_states': 0},
    {'dt_schedule': (1/30,)*5}, {'seconds': 0},
])
def test_limits_never_publish_a_partial_route_as_success(tmp_path, options):
    path = source(tmp_path, '0,HeartMode,0\n0.1,SansText,abcdefgh\n0,EndAttack\n')
    settings = dict(dt_schedule=(1/30,)*100, max_ticks=100, width=10)
    settings.update(options)
    result = solve_csv(path, INITIAL, **settings)
    assert result['status'] == 'unknown' and not result['verified']
    assert result['actions'] == [] and not result['deadlock_proven']


def test_native_timestamp_clock_is_exported_without_relabeling(tmp_path):
    path = source(tmp_path, '0,HeartMode,0\n0.04,EndAttack\n')
    start = 971260.6666634805
    result = solve_csv(path, INITIAL, clock_start_ms=start, max_ticks=100, width=1)
    check_candidate(result)
    n = len(result['actions']) + 1
    assert np.asarray(result['dt_sequence']).tobytes() == np.asarray(native_fixed_dt(start, 100)[:n]).tobytes()
    assert result['clock_start_ms'] == start


def test_varying_clock_keeps_each_physical_tick(tmp_path):
    path = source(tmp_path, '0,HeartMode,0\n0.1,EndAttack\n')
    schedule = (1/30, 1/60)*50
    result = solve_csv(path, INITIAL, dt_schedule=schedule, max_ticks=100, width=1)
    check_candidate(result)
    assert result['physics_hz'] is None
    assert result['dt_sequence'] == list(schedule[:len(result['actions'])+1])


def test_initial_text_primes_world_without_repeating_observed_player_movement(tmp_path):
    path=source(tmp_path,'0,SansText,a,\n0,EndAttack\n')
    initial=INITIAL.copy();initial[2]=75.
    result=solve_csv(path,initial,dt_schedule=(1/30,)*100,max_ticks=100,width=1)
    check_candidate(result)
    assert result['primed_initial_frame'] and result['dialogue_start_tick']==0
    assert result['trajectory'][0]==initial


def test_dialogue_remainder_respects_global_tick_budget(tmp_path):
    path=source(tmp_path,'0.03333333333333333,SansText,a,\n9,EndAttack\n')
    result=solve_csv(path,INITIAL,dt_schedule=(1/30,)*400,max_ticks=400,width=1)
    check_candidate(result)
    assert result['reached_tick']>256
