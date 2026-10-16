"""Actual HTTP endpoints preserve raw CSV bytes and the native AJAX text view."""
import hashlib
from http.server import ThreadingHTTPServer
import json
import threading
from urllib.request import Request, urlopen

import pytest

from nohit.dashboard.server import DashboardHandler


@pytest.fixture
def source_server():
    server=ThreadingHTTPServer(('127.0.0.1',0),DashboardHandler)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown();server.server_close();thread.join(timeout=1)


@pytest.mark.parametrize('raw',[
    b'\xef\xbb\xbf0,HeartMode,0\r\n0.1,EndAttack\r\n',
    '0,SansText,你好\r\n0,SansText,"line1\r\nline2"\n0,EndAttack\r'.encode('utf-8'),
])
def test_path_http_registration_exposes_native_text_hash_and_unchanged_raw_copy(tmp_path,source_server,raw):
    path=tmp_path/'原版.csv';path.write_bytes(raw)
    body=json.dumps({'csv_path':str(path)}).encode('utf-8')
    with urlopen(Request(source_server+'/api/csv-source',data=body,headers={'Content-Type':'application/json'})) as response:
        assert response.status==200;entry=json.load(response)
    native_text=raw.decode('utf-8-sig').replace('\r\n','\n')
    assert entry['id']==entry['raw_sha256']==hashlib.sha256(raw).hexdigest()
    assert entry['sha256']==hashlib.sha256(native_text.encode('utf-8')).hexdigest()
    assert entry['byte_count']==len(raw)
    path.write_bytes(b'changed after registration')
    with urlopen(source_server+'/api/csv-source/'+entry['id']) as response:
        descriptor=json.load(response)
    assert descriptor['text']==native_text
    with urlopen(source_server+entry['url']) as response:
        assert response.read()==raw
        assert response.headers['Content-Length']==str(len(raw))


def test_pasted_crlf_keeps_raw_identity_but_hashes_native_lf_text(source_server):
    text='0,SansText,你好\r\n0,EndAttack\r\n'
    with urlopen(Request(source_server+'/api/csv-source',data=json.dumps({'custom_csv':text}).encode(),
                         headers={'Content-Type':'application/json'})) as response:
        entry=json.load(response)
    with urlopen(source_server+'/api/csv-source/'+entry['id']) as response:
        descriptor=json.load(response)
    assert descriptor['text']==text.replace('\r\n','\n')
    assert descriptor['raw_sha256']==hashlib.sha256(text.encode()).hexdigest()
    assert descriptor['sha256']==hashlib.sha256(descriptor['text'].encode()).hexdigest()
    with urlopen(source_server+entry['url']) as response:
        assert response.read()==text.encode()


def test_prepared_source_download_and_original_import_have_separate_immutable_identities(tmp_path, source_server):
    raw = b'\xef\xbb\xbf0,HeartMode,0\r\n0.5,DaMaGePlAyEr,-10000,\r\n0.1,EndAttack\r\n'
    expected = raw.replace(b',DaMaGePlAyEr,', b',,')
    path = tmp_path/'scripted.csv'
    path.write_bytes(raw)
    body = json.dumps({'csv_path': str(path)}).encode('utf-8')
    with urlopen(Request(source_server+'/api/csv-source', data=body,
                         headers={'Content-Type': 'application/json'})) as response:
        entry = json.load(response)
    assert entry['id'] == entry['raw_sha256'] == hashlib.sha256(expected).hexdigest()
    assert entry['import_id'] == hashlib.sha256(raw).hexdigest()
    assert entry['id'] != entry['import_id']
    assert entry['byte_count'] == len(expected)
    path.write_bytes(b'changed after import')
    with urlopen(source_server+entry['url']) as response:
        assert response.read() == expected
    with urlopen(source_server+entry['original_url']) as response:
        assert response.read() == raw
        assert response.headers['Content-Length'] == str(len(raw))
    with urlopen(source_server+entry['import_url']) as response:
        imported = json.load(response)
    with urlopen(source_server+'/api/csv-source/'+entry['id']) as response:
        canonical = json.load(response)
    text = expected.decode('utf-8-sig').replace('\r\n', '\n')
    assert imported['text'] == canonical['text'] == text
    assert imported['sha256'] == hashlib.sha256(text.encode('utf-8')).hexdigest()
    assert imported['preparation']['original_raw_sha256'] == entry['import_id']
    assert imported['preparation']['executable_raw_sha256'] == entry['id']
    assert imported['preflight']['supported'] is True
    assert imported['preflight']['warnings'] == [dict(
        line=2, command='DaMaGePlAyEr', reason='scripted_damage_disabled')]
    assert 'preparation' not in canonical and 'import_id' not in canonical
    assert canonical['preflight']['warnings'] == []


def test_original_import_descriptors_do_not_alias_when_cleaned_sources_match(source_server):
    entries = []
    for spelling in ('DamagePlayer', 'damageplayer'):
        text = '0,'+spelling+',1,0\n'
        with urlopen(Request(source_server+'/api/csv-source',
                             data=json.dumps({'custom_csv': text}).encode('utf-8'),
                             headers={'Content-Type': 'application/json'})) as response:
            entries.append(json.load(response))
    assert entries[0]['id'] == entries[1]['id']
    assert entries[0]['import_id'] != entries[1]['import_id']
    for entry, spelling in zip(entries, ('DamagePlayer', 'damageplayer')):
        with urlopen(source_server+entry['import_url']) as response:
            imported = json.load(response)
        assert imported['preparation']['original_raw_sha256'] == entry['import_id']
        assert imported['preparation']['changes'][0]['command'] == spelling
        with urlopen(source_server+entry['original_url']) as response:
            assert response.read() == ('0,'+spelling+',1,0\n').encode('utf-8')
