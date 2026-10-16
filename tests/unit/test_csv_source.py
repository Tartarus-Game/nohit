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


def test_native_source_preflight_cleans_scripted_damage_and_retains_original_import():
    text = '0,setmaxhp,92\n0,damafeeplayer,0\n0,NoTooth,0\n0,DamagePlayer,-10000,\n'
    sources = {}
    entry = register_csv_source({'custom_csv': text}, sources)
    check = entry['preflight']
    assert check['supported'] is True
    assert check['scope'] == 'source_admission_only'
    assert check['termination_policy'] == 'eof_hazards_drained'
    assert check['issues'] == []
    assert [(warning['line'], warning['command'], warning['reason']) for warning in check['warnings']] == [
        (1, 'setmaxhp', 'native_function_has_no_handler'),
        (2, 'damafeeplayer', 'native_function_has_no_handler'),
        (3, 'NoTooth', 'native_function_has_no_handler'),
        (4, 'DamagePlayer', 'scripted_damage_disabled')]
    expected = text.replace(',DamagePlayer,', ',,').encode('utf-8')
    assert sources[entry['id']][0] == expected
    assert entry['id'] == entry['raw_sha256'] == hashlib.sha256(expected).hexdigest()
    assert entry['import_id'] == hashlib.sha256(text.encode('utf-8')).hexdigest()
    assert entry['import_url'] == '/api/csv-source/import/' + entry['import_id']
    assert entry['original_url'] == entry['import_url'] + '.original.csv'
    assert sources['import:' + entry['import_id']][2] == text.encode('utf-8')
    assert entry['preparation']['changes'] == [dict(
        line=4, command='DamagePlayer', action='disable_command_keep_delay')]


def test_distinct_original_imports_can_share_one_executable_source_without_provenance_leaks():
    sources = {}
    first = register_csv_source({'custom_csv': '0,DamagePlayer,1,2\n'}, sources)
    second = register_csv_source({'custom_csv': '0,dAMAGEpLAYER,1,2\n'}, sources)
    assert first['id'] == second['id']
    assert first['import_id'] != second['import_id']
    assert len(sources) == 3
    for entry, spelling in ((first, 'DamagePlayer'), (second, 'dAMAGEpLAYER')):
        imported = sources['import:' + entry['import_id']][1]
        assert imported['preparation']['original_raw_sha256'] == entry['import_id']
        assert imported['preparation']['executable_raw_sha256'] == entry['id']
        assert imported['preparation']['changes'][0]['command'] == spelling
    canonical = sources[first['id']][1]
    assert 'preparation' not in canonical and 'import_id' not in canonical
    assert canonical['preflight']['warnings'] == []
    clean = register_csv_source({'custom_csv': '0,,1,2\n'}, sources)
    assert clean['id'] == first['id'] and 'import_id' not in clean
    assert len(sources) == 3


def test_native_source_preflight_uses_eof_policy_and_admits_audited_noops():
    entry = register_csv_source({'custom_csv': '0,score,0\n0,mus_zz_megalovania\n'}, {})
    assert entry['preflight']['supported'] is True
    assert entry['preflight']['issues'] == []


def test_native_source_warns_and_continues_only_for_confirmed_absent_handlers():
    entry = register_csv_source({'custom_csv': '0,SETMAXHP,92\n0,DamafeePlayer,0\n0,NoTooth,0\n'}, {})
    assert entry['preflight']['supported'] is True
    assert len(entry['preflight']['warnings']) == 3
    unknown = register_csv_source({'custom_csv': '0,AnUnauditedFunction,0\n'}, {})
    assert unknown['preflight']['supported'] is False
    assert unknown['preflight']['warnings'] == []


def test_absent_handler_permission_requires_the_audited_native_source(monkeypatch):
    from nohit.engine import native_function_dispatch as dispatch
    monkeypatch.setattr(dispatch, '_current_registry_matches', lambda: False)
    entry = register_csv_source({'custom_csv': '0,NoTooth,0\n'}, {})
    assert entry['preflight']['supported'] is False
    assert entry['preflight']['warnings'] == []


def test_absent_handler_audit_rechecks_native_bytes_after_a_previous_success(monkeypatch):
    from pathlib import Path
    text = '0,NoTooth,0\n'
    assert register_csv_source({'custom_csv': text}, {})['preflight']['supported']
    read_bytes = Path.read_bytes
    monkeypatch.setattr(Path, 'read_bytes', lambda path:
        b'changed-native-handler-registry' if path.name == 'data.js' else read_bytes(path))
    entry = register_csv_source({'custom_csv': text}, {})
    assert entry['preflight']['supported'] is False
    assert entry['preflight']['warnings'] == []
