"""Independent Boolean-relation and reverse-witness audit."""
import numpy as np
import pytest
from nohit.engine.compact_wave import compile_wave
from nohit.engine.cspace import bake_cspace
from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.local_relation import full_local_relation
from nohit.engine.red_joint_frontier import AxisFrontier
from nohit.engine.red_dense_frontier import DenseFrontier, advance_dense, predecessor, unpack_keys, _advance


def scene(tmp_path):
    path=tmp_path/'dense.csv'
    path.write_text('0,HeartMode,0\n0.2,EndAttack\n')
    wave=compile_wave(path)
    return wave,bake_cspace(wave)


def state(x=320.,y=304.,dx=0.,dy=0.):
    return np.array([x,y,dx,dy,0.,0.,0.,1.,750.,0.,0.])


def frontier(states):
    return DenseFrontier.from_axis(AxisFrontier.from_states(states))


def test_reverse_never_infers_cartesian_reachability(tmp_path):
    wave,space=scene(tmp_path)
    front=frontier([state(),state(321.,305.)])
    target=state(320.,305.)
    with pytest.raises(ValueError,match='no safe joint predecessor'):
        predecessor(wave,front,target,(0,),0,1,space)


def test_reverse_searches_all_many_to_one_inverse_pairs(tmp_path):
    wave,space=scene(tmp_path)
    dt=wave.env_schedule[1,7]
    # Both x axes and both y axes converge, but only two of four pairs exist.
    original=np.array([state(320.,304.+150.*dt,150.,0.),
                       state(320.+150.*dt,304.,0.,150.)])
    front=frontier(original)
    assert len(front.x)==len(front.y)==2 and front.count==2
    status,out,_=advance_dense(wave,front,(0,),0,1,space)
    assert status=='complete' and out.count==1
    target=out.state(unpack_keys(out.bits,len(out.x)*len(out.y))[0])
    key,mask=predecessor(wave,front,target,(0,),0,1,space)
    assert int(front.bits[key//64]) & (1<<(key%64))
    s=front.state(key)
    step_mask_into(s,mask,wave.env_schedule[1],wave.platform_table[1],s)
    assert s[:4].tobytes()==target[:4].tobytes()


@pytest.mark.parametrize('hold',[1,4])
def test_nonuniform_dt_dense_relation_matches_complete_operator(tmp_path,hold):
    wave,space=scene(tmp_path)
    wave.env_schedule[1:hold*2+1,7]=np.resize([.0031,.0067,.0042,.0048],hold*2)
    initial=np.array([state(),state(np.nextafter(320.,np.inf),305.,75.,-150.)])
    front=frontier(initial)
    for tick in range(0,hold*2,hold):
        status,front,_=advance_dense(wave,front,tuple(range(32)),tick,hold,space)
        assert status=='complete'
    relation=full_local_relation(wave,0,hold*2,initial,controls=tuple(range(32)),hold=hold,cspace=space)
    expected={s[:4].tobytes() for s in relation.states}
    actual={front.state(k)[:4].tobytes() for k in unpack_keys(front.bits,len(front.x)*len(front.y))}
    assert actual==expected


@pytest.mark.parametrize('unsafe_first',[False,True])
def test_dense_union_marks_only_after_safe_edge(unsafe_first):
    tx=np.zeros((1,2,2,2));tx[0,:,0,0]=[100.,200.] if unsafe_first else [200.,100.]
    tx[0,:,1,0]=300.
    ty=np.zeros((1,1,2,2));ty[0,0,:,0]=304.
    white=np.array([[[95.,295.,105.,313.]]]*3)
    payload=(np.empty((3,2,0,0),np.uint8),np.empty((3,0,8)),0.,0.,1.)
    bits,_,_,count,_,checks=_advance(np.array([3],np.uint64),2,1,state(),np.array([0],np.int64),
        tx,ty,np.zeros((1,2),np.int64),np.zeros((1,1),np.int64),1,1,0,2,
        np.zeros((3,22)),white,np.empty((3,0,4)),payload)
    assert count==1 and bits.tolist()==[1]
    assert checks==1+int(unsafe_first)


@pytest.mark.parametrize('empty',[False,True])
@pytest.mark.parametrize('boundary',['pending','observed','dialogue'])
def test_even_empty_frontiers_respect_observation_domain(tmp_path,empty,boundary):
    wave,space=scene(tmp_path);front=frontier([state()]);hold=4
    if empty:front.bits[:]=0;front.count=0
    if boundary=='pending':wave.pending_target={'tick':2}
    elif boundary=='observed':wave.source_events=[(2,'getheartpos',())]
    else:wave.termination_reason='dialogue_boundary';hold=len(wave.env_schedule)-1
    status,result,_=advance_dense(wave,front,(0,),0,hold,space)
    assert status=='unsupported' and result is None


def test_reverse_preserves_requested_terminal_alias_and_persistent_bits(tmp_path):
    wave,space=scene(tmp_path);front=frontier([state()]);controls=tuple(range(32))
    for requested in controls:
        target=front.state(0)
        for tick in range(1,5):
            step_mask_into(target,requested,wave.env_schedule[tick],wave.platform_table[tick],target)
        key,mask=predecessor(wave,front,target,controls,0,4,space,terminal_mask=requested)
        assert mask==requested
        replay=front.state(key)
        for tick in range(1,5):
            step_mask_into(replay,mask,wave.env_schedule[tick],wave.platform_table[tick],replay)
        assert replay.tobytes()==target.tobytes()
    target=front.state(0)
    step_mask_into(target,0,wave.env_schedule[1],wave.platform_table[1],target)
    for field in range(5,11):
        altered=target.copy();altered[field]=np.nextafter(altered[field],np.inf)
        with pytest.raises(ValueError,match='no safe joint predecessor'):
            predecessor(wave,front,altered,controls,0,1,space)
    with pytest.raises(ValueError,match='terminal_mask'):
        predecessor(wave,front,target,(0,),0,1,space,terminal_mask=3)


def test_real_empty_result_can_continue_in_certified_domain(tmp_path):
    path=tmp_path/'blocked.csv'
    path.write_text('0,HeartMode,0\n0,BoneV,320,294,20,0,0\n0.2,EndAttack\n')
    wave=compile_wave(path);space=bake_cspace(wave);front=frontier([state()])
    # A complete empty relation compacts to zero marginal IDs and zero words.
    status,empty,_=advance_dense(wave,front,(0,),0,1,space)
    assert status=='complete' and empty.count==0 and len(empty.bits)==0
    status,out,_=advance_dense(wave,empty,(0,),1,4,space)
    assert status=='complete' and out.count==0
    with pytest.raises(ValueError,match='tick_range'):
        advance_dense(wave,empty,(0,),-1,4,space)
