"""Stable parallel evaluation of exact local-relation edges.

Only independent state/control edges run in parallel. Collision, arithmetic,
output order, and subsequent deduplication retain the scalar contract.
"""
import numpy as np
from numba import config,get_num_threads,njit,prange,set_num_threads
from .discrete_operator import step_mask_into
from .cspace import collision_query


@njit(cache=True,parallel=True)
def _expand_parallel_kernel(states,controls,start,hold,env,platforms,white,blue,payload):
    count=len(states)*len(controls)
    slots=np.empty((count,11),np.float64)
    safe=np.empty(count,np.bool_)
    parents=np.empty(count,np.int64)
    masks=np.empty(count,np.int64)
    # Each iteration owns one slot. Within-edge tick order and the first-hit
    # early exit are identical to the scalar local-relation operator.
    for edge in prange(count):
        parent=edge//len(controls)
        mask=controls[edge%len(controls)]
        state=states[parent].copy()
        accepted=True
        for tick in range(start+1,start+hold+1):
            step_mask_into(state,mask,env[tick],platforms[tick],state)
            if collision_query(white,blue,tick,state,0.,payload):
                accepted=False
                break
        safe[edge]=accepted
        if accepted:
            for axis in range(11):slots[edge,axis]=state[axis]
    # The prange barrier precedes this serial stable compaction. Backward
    # moves cannot overwrite an unread slot; parent/control attribution stays
    # exactly in the original nested-loop order, including duplicate controls.
    retained=0
    for edge in range(count):
        if safe[edge]:
            for axis in range(11):slots[retained,axis]=slots[edge,axis]
            parents[retained]=edge//len(controls)
            masks[retained]=controls[edge%len(controls)]
            retained+=1
    return slots[:retained],parents[:retained],masks[:retained]


def expand_parallel(states,controls,start,hold,env,platforms,white,blue,payload,*,workers=2):
    """Match ``local_relation._expand``, temporarily using ``workers`` threads.

    The caller's Numba thread mask is restored even if compilation or execution
    raises. No environment variables or process-wide thread defaults change.
    """
    if type(workers) is not int or not 1<=workers<=config.NUMBA_NUM_THREADS:
        raise ValueError(f'workers must be an integer from 1 to {config.NUMBA_NUM_THREADS}')
    previous=get_num_threads()
    try:
        set_num_threads(workers)
        return _expand_parallel_kernel(states,controls,start,hold,env,platforms,white,blue,payload)
    finally:
        set_num_threads(previous)
