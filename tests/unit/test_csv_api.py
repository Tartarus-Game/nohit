"""Direct CSV ingestion preserves bytes and exposes honest candidate status."""
import hashlib
import json

import numpy as np
import pytest

from nohit.dashboard.csv_api import solve_csv_request


INITIAL = [320., 304., 0., 0., 0., 0., 0., 1., 750., 0., 0.]


@pytest.mark.parametrize('payload', [
    {}, {'csv_path': 'x.csv', 'custom_csv': '0,EndAttack'},
    {'custom_csv': '0,EndAttack', 'initial': [1, 2]},
    {'custom_csv': '0,EndAttack', 'fps': 0},
    {'custom_csv': '0,EndAttack', 'max_ticks': True},
])
def test_invalid_requests_fail_before_search(payload):
    with pytest.raises(ValueError):
        solve_csv_request({'initial': INITIAL, **payload})


def test_file_unknown_is_not_unsat_and_source_is_unchanged(tmp_path):
    path = tmp_path/'sample.csv'
    path.write_bytes(b'0,HeartMode,0\r\n10,EndAttack\r\n')
    before = path.read_bytes()
    result = solve_csv_request(dict(csv_path=str(path), initial=INITIAL, max_ticks=2))
    assert result['status'] == 'unknown' and not result['deadlock_proven']
    assert not result['original_replay_passed']
    assert 'visualization' not in result
    assert path.read_bytes() == before
    assert result['csv_sha256'] == hashlib.sha256(before).hexdigest()
    json.dumps(result, allow_nan=False)


def test_pasted_csv_does_not_need_a_browser_file_picker():
    result = solve_csv_request(dict(custom_csv='10,EndAttack\n', initial=INITIAL, max_ticks=2))
    assert result['status'] == 'unknown'
    assert result['csv_sha256'] == hashlib.sha256(b'10,EndAttack\n').hexdigest()


def test_fresh_request_provenance_binds_actual_solver_sources_and_request_identity():
    from nohit.dashboard.csv_api import implementation_hashes, IMPLEMENTATION_PATHS
    payload = dict(custom_csv='10,EndAttack\n', initial=INITIAL, max_ticks=2)
    first = solve_csv_request(dict(payload, request_id='first-attempt'))
    second = solve_csv_request(dict(payload, request_id='second-attempt'))
    assert first['provenance']['request_id'] == 'first-attempt'
    assert second['provenance']['request_id'] == 'second-attempt'
    for result in (first, second):
        proof = result['provenance']
        assert proof['fresh_computation'] is True and proof['route_cache_hit'] is False
        assert proof['implementation_sha256'] == implementation_hashes()
        assert set(proof['implementation_sha256']) == set(IMPLEMENTATION_PATHS)


def test_changed_solver_source_rejects_stale_import_provenance(monkeypatch):
    from nohit.dashboard import csv_api
    changed = dict(csv_api.implementation_hashes())
    changed['nohit/engine/csv_solver.py'] = '0'*64
    monkeypatch.setattr(csv_api, 'implementation_hashes', lambda: changed)
    with pytest.raises(ValueError, match='source changed after import'):
        solve_csv_request(dict(custom_csv='0,EndAttack\n', initial=INITIAL, max_ticks=2))


def timestamp_schedule(count=40):
    stamp=971260.6666634805
    result=[1/60]
    for _ in range(count-1):
        previous=stamp
        stamp+=1000/60
        result.append(min((stamp-previous)/1000,1/30))
    assert len(set(result))>1
    return result


def entry_environment(dt):
    return [133.,251.,508.,391.,0.,1.,0.,dt,750.,0.,0.,0.,0.,
            133.,251.,508.,391.,0.,0.,0.,0.,0.]


def test_explicit_native_timestamp_schedule_survives_solve_and_visualization_bitwise():
    schedule=timestamp_schedule()
    result=solve_csv_request(dict(custom_csv='0,HeartMode,0\n0.1,EndAttack\n',
        initial=INITIAL,initial_environment=entry_environment(schedule[0]),
        dt_schedule=schedule,width=10,max_ticks=30,fps=60))
    assert result['status']=='candidate_found'
    assert result['clock_protocol']=='explicit_dt_schedule'
    assert result['clock']['schedule_count']==len(schedule)
    assert result['clock']['schedule_sha256']==hashlib.sha256(np.asarray(schedule,dtype='<f8').tobytes()).hexdigest()
    assert result['physics_hz'] is None and result['control_hz'] is None
    actual=np.asarray(result['dt_sequence'],dtype='<f8')
    assert actual.tobytes()==np.asarray(schedule[:len(actual)],dtype='<f8').tobytes()
    frames=result['visualization']['frames']
    assert np.asarray([frame['dt'] for frame in frames],dtype='<f8').tobytes()==actual.tobytes()
    json.dumps(result,allow_nan=False)


def test_explicit_schedule_defaults_budget_to_its_complete_length():
    schedule=timestamp_schedule(3)
    result=solve_csv_request(dict(custom_csv='10,EndAttack\n',initial=INITIAL,dt_schedule=schedule))
    assert result['max_ticks']==len(schedule)
    assert result['clock']['schedule_count']==len(schedule)
    assert result['clock_protocol']=='explicit_dt_schedule'
    assert result['status']=='unknown'


@pytest.mark.parametrize('schedule',[
    [],None,1/60,'0.016',[[1/60]],[0.],[-1.],[float('nan')],[float('inf')],
    [1/30+0.000001],[True],['0.016'],[1/60,None],[10**400],
])
def test_invalid_explicit_schedules_fail_before_search(schedule):
    with pytest.raises(ValueError,match='dt_schedule'):
        solve_csv_request(dict(custom_csv='10,EndAttack\n',initial=INITIAL,dt_schedule=schedule,max_ticks=1))


def test_explicit_schedule_must_cover_declared_budget():
    with pytest.raises(ValueError,match='dt_schedule.*max_ticks'):
        solve_csv_request(dict(custom_csv='10,EndAttack\n',initial=INITIAL,
            dt_schedule=[1/60]*3,max_ticks=4))


def test_explicit_initial_dt_must_match_observed_environment_exactly():
    schedule=timestamp_schedule()
    environment=entry_environment(np.nextafter(schedule[0],1.))
    with pytest.raises(ValueError,match=r'dt_schedule\[0\].*initial_environment\[7\]'):
        solve_csv_request(dict(custom_csv='10,EndAttack\n',initial=INITIAL,
            initial_environment=environment,dt_schedule=schedule))


def test_omitting_schedule_preserves_default_30hz_clock():
    result=solve_csv_request(dict(custom_csv='10,EndAttack\n',initial=INITIAL,max_ticks=2))
    assert result['physics_hz']==30 and result['control_hz']==30
    assert result['clock']['schedule_count']==2
    assert result['clock']['schedule_sha256']==hashlib.sha256(np.asarray([1/30]*2,dtype='<f8').tobytes()).hexdigest()


def test_explicit_eof_policy_returns_one_complete_execution_and_visualization():
    schedule=timestamp_schedule(40)
    result=solve_csv_request(dict(custom_csv='0,HeartMode,0\n0.1,Score,Flash\n',
        initial=INITIAL,dt_schedule=schedule,termination_policy='eof_hazards_drained',width=4))
    assert result['status']=='candidate_found' and result['completion']['kind']=='eof_invariant'
    n=len(result['actions']);d=result['completion']['drain_tick']
    assert n-d>=2 and result['actions'][d:]==[0]*(n-d)
    assert result['confirm_sequence'][d:]==[False]*(n-d)
    assert len(result['visualization']['frames'])==n+1
    assert result['dt_sequence']==schedule[:n+1]
    assert result['completion']['native_verified'] is False


def test_invalid_termination_policy_is_rejected():
    with pytest.raises(ValueError,match='termination_policy'):
        solve_csv_request(dict(custom_csv='0,HeartMode,0\n',initial=INITIAL,
            max_ticks=3,termination_policy='pretend_endattack'))


@pytest.mark.parametrize('option,value', [
    ('observation_chunk_ticks', -1),
    ('observation_preview_ticks', 1.5),
    ('observation_preview_reads', True),
    ('observation_goal_retries', 1),
])
def test_observation_options_reach_engine_validation(option, value):
    with pytest.raises(ValueError, match=option):
        solve_csv_request(dict(custom_csv='0,HeartMode,0\n0.1,EndAttack\n',
            initial=INITIAL, max_ticks=20, **{option: value}))


def test_observation_options_select_existing_segmented_solver_and_preserve_verification():
    result=solve_csv_request(dict(custom_csv='0,HeartMode,0\n0.1,GetHeartPos,x,y\n0.1,EndAttack\n',
        initial=INITIAL, max_ticks=40, fps=60, width=4, seconds=5,
        observation_chunk_ticks=6, observation_preview_ticks=12,
        observation_preview_reads=32, observation_goal_retries=True))
    assert result['status']=='candidate_found' and result['verified'] is True
    assert result['search_stats']['backend']=='native-coupled-segments'
    for option,value in dict(observation_chunk_ticks=6, observation_preview_ticks=12,
                             observation_preview_reads=32, observation_goal_retries=True).items():
        assert result['search_stats'][option]==value
    assert not result['original_replay_passed']


@pytest.mark.parametrize('text,profile,seconds,width,segmented', [
    ('0,HeartMode,0\n0.1,EndAttack\n', 'short', 30, 2048, False),
    ('30,GetHeartPos,x,y\n0,EndAttack\n', 'medium', 60, 4096, False),
    ('120,GetHeartPos,x,y\n0,EndAttack\n', 'long', 90, 8192, True),
    ('0,GetHeartPos,x,y\n'*64+'0,EndAttack\n', 'long', 90, 8192, True),
])
def test_auto_budget_uses_source_complexity(tmp_path, monkeypatch, text, profile, seconds, width, segmented):
    from nohit.dashboard import csv_api
    path=tmp_path/'budget.csv';path.write_text(text, encoding='utf-8')
    monkeypatch.setattr(csv_api.os, 'cpu_count', lambda: 32)
    budget=csv_api._budget_selection({}, path)
    assert budget['mode']=='auto' and budget['profile']==profile
    assert budget['selected']['seconds']==seconds and budget['selected']['width']==width
    assert budget['selected']['workers']==4
    if segmented:
        assert budget['selected']['observation_chunk_ticks']==480
        assert budget['selected']['observation_preview_ticks']==480
        assert budget['selected']['observation_preview_reads']==128
        assert budget['selected']['observation_goal_retries'] is True
    else:
        assert 'observation_chunk_ticks' not in budget['selected']


def test_default_auto_budget_is_returned_with_real_verified_candidate():
    result=solve_csv_request(dict(custom_csv='0,HeartMode,0\n0.1,EndAttack\n',
        initial=INITIAL, max_ticks=20, request_id='automatic-candidate'))
    budget=result['budget_selection']
    assert result['status']=='candidate_found' and result['verified'] is True
    assert budget['mode']=='auto' and budget['profile']=='short'
    assert budget['attempts'][0]['status']=='candidate_found'
    assert len(budget['attempts'])==1
    assert result['provenance']['request_id']=='automatic-candidate'
    assert result['provenance']['fresh_computation'] is True
    assert not result['original_replay_passed']


@pytest.mark.parametrize('data,mode,width,seconds', [
    ({'width':12,'seconds':7},'manual',12,7),
    ({'budget_mode':'manual'},'manual',3000,30),
    ({'budget_mode':'auto','width':12,'seconds':7},'auto',2048,30),
])
def test_budget_mode_preserves_explicit_legacy_requests_and_automatic_override(tmp_path, data, mode, width, seconds):
    from nohit.dashboard import csv_api
    path=tmp_path/'budget.csv';path.write_text('0,EndAttack\n', encoding='utf-8')
    budget=csv_api._budget_selection(data,path)
    assert budget['mode']==mode
    assert budget['selected']['width']==width and budget['selected']['seconds']==seconds


@pytest.mark.parametrize('reason,retries', [
    ('wall_budget',True),('frontier_exhausted',True),
    ('native_search_limited',True),
    ('native_observation_budget',True),('unsupported_mechanism',False),
    ('tick_budget',False),('native_scope_or_resource_limit',False),
])
def test_auto_budget_retry_is_bounded_and_keeps_unknown_honest(monkeypatch, reason, retries):
    from nohit.dashboard import csv_api,solve_progress
    calls=[]
    def limited_solver(path, initial, **settings):
        calls.append(settings)
        snapshot=solve_progress.snapshot('auto-limited')
        assert snapshot['state']=='running'
        return dict(status='unknown',verified=False,reason=reason,deadlock_proven=False,
                    original_replay_passed=False)
    monkeypatch.setattr(csv_api,'solve_csv',limited_solver)
    result=solve_csv_request(dict(custom_csv='120,GetHeartPos,x,y\n0,EndAttack\n',
        initial=INITIAL, max_ticks=20, budget_mode='auto',progress_id='auto-limited',
        request_id='bounded-request'))
    assert len(calls)==(2 if retries else 1)
    assert sum(call['seconds'] for call in calls)<=180
    if retries:
        assert calls[1]['width']>calls[0]['width']
    assert result['status']=='unknown' and result['verified'] is False
    assert not result['deadlock_proven'] and not result['original_replay_passed']
    assert len(result['budget_selection']['attempts'])==len(calls)
    assert result['provenance']['request_id']=='bounded-request'
    assert solve_progress.snapshot('auto-limited')['state']=='done'


def test_manual_budget_never_retries_without_another_request(monkeypatch):
    from nohit.dashboard import csv_api
    calls=[]
    def limited_solver(path, initial, **settings):
        calls.append(settings)
        return dict(status='unknown',verified=False,reason='wall_budget')
    monkeypatch.setattr(csv_api,'solve_csv',limited_solver)
    result=solve_csv_request(dict(custom_csv='0,EndAttack\n',initial=INITIAL,max_ticks=20,
        seconds=7,width=12))
    assert len(calls)==1 and calls[0]['seconds']==7 and calls[0]['width']==12
    assert result['budget_selection']['mode']=='manual'


def test_invalid_budget_mode_is_rejected():
    with pytest.raises(ValueError,match='budget_mode'):
        solve_csv_request(dict(custom_csv='0,EndAttack\n',initial=INITIAL,budget_mode='guess'))


@pytest.mark.parametrize('count,profile',[(250,'medium'),(2000,'long')])
def test_command_count_can_raise_auto_budget_without_target_reads(tmp_path, count, profile):
    from nohit.dashboard import csv_api
    path=tmp_path/'many.csv';path.write_text('0,Wait\n'*count+'0,EndAttack\n',encoding='utf-8')
    budget=csv_api._budget_selection({},path)
    assert budget['profile']==profile
    assert budget['source_summary']['command_count']==count+1
    assert 'observation_chunk_ticks' not in budget['selected']


@pytest.mark.parametrize('cpus',[1,None])
def test_auto_budget_works_when_only_one_cpu_is_available(tmp_path, monkeypatch, cpus):
    from nohit.dashboard import csv_api
    path=tmp_path/'one.csv';path.write_text('0,EndAttack\n',encoding='utf-8')
    monkeypatch.setattr(csv_api.os,'cpu_count',lambda:cpus)
    assert csv_api._budget_selection({},path)['selected']['workers']==1


def test_auto_retry_also_respects_elapsed_preparation_time(monkeypatch):
    from types import SimpleNamespace
    from nohit.dashboard import csv_api
    now=[0.];calls=[]
    monkeypatch.setattr(csv_api,'time',SimpleNamespace(perf_counter=lambda:now[0]))
    def limited_solver(path, initial, **settings):
        calls.append(settings)
        now[0]+=100 if len(calls)==1 else settings['seconds']
        return dict(status='unknown',verified=False,reason='wall_budget')
    monkeypatch.setattr(csv_api,'solve_csv',limited_solver)
    result=solve_csv_request(dict(custom_csv='120,GetHeartPos,x,y\n0,EndAttack\n',
        initial=INITIAL,budget_mode='auto',max_ticks=20))
    assert [call['seconds'] for call in calls]==[90,80]
    assert result['request_seconds']==180


def test_auto_retry_does_not_start_after_total_elapsed_limit(monkeypatch):
    from types import SimpleNamespace
    from nohit.dashboard import csv_api
    now=[0.];calls=[]
    monkeypatch.setattr(csv_api,'time',SimpleNamespace(perf_counter=lambda:now[0]))
    def limited_solver(path, initial, **settings):
        calls.append(settings);now[0]+=181
        return dict(status='unknown',verified=False,reason='wall_budget')
    monkeypatch.setattr(csv_api,'solve_csv',limited_solver)
    solve_csv_request(dict(custom_csv='120,GetHeartPos,x,y\n0,EndAttack\n',
        initial=INITIAL,budget_mode='auto',max_ticks=20))
    assert len(calls)==1


def test_native_entry_visualization_avoids_full_scene_rebuild_but_keeps_verified_route(monkeypatch):
    from nohit.dashboard import csv_visualization
    def forbidden(*args,**kwargs):
        raise AssertionError('native requests must not rebuild full geometry history')
    monkeypatch.setattr(csv_visualization,'build_csv_visualization',forbidden)
    result=solve_csv_request(dict(custom_csv='0,HeartMode,0\n0,GetHeartPos,x,y\n0.1,EndAttack\n',
        initial=INITIAL,max_ticks=40,width=4,visualization_mode='entry'))
    assert result['status']=='candidate_found' and result['verified'] is True
    assert result['visualization_mode']=='entry'
    assert result['visualization']['frame_count']==1
    assert len(result['trajectory'])==len(result['actions'])+1>1
    assert not result['original_replay_passed']


def test_unknown_visualization_mode_is_rejected_before_search():
    with pytest.raises(ValueError,match='visualization_mode'):
        solve_csv_request(dict(custom_csv='0,EndAttack\n',initial=INITIAL,
            max_ticks=20,visualization_mode='skip_every_check'))
