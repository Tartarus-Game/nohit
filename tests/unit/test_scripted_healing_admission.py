import pytest
from nohit.engine.source_contract import model_issues


@pytest.mark.parametrize('amount', ['-15', '-142', '-0.01'])
def test_literal_healing_requires_opt_in(tmp_path, amount):
    path=tmp_path/'heal.csv'
    path.write_text(f'0,DamagePlayer,{amount},1\n0,EndAttack\n')
    assert model_issues(path)
    assert not model_issues(path,allow_scripted_healing=True)


@pytest.mark.parametrize('amount', ['141','999','0','-0','$HP','','nan','-inf'])
def test_positive_or_unresolved_damage_is_never_admitted(tmp_path, amount):
    path=tmp_path/'hurt.csv'
    path.write_text(f'0,DamagePlayer,{amount},1\n0,EndAttack\n')
    assert model_issues(path,allow_scripted_healing=True)


def test_positive_script_effect_requires_separate_opt_in_and_audit(tmp_path):
    from nohit.engine.csv_solver import solve_csv
    path=tmp_path/'script-effects.csv'
    path.write_text('0,HeartMode,0\n0,SansText,Hi.,\n'
        '0,DamagePlayer,-142,1\n0,DamagePlayer,141,1\n0.1,EndAttack\n')
    initial=[320,304,0,0,0,0,0,1,750,0,0]
    settings=dict(dt_schedule=[1/60]*1000,max_ticks=1000,search_strategy='native',seconds=3)
    strict=solve_csv(path,initial,allow_scripted_healing=True,**settings)
    assert strict['reason']=='unsupported_mechanism' and not strict['verified']
    projection=solve_csv(path,initial,allow_scripted_damage=True,**settings)
    assert projection['verified'] and not projection['original_replay_passed']
    assert projection['health_model']=='scripted_damage_native_replay_required'
    assert [e['amount'] for e in projection['scripted_damage_events']]==[-142,141]
    assert all(e['kr']==1 for e in projection['scripted_damage_events'])
    path.write_text('0,DamagePlayer,$unknown,1\n0.1,EndAttack\n')
    dynamic=solve_csv(path,initial,allow_scripted_damage=True,**settings)
    assert dynamic['reason']=='unsupported_mechanism'
