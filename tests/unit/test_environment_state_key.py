"""Exact committed-state equality is independent of historical evidence."""
import copy
import struct

import numpy as np
import pytest

from nohit.engine.environment_state_key import encode_typed,encode_environment_state,REQUIRED_STATE_FIELDS
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.parametric_dag import ParametricRouteIterator,_Node


def snapshot():
    state=dict.fromkeys(REQUIRED_STATE_FIELDS,None)
    state.update(phase='post_world_tick',vars={'x':1.},active_blasters=[],next_tick=4)
    return state


def test_typed_encoding_is_injective_for_ambiguous_python_values():
    values=[None,False,True,0,1,0.,-0.,1.,'1','1.0',b'1',(),[],{},
            ('ab','c'),('a','bc'),[1,2],(1,2),np.float64(1),np.int64(1)]
    assert len({encode_typed(value) for value in values})==len(values)
    assert encode_typed({'b':2,'a':1})==encode_typed({'a':1,'b':2})
    a=struct.unpack('<d',struct.pack('<Q',0x7ff8000000000001))[0]
    b=struct.unpack('<d',struct.pack('<Q',0x7ff8000000000002))[0]
    assert encode_typed(a)!=encode_typed(b)


def test_all_declared_snapshot_fields_participate_in_the_key():
    original=snapshot();key=encode_environment_state(original)
    for name in REQUIRED_STATE_FIELDS-{'phase'}:
        modified=copy.deepcopy(original);modified[name]=('changed',modified[name])
        assert encode_environment_state(modified)!=key,name
    with pytest.raises(ValueError,match='missing fields'):
        encode_environment_state({'phase':'post_world_tick'})
    original['phase']='await_target'
    with pytest.raises(ValueError,match='committed'):
        encode_environment_state(original)


def pair(tmp_path,tail='0.025,EndAttack\n'):
    path=tmp_path/'state_key.csv'
    path.write_text('0,GetHeartPos,hx,hy\n0,BoneV,$hx,100,20,0,0\n'
                    '0.0125,BlackScreen,1\n0,HeartTeleport,320,304\n'
                    '0,Set,hx,320\n0,Set,hy,304\n'+tail)
    template=ParametricEnvironment(path,max_ticks=100,capture_state_keys=True)
    root=template.bind()
    return path,template,template.extend(root,20,40),template.extend(root,80,90)


def test_full_state_capture_merges_only_equal_committed_states_and_keeps_evidence(tmp_path):
    path,template,a,b=pair(tmp_path)
    ka,kb=a.wave.environment_state_keys,b.wave.environment_state_keys
    assert len(ka)==len(a.wave.env_schedule)
    assert ka[0]!=kb[0]
    assert ka[3]==kb[3] and type(ka[3]) is bytes
    assert a.identity!=b.identity and a.history!=b.history
    search=ParametricRouteIterator(path,[320,304,0,0,0,0,0,1,750,0,0],
                                   max_ticks=100,environment_state_quotient=True)
    state=np.array([320.,304.,0,0,0,0,0,1,750,0,0])
    na,nb=_Node(4,state,a,0),_Node(4,state.copy(),b,0)
    assert search._key(na)==search._key(nb)
    assert na.binding is a and nb.binding is b
    for index in range(11):
        changed=state.copy();changed[index]+=4 if index==4 else 1
        assert search._key(_Node(4,changed,b,0))!=search._key(na)
    assert search._key(_Node(5,state,b,0))!=search._key(na)


def test_pending_rows_and_prebound_future_observations_keep_exact_history(tmp_path):
    path,template,a,b=pair(tmp_path,'0.025,GetHeartPos,hx,hy\n0.025,EndAttack\n')
    request=a.pending_target
    assert request and a.wave.environment_state_keys[request['tick']] is None
    search=ParametricRouteIterator(path,[320,304,0,0,0,0,0,1,750,0,0],
                                   max_ticks=100,environment_state_quotient=True)
    state=np.array([320.,304.,0,0,0,0,0,1,750,0,0])
    assert search._key(_Node(request['tick'],state,a,0))!=search._key(_Node(request['tick'],state,b,0))
    aa=template.extend(a,25,45);bb=template.extend(b,85,95)
    assert aa.wave.environment_state_keys[4]==bb.wave.environment_state_keys[4]
    # Their already-baked future samples differ; the current consumer must
    # not project them away before its per-action binding behavior is changed.
    assert search._key(_Node(4,state,aa,0))!=search._key(_Node(4,state,bb,0))


def test_still_live_variable_values_are_not_projected_by_full_state_key(tmp_path):
    path=tmp_path/'live_vars.csv'
    path.write_text('0,GetHeartPos,hx,hy\n0.0125,BlackScreen,1\n'
                    '0,HeartTeleport,320,304\n0.025,BoneV,$hx,100,20,0,0\n0.025,EndAttack\n')
    template=ParametricEnvironment(path,max_ticks=100,capture_state_keys=True)
    root=template.bind();a=template.extend(root,20,40);b=template.extend(root,80,90)
    assert a.wave.environment_state_keys[4]!=b.wave.environment_state_keys[4]


def test_capture_is_disabled_by_default(tmp_path):
    path=tmp_path/'default.csv';path.write_text('0.008333,GetHeartPos,x,y\n0.01,EndAttack\n')
    assert ParametricEnvironment(path,max_ticks=100).bind().wave.environment_state_keys==()


def test_canonical_entry_exposes_same_solver_with_exact_state_memo(tmp_path):
    from nohit.engine.canonical_solver import solve_attack
    path=tmp_path/'public.csv'
    path.write_text('0.008333,GetHeartPos,x,y\n0.01,EndAttack\n')
    result=solve_attack(path,[320,304,0,0,0,0,0,1,750,0,0],
        max_ticks=100,environment_state_quotient=True,
        weights=dict(clearance=0,lookahead=0,center=0,switches=0))
    assert result['status']=='candidate_found'
    assert result['planner']=='canonical-dag-dp'
    assert result['environment_state_quotient'] is True
    assert result['target_history']


def test_foreign_seed_or_clock_template_is_never_compared_under_local_base(tmp_path):
    path,template,a,b=pair(tmp_path)
    search=ParametricRouteIterator(path,[320,304,0,0,0,0,0,1,750,0,0],
                                   max_ticks=100,environment_state_quotient=True)
    state=np.array([320.,304.,0,0,0,0,0,1,750,0,0])
    local=search._key(_Node(4,state,a,0))
    for settings in ({'seed':43},{'clock_start_ms':100.}):
        other=ParametricEnvironment(path,max_ticks=100,capture_state_keys=True,**settings)
        foreign=other.extend(other.bind(),20,40)
        assert search._key(_Node(4,state,foreign,0))!=local


def test_exact_state_memo_reduces_actual_complete_small_search(tmp_path):
    path=tmp_path/'join_then_blocked.csv'
    path.write_text('0,HeartMode,0\n'
                    '0.004167,GetHeartPos,hx,hy\n0,BoneV,$hx,100,20,0,0\n'
                    '0.008333,BlackScreen,1\n0,Set,hx,0\n0,Set,hy,0\n'
                    '0.008333,HeartTeleport,320,304\n'
                    '0.016667,BoneH,0,304,640,0,0\n0.008333,EndAttack\n')
    counts=[]
    for quotient in (False,True):
        search=ParametricRouteIterator(path,[320,304,0,0,0,0,0,1,750,0,0],
            environment_state_quotient=quotient,max_ticks=100,weights=[0,0,0,0],
            # Isolate this quotient: red-box certificates can reject both
            # histories before their otherwise duplicate state is expanded.
            red_box_pruning=False)
        search._options=lambda node:[0,1] if node.tick==0 else [0]
        with pytest.raises(StopIteration):next(search)
        assert search.status=='exhausted_in_declared_model'
        counts.append((len(search.dead),search.expansions))
    assert counts==[(5,5),(4,4)]
