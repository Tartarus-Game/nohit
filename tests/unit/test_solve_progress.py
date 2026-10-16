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


def test_a_running_solve_publishes_search_snapshots_while_it_runs(monkeypatch):
    # A native solve can finish before the polling thread is scheduled. Hold
    # its first real search snapshot until the reader has observed it.
    published=threading.Event();observed=threading.Event();outcome={}
    original=solve_progress.ProgressReporter.update

    def update(reporter,**fields):
        original(reporter,**fields)
        snap=solve_progress.snapshot(reporter.progress_id)
        if (reporter.progress_id=='live-watch' and not published.is_set()
                and snap['phase']=='search' and snap['expanded_states']):
            published.set()
            observed.wait(timeout=10)

    monkeypatch.setattr(solve_progress.ProgressReporter,'update',update)

    def solve():
        try:
            solve_csv_request(dict(custom_csv='0,HeartMode,0\n0.1,EndAttack\n', initial=INITIAL,
                max_ticks=400, width=400, seconds=10, progress_id='live-watch'))
        except Exception as exc:  # pragma: no cover - reported through outcome
            outcome['error']=exc

    worker=threading.Thread(target=solve,daemon=True)
    worker.start()
    try:
        assert published.wait(timeout=10),'native solve did not publish a search snapshot'
        snap=solve_progress.snapshot('live-watch')
        assert worker.is_alive() and snap['state']=='running' and snap['phase']=='search'
        assert snap['expanded_states']>0 and snap['elapsed_seconds'] is not None
        assert snap['fraction_basis'] in ('tick_horizon','wall_budget')
    finally:
        observed.set();worker.join(timeout=10)
    assert 'error' not in outcome
    assert not worker.is_alive()
    assert solve_progress.snapshot('live-watch')['state']=='done'


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


def test_running_snapshots_refresh_elapsed_without_inventing_solver_activity(monkeypatch):
    now=[100.]
    monkeypatch.setattr(solve_progress,'_now',lambda:now[0])
    reporter=solve_progress.begin('idle-clock',seconds_budget=10)
    reporter.update(phase='search',expanded_states=100)
    before=solve_progress.snapshot('idle-clock')
    now[0]+=2
    running=solve_progress.snapshot('idle-clock')
    assert running['elapsed_seconds']==2
    assert running['fraction']==.2 and running['states_per_second']==50
    assert running['updated_at']==before['updated_at']
    assert running['expanded_states']==100
    reporter.finish(status='candidate_found')
    finished=solve_progress.snapshot('idle-clock')
    now[0]+=3
    assert solve_progress.snapshot('idle-clock')==finished


def test_source_eta_uses_committed_ticks_and_survives_window_baking(monkeypatch):
    now=[100.]
    monkeypatch.setattr(solve_progress,'_now',lambda:now[0])
    reporter=solve_progress.begin('source-eta',seconds_budget=90)
    reporter.update(estimated_total_ticks=1000,estimated_total_ticks_basis='csv_literal_duration_estimate')
    reporter.update(phase='bake',committed_tick=0)
    now[0]=102.
    reporter.update(phase='search',tick=900,ticks=None,committed_tick=100)
    snap=solve_progress.snapshot('source-eta')
    assert snap['eta_seconds']==18.
    assert snap['eta_basis']=='csv_literal_duration_estimate'
    assert snap['committed_tick']==100 and snap['estimated_total_ticks']==1000
    # Preview may reach the literal end; only actual committed progress counts.
    now[0]=104.
    reporter.update(phase='bake',tick=1000,committed_tick=200)
    assert solve_progress.snapshot('source-eta')['eta_seconds']==16.
    # Budget expiry is never presented as time to completion.
    now[0]=200.
    assert solve_progress.snapshot('source-eta')['eta_seconds']==400.
    reporter.update(committed_tick=1000)
    exhausted=solve_progress.snapshot('source-eta')
    assert exhausted['eta_seconds'] is None and exhausted['eta_basis']=='unknown'


def test_eta_resets_on_retry_and_verification_has_its_own_clock(monkeypatch):
    now=[100.]
    monkeypatch.setattr(solve_progress,'_now',lambda:now[0])
    reporter=solve_progress.begin('eta-reset',estimated_total_ticks=1000,
        estimated_total_ticks_basis='csv_literal_duration_estimate')
    reporter.update(phase='search',committed_tick=0)
    now[0]=102.;reporter.update(committed_tick=100)
    assert solve_progress.snapshot('eta-reset')['eta_seconds']==18.
    reporter.update(phase='prepare',committed_tick=None)
    assert solve_progress.snapshot('eta-reset')['eta_seconds'] is None
    now[0]=200.;reporter.update(phase='search',committed_tick=0)
    now[0]=202.;reporter.update(committed_tick=200)
    assert solve_progress.snapshot('eta-reset')['eta_seconds']==8.
    reporter.update(phase='verify',tick=0,ticks=1200)
    assert solve_progress.snapshot('eta-reset')['eta_seconds'] is None
    now[0]=205.;reporter.update(tick=300)
    assert solve_progress.snapshot('eta-reset')['eta_seconds'] is None
    now[0]=208.;reporter.update(tick=600)
    verifying=solve_progress.snapshot('eta-reset')
    assert verifying['eta_seconds']==6. and verifying['eta_basis']=='scalar_replay_tick_rate'
    reporter.finish(status='unknown')
    assert solve_progress.snapshot('eta-reset')['eta_seconds'] is None


def test_unknown_or_nonfinite_horizons_cannot_create_eta(monkeypatch):
    now=[100.]
    monkeypatch.setattr(solve_progress,'_now',lambda:now[0])
    reporter=solve_progress.begin('eta-unknown',seconds_budget=2)
    reporter.update(phase='search',tick=900,ticks=None,committed_tick=0)
    now[0]+=3;reporter.update(committed_tick=100,estimated_total_ticks=float('inf'))
    snap=solve_progress.snapshot('eta-unknown')
    assert snap['eta_seconds'] is None and snap['eta_basis']=='unknown'
    assert snap['estimated_total_ticks'] is None
    assert solve_progress.unknown_snapshot('missing')['eta_seconds'] is None
    json.dumps(snap,allow_nan=False)


def test_verification_eta_excludes_source_rebuild_before_first_tick_progress(monkeypatch):
    now=[100.]
    monkeypatch.setattr(solve_progress,'_now',lambda:now[0])
    reporter=solve_progress.begin('verify-preparation')
    reporter.update(phase='verify',tick=0,ticks=1000)
    # Source reconstruction is opaque; its time cannot predict scalar speed.
    now[0]=106.;reporter.update(tick=0)
    assert solve_progress.snapshot('verify-preparation')['eta_seconds'] is None
    now[0]=106.1;reporter.update(tick=100)
    assert solve_progress.snapshot('verify-preparation')['eta_seconds'] is None
    now[0]=106.2;reporter.update(tick=200)
    snap=solve_progress.snapshot('verify-preparation')
    assert snap['eta_basis']=='scalar_replay_tick_rate'
    assert snap['eta_seconds']==pytest.approx(.8)
