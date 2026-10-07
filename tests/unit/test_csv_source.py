"""The game and planner receive identical text from an immutable byte copy."""
import hashlib
import pytest
from nohit.dashboard.csv_source import register_csv_source


def test_registration_preserves_original_bytes_and_freezes_source(tmp_path):
    path = tmp_path/'测试.csv'
    raw = b'\xef\xbb\xbf0,HeartMode,0\r\n0.1,EndAttack\r\n'
    path.write_bytes(raw)
    sources = {}
    entry = register_csv_source({'csv_path':str(path)},sources)
    assert sources[entry['id']][0] == raw == path.read_bytes()
    assert entry['raw_sha256'] == hashlib.sha256(raw).hexdigest()
    assert entry['sha256'] == hashlib.sha256(raw[3:].replace(b'\r\n',b'\n')).hexdigest()
    path.write_bytes(b'changed')
    assert sources[entry['id']][0] == raw


def test_paste_keeps_newlines_and_has_one_content_identity():
    sources = {}
    content = '0,SansText,你好\n0,EndAttack\n'
    a = register_csv_source({'custom_csv':content},sources)
    b = register_csv_source({'custom_csv':content},sources)
    assert a == b and len(sources) == 1
    assert sources[a['id']][0] == content.encode('utf-8')
    assert sources[a['id']][1]['text'] == content


@pytest.mark.parametrize('data', [{},{'csv_path':'a.csv','custom_csv':'a'},
                                   {'custom_csv':3}, {'csv_path':'a.txt'}])
def test_invalid_sources_do_not_register(data):
    sources = {}
    with pytest.raises(ValueError):
        register_csv_source(data,sources)
    assert not sources
