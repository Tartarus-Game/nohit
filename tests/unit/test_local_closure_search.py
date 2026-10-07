import numpy as np
from nohit.engine.parametric_dag import ParametricRouteIterator


def test_full_local_exhaustion_closes_ancestor_without_changing_verdict(tmp_path):
    path=tmp_path/'deadline.csv'
    path.write_text('0,HeartMode,0\n0.05,BoneV,290,0,480,0,0\n0,BoneV,300,0,480,0,0\n0,BoneV,310,0,480,0,0\n0,BoneV,320,0,480,0,0\n0,BoneV,330,0,480,0,0\n0.05,EndAttack\n')
    initial=[315,304,0,0,0,0,0,1,750,0,0]
    common=dict(weights=np.zeros(4),red_box_pruning=False,max_nodes=50000)
    ordinary=ParametricRouteIterator(path,initial,**common)
    closure=ParametricRouteIterator(path,initial,closure_window=64,closure_trigger=1,**common)
    assert list(closure)==list(ordinary)==[]
    assert closure.status==ordinary.status=='exhausted_in_declared_model'
    assert closure.closure_stats['exhausted']>0
    assert closure.expansions<ordinary.expansions


def test_nonempty_or_resource_limited_relation_leaves_stack_unchanged(tmp_path):
    path=tmp_path/'safe.csv';path.write_text('0,HeartMode,0\n0.1,EndAttack\n')
    for limit in (1,100000):
        search=ParametricRouteIterator(path,[320,304,0,0,0,0,0,1,750,0,0],
            weights=np.zeros(4),closure_window=64,closure_trigger=1,closure_max_states=limit)
        search.expansions=2;search.furthest_tick=8
        stack=search.stack.copy()
        assert search._try_local_closure() is False
        assert search.stack==stack and not search.dead
        assert search.closure_stats['resource_limit' if limit==1 else 'complete']==1
