"""Default one-click solving cleans scripted health effects before search."""
import hashlib

from nohit.dashboard.csv_api import solve_csv_request


INITIAL=[320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.]


def test_default_api_disables_csv_damage_and_records_exact_executable_source(tmp_path):
    source=tmp_path/'original.csv'
    raw=b'0,HeartMode,0\r\n0,DamagePlayer,-10000,\r\n0.1,EndAttack\r\n'
    source.write_bytes(raw)
    result=solve_csv_request(dict(csv_path=str(source),initial=INITIAL,max_ticks=60))
    assert result['status']=='candidate_found' and result['verified']
    assert source.read_bytes()==raw
    assert result['source_preparation']['original_raw_sha256']==hashlib.sha256(raw).hexdigest()
    assert result['csv_sha256']==hashlib.sha256(raw.replace(b'DamagePlayer',b'')).hexdigest()
    assert result['warnings']==[dict(line=2,command='DamagePlayer',reason='scripted_damage_disabled')]
    assert result['visualization']['csv_sha256']==result['csv_sha256']
    assert result['budget_selection']['mode']=='auto'


def test_default_paste_cleans_nonfinite_health_and_keeps_other_mechanisms_strict():
    result=solve_csv_request(dict(custom_csv='0,DamagePlayer,NaN,\n0,SomeNewMechanism,x\n0,EndAttack\n',
        initial=INITIAL,max_ticks=10))
    assert result['status']=='unknown' and not result['verified']
    assert [(issue.get('command'),issue['reason']) for issue in result['issues']]==[
        ('SomeNewMechanism','mechanism_not_validated')]
    assert result['warnings']==[dict(line=1,command='DamagePlayer',reason='scripted_damage_disabled')]


def test_path_without_scripted_damage_is_frozen_before_budget_search_and_visualization(tmp_path, monkeypatch):
    from nohit.dashboard import csv_api
    source=tmp_path/'mutable.csv'
    captured=b'0,HeartMode,0\r\n0.1,EndAttack\r\n'
    changed=b'0,HeartMode,0\r\n0.2,EndAttack\r\n'
    source.write_bytes(captured)
    select=csv_api._budget_selection
    paths=[]
    def edit_after_capture(data,path):
        paths.append(path)
        source.write_bytes(changed)
        return select(data,path)
    monkeypatch.setattr(csv_api,'_budget_selection',edit_after_capture)
    result=solve_csv_request(dict(csv_path=str(source),initial=INITIAL,max_ticks=30))
    expected=hashlib.sha256(captured).hexdigest()
    assert result['status']=='candidate_found' and result['verified']
    assert result['csv_sha256']==result['visualization']['csv_sha256']==expected
    assert result['source_preparation']['original_raw_sha256']==expected
    assert result['source_preparation']['executable_raw_sha256']==expected
    assert result['source_preparation']['changes']==[]
    assert paths[0]!=source and source.read_bytes()==changed
