"""Exact bit identity, first representative and byte sorting for frontier keys."""
import numpy as np
import pytest
from nohit.engine.exact_state_dedup import (unique_state_indices,state_keys,
    _unique_indices,_unique_first,_latch)


def samples():
    rng=np.random.default_rng(2140)
    states=rng.integers(-2,3,(128,11)).astype(np.float64)
    states[:,4]=rng.integers(0,16,len(states))
    states[1]=states[0];states[1,4]=int(states[0,4])^2
    states[2]=states[0];states[2,0]=0.;states[3]=states[2];states[3,0]=-0.
    states[4]=states[0];states[4,1]=1.;states[5]=states[4];states[5,1]=np.nextafter(1.,2.)
    states[6]=states[0];states[6,2]=np.inf;states[7]=states[6];states[7,2]=-np.inf
    states[8]=states[0];states[9]=states[0]
    states.view(np.uint64)[8,3]=0x7ff8000000000001
    states.view(np.uint64)[9,3]=0x7ff8000000000002
    states[10]=states[0];states[10,4]=0.;states[11]=states[10];states[11,4]=-0.
    return np.concatenate((states,states[[3,2,0,5,4,7,6,9,8]],states))


def environment(kind):
    if kind=='terminal':return None
    row=np.zeros(22)
    if kind!='red':row[4]=1.;row[5]={'right':0,'down':1,'left':2,'up':3}[kind]
    return row


def reference(states,row):
    keys=states.copy()
    if row is not None:
        blue=row[4]!=0. or row[6]!=0.
        jump=(1,4,2,8)[int(row[5])]
        keys[:,4]=(keys[:,4].astype(np.int64)&jump) if blue else 0.
    return np.unique(keys.view(np.dtype((np.void,88))).ravel(),return_index=True)


@pytest.mark.parametrize('kind',['terminal','red','right','down','left','up'])
@pytest.mark.parametrize('strided',[False,True])
def test_first_indices_states_and_keys_match_reference_without_mutation(kind,strided):
    states=samples();row=environment(kind)
    if strided:states=states[::-1]
    before=states.tobytes();expected_keys,expected=reference(states,row)
    actual=unique_state_indices(states,row)
    assert actual.dtype==expected.dtype==np.dtype(np.intp)
    assert actual.tobytes()==expected.tobytes()
    assert states[actual].tobytes()==states[expected].tobytes()
    assert state_keys(states[actual],row).tobytes()==expected_keys.tobytes()
    assert states.tobytes()==before


@pytest.mark.parametrize('kind',['terminal','red','right','down','left','up'])
def test_all_hashes_collide_and_table_grows_without_false_merges(kind):
    states=samples();row=environment(kind);bit=_latch(row)
    expected_keys,expected=reference(states,row)
    indices=_unique_indices(states,bit,np.uint64(0),8)
    assert indices.tobytes()==expected.tobytes()
    assert state_keys(states[indices],row).tobytes()==expected_keys.tobytes()
    jump_word=np.asarray([float(max(0,bit))],np.float64).view(np.uint64)[0]
    reps,collisions,capacity=_unique_first(states,bit,jump_word,np.uint64(0),8)
    assert collisions>len(states) and len(reps)>100 and capacity>8


@pytest.mark.parametrize('kind',['terminal','red','down'])
def test_empty(kind):
    states=np.empty((0,11));row=environment(kind)
    assert unique_state_indices(states,row).shape==(0,)
    assert state_keys(states,row).shape==(0,)


def test_slam_forces_blue_latch_and_terminal_preserves_actual_masks():
    states=np.zeros((16,11));states[:,4]=np.arange(16)
    red=np.zeros(22);red[5]=2
    slam=red.copy();slam[6]=1
    assert len(unique_state_indices(states))==16
    assert len(unique_state_indices(states,red))==1
    assert len(unique_state_indices(states,slam))==2
    assert unique_state_indices(states,slam).tobytes()==reference(states,slam)[1].tobytes()


@pytest.mark.parametrize('states',[np.empty((1,10)),np.empty((2,11),np.float32),np.empty(11)])
def test_invalid_state_layout_rejected(states):
    with pytest.raises(ValueError,match='float64 array'):unique_state_indices(states)


@pytest.mark.parametrize('row',[np.zeros(6),np.zeros((1,22)),np.full(22,np.nan)])
def test_invalid_environment_rejected(row):
    with pytest.raises(ValueError,match='next environment'):unique_state_indices(samples(),row)
