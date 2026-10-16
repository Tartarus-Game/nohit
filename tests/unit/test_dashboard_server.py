"""HTTP contracts for the current CSV dashboard and original-game integration."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from nohit.dashboard.server import DashboardHandler


@pytest.fixture(scope="module")
def base_url():
    server=ThreadingHTTPServer(('127.0.0.1',0),DashboardHandler)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown();server.server_close();thread.join(timeout=1)


def request(base_url,path,body=None,method=None):
    data=json.dumps(body).encode() if body is not None else None
    req=urllib.request.Request(base_url+path,data=data,method=method,
                               headers={'Content-Type':'application/json'})
    try:
        response=urllib.request.urlopen(req,timeout=10)
    except urllib.error.HTTPError as error:
        response=error
    with response:
        return response.status,dict(response.headers),response.read()


def test_dashboard_and_current_game_assets(base_url):
    status,headers,body=request(base_url,'/')
    assert status==200 and 'text/html' in headers['Content-Type']
    assert b'<canvas' in body and b'/api/solve-csv' in body
    assert b'old.html' not in body and b'renderOldEngine' not in body
    assert b'id="engine"' not in body and b'id="bindings"' not in body
    status,headers,game=request(base_url,'/game/')
    assert status==200 and 'no-store' in headers['Cache-Control']
    assert b'csv_round_controller.js' in game and b'full_game_runner.js' in game
    assert b'engine_oracle.js' not in game and b'auto_solver.js' not in game
    for name in ('tas_runner.js','csv_source_bridge.js','solver_state.js','csv_round_controller.js',
                 'csv_tas_runner.js','custom_wave_acceptance.js','lag_compensation.js',
                 'menu_controller.js','full_game_runner.js','full_game_acceptance.js'):
        status,_,body=request(base_url,'/game/'+name)
        assert status==200 and body,name


@pytest.mark.parametrize('path',['/api/waves','/api/benchmark','/api/tas?wave=sans_bonegap1.csv',
    '/api/coverage','/old.html','/app.js','/style.css','/game/coverage.html','/game/operators.html'])
def test_retired_routes_are_absent(base_url,path):
    assert request(base_url,path)[0]==404


@pytest.mark.parametrize('path',['/api/solve','/api/oracle-plan','/api/coverage'])
def test_retired_post_routes_are_absent(base_url,path):
    assert request(base_url,path,{})[0]==404


def test_current_solver_endpoint_forwards_only_current_request(base_url,monkeypatch):
    from nohit.dashboard import csv_api
    calls=[]
    def solve(payload):
        calls.append(payload)
        return {'status':'unknown','verified':False,'reason':'wall_budget'}
    monkeypatch.setattr(csv_api,'solve_csv_request',solve)
    payload={'custom_csv':'0,EndAttack\n','initial':[320,304,0,0,0,0,0,1,750,0,0]}
    status,headers,body=request(base_url,'/api/solve-csv',payload)
    assert status==200 and calls==[payload]
    assert json.loads(body)['status']=='unknown'
    assert headers['Access-Control-Allow-Origin']=='*'


def test_invalid_json_returns_json_error(base_url):
    req=urllib.request.Request(base_url+'/api/solve-csv',data=b'{bad',method='POST')
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(req,timeout=10)
    assert caught.value.code==400
    assert 'Invalid JSON' in json.loads(caught.value.read())['error']


def test_runtime_status_and_cors_preflight(base_url):
    status,_,body=request(base_url,'/api/runtime-status')
    assert status==200 and json.loads(body)['engine']=='native-csv'
    status,headers,_=request(base_url,'/api/solve-csv',method='OPTIONS')
    assert status==204 and 'POST' in headers['Access-Control-Allow-Methods']


@pytest.mark.parametrize('path',['/../start_dashboard.py','/game/../start_dashboard.py'])
def test_static_paths_cannot_escape_served_directories(base_url,path):
    assert request(base_url,path)[0]==403
