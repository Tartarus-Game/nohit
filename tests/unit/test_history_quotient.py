"""No-historical-information-loss contract for future-only DAG memo keys."""
from pathlib import Path
from itertools import product
import numpy as np
import pytest

from nohit.engine.history_quotient import FutureHistoryKey,certify_clears
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.parametric_dag import ParametricRouteIterator,_Node


def bindings(tmp_path,body):
    path=tmp_path/'quotient.csv';path.write_text(body)
    template=ParametricEnvironment(path,max_ticks=100)
    root=template.bind()
    return path,template,template.extend(root,20,40),template.extend(root,80,90)


def test_clear_dead_variables_merges_future_only_after_real_clear_tick(tmp_path):
    path,template,a,b=bindings(tmp_path,
        '0,GetHeartPos,hx,hy\n0,BoneV,$hx,100,20,0,0\n'
        '0.0125,BlackScreen,1\n0,HeartTeleport,320,304\n'
        '0,Set,hx,320\n0.0125,BoneV,$hx,100,20,0,0\n0.025,EndAttack\n')
    key=FutureHistoryKey(template)
    assert len(key.certificates)==1
    clear=next(t for t,cmd,args in a.wave.source_events if cmd=='blackscreen')
    assert key(a,clear-1)!=key(b,clear-1)
    assert key(a,clear)!=key(b,clear)  # conservative sub-tick boundary
    assert key(a,clear+1)==key(b,clear+1)
    assert a.identity!=b.identity and a.history!=b.history
    assert template.bind(a.history) is a and template.bind(b.history) is b
    # Exercise the production memo-key consumer, without merging the actual
    # bindings used to reconstruct each path's observations and native replay.
    search=ParametricRouteIterator(path,[320,304,0,0,0,0,0,1,750,0,0],
                                   history_quotient=True,max_ticks=100)
    state=np.array([320,304,0,0,0,0,0,1,750,0,0.])
    na=_Node(clear+1,state,a,0);nb=_Node(clear+1,state.copy(),b,0)
    assert search._key(na)==search._key(nb)
    search.dead.add(search._key(na))
    assert search._key(nb) in search.dead
    assert na.binding.history!=nb.binding.history
    assert search._key(_Node(clear+2,state.copy(),b,0))!=search._key(na)
    for index in range(11):
        changed=state.copy()
        # The existing input-latch bisimulation keeps the active blue jump
        # bit, while provably irrelevant old key bits were already quotiented.
        changed[index]+=4 if index==4 else 1
        assert search._key(_Node(clear+1,changed,b,0))!=search._key(na)


@pytest.mark.parametrize('body',[
    # Live old target is read after the clear.
    '0,GetHeartPos,hx,hy\n0.0125,BlackScreen,1\n0.0125,BoneV,$hx,100,20,0,0\n0.025,EndAttack\n',
    # Teleport does not destroy the target-dependent object.
    '0,GetHeartPos,hx,hy\n0,BoneV,$hx,100,20,0,0\n0.0125,HeartTeleport,320,304\n0.025,EndAttack\n',
    # A fixed clear cannot reset a target-dependent arena width.
    '0,GetHeartPos,hx,hy\n0,CombatZoneResize,0,0,$hx,100\n0.0125,BlackScreen,1\n0.025,EndAttack\n',
    # This certificate cannot reason about branches or argument indirection.
    '0,GetHeartPos,hx,hy\n0,JmpRel,1\n0.0125,BlackScreen,1\n0.025,EndAttack\n',
])
def test_live_variables_live_objects_and_persistent_taint_never_merge(tmp_path,body):
    path,template,a,b=bindings(tmp_path,body)
    key=FutureHistoryKey(template)
    assert not key.certificates
    assert key(a,8)!=key(b,8)


def test_unbound_target_does_not_require_baking_future_arrays(tmp_path):
    path,template,a,b=bindings(tmp_path,
        '0,GetHeartPos,hx,hy\n0,BoneV,$hx,100,20,0,0\n'
        '0.0125,BlackScreen,1\n0.025,GetHeartPos,hx,hy\n'
        '0,BoneV,$hx,100,20,0,0\n0.025,EndAttack\n')
    assert a.pending_target and b.pending_target and not a.complete and not b.complete
    key=FutureHistoryKey(template)
    assert key(a,4)==key(b,4)
    assert a.pending_target['tick']>4
    # Different observations after the clear must remain distinguished.
    aa=template.extend(a,25,45);bb=template.extend(b,85,95)
    tick=aa.history[-1][0]
    assert key(aa,tick)!=key(bb,tick)
    ab=template.extend(b,25,45)
    assert key(aa,tick)==key(ab,tick)
    assert aa.history!=ab.history


def test_default_search_keeps_exact_history_keys(tmp_path):
    path,template,a,b=bindings(tmp_path,
        '0,GetHeartPos,hx,hy\n0.0125,BlackScreen,1\n0.025,EndAttack\n')
    search=ParametricRouteIterator(path,[320,304,0,0,0,0,0,1,750,0,0],max_ticks=100)
    state=np.array([320,304,0,0,0,0,0,1,750,0,0.])
    assert search._key(_Node(4,state,a,0))!=search._key(_Node(4,state.copy(),b,0))


def test_unsupported_native_variable_name_expansion_has_no_certificate(tmp_path):
    path=tmp_path/'indirect.csv'
    path.write_text('0,GetHeartPos,HeartX,$HeartY\n0,BlackScreen,1\n0.1,EndAttack\n')
    assert not certify_clears(path)


def test_original_realhell_is_not_enabled_by_the_restricted_certificate():
    root=Path(__file__).resolve().parents[2]
    assert not certify_clears(next(root.glob('Real HELL*.csv')))


@pytest.mark.parametrize('callback',['1','TLResume','$callback'])
def test_resize_callbacks_are_outside_the_restricted_proof(tmp_path,callback):
    path=tmp_path/'callback.csv'
    path.write_text('0,CombatZoneResize,0,0,100,100,'+callback+'\n0,BlackScreen,1\n0.1,EndAttack\n')
    assert not certify_clears(path)


@pytest.mark.parametrize('overwrite',[False,True])
def test_exhaustive_small_control_suffix_languages(tmp_path,overwrite):
    body=('0,GetHeartPos,hx,hy\n0,BoneV,$hx,100,20,0,0\n'
          '0.0125,BlackScreen,1\n0,HeartTeleport,320,304\n')
    if overwrite:body+='0,Set,hx,320\n'
    body+='0.0125,BoneV,$hx,100,20,0,0\n0.025,EndAttack\n'
    path,template,a,b=bindings(tmp_path,body)
    search=ParametricRouteIterator(path,[320,304,0,0,0,0,0,1,750,0,0],
                                   history_quotient=True,max_ticks=100,weights=[0,0,0,0])
    initial=np.array([20.,105.,0,0,0,0,1,1,750,0,0])
    languages=[];traces=[]
    for binding in (a,b):
        safe_words=set();states={}
        for word in product((0,1,2,4),repeat=3):
            node=_Node(4,initial.copy(),binding,0)
            for mask in word:
                node=search._advance(node,mask)
                if node is None:break
            if node is not None:
                safe_words.add(word);states[word]=node.state.tobytes()
        languages.append(safe_words);traces.append(states)
    if overwrite:
        assert languages[0]==languages[1] and traces[0]==traces[1]
        assert len(languages[0])==64
    else:
        assert languages[0]!=languages[1]


def test_actual_dead_memo_and_expansions_shrink_after_history_join(tmp_path):
    path=tmp_path/'join_then_blocked.csv'
    path.write_text('0,HeartMode,0\n'
                    '0.004167,GetHeartPos,hx,hy\n0,BoneV,$hx,100,20,0,0\n'
                    '0.008333,BlackScreen,1\n0.008333,HeartTeleport,320,304\n'
                    '0.016667,BoneH,0,304,640,0,0\n0.008333,EndAttack\n')
    counts=[]
    for quotient in (False,True):
        search=ParametricRouteIterator(path,[320,304,0,0,0,0,0,1,750,0,0],
            history_quotient=quotient,max_ticks=100,weights=[0,0,0,0],
            red_box_pruning=False)
        # Isolate history merging: the independent red-box certificate can
        # prove these leaves before expansion, hiding the expansion reduction.
        # Exhaust this declared tiny action language exactly: two initial
        # controls, then only coast. Both complete prefixes reach the same
        # full player state before the unavoidable terminal barrier.
        search._options=lambda node:[0,1] if node.tick==0 else [0]
        with pytest.raises(StopIteration):next(search)
        assert search.status=='exhausted_in_declared_model'
        counts.append((len(search.dead),search.expansions))
    assert counts[1][0]<counts[0][0]
    assert counts[1][1]<counts[0][1]
    assert counts==[(5,5),(4,4)]
