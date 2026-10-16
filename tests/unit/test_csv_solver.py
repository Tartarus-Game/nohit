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


def test_explicit_observation_segments_report_actual_wall_budget_exhaustion(tmp_path):
    path=source(tmp_path,'0,HeartMode,0\n0.1,GetHeartPos,x,y\n0.1,EndAttack\n')
    result=solve_csv(path,INITIAL,dt_schedule=(1/60,)*100,max_ticks=100,
        width=4,seconds=1e-9,observation_chunk_ticks=6,observation_preview_ticks=6)
    assert result['status']=='unknown' and result['verified'] is False
    assert result['reason']=='native_observation_budget'
    assert not result['deadlock_proven'] and result['actions']==[]
    assert result['clock']['schedule_count']==100


def test_explicit_observation_segments_do_not_call_tick_exhaustion_a_wall_budget(tmp_path):
    path=source(tmp_path,'0,HeartMode,0\n0.1,GetHeartPos,x,y\n0.1,EndAttack\n')
    result=solve_csv(path,INITIAL,dt_schedule=(1/60,)*100,max_ticks=1,
        width=4,seconds=5,observation_chunk_ticks=6,observation_preview_ticks=6)
    assert result['status']=='unknown' and result['verified'] is False
    assert result['reason']=='native_scope_or_resource_limit'


def test_explicit_observation_segments_keep_unidentified_backend_scope_separate(tmp_path,monkeypatch):
    from nohit.engine import native_dynamic
    monkeypatch.setattr(native_dynamic,'find_native_candidate',lambda *args,**kwargs:None)
    path=source(tmp_path,'0,HeartMode,0\n0.1,GetHeartPos,x,y\n0.1,EndAttack\n')
    result=solve_csv(path,INITIAL,dt_schedule=(1/60,)*100,max_ticks=100,
        width=4,seconds=5,observation_chunk_ticks=6,observation_preview_ticks=6)
    assert result['status']=='unknown' and result['reason']=='native_scope_or_resource_limit'


def test_explicit_observation_segments_preserve_a_bounded_search_failure(tmp_path,monkeypatch):
    from nohit.engine import native_dynamic
    def limited(path,initial,**settings):
        return native_dynamic._unknown_candidate(initial,settings,'native_search_limited')
    monkeypatch.setattr(native_dynamic,'find_native_candidate',limited)
    path=source(tmp_path,'0,HeartMode,0\n0.1,GetHeartPos,x,y\n0.1,EndAttack\n')
    result=solve_csv(path,INITIAL,dt_schedule=(1/60,)*100,max_ticks=100,
        width=4,seconds=5,observation_chunk_ticks=6,observation_preview_ticks=6)
    assert result['status']=='unknown' and result['reason']=='native_search_limited'
    assert result['verified'] is False and result['actions']==[]


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
                       max_ticks=100, width=10)
    check_candidate(result)
    assert len(result['target_history']) == 1
    assert any(result['confirm_sequence'])
    assert result['dialogue_start_tick'] < result['reached_tick']
    assert result['reached_tick'] == len(result['actions'])
    assert result.get('prefix_verification_seconds',result['search_stats']['verification_seconds']) > 0


def test_target_read_on_dialogue_tick_keeps_its_real_origin(tmp_path):
    path = source(tmp_path, '0,HeartMode,0\n0.1,GetHeartPos,x,y\n'
                  '0,SansText,a,\n0,EndAttack\n')
    result = solve_csv(path, INITIAL, dt_schedule=(1/30,)*100,
                       max_ticks=100, width=10)
    check_candidate(result)
    assert result['target_history'][0][0] == result['dialogue_start_tick'] + 1


@pytest.mark.parametrize('options', [
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


def test_short_chunks_preview_many_target_reads_and_preserve_a_fixed_prefix(tmp_path):
    path=source(tmp_path,'0,HeartMode,0\n0.2,GetHeartPos,x,y\n'+
        '0,GetHeartPos,x,y\n'*12+'0.2,SansText,a,\n0.2,GetHeartPos,x,y\n0.2,EndAttack\n')
    settings=dict(dt_schedule=(1/60,)*160,max_ticks=160,width=8,seconds=5)
    baseline=solve_csv(path,INITIAL,**settings)
    check_candidate(baseline)
    count=5
    prefix=dict(csv_sha256=baseline['csv_sha256'],actions=baseline['actions'][:count],
        trajectory=baseline['trajectory'][:count+1],confirm_sequence=baseline['confirm_sequence'][:count])
    result=solve_csv(path,INITIAL,**settings,observation_chunk_ticks=6,
        observation_preview_ticks=40,observation_preview_reads=128,fixed_prefix=prefix)
    check_candidate(result)
    assert result['actions'][:count] == prefix['actions']
    assert np.asarray(result['trajectory'][:count+1]).tobytes() == np.asarray(prefix['trajectory']).tobytes()
    assert result['target_history'] == baseline['target_history']
    assert result['search_stats']['fixed_prefix_ticks'] == count
    assert result['search_stats']['observation_preview_reads'] == 128
    assert max(row['preview_target_reads'] for row in result['search_stats']['observation_search_audit']) > 8
    assert all(type(row[2]) is float and type(row[3]) is float for row in result['target_history'])

    prefix['trajectory'][2][0] += 1e-8
    rejected=solve_csv(path,INITIAL,**settings,observation_chunk_ticks=6,fixed_prefix=prefix)
    assert rejected['status'] == 'unknown' and not rejected['verified']


def test_fixed_prefix_from_a_different_csv_is_rejected(tmp_path):
    path=source(tmp_path,'0,HeartMode,0\n0.2,EndAttack\n')
    prefix=dict(csv_sha256='another-source',actions=[],trajectory=[INITIAL],confirm_sequence=[])
    with pytest.raises(ValueError,match='source hash'):
        solve_csv(path,INITIAL,dt_schedule=(1/30,)*100,max_ticks=100,fixed_prefix=prefix)


@pytest.mark.parametrize('text',['0,EndAttack\n','0,HeartMode,0\n0.2,EndAttack\n'])
def test_chunked_search_can_independently_certify_an_entire_fixed_word(tmp_path,text):
    path=source(tmp_path,text)
    settings=dict(dt_schedule=(1/30,)*100,max_ticks=100,width=4)
    baseline=solve_csv(path,INITIAL,**settings)
    check_candidate(baseline)
    result=solve_csv(path,INITIAL,**settings,observation_chunk_ticks=6,
        observation_preview_ticks=20,fixed_prefix=baseline)
    check_candidate(result)
    assert result['actions'] == baseline['actions']
    assert result['confirm_sequence'] == baseline['confirm_sequence']
    assert np.asarray(result['trajectory']).tobytes() == np.asarray(baseline['trajectory']).tobytes()


@pytest.mark.parametrize('mask',[16,17,31])
def test_fixed_prefix_rejects_cancel_even_when_its_scalar_trajectory_matches(tmp_path,mask):
    from nohit.engine.parametric_environment import ParametricEnvironment
    from nohit.engine.source_oracle import scalar_module
    path=source(tmp_path,'0,HeartMode,0\n0.2,EndAttack\n')
    settings=dict(dt_schedule=(1/30,)*100,max_ticks=100,width=4)
    baseline=solve_csv(path,INITIAL,**settings)
    check_candidate(baseline)
    wave=ParametricEnvironment(path,dt_schedule=settings['dt_schedule'],max_ticks=100).bind().wave
    player=scalar_module('discrete_operator')
    physical=player.initial_state(INITIAL,wave.env_schedule[0])
    actions=[mask]+baseline['actions'][1:]
    trajectory=[physical.copy()]
    for tick,control in enumerate(actions,1):
        player.step_mask_into(physical,control,wave.env_schedule[tick],wave.platform_table[tick],physical)
        trajectory.append(physical.copy())
    prefix=dict(csv_sha256=baseline['csv_sha256'],actions=actions,
        trajectory=np.asarray(trajectory).tolist(),confirm_sequence=baseline['confirm_sequence'])
    with pytest.raises(ValueError,match='invalid fixed prefix witness'):
        solve_csv(path,INITIAL,**settings,fixed_prefix=prefix)


@pytest.mark.parametrize('previous_mask',[16,31])
def test_fixed_prefix_keeps_observed_cancel_latch_but_emits_only_arrows(tmp_path,previous_mask):
    path=source(tmp_path,'0,HeartMode,0\n0.2,EndAttack\n')
    initial=INITIAL.copy();initial[4]=float(previous_mask)
    settings=dict(dt_schedule=(1/30,)*100,max_ticks=100,width=4)
    baseline=solve_csv(path,initial,**settings)
    check_candidate(baseline)
    assert all(0 <= mask <= 15 for mask in baseline['actions'])
    result=solve_csv(path,initial,**settings,fixed_prefix=baseline)
    check_candidate(result)
    assert result['trajectory'][0][4] == previous_mask
    assert np.asarray(result['trajectory']).tobytes() == np.asarray(baseline['trajectory']).tobytes()
