"""Bellman false means no suffix exists, not that one prefix was enumerated."""
import numpy as np

from nohit.engine.parametric_dag import ParametricRouteIterator, _Node


def test_diamond_keeps_all_prefixes_to_a_successful_shared_suffix(tmp_path):
    path=tmp_path/'diamond.csv'
    path.write_text('0,HeartMode,0\n0.05,EndAttack\n')
    search=ParametricRouteIterator(path,[320,304,0,0,0,0,0,1,750,0,0],
                                   weights=np.zeros(4),max_ticks=100)
    # A tiny exact DAG: two labelled edges at each layer, both reaching the
    # same next state. Input labels are distinct route evidence. The test
    # supplies graph transitions so it tests memo semantics independently of
    # game physics, geometry, and control-equivalence optimizations.
    terminal=len(search.stack[0].binding.wave.env_schedule)-1
    search._options=lambda node:[0,1]
    def advance(node,mask):
        tick=terminal if node.tick else 4
        return _Node(tick,node.state.copy(),node.binding,mask)
    search._advance=advance
    candidates=list(search)
    assert [c['actions'] for c in candidates]==[[0,0],[0,1],[1,0],[1,1]]
    assert not search.dead
    assert search.status=='exhausted_in_declared_model'


def test_actual_dead_suffix_remains_memoized(tmp_path):
    path=tmp_path/'dead.csv'
    path.write_text('0,HeartMode,0\n0.05,EndAttack\n')
    search=ParametricRouteIterator(path,[320,304,0,0,0,0,0,1,750,0,0],
                                   weights=np.zeros(4),max_ticks=100)
    search._options=lambda node:[0,1]
    calls=[]
    def advance(node,mask):
        calls.append((node.tick,mask))
        if node.tick:return None
        return _Node(4,node.state.copy(),node.binding,mask)
    search._advance=advance
    assert list(search)==[]
    assert calls==[(0,0),(4,0),(4,1),(0,1)]
    assert len(search.dead)==2
