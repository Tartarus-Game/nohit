"""Execution backends preserve the complete relation, ordering and budgets."""
from types import SimpleNamespace
import numpy as np
import pytest
from numba import config,get_num_threads

import nohit.engine.local_relation as module
from nohit.engine.cspace import bake_cspace
from nohit.engine.discrete_operator import step_mask_into


def scene(hold=4,transition='red'):
    n=hold*4+2
    row=np.array([0.,0.,100.,100.,0.,1.,0.,1/240,750.,0.,40.,71.95,
                  0.,0.,0.,0.,100.,100.,0.,0.,100.,100.])
    env=np.tile(row,(n,1));env[:,7]+=np.arange(n)*1e-7
    if transition!='red':
        direction=int(transition[-1])
        env[:,4]=1.;env[:,5]=direction
        env[hold+1:,5]=(direction+2)%4
        if transition.startswith('slam'):
            env[:hold+1,4]=0.;env[hold+1,6]=1.
    platforms=np.zeros((n,1,9))
    platforms[:,0]=[20.,80.,50.,7.,0.,-15.,1.,1.,-15.]
    platforms[:,0,1]-=np.arange(n)*15/240
    white=np.full((n,1,4),np.nan)
    white[hold:hold*3,0]=[46.,30.,54.,60.]
    wave=SimpleNamespace(env_schedule=env,platform_table=platforms,
        geometry_white=white,geometry_blue=np.full((n,1,4),np.nan),
        geometry_polygons=np.full((n,0,8),np.nan),origin=(0.,0.),dimensions=(100,100),
        pending_target=None,termination_reason='endattack',source_events=())
    initial=np.array([[40.,71.95,0.,-15.,0.,1.,env[0,4],env[0,5],750.,0.,0.],
                      [50.,40.,0.,0.,8.,0.,env[0,4],env[0,5],750.,0.,0.],
                      [13.,13.,-150.,0.,1.,0.,env[0,4],env[0,5],750.,0.,0.]])
    return wave,bake_cspace(wave),initial


def same(actual,expected):
    assert (actual.status,actual.start_tick,actual.reached_tick,actual.counts,
        actual.input_latch_quotient,actual.control_quotient)==(
        expected.status,expected.start_tick,expected.reached_tick,expected.counts,
        expected.input_latch_quotient,expected.control_quotient)
    for name in ('layers','parents','masks'):
        aa=getattr(actual,name);bb=getattr(expected,name)
        assert len(aa)==len(bb)
        for a,b in zip(aa,bb):
            assert a.shape==b.shape and a.dtype==b.dtype and a.tobytes()==b.tobytes()
    assert actual.states.tobytes()==expected.states.tobytes()
    assert actual.states is actual.layers[-1]
    for index in {0,len(actual.states)//2,len(actual.states)-1}:
        if index<0 or not len(actual.states):continue
        assert actual.witness(index)==expected.witness(index)
        assert actual.origin_index(index)==expected.origin_index(index)


@pytest.mark.parametrize('hold',[1,4])
@pytest.mark.parametrize('transition',['red','blue0','blue1','blue2','blue3','slam3'])
@pytest.mark.parametrize('latch,controls',[(False,False),(True,False),(True,True)])
def test_full_relation_all_bytes_match_reference(hold,transition,latch,controls,monkeypatch):
    wave,space,initial=scene(hold,transition)
    before=[a.tobytes() for a in (initial,wave.env_schedule,wave.platform_table)]
    args=dict(controls=(8,0,8,16,31,1,3),hold=hold,cspace=space,
        input_latch_quotient=latch,control_quotient=controls,max_states=100000)
    reference=module.full_local_relation(wave,0,hold*4,initial,
        expansion_backend='scalar',dedup_backend='numpy',**args)
    # Force auto branches even in this small fixture; policy thresholds have
    # separate coverage below and never change the relation being verified.
    monkeypatch.setattr(module,'_PARALLEL_MIN_EDGES',0)
    monkeypatch.setattr(module,'_HASH_MIN_STATES',0)
    for expansion,dedup in [('scalar','hash'),('parallel','numpy'),('parallel','hash'),('auto','auto')]:
        actual=module.full_local_relation(wave,0,hold*4,initial,
            expansion_backend=expansion,dedup_backend=dedup,workers=1 if config.NUMBA_NUM_THREADS==1 else 2,**args)
        same(actual,reference)
    assert before==[a.tobytes() for a in (initial,wave.env_schedule,wave.platform_table)]


@pytest.mark.parametrize('budget',[0,1,2,16,100])
@pytest.mark.parametrize('latch,controls',[(False,False),(True,False),(True,True)])
def test_budget_retains_identical_last_complete_layers(budget,latch,controls):
    wave,space,initial=scene()
    kwargs=dict(cspace=space,max_states=budget,input_latch_quotient=latch,control_quotient=controls)
    expected=module.full_local_relation(wave,0,16,initial,
        expansion_backend='scalar',dedup_backend='numpy',**kwargs)
    actual=module.full_local_relation(wave,0,16,initial,
        expansion_backend='parallel',dedup_backend='hash',workers=1,**kwargs)
    same(actual,expected)
    assert actual.status=='resource_limit'


def test_terminal_full_masks_and_all_scalar_witnesses():
    wave,space,initial=scene(1)
    wave.geometry_white[:]=np.nan;space=bake_cspace(wave)
    initial=initial[:1].copy();initial[0,:4]=[50.,50.,0.,0.]
    result=module.full_local_relation(wave,0,3,initial,hold=1,controls=tuple(range(32)),
        cspace=space,input_latch_quotient=True,control_quotient=True,
        expansion_backend='parallel',dedup_backend='hash',workers=1)
    assert result.status=='complete' and set(result.states[:,4])==set(range(32))
    for index,state in enumerate(result.states):
        actual=initial[result.origin_index(index)].copy()
        for tick,mask in enumerate(result.witness(index),1):
            step_mask_into(actual,mask,wave.env_schedule[tick],wave.platform_table[tick],actual)
        assert actual.tobytes()==state.tobytes()


@pytest.mark.parametrize('initial_empty',[False,True])
def test_exhausted_relation_keeps_same_empty_layer(initial_empty):
    wave,space,initial=scene()
    if initial_empty:initial=initial[:0]
    else:wave.geometry_white[:,0]=[0.,0.,100.,100.];space=bake_cspace(wave)
    reference=module.full_local_relation(wave,0,8,initial,cspace=space,
        expansion_backend='scalar',dedup_backend='numpy')
    result=module.full_local_relation(wave,0,8,initial,cspace=space,
        expansion_backend='parallel',dedup_backend='hash',workers=1)
    same(result,reference)
    assert result.status=='exhausted' and result.reached_tick==4


def test_auto_policy_counts_quotiented_edges_and_restores_threads(monkeypatch):
    wave,space,initial=scene(1)
    initial=np.tile(initial[:1],(100,1))
    calls=[];original=module.expand_parallel
    def checked(*args,**kwargs):
        calls.append((len(args[0])*len(args[1]),kwargs['workers']))
        return original(*args,**kwargs)
    monkeypatch.setattr(module,'expand_parallel',checked)
    monkeypatch.setattr(module,'_PARALLEL_MIN_EDGES',1200)
    before=get_num_threads()
    module.full_local_relation(wave,0,2,initial,hold=1,cspace=space,
        input_latch_quotient=True,control_quotient=True)
    assert calls==[]  # 100 * 9 representatives, despite 100 * 16 raw masks.
    module.full_local_relation(wave,0,2,initial,hold=1,cspace=space)
    assert calls==([] if config.NUMBA_NUM_THREADS==1 else [(1600,2)])
    assert get_num_threads()==before


def test_small_default_relation_keeps_scalar_numpy_paths(monkeypatch):
    wave,space,initial=scene(1)
    def unexpected(*args,**kwargs):raise AssertionError('small relation used accelerated backend')
    monkeypatch.setattr(module,'expand_parallel',unexpected)
    monkeypatch.setattr(module,'unique_state_indices',unexpected)
    module.full_local_relation(wave,0,2,initial[:1],hold=1,cspace=space)


def test_initial_budget_precedes_any_expansion(monkeypatch):
    wave,space,initial=scene()
    def unexpected(*args,**kwargs):raise AssertionError('resource-limited frontier was expanded')
    monkeypatch.setattr(module,'_expand',unexpected)
    monkeypatch.setattr(module,'expand_parallel',unexpected)
    result=module.full_local_relation(wave,0,8,initial,cspace=space,max_states=0,
        expansion_backend='parallel',dedup_backend='hash')
    assert result.status=='resource_limit' and result.counts==[(0,3)]


@pytest.mark.parametrize('kwargs',[
    {'workers':True},{'workers':1.5},{'workers':0},{'workers':-1},{'workers':config.NUMBA_NUM_THREADS+1},
    {'expansion_backend':None},{'expansion_backend':'fast'},
    {'dedup_backend':None},{'dedup_backend':'approximate'},
])
def test_invalid_backend_configuration_rejected_without_thread_changes(kwargs):
    wave,space,initial=scene();before=get_num_threads()
    with pytest.raises(ValueError):module.full_local_relation(wave,0,8,initial,cspace=space,**kwargs)
    assert get_num_threads()==before
