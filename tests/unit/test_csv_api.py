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
