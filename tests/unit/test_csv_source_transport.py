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
