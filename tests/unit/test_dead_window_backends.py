"""Proof backends preserve every fact key, representative and budget boundary."""
from types import SimpleNamespace
import numpy as np
import pytest
from numba import config, get_num_threads

import nohit.engine.dead_window as module
from nohit.engine.cspace import bake_cspace
from nohit.engine.exact_state_dedup import state_keys, unique_state_indices


def scene(hold=4, transition='red', fatal=True):
    n=hold*3+3
    row=np.array([0.,0.,100.,100.,0.,1.,0.,1/240,750.,0.,40.,71.95,
                  0.,0.,0.,0.,100.,100.,0.,0.,100.,100.])
    env=np.tile(row,(n,1))
    if transition!='red':
        direction=int(transition[-1]);env[:,4]=1.;env[:,5]=direction
        env[hold+1:,5]=(direction+2)%4
        if transition.startswith('slam'):env[hold+1,6]=1.
    platforms=np.zeros((n,1,9));platforms[:,0]=[20.,80.,50.,7.,0.,-15.,1.,1.,-15.]
    platforms[:,0,1]-=np.arange(n)*15/240
    white=np.full((n,1,4),np.nan)
    if fatal:white[hold*3,0]=[0.,0.,100.,100.]
    wave=SimpleNamespace(env_schedule=env,platform_table=platforms,
        geometry_white=white,geometry_blue=np.full((n,1,4),np.nan),
        geometry_polygons=np.full((n,0,8),np.nan),origin=(0.,0.),dimensions=(100,100),
        pending_target=None,termination_reason='endattack',source_events=())
    initial=np.array([[40.,71.95,0.,-15.,8.,1.,env[0,4],env[0,5],750.,0.,0.],
                      [50.,40.,0.,0.,1.,0.,env[0,4],env[0,5],750.,0.,0.]])
    return wave,bake_cspace(wave),initial


def same(actual,expected):
    for name in ('status','reason','start_tick','reached_tick','counts','known_dead_hits',
                 'peak_frontier','expanded_states','safe_transition_rows','retained_representatives'):
        assert getattr(actual,name)==getattr(expected,name),name
    assert actual.frontier.shape==expected.frontier.shape
    assert actual.frontier.tobytes()==expected.frontier.tobytes()
    for name in ('_visited_layers','memo_layers'):
        aa=getattr(actual,name);bb=getattr(expected,name)
        assert len(aa)==len(bb)
        for a,b in zip(aa,bb):
            assert a.tick==b.tick
            for field in ('states','keys'):
                av=getattr(a,field);bv=getattr(b,field)
                assert av.shape==bv.shape and av.dtype==bv.dtype and av.tobytes()==bv.tobytes()


@pytest.mark.parametrize('hold',[1,4])
@pytest.mark.parametrize('transition',['red','blue0','blue1','blue2','blue3','slam3'])
@pytest.mark.parametrize('latch,quotient',[(False,False),(True,False),(True,True)])
def test_every_proof_array_matches_reference(hold,transition,latch,quotient,monkeypatch):
    wave,space,initial=scene(hold,transition)
    before=[a.tobytes() for a in (initial,wave.env_schedule,wave.platform_table)]
    kwargs=dict(binding_identity='a',controls=(8,0,8,16,31,1,3),hold=hold,cspace=space,
        input_latch_quotient=latch,control_quotient=quotient,max_states=100000)
    expected=module.prove_dead_window(wave,0,hold*3,initial,
        expansion_backend='scalar',dedup_backend='numpy',**kwargs)
    assert expected.status=='proven_dead'
    monkeypatch.setattr(module,'_PARALLEL_MIN_EDGES',0)
    monkeypatch.setattr(module,'_HASH_MIN_STATES',0)
    for expansion,dedup in [('scalar','hash'),('parallel','numpy'),('parallel','hash'),('auto','auto')]:
        actual=module.prove_dead_window(wave,0,hold*3,initial,
            expansion_backend=expansion,dedup_backend=dedup,workers=min(2,config.NUMBA_NUM_THREADS),**kwargs)
        same(actual,expected)
    assert before==[a.tobytes() for a in (initial,wave.env_schedule,wave.platform_table)]


@pytest.mark.parametrize('pending',[False,True])
@pytest.mark.parametrize('transition',['red','blue0','blue1','blue2','blue3','slam3'])
def test_exact_dedup_projection_matches_dag_even_at_proof_exit(pending,transition):
    wave,space,initial=scene(transition=transition)
    if pending:wave.pending_target={'tick':9}
    states=np.repeat(initial[:1],32,axis=0);states[:,4]=np.arange(32)
    row=module._next_row(wave,8)
    keys=module.dag_state_keys(wave,8,states)
    assert keys.tobytes()==state_keys(states,row).tobytes()
    _,expected=np.unique(keys,return_index=True)
    assert unique_state_indices(states,row).tobytes()==expected.tobytes()
    assert len(expected)==(32 if pending else 1 if transition=='red' else 2)


@pytest.mark.parametrize('pending',[False,True])
@pytest.mark.parametrize('latch,quotient',[(False,False),(True,False),(True,True)])
def test_known_dead_filter_and_terminal_pending_mask(pending,latch,quotient):
    wave,space,initial=scene(fatal=False)
    if pending:wave.pending_target={'tick':5}
    kwargs=dict(binding_identity='a',controls=(0,3),cspace=space,
        input_latch_quotient=latch,control_quotient=quotient)
    plain=module.prove_dead_window(wave,0,4,initial[:1],expansion_backend='scalar',dedup_backend='numpy',**kwargs)
    final=plain._visited_layers[-1]
    assert len(final.states)==(2 if pending or not latch else 1)
    facts=module.DeadFacts('a',4,(0,3),{4:{bytes(final.keys[0])}})
    expected=module.prove_dead_window(wave,0,4,initial[:1],known_dead=facts,
        expansion_backend='scalar',dedup_backend='numpy',**kwargs)
    actual=module.prove_dead_window(wave,0,4,initial[:1],known_dead=facts,
        expansion_backend='parallel',dedup_backend='hash',workers=1,**kwargs)
    same(actual,expected)
    assert actual.known_dead_hits>0
    assert actual.status==('unknown' if pending else 'proven_dead')


@pytest.mark.parametrize('budget,frontier',[(0,None),(1,None),(2,None),(10,None),(1000,1),(1000,2),(1000,4)])
def test_limits_precede_known_dead_filter_and_preserve_last_admitted_layer(budget,frontier):
    wave,space,initial=scene()
    common=dict(binding_identity='a',cspace=space)
    proof=module.prove_dead_window(wave,0,12,initial,expansion_backend='scalar',dedup_backend='numpy',**common)
    facts=module.DeadFacts('a',4,tuple(range(16)),
        {layer.tick:set(map(bytes,layer.keys)) for layer in proof.memo_layers if layer.tick>0})
    kwargs=dict(**common,known_dead=facts,max_states=budget,max_frontier_states=frontier)
    expected=module.prove_dead_window(wave,0,12,initial,expansion_backend='scalar',dedup_backend='numpy',**kwargs)
    actual=module.prove_dead_window(wave,0,12,initial,expansion_backend='parallel',dedup_backend='hash',workers=1,**kwargs)
    same(actual,expected)
    assert actual.reason=='resource_limit' and actual.memo_layers==()


def test_small_defaults_stay_scalar_numpy_and_initial_limit_precedes_expansion(monkeypatch):
    wave,space,initial=scene()
    def unexpected(*args,**kwargs):raise AssertionError('unexpected accelerated call')
    monkeypatch.setattr(module,'expand_parallel',unexpected)
    monkeypatch.setattr(module,'unique_state_indices',unexpected)
    module.prove_dead_window(wave,0,8,initial,binding_identity='a',cspace=space)
    monkeypatch.setattr(module,'_expand',unexpected)
    result=module.prove_dead_window(wave,0,8,initial,binding_identity='a',cspace=space,
        max_states=1,expansion_backend='parallel',dedup_backend='numpy')
    assert result.reason=='resource_limit' and result.expanded_states==0


def test_auto_policy_uses_quotiented_edges_and_restores_thread_mask(monkeypatch):
    wave,space,initial=scene(1,fatal=False)
    calls=[];original=module.expand_parallel
    def checked(*args,**kwargs):
        calls.append((len(args[0])*len(args[1]),kwargs['workers']))
        return original(*args,**kwargs)
    monkeypatch.setattr(module,'expand_parallel',checked)
    monkeypatch.setattr(module,'_PARALLEL_MIN_EDGES',25)
    before=get_num_threads()
    module.prove_dead_window(wave,0,1,initial,hold=1,binding_identity='a',cspace=space)
    assert calls==[]  # Two states * nine control representatives, not 32 raw edges.
    module.prove_dead_window(wave,0,1,initial,hold=1,binding_identity='a',cspace=space,control_quotient=False)
    assert calls==([] if config.NUMBA_NUM_THREADS==1 else [(32,2)])
    assert get_num_threads()==before


def test_exact_cumulative_budget_accepts_complete_proof_and_one_less_does_not():
    wave,space,initial=scene()
    kwargs=dict(binding_identity='a',cspace=space)
    reference=module.prove_dead_window(wave,0,12,initial,
        expansion_backend='scalar',dedup_backend='numpy',**kwargs)
    result=module.prove_dead_window(wave,0,12,initial,max_states=reference.retained_representatives,
        expansion_backend='parallel',dedup_backend='hash',workers=1,**kwargs)
    same(result,reference)
    limited=module.prove_dead_window(wave,0,12,initial,max_states=reference.retained_representatives-1,
        expansion_backend='parallel',dedup_backend='hash',workers=1,**kwargs)
    assert limited.reason=='resource_limit' and limited.memo_layers==()


@pytest.mark.parametrize('kwargs',[
    {'workers':True},{'workers':1.5},{'workers':0},{'workers':-1},{'workers':config.NUMBA_NUM_THREADS+1},
    {'expansion_backend':None},{'expansion_backend':'fast'},{'dedup_backend':None},{'dedup_backend':'approximate'}])
def test_invalid_configuration_rejected_without_thread_changes(kwargs):
    wave,space,initial=scene();before=get_num_threads()
    with pytest.raises(ValueError):module.prove_dead_window(wave,0,8,initial,binding_identity='a',cspace=space,**kwargs)
    assert get_num_threads()==before
