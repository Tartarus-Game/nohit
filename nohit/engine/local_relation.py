"""Standalone exact finite-window relation using the complete player operator.

No geometric state quotient or local winner: every bit-distinct safe exit is
retained. An optional internal-layer input-latch quotient merges only states
whose every next control produces the identical full state. Terminal masks
remain exact. Resource truncation is explicit and never means infeasible.
"""
from dataclasses import dataclass
import numpy as np
from numba import config,njit
from .discrete_operator import step_mask_into
from .cspace import collision_query,bake_cspace
from .exact_state_dedup import unique_state_indices
from .parallel_expansion import expand_parallel


# Large real edge batches benefit from two workers; small frontiers retain
# the scalar path to avoid thread/compilation overhead. Defaults never select
# every logical CPU. These affect execution cost, not the accepted relation.
_PARALLEL_MIN_EDGES=131072
_HASH_MIN_STATES=16384


@njit(cache=True)
def _expand(states,controls,start,hold,env,platforms,white,blue,payload):
    out=np.empty((len(states)*len(controls),11));parents=np.empty(len(out),np.int64)
    masks=np.empty(len(out),np.int64);n=0
    for i in range(len(states)):
        for mask in controls:
            s=states[i].copy();safe=True
            for tick in range(start+1,start+hold+1):
                step_mask_into(s,mask,env[tick],platforms[tick],s)
                if collision_query(white,blue,tick,s,0.,payload):safe=False;break
            if safe:out[n]=s;parents[n]=i;masks[n]=mask;n+=1
    return out[:n],parents[:n],masks[:n]


@dataclass
class LocalRelation:
    status: str
    start_tick: int
    reached_tick: int
    states: np.ndarray
    layers: list
    parents: list
    masks: list
    counts: list
    input_latch_quotient: bool = False
    control_quotient: bool = False

    def witness(self,index):
        word=[]
        for parents,masks in zip(reversed(self.parents),reversed(self.masks)):
            word.append(int(masks[index]));index=int(parents[index])
        return word[::-1]

    def origin_index(self,index):
        """Index in layers[0] for callers supplying multiple initial states."""
        for parents in reversed(self.parents):index=int(parents[index])
        return index


def _internal_layer_keys(states,next_environment):
    """Exact next-step congruence; real representatives are never modified.

    CustomMovement does not inspect the old input mask. PlayerMovement reads
    only its jump bit, after applying the next row's mode, gravity, and slam.
    Red mode reads no old mask; a slam forces blue even if row[4] says red.
    The selected current mask then replaces the old mask in the full output.
    Therefore equal projected keys imply bit-identical next states under each
    fixed control, including collision-relevant velocity and damage fields.
    """
    keys=states.copy()
    blue=next_environment[4]!=0. or next_environment[6]!=0.
    direction=next_environment[5]
    jump=1 if direction==0. else 4 if direction==1. else 2 if direction==2. else 8
    keys[:,4]=(keys[:,4].astype(np.int64)&jump) if blue else 0.
    return keys.view(np.dtype((np.void,88))).ravel()


def full_local_relation(wave,start_tick,stop_tick,initial,*,controls=tuple(range(16)),
                        hold=4,max_states=250_000,cspace=None,input_latch_quotient=False,
                        control_quotient=False,expansion_backend='auto',
                        dedup_backend='auto',workers=None):
    """Complete safe exits in a known finite window, or explicit resource limit.

    Inputs may be one state or a set. Byte-key dedup is valid because the full
    state and fixed environment determine all future transitions. Optional
    internal-layer latch projection preserves each control's full next state,
    hence every future language and all exact terminal exits. One real witness
    per equivalent internal state is retained; terminal-layer keys stay full.

    Execution backends preserve every state, parent, mask, and their order.
    ``expansion_backend='scalar', dedup_backend='numpy'`` selects the reference
    operators. Auto uses parallel expansion only for large edge batches and
    exact hash deduplication only for large safe-edge batches. Default workers
    are at most two; explicit workers select a supported Numba thread count.
    The caller's thread mask is restored and no environment variables change.
    """
    if not 0<=start_tick<stop_tick<len(wave.env_schedule):raise ValueError('tick_range')
    if hold<1 or (stop_tick-start_tick)%hold:raise ValueError('control_hold')
    if not isinstance(input_latch_quotient,bool):raise ValueError('input_latch_quotient')
    if not isinstance(control_quotient,bool):raise ValueError('control_quotient')
    if control_quotient and not input_latch_quotient:raise ValueError('control quotient requires input latch quotient')
    if expansion_backend not in ('auto','scalar','parallel'):raise ValueError('expansion_backend')
    if dedup_backend not in ('auto','numpy','hash'):raise ValueError('dedup_backend')
    if workers is None:workers=min(2,config.NUMBA_NUM_THREADS)
    elif type(workers) is not int or not 1<=workers<=config.NUMBA_NUM_THREADS:
        raise ValueError(f'workers must be an integer from 1 to {config.NUMBA_NUM_THREADS}')
    pending=wave.pending_target
    if pending is not None and pending['tick']<=stop_tick:raise ValueError('unresolved_target')
    if getattr(wave,'termination_reason',None)=='dialogue_boundary' and stop_tick>=len(wave.env_schedule)-1:
        raise ValueError('unresolved_dialogue')
    if any(start_tick<t<=stop_tick and cmd=='getheartpos' for t,cmd,_ in wave.source_events):
        raise ValueError('target_observation_boundary')
    s=np.asarray(initial,dtype=np.float64).reshape(-1,11).copy()
    controls=np.asarray(controls,dtype=np.int64)
    if not len(controls) or np.any(controls<0) or np.any(controls>=32):raise ValueError('controls')
    space=bake_cspace(wave) if cspace is None else cspace
    s=np.asarray([row for row in s if not collision_query(wave.geometry_white,wave.geometry_blue,start_tick,row,0.,space.payload)]).reshape(-1,11)
    result=LocalRelation('complete',start_tick,start_tick,s,[s],[],[],[(start_tick,len(s))],input_latch_quotient,control_quotient)
    for tick in range(start_tick,stop_tick,hold):
        # Keep the already-complete last layer when expansion cannot be stored.
        if len(s)*len(controls)>max_states*len(controls):
            result.status='resource_limit';return result
        layer_controls=controls
        if control_quotient and tick+hold<stop_tick:
            from .control_quotient import control_classes
            classes=control_classes(wave.env_schedule[tick+1:tick+hold+1],controls,
                                    next_environment=wave.env_schedule[tick+hold+1])
            layer_controls=np.asarray([group[0] for group in classes],dtype=np.int64)
        parallel=(expansion_backend=='parallel' or
            (expansion_backend=='auto' and workers>1 and len(s)*len(layer_controls)>=_PARALLEL_MIN_EDGES))
        if parallel:
            following,parents,masks=expand_parallel(s,layer_controls,tick,hold,wave.env_schedule,
                wave.platform_table,wave.geometry_white,wave.geometry_blue,space.payload,workers=workers)
        else:
            following,parents,masks=_expand(s,layer_controls,tick,hold,wave.env_schedule,
                wave.platform_table,wave.geometry_white,wave.geometry_blue,space.payload)
        # Never project at the requested exit boundary: callers are promised
        # the exact set of terminal states, including their physical mask.
        next_env=wave.env_schedule[tick+hold+1] if input_latch_quotient and tick+hold<stop_tick else None
        if dedup_backend=='hash' or (dedup_backend=='auto' and len(following)>=_HASH_MIN_STATES):
            indices=unique_state_indices(following,next_env)
        else:
            keys=(_internal_layer_keys(following,next_env) if next_env is not None
                  else following.view(np.dtype((np.void,88))).ravel())
            unique_keys,indices=np.unique(keys,return_index=True)
            del keys,unique_keys
        if len(indices)>max_states:
            result.status='resource_limit';return result
        s=following[indices];result.layers.append(s);result.parents.append(parents[indices]);result.masks.append(masks[indices])
        result.states=s;result.reached_tick=tick+hold;result.counts.append((tick+hold,len(s)))
        # All retained arrays own their selected rows. Do not keep the previous
        # full edge batch alive while allocating the next one.
        del following,parents,masks,indices
        if not len(s):result.status='exhausted';return result
    return result
