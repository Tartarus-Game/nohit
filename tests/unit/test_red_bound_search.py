import numpy as np
import pytest
from nohit.engine.parametric_dag import ParametricRouteIterator


@pytest.mark.parametrize('decision_ticks',[1,4])
def test_red_certificate_stops_before_an_unbound_observation(tmp_path,monkeypatch,decision_ticks):
    import nohit.engine.parametric_dag as module
    path=tmp_path/'target.csv'
    path.write_text('0,HeartMode,0\n0.025,GetHeartPos,x,y\n0.05,EndAttack\n')
    search=ParametricRouteIterator(path,[320,304,0,0,0,0,0,1,750,0,0],
        decision_ticks=decision_ticks,weights=np.zeros(4),max_nodes=2)
    boundary=search.stack[0].binding.pending_target['tick']
    stops=[]
    def observe(*args):
        stops.append(args[-1])
        return False
    monkeypatch.setattr(module,'red_box_deadline',observe)
    with pytest.raises(StopIteration):next(search)
    assert stops==[boundary-1]
    assert search.status=='resource_limit' and search.red_box_pruned==0


@pytest.mark.parametrize('decision_ticks',[1,4])
def test_exact_future_coverage_prunes_before_enumerating_controls(tmp_path,decision_ticks):
    path=tmp_path/'covered.csv'
    path.write_text('0,HeartMode,0\n0.0125,BoneV,300,0,480,0,0\n0.03,EndAttack\n')
    # The rectangle is [300,310], whose expanded center interval is [298,312].
    initial=[305,304,0,0,0,0,0,1,750,0,0]
    common=dict(decision_ticks=decision_ticks,weights=np.zeros(4),max_nodes=10000)
    pruned=ParametricRouteIterator(path,initial,**common)
    ordinary=ParametricRouteIterator(path,initial,red_box_pruning=False,**common)
    assert list(pruned)==list(ordinary)==[]
    assert pruned.status==ordinary.status=='exhausted_in_declared_model'
    assert pruned.red_box_pruned==1 and pruned.expansions==0
    assert ordinary.expansions>0
