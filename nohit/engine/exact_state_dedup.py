"""Exact first representatives of full player-state byte keys.

Hashing only locates candidate buckets: equality compares all eleven projected
uint64 words. Only unique representatives are sorted, using the same void88 byte
ordering as ``np.unique(..., return_index=True)``. Input states are never changed.
"""
import numpy as np
from numba import njit

_KEY_DTYPE=np.dtype((np.void,88))


def _latch(next_environment):
    if next_environment is None:return -1
    row=np.asarray(next_environment)
    if row.ndim!=1 or len(row)<7 or not np.isfinite(row).all():
        raise ValueError('finite next environment row required')
    if row[4]==0. and row[6]==0.:return 0
    if row[5] not in (0.,1.,2.,3.):raise ValueError('invalid gravity direction')
    return (1,4,2,8)[int(row[5])]


def _states(states):
    states=np.asarray(states)
    if states.dtype!=np.dtype(np.float64) or states.ndim!=2 or states.shape[1]!=11:
        raise ValueError('states must be a float64 array with shape (n,11)')
    return np.ascontiguousarray(states)


def _project_inplace(states,bit):
    if bit<0:return
    if bit:states[:,4]=states[:,4].astype(np.int64)&bit
    else:states[:,4]=0.


def state_keys(states,next_environment=None):
    """Build exact byte keys, normally for a small selected representative set.

    Without a next environment every state bit, including its full mask, stays
    in the key. Otherwise only the old-mask bit read on the next tick remains.
    The projected next-step congruence requires the discrete player operator;
    callers must not use it to discard distinct requested terminal masks.
    """
    keys=_states(states).copy()
    _project_inplace(keys,_latch(next_environment))
    return keys.view(_KEY_DTYPE).ravel()


@njit(inline='always')
def _word(raw,states,i,j,bit,jump_word):
    if j!=4 or bit<0:return raw[i,j]
    if bit and (int(states[i,4])&bit):return jump_word
    return np.uint64(0)


@njit(inline='always')
def _hash(raw,states,i,bit,jump_word,hash_mask):
    h=np.uint64(0xcbf29ce484222325)
    for j in range(11):
        h=(h^_word(raw,states,i,j,bit,jump_word))*np.uint64(0x100000001b3)
    h^=h>>np.uint64(30)
    h*=np.uint64(0xbf58476d1ce4e5b9)
    h^=h>>np.uint64(27)
    h*=np.uint64(0x94d049bb133111eb)
    h^=h>>np.uint64(31)
    return h&hash_mask


@njit(inline='always')
def _equal(raw,states,a,b,bit,jump_word):
    for j in range(11):
        if _word(raw,states,a,j,bit,jump_word)!=_word(raw,states,b,j,bit,jump_word):return False
    return True


@njit(cache=True)
def _unique_first(states,bit,jump_word,hash_mask,initial_capacity):
    raw=states.view(np.uint64)
    capacity=8
    while capacity<initial_capacity:capacity*=2
    table=np.full(capacity,-1,np.int64)
    representatives=np.empty(len(states),np.intp)
    count=0;collisions=0
    for i in range(len(states)):
        bucket=np.int64(_hash(raw,states,i,bit,jump_word,hash_mask)&np.uint64(capacity-1))
        while table[bucket]>=0:
            if _equal(raw,states,i,table[bucket],bit,jump_word):break
            collisions+=1;bucket=(bucket+1)&(capacity-1)
        if table[bucket]>=0:continue
        table[bucket]=i;representatives[count]=i;count+=1
        if count*10>capacity*6:
            capacity*=2;table=np.full(capacity,-1,np.int64)
            for k in range(count):
                prior=representatives[k]
                b=np.int64(_hash(raw,states,prior,bit,jump_word,hash_mask)&np.uint64(capacity-1))
                while table[b]>=0:b=(b+1)&(capacity-1)
                table[b]=prior
    return representatives[:count],collisions,capacity


def _unique_indices(states,bit,hash_mask,initial_capacity):
    jump_word=np.asarray([float(max(0,bit))],np.float64).view(np.uint64)[0]
    reps,_,_=_unique_first(states,bit,jump_word,hash_mask,initial_capacity)
    keys=states[reps]
    _project_inplace(keys,bit)
    order=np.argsort(keys.view(_KEY_DTYPE).ravel(),kind='stable')
    return reps[order]


def unique_state_indices(states,next_environment=None):
    """Return np.intp first indices in exactly the reference byte-key order.

    ``next_environment=None`` selects full-state/terminal deduplication.
    Supplying the next row enables the existing internal-layer input-latch
    quotient, including a slam that forces blue mode. State mask fields follow
    the discrete operator's integral-mask contract. Hash collisions never merge
    unequal keys, including distinct signed zeros or NaN payloads elsewhere.
    """
    states=_states(states);bit=_latch(next_environment)
    # Reserve for the input upper bound at the existing 60% load limit. This
    # avoids rehashing earlier representatives while preserving their order.
    capacity=1024
    while capacity*6<len(states)*10:capacity*=2
    return _unique_indices(states,bit,np.uint64(0xffffffffffffffff),capacity)
