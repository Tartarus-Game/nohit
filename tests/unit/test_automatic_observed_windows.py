"""The public entry must not bake a completed world before its first read."""
from nohit.engine import native_candidate,native_dynamic
from nohit.engine.csv_solver import solve_csv


def test_default_observed_solver_skips_inapplicable_completed_world(tmp_path,monkeypatch):
    path=tmp_path/'observed.csv'
    path.write_text('0,HeartMode,0\n0.1,GetHeartPos,x,y\n0.2,EndAttack\n')
    def forbidden(*args,**kwargs):
        raise AssertionError('completed-world entry must not bake this observed source')
    # The rolling module retains its real proposal function; intercept only
    # the inappropriate top-level completed-world attempt.
    assert native_dynamic.find_native_candidate is not forbidden
    monkeypatch.setattr(native_candidate,'find_native_candidate',forbidden)
    result=solve_csv(path,[320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.],
        dt_schedule=[1/60]*120,max_ticks=120,seconds=5)
    assert result['verified'] and result['status']=='candidate_found'
    assert result['search_stats']['observation_chunk_ticks']==240
    assert result['search_stats']['observation_preview_ticks']==720
