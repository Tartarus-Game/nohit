"""Known-dead closure integration preserves DFS semantics and binding scope."""
from dataclasses import replace
import numpy as np
import pytest

from nohit.engine.closure_search import try_known_dead_closure
from nohit.engine.parametric_dag import ParametricRouteIterator, _Node


def make_search(tmp_path, *, fatal=False):
    path=tmp_path/'window.csv';path.write_text('0,HeartMode,0\n0.2,EndAttack\n')
    search=ParametricRouteIterator(path,[320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.],
        allow_cancel=False,weights=np.zeros(4),closure_window=128,closure_trigger=1)
    if fatal:
        wave=search.stack[0].binding.wave
        wave.geometry_white=np.full((len(wave.env_schedule),1,4),np.nan)
        wave.geometry_white[8,0]=[0.,0.,640.,480.]
    search.expansions=1;search.furthest_tick=8
    return search


def signature(search):
    return [(id(n),n.tick,n.state.tobytes(),n.cursor,n.options,n.has_solution) for n in search.stack]


def test_unknown_does_not_change_stack_cursors_or_dead_contents(tmp_path):
    search=make_search(tmp_path);search.closure_proof_max_states=1
    before=signature(search),set(search.dead)
    assert try_known_dead_closure(search) is False
    assert (signature(search),set(search.dead))==before
    assert search.closure_stats['resource_limit']==1


def test_existing_frontier_limit_is_honored_with_a_larger_proof_budget(tmp_path):
    search=make_search(tmp_path)
    search.closure_max_states=1
    search.closure_proof_max_states=250000
    before=signature(search),set(search.dead)
    assert try_known_dead_closure(search) is False
    assert (signature(search),set(search.dead))==before
    assert search.closure_stats['resource_limit']==1
    assert search.closure_stats['complete']==0


def test_proof_closes_ancestor_and_memoizes_all_scoped_facts(tmp_path):
    search=make_search(tmp_path,fatal=True)
    key=search._key(search.stack[0])
    assert try_known_dead_closure(search) is True
    assert not search.stack and key in search.dead
    assert search.closure_stats['memoized_states']==len(search.dead)>1
    assert search.closure_stats['exhausted']==1


def test_cache_cap_only_reduces_memoization(tmp_path):
    search=make_search(tmp_path,fatal=True);search.closure_dead_cache_limit=1
    key=search._key(search.stack[0])
    assert try_known_dead_closure(search) is True
    assert not search.stack and search.dead=={key}
    assert search.closure_stats['cache_additions_skipped']>0


def test_nonroot_binding_uses_full_wave_clock_and_excludes_other_binding_facts(tmp_path):
    search=make_search(tmp_path)
    root=search.stack[0]
    root_at_four=_Node(4,root.state.copy(),root.binding,0)
    search.dead.add(search._key(root_at_four))
    binding=replace(root.binding,identity=root.binding.identity+b'other',history=((4,0,320.,304.),))
    search.stack=[_Node(4,root.state.copy(),binding,0)]
    search.closure_proof_max_states=1
    before=signature(search)
    assert try_known_dead_closure(search) is False
    assert signature(search)==before and search.closure_stats['known_dead_hits']==0
    assert binding.identity in search._known_dead_full_cspace


def test_nonroot_proof_reuses_only_its_own_dead_facts(tmp_path):
    search=make_search(tmp_path,fatal=True);root=search.stack[0]
    binding=replace(root.binding,identity=root.binding.identity+b'other',history=((4,0,320.,304.),))
    search.stack=[_Node(4,root.state.copy(),binding,0)]
    key=search._key(search.stack[0]);search.dead.add(key)
    assert try_known_dead_closure(search) is True
    assert not search.stack and search.closure_stats['known_dead_hits']==1


@pytest.mark.parametrize('quotient',['history','environment'])
def test_quotient_modes_do_not_consume_ordinary_indexed_facts(tmp_path,quotient):
    search=make_search(tmp_path);search.closure_proof_max_states=1
    search.dead.add(search._key(search.stack[0]))
    if quotient=='history':
        search.future_history_key=lambda binding,tick: ('history',binding.identity)
    else:
        search.environment_state_quotient=True
    before=signature(search),set(search.dead)
    assert try_known_dead_closure(search) is False
    assert (signature(search),set(search.dead))==before
    assert search.closure_stats['known_dead_hits']==0


def test_tiny_complete_search_keeps_ordinary_exhaustion_verdict(tmp_path):
    path=tmp_path/'deadline.csv'
    path.write_text('0,HeartMode,0\n0.05,BoneV,290,0,480,0,0\n0,BoneV,300,0,480,0,0\n'
                    '0,BoneV,310,0,480,0,0\n0,BoneV,320,0,480,0,0\n0,BoneV,330,0,480,0,0\n0.05,EndAttack\n')
    initial=[315.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.]
    kwargs=dict(weights=np.zeros(4),red_box_pruning=False,max_nodes=50000)
    ordinary=ParametricRouteIterator(path,initial,**kwargs)
    closure=ParametricRouteIterator(path,initial,closure_window=64,closure_trigger=1,**kwargs)
    closure._try_local_closure=lambda: try_known_dead_closure(closure)
    assert list(ordinary)==list(closure)==[]
    assert ordinary.status==closure.status=='exhausted_in_declared_model'
    assert closure.closure_stats['exhausted']>0
    assert closure.expansions<ordinary.expansions


def test_tiny_solvable_search_is_not_turned_into_unsat(tmp_path):
    path=tmp_path/'safe.csv';path.write_text('0,HeartMode,0\n0.05,EndAttack\n')
    search=ParametricRouteIterator(path,[320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.],
        weights=np.zeros(4),closure_window=16,closure_trigger=1,max_nodes=10000)
    search._try_local_closure=lambda: try_known_dead_closure(search)
    assert next(search)['status']=='candidate_found'
    assert search.closure_stats['exhausted']==0
