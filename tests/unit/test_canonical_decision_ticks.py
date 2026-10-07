"""The public solver must not silently coarsen the requested input domain."""
import pytest

from nohit.engine.canonical_solver import solve_attack


@pytest.mark.parametrize('ticks',[True,0,2,1.0,None])
def test_invalid_decision_grid_is_rejected(tmp_path,ticks):
    path=tmp_path/'simple.csv'
    path.write_text('0,HeartMode,0\n0.05,EndAttack\n')
    with pytest.raises(ValueError,match='decision_ticks'):
        solve_attack(path,[320,304,0,0,0],decision_ticks=ticks)


@pytest.mark.parametrize('targeted',[False,True])
def test_single_tick_grid_reaches_public_solver(tmp_path,targeted):
    path=tmp_path/'simple.csv'
    path.write_text('0,HeartMode,0\n'+('0,GetHeartPos,x,y\n' if targeted else '')+'0.05,EndAttack\n')
    result=solve_attack(path,[320,304,0,0,0,0,0,1,750,0,0],
        decision_ticks=1,allow_cancel=False,max_ticks=100,
        weights={'clearance':0,'lookahead':0,'center':0,'switches':0})
    assert result['status']=='candidate_found'
    assert result['control_ticks']==1 and result['control_hz']==240
    assert len(result['actions'])==len(result['trajectory'])-1
    # A complete timing grid is not proof of the entire original game's model.
    assert result['complete_in_original_game'] is False
