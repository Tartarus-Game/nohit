"""Real HTTP persistence for complete multipart campaign evidence."""
import base64
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from nohit.dashboard import server as dashboard
from nohit.dashboard.acceptance_evidence import read_evidence_manifest


@pytest.fixture
def evidence_server(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    root.mkdir()
    monkeypatch.setattr(dashboard, '__file__', str(root / 'nohit/dashboard/server.py'))
    game = root / 'c2-sans-fight'
    game.mkdir()
    monkeypatch.setattr(dashboard, 'C2_REPO_DIR', game)
    for name in ('c2runtime.js', 'data.js', 'attack_seed.js', 'tas_runner.js',
                 'full_game_runner.js', 'full_game_acceptance.js', 'lag_compensation.js',
                 'menu_controller.js', 'solver_state.js', 'csv_round_controller.js'):
        (game / name).write_text('// ' + name, encoding='utf-8')
    (game / 'sans_intro.csv').write_bytes(b'\xef\xbb\xbf0,HeartMode,0\r\n1,EndAttack\r\n')
    server = ThreadingHTTPServer(('127.0.0.1', 0), dashboard.DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}', root
    server.shutdown()
    server.server_close()
    thread.join(timeout=1)


def post(base, path, body):
    request = Request(base + path, data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json'})
    with urlopen(request) as response:
        assert response.status == 200
        return json.load(response)


def prepared_manifest(base, data):
    raw = json.dumps(data, ensure_ascii=False).encode('utf-8')
    descriptors = []
    for start in range(0, len(raw), 97):
        part = raw[start:start + 97]
        stored = post(base, '/api/acceptance-evidence', {'evidenceVersion': 3, 'encoding': 'base64',
            'sha256': hashlib.sha256(part).hexdigest(), 'data': base64.b64encode(part).decode()})
        descriptors.append(dict(index=len(descriptors), **stored))
    return {**{key: data[key] for key in ('suite', 'evidenceVersion', 'seed', 'clock', 'criterion', 'result')},
        'storage': 'json-utf8-parts-v1', 'evidenceParts': descriptors,
        'total_sha256': hashlib.sha256(raw).hexdigest(), 'total_byte_count': len(raw)}


def failed_record():
    return {'suite': 'continuous-normal-game', 'evidenceVersion': 3, 'seed': 42,
        'clock': 'original-runtime-realtime-catchup-240hz', 'criterion': 'test',
        'result': {'passed': False, 'status': 'failed_driver'},
        'tickEvidence': [[7, 92, 0, 0, 0, 3, 1, 1 / 240, 1.2345, 0,
            [320, 304, 0, 0, 3, 0, 0, 1, 750, 0, 0]]],
        'events': [{'fn': 'tlplay', 'param': '原始事件\r\n'}], 'computedPlans': [], 'rows': []}


def test_http_manifest_preserves_full_payload_and_adds_shared_source_and_text_hashes(evidence_server):
    base, root = evidence_server
    original = failed_record()
    manifest = prepared_manifest(base, original)
    saved = post(base, '/api/acceptance', manifest)
    path = Path(saved['trace'])
    assert path.parent == root / 'tools/real-game'
    stored = json.loads(path.read_text(encoding='utf-8'))
    assert read_evidence_manifest(stored, path.parent) == original
    assert stored['source_sha256']['csv_round_controller.js'] == hashlib.sha256(
        (root / 'c2-sans-fight/csv_round_controller.js').read_bytes()).hexdigest()
    csv = (root / 'c2-sans-fight/sans_intro.csv').read_bytes()
    assert stored['script_sha256']['sans_intro.csv'] == hashlib.sha256(csv).hexdigest()
    assert stored['script_text_sha256']['sans_intro.csv'] == hashlib.sha256(
        csv.decode('utf-8-sig').replace('\r\n', '\n').encode()).hexdigest()
    assert stored['script_text_sha256']['sans_intro.csv'] != stored['script_sha256']['sans_intro.csv']
    from nohit.dashboard.csv_api import implementation_hashes
    assert stored['solver_source_sha256'] == implementation_hashes()
    assert 'nohit/engine/csv_solver.py' in stored['solver_source_sha256']


def test_http_final_manifest_rejects_a_part_altered_after_upload(evidence_server):
    base, root = evidence_server
    manifest = prepared_manifest(base, failed_record())
    part = manifest['evidenceParts'][0]
    (root / 'tools/real-game' / part['path']).write_bytes(b'x' * part['byte_count'])
    with pytest.raises(HTTPError) as exc:
        post(base, '/api/acceptance', manifest)
    assert exc.value.code == 400
    assert not list((root / 'tools/real-game').glob('*.json'))


def test_http_success_claim_checks_reconstructed_damage_evidence(evidence_server):
    base, root = evidence_server
    original = failed_record()
    original.update(result={'passed': True, 'status': 'passed'}, winObserved=True, checkedTicks=1,
        firstDamage=None, tickGaps=[], clockErrors=[], protocolErrors=[], rows=[{'HP': 91, 'KR': 0}])
    manifest = prepared_manifest(base, original)
    with pytest.raises(HTTPError) as exc:
        post(base, '/api/acceptance', manifest)
    assert exc.value.code == 400
    assert not list((root / 'tools/real-game').glob('*.json'))
