"""Live solve telemetry is observable, honest and read-only.

The registry only records counters the solver already maintains; a request
without a progress_id must behave exactly as before. These tests drive the
registry directly, over real HTTP for the route, and through one small solve.
"""
import json
import threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen

import pytest

from nohit.dashboard import solve_progress
from nohit.dashboard.csv_api import solve_csv_request
from nohit.dashboard.server import DashboardHandler

INITIAL = [320., 304., 0., 0., 0., 0., 0., 1., 750., 0., 0.]


@pytest.fixture
def progress_server():
    server = ThreadingHTTPServer(('127.0.0.1', 0), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown(); server.server_close(); thread.join(timeout=1)


def test_unknown_id_is_an_explicit_answer_not_a_missing_route(progress_server):
    with urlopen(progress_server + '/api/progress/never-registered') as response:
        assert response.status == 200
        payload = json.loads(response.read().decode('utf-8'))
    assert payload['state'] == 'unknown'
    assert payload['schema_version'] == 1
    assert payload['progress_id'] == 'never-registered'
    assert payload['expanded_states'] is None and payload['fraction'] is None
    json.dumps(payload, allow_nan=False)


def test_registered_attempt_is_readable_over_http(progress_server):
    reporter = solve_progress.begin('http-attempt', engine='bounded-frontier-with-dialogue',
                                    seconds_budget=30, ticks=1000)
    reporter.update(tick=250, alive_states=1234, expanded_states=500000)
    with urlopen(progress_server + '/api/progress/http-attempt') as response:
        payload = json.loads(response.read().decode('utf-8'))
    assert payload['state'] == 'running'
    assert payload['tick'] == 250 and payload['ticks'] == 1000
    assert payload['alive_states'] == 1234
    assert payload['expanded_states'] == 500000
    assert payload['fraction_basis'] == 'tick_horizon'
    assert payload['fraction'] == pytest.approx(0.25)
    assert payload['states_per_second'] is not None and payload['states_per_second'] >= 0
    assert payload['peak_alive_states'] == 1234


def test_phase_and_terminal_states_are_recorded():
    reporter = solve_progress.begin('lifecycle', seconds_budget=10)
    assert solve_progress.snapshot('lifecycle')['phase'] == 'prepare'
    assert solve_progress.snapshot('lifecycle')['fraction_basis'] == 'wall_budget'
    reporter.phase('search')
    assert solve_progress.snapshot('lifecycle')['phase'] == 'search'
    reporter.phase('visualization')
    reporter.finish(status='candidate_found')
    done = solve_progress.snapshot('lifecycle')
    assert done['state'] == 'done' and done['phase'] == 'visualization'
    assert 'candidate_found' in done['message']


def test_failure_keeps_the_error_visible():
    reporter = solve_progress.begin('failing')
    reporter.fail(ValueError('boom'))
    snapshot = solve_progress.snapshot('failing')
    assert snapshot['state'] == 'failed' and 'boom' in snapshot['message']


def test_expired_entries_become_unknown():
    solve_progress.begin('expiring')
    with solve_progress._LOCK:
        solve_progress._ENTRIES['expiring']['_updated_mono'] -= solve_progress.TTL_SECONDS + 1
    assert solve_progress.snapshot('expiring')['state'] == 'unknown'


def test_updated_at_is_comparable_with_epoch_time():
    import time as _time
    solve_progress.begin('epoch-check')
    stamp = solve_progress.snapshot('epoch-check')['updated_at']
    assert abs(_time.time() - stamp) < 60


def test_a_rejected_request_still_leaves_a_failed_snapshot():
    # The reporter is registered before the other validation, so a request that
    # never reaches the search is still observable as failed.
    with pytest.raises(ValueError):
        solve_csv_request(dict(custom_csv='10,EndAttack\n', initial=[1, 2],
                               max_ticks=2, progress_id='rejected-early'))
    snapshot = solve_progress.snapshot('rejected-early')
    assert snapshot['state'] == 'failed' and snapshot['message']


def test_a_running_solve_publishes_search_snapshots_while_it_runs():
    import time as _time
    outcome = {}

    def solve():
        try:
            solve_csv_request(dict(custom_csv='0,HeartMode,0\n0.1,EndAttack\n', initial=INITIAL,
                max_ticks=400, width=400, seconds=10, progress_id='live-watch'))
        except Exception as exc:  # pragma: no cover - reported through outcome
            outcome['error'] = exc

    worker = threading.Thread(target=solve, daemon=True)
    worker.start()
    live = []
    deadline = _time.perf_counter() + 30
    while worker.is_alive() and _time.perf_counter() < deadline:
        snapshot = solve_progress.snapshot('live-watch')
        if snapshot['state'] == 'running' and snapshot['phase'] == 'search' and snapshot['expanded_states']:
            live.append(snapshot)
        else:
            _time.sleep(0.001)
    worker.join(timeout=30)
    assert 'error' not in outcome
    assert live, 'no running search snapshot was observable during the solve'
    assert live[0]['elapsed_seconds'] is not None
    assert live[0]['fraction_basis'] in ('tick_horizon', 'wall_budget')
    assert solve_progress.snapshot('live-watch')['state'] == 'done'


def test_concurrent_updates_never_raise_and_leave_a_consistent_snapshot():
    reporter = solve_progress.begin('concurrent')
    errors = []

    def worker(offset):
        try:
            for step in range(200):
                reporter.update(tick=step, alive_states=offset + step, expanded_states=(offset + 1) * (step + 1))
        except Exception as exc:  # pragma: no cover - the assertion below reports it
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert errors == []
    snapshot = solve_progress.snapshot('concurrent')
    assert snapshot['state'] == 'running'
    assert isinstance(snapshot['tick'], int) and 0 <= snapshot['tick'] < 200
    assert isinstance(snapshot['expanded_states'], int)
    json.dumps(snapshot, allow_nan=False)


def test_non_finite_counters_can_never_reach_the_json_response():
    # The route serialises with plain json.dumps, so one NaN/Infinity would make
    # the page's response.json() throw. Unknown values must degrade to null.
    reporter = solve_progress.begin('finite-only')
    reporter.update(tick=float('nan'), alive_states=float('inf'),
                    expanded_states=float('-inf'), discarded_states=1.5, ticks=100)
    snapshot = solve_progress.snapshot('finite-only')
    assert snapshot['tick'] is None and snapshot['alive_states'] is None
    assert snapshot['expanded_states'] is None and snapshot['discarded_states'] is None
    assert snapshot['ticks'] == 100
    text = json.dumps(snapshot, allow_nan=False)
    assert 'NaN' not in text and 'Infinity' not in text


def test_a_real_solve_publishes_counters_and_finishes():
    result = solve_csv_request(dict(custom_csv='0,HeartMode,0\n0.1,EndAttack\n', initial=INITIAL,
        max_ticks=200, width=200, seconds=10, progress_id='real-solve'))
    assert result['status'] in ('candidate_found', 'unknown')
    snapshot = solve_progress.snapshot('real-solve')
    assert snapshot['state'] == 'done'
    assert snapshot['progress_id'] == 'real-solve'
    assert isinstance(snapshot['expanded_states'], int) and snapshot['expanded_states'] > 0
    assert snapshot['elapsed_seconds'] is not None and snapshot['elapsed_seconds'] > 0
    assert snapshot['states_per_second'] is not None and snapshot['states_per_second'] >= 0
    json.dumps(snapshot, allow_nan=False)


def test_invalid_progress_id_is_rejected_before_the_search():
    for bad in ('', 17, 'x' * 129):
        with pytest.raises(ValueError, match='progress_id'):
            solve_csv_request(dict(custom_csv='10,EndAttack\n', initial=INITIAL, max_ticks=2,
                progress_id=bad))


def test_a_request_without_progress_id_registers_nothing():
    result = solve_csv_request(dict(custom_csv='10,EndAttack\n', initial=INITIAL, max_ticks=2))
    assert result['status'] == 'unknown'
    assert solve_progress.snapshot('')['state'] == 'unknown'
