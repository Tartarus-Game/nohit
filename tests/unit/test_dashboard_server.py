"""
tests/unit/test_dashboard_server.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Comprehensive integration tests for the Web Dashboard server (nohit.dashboard.server).
Tests:
- Server startup and endpoint binding.
- GET /api/waves
- POST /api/solve (real C2 waves, synthetic feasible, synthetic deadlock, custom CSV)
- GET /api/benchmark
- GET /, GET /index.html, GET /style.css, GET /app.js (static files)
- Error handling (invalid JSON, unknown wave, 404 endpoints, path traversal)
"""

import json
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Tuple
import pytest

from nohit.dashboard.server import start_server


TEST_PORT = 8085
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"


@pytest.fixture(scope="module")
def running_server():
    """Starts the Dashboard HTTP server on port 8085 in a background daemon thread."""
    server = start_server(port=TEST_PORT, host="127.0.0.1")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    
    # Wait for server to become responsive
    deadline = time.time() + 5.0
    responsive = False
    while time.time() < deadline:
        try:
            req = urllib.request.Request(f"{BASE_URL}/api/waves")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    responsive = True
                    break
        except Exception:
            time.sleep(0.1)

    assert responsive, f"Server on port {TEST_PORT} failed to respond within 5 seconds."
    
    yield server
    
    server.shutdown()
    server.server_close()


def http_get(path: str) -> Tuple[int, Dict[str, str], bytes]:
    """Helper to perform HTTP GET."""
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req) as resp:
            headers = {k.lower(): v for k, v in resp.getheaders()}
            return resp.status, headers, resp.read()
    except urllib.error.HTTPError as e:
        headers = {k.lower(): v for k, v in e.headers.items()}
        return e.code, headers, e.read()


def http_post(path: str, data: Any, raw_bytes: bytes = None) -> Tuple[int, Dict[str, str], bytes]:
    """Helper to perform HTTP POST."""
    url = f"{BASE_URL}{path}"
    if raw_bytes is None:
        payload = json.dumps(data).encode("utf-8")
        headers = {"Content-Type": "application/json"}
    else:
        payload = raw_bytes
        headers = {"Content-Type": "application/json"}
        
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            resp_headers = {k.lower(): v for k, v in resp.getheaders()}
            return resp.status, resp_headers, resp.read()
    except urllib.error.HTTPError as e:
        resp_headers = {k.lower(): v for k, v in e.headers.items()}
        return e.code, resp_headers, e.read()


def test_legacy_compute_url_cannot_select_another_search_system(running_server):
    status,_,body=http_get('/api/tas?wave=sans_platforms4hard.csv&seed=42&compute=compact')
    result=json.loads(body)
    assert status==200 and result['planner']=='canonical-dag-dp'
    assert result['search_status']=='initial_state_required'
    assert not result['candidate_found'] and not result['deadlock_proven']


def test_fresh_default_tas_requires_current_original_initial_state(running_server):
    status,_,body=http_get('/api/tas?wave=sans_bonegap1.csv')
    result=json.loads(body)
    assert status==200 and result['planner']=='canonical-dag-dp'
    assert result['search_status']=='initial_state_required'
    assert not result['candidate_found'] and not result['deadlock_proven']


def test_adaptive_dag_api_uses_one_unpruned_graph(running_server):
    from urllib.parse import urlencode
    query=urlencode(dict(wave='sans_bonegap1.csv',compute='canonical',seed=42,
        initial=json.dumps([320,377.81875,0,0,0])))
    status,_,body=http_get('/api/tas?'+query)
    result=json.loads(body)
    assert status==200 and result['candidate_found']
    assert result['planner']=='canonical-dag-dp'
    assert result['no_beam_pruning'] and result['deferred_states_discarded']==0
    assert result['retained_states']>=result['expansions']
    assert result['objective']=='no_hit_with_style_preferences'
    assert result['weights_affect_safety'] is False
    assert not result['optimality_proven'] and not result['deadlock_proven']
    status,_,body=http_get('/api/tas?'+query+'&max_nodes=2')
    limited=json.loads(body)
    assert status==200 and limited['search_status']=='resource_limit'
    assert not limited['candidate_found'] and not limited['deadlock_proven']
    zero=dict.fromkeys(('clearance','lookahead','center','switches'),0)
    status,_,body=http_get('/api/tas?'+query+'&'+urlencode(dict(max_nodes=2,weights=json.dumps(zero))))
    unweighted=json.loads(body)
    assert status==200 and unweighted['ranking_weights']==zero
    assert unweighted['weights_affect_safety'] is False
    assert unweighted['search_status']=='resource_limit'


@pytest.mark.parametrize('option',['max_nodes=0','max_nodes=2000001','margin=nan','lookahead=-1',
    'weights=%7B%22center%22%3A-1%7D','weights=%7B%22unknown%22%3A1%7D','weights=%5B%5D',
    'initial_environment=%5B%5D','initial_environment=%7B%7D'])
def test_adaptive_api_rejects_invalid_limits(running_server,option):
    status,_,_=http_get('/api/tas?compute=canonical&wave=sans_bonegap1.csv&initial=%5B320,377,0,0,0%5D&'+option)
    assert status==400


# ---------------------------------------------------------------------------
# Test Suite
# ---------------------------------------------------------------------------

def test_static_files_served(running_server):
    """Verify static files (index.html, style.css, app.js) are properly served."""
    # GET /
    status, headers, body = http_get("/")
    assert status == 200
    assert "text/html" in headers.get("content-type", "")
    assert b"SANS TAS ROUTE SYSTEM" in body
    assert b"<canvas" in body

    # GET /index.html
    status, headers, body = http_get("/index.html")
    assert status == 200
    assert "text/html" in headers.get("content-type", "")

    # GET /style.css
    status, headers, body = http_get("/style.css")
    assert status == 200
    assert "text/css" in headers.get("content-type", "")
    assert len(body) > 100
    assert b".stage-canvas" in body or b"body" in body

    # GET /app.js
    status, headers, body = http_get("/app.js")
    assert status == 200
    assert "javascript" in headers.get("content-type", "")
    assert len(body) > 100
    assert b"class DashboardApp" in body or b"function" in body or b"addEventListener" in body


def test_get_api_waves(running_server):
    """Verify GET /api/waves returns wave list including C2 files and presets."""
    status, headers, body = http_get("/api/waves")
    assert status == 200
    assert "application/json" in headers.get("content-type", "")
    
    data = json.loads(body.decode("utf-8"))
    assert "waves" in data
    waves = data["waves"]
    assert isinstance(waves, list)
    assert len(waves) > 0

    wave_ids = [w["id"] for w in waves]
    # Check C2 waves present
    assert "sans_bonegap1.csv" in wave_ids
    assert "sans_boneslideh.csv" in wave_ids
    assert "sans_platforms1.csv" in wave_ids

    # Check synthetic presets present
    assert "preset_platform_ferry" in wave_ids
    assert "preset_deadlock_spikes" in wave_ids
    assert "preset_deadlock_sweeper" in wave_ids
    assert "preset_deadlock_eruption" in wave_ids

    # Check structure
    for w in waves:
        assert "id" in w
        assert "name" in w
        assert "category" in w


def test_post_api_solve_real_wave(running_server):
    """Verify POST /api/solve with sans_bonegap1.csv returns solution and visualization data."""
    payload = {
        "wave": "sans_bonegap1.csv",
        "T": 100
    }
    status, headers, body = http_post("/api/solve", payload)
    assert status == 200
    assert "application/json" in headers.get("content-type", "")
    
    res = json.loads(body.decode("utf-8"))
    assert "is_deadlock" in res
    assert "action_sequence" in res
    assert "trajectory" in res
    assert "hazard_runs" in res
    assert "platforms" in res
    assert "stats" in res
    assert "verified" in res

    # Verify types and structure
    assert res["is_deadlock"] is None and res['deadlock_proven'] is False
    assert isinstance(res["action_sequence"], list)
    assert isinstance(res["trajectory"], list)
    assert isinstance(res["hazard_runs"], list)
    assert isinstance(res["platforms"], list)
    assert res["T"] == 100
    assert res["W"] == 200
    assert res["H"] == 160

    # For feasible wave, verify action sequence and trajectory lengths match
    if res['candidate_found']:
        assert len(res["action_sequence"]) == res["T"] - 1
        assert len(res["trajectory"]) == res["T"]
        assert res["verified"] is False and res['realtime_accepted'] is False
        assert len(res["collision_frames"]) == 0


def test_post_api_solve_synthetic_deadlock_spikes(running_server):
    """Model exhaustion is reported without claiming original-game deadlock."""
    payload = {
        "wave": "preset_deadlock_spikes",
        "T": 40
    }
    status, headers, body = http_post("/api/solve", payload)
    assert status == 200
    
    res = json.loads(body.decode("utf-8"))
    assert res["is_deadlock"] is None and res['deadlock_proven'] is False
    assert not res['candidate_found'] and res['search_exhausted_frame'] == 15
    assert res["action_sequence"] is None
    assert res["trajectory"] is None
    assert res["verified"] is False


def test_post_api_solve_synthetic_feasible(running_server):
    """A synthetic candidate does not become an original-game verification."""
    payload = {
        "wave": "preset_platform_ferry",
        "T": 50
    }
    status, headers, body = http_post("/api/solve", payload)
    assert status == 200
    
    res = json.loads(body.decode("utf-8"))
    assert res["is_deadlock"] is None and res['candidate_found'] is True
    assert res["verified"] is False and res['realtime_accepted'] is False
    assert len(res["trajectory"]) == 50
    assert len(res["platforms"]) == 50
    # Check that platform instances were returned in platforms list
    assert len(res["platforms"][0]) > 0
    assert "x_left" in res["platforms"][0][0]
    assert "y_surf" in res["platforms"][0][0]


def test_post_api_solve_custom_csv(running_server):
    """Verify POST /api/solve with custom_csv executes without errors."""
    csv_text = (
        "0,BoneVRepeat,128,257,95,0,180,8,120\n"
        "6.4,EndAttack\n"
    )
    payload = {
        "custom_csv": csv_text,
        "T": 40
    }
    status, headers, body = http_post("/api/solve", payload)
    assert status == 200
    
    res = json.loads(body.decode("utf-8"))
    assert "is_deadlock" in res
    assert "stats" in res
    assert res["T"] == 40


def test_get_api_benchmark(running_server):
    """Verify GET /api/benchmark executes benchmark and returns structured rows."""
    status, headers, body = http_get("/api/benchmark")
    assert status == 200
    assert "application/json" in headers.get("content-type", "")
    
    data = json.loads(body.decode("utf-8"))
    assert "benchmark" in data
    rows = data["benchmark"]
    assert isinstance(rows, list)
    assert len(rows) > 0

    first = rows[0]
    expected_fields = [
        "name", "category", "outcome", "bake_ms", "dp_ms",
        "total_ms", "peak_states", "peak_memory_mb", "verified"
    ]
    for field in expected_fields:
        assert field in first


def test_error_handling(running_server):
    """Verify error cases return appropriate HTTP status codes."""
    # 1. Invalid JSON body
    status, _, body = http_post("/api/solve", None, raw_bytes=b"invalid json {[")
    assert status == 400
    res = json.loads(body.decode("utf-8"))
    assert "error" in res

    # 2. Non-existent wave
    payload = {"wave": "non_existent_wave_9999.csv"}
    status, _, body = http_post("/api/solve", payload)
    assert status == 404
    res = json.loads(body.decode("utf-8"))
    assert "error" in res

    # 3. Unknown API route
    status, _, _ = http_get("/api/unknown_route")
    assert status == 404

    # 4. Unknown static file
    status, _, _ = http_get("/non_existent_file.png")
    assert status == 404


def test_get_api_tas_rejects_partial_horizon(running_server):
    status,_,body=http_get('/api/tas?wave=sans_bonegap1.csv&T=40')
    result=json.loads(body)
    assert status==200 and result['search_status']=='unsupported_configuration'
    assert not result['candidate_found'] and not result['deadlock_proven']


def test_serve_game_file(running_server):
    """Verify /game/ serves C2 game files."""
    status, headers, body = http_get("/game/index.html")
    assert status == 200
    assert "text/html" in headers.get("content-type", "")
    assert b"c2canvas" in body
