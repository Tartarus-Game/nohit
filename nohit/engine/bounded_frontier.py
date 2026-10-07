"""Incomplete candidate discovery with exact edges and mandatory scalar replay.

Width and observation-branch limits discard alternatives, never prove them
dead. This module has no dead memo and does not replace complete reachability.
One action is one source-model tick under the explicitly scoped clock.
"""
from dataclasses import dataclass, field
import hashlib
import math
import struct
import time

import numpy as np
from numba import njit

from .control_quotient import control_classes
from .cspace import bake_cspace, collision_query
from .discrete_operator import initial_state, sample_position, step_mask_into
from .exact_state_dedup import unique_state_indices
from .expansion_dispatch import expand_dispatch as _expand, prepare_expansion
from .initial_target_history import bind_initial_target_history, normalize_initial_target_history
from .parametric_environment import ParametricEnvironment
from .selection_buckets import build_selection_buckets, unique_bucket_indices
from .terminal_completion import complete_eof_tail


# Input-cost ranking. A candidate is ranked by what it costs the player to
# execute it, so the retained frontier prefers calm routes over twitchy ones:
#   * every tick that presses anything costs INPUT_HELD_COST;
#   * every change of the pressed set costs INPUT_CHURN_COST.
# Churn is deliberately the more expensive term: holding one direction through a
# hazard is smoother than alternating two, even when both press the same number
# of times. Measured on user-style/bonegap1 (800 ticks, width 3000), raising churn
# from 4 to 12 cuts press segments 20->17 and 21->14 and lengthens the longest
# continuous hold 18->35 and 25->33 frames, while churn itself plateaus (64->59,
# 65->58) and both stay candidate_found. Above 12 nothing improves further, so 12
# is the default. These weights rank candidates only; they never gate safety, and
# a width cut made under them is still just a width cut.
INPUT_CHURN_COST: int = 12
INPUT_HELD_COST: int = 1


def record_input_cost(stats, actions):
    """Publish what the witness costs the player to execute.

    Churn counts how many times the pressed set changes; held_frames counts the
    ticks that press anything. Both are recorded, and ``total`` applies the same
    weights the frontier ranks with, so the reported number and the ranking
    cannot drift apart. This observes a finished witness; it never gates safety.
    """
    word=[int(mask) for mask in actions]
    churn=0
    for index,mask in enumerate(word):
        if mask!=(word[index-1] if index else 0):churn+=1
    held=sum(1 for mask in word if mask!=0)
    stats['input_cost']=dict(frames=len(word),churn=churn,held_frames=held,
        churn_weight=INPUT_CHURN_COST,held_weight=INPUT_HELD_COST,
        total=churn*INPUT_CHURN_COST+held*INPUT_HELD_COST)
    return stats['input_cost']


@dataclass(frozen=True)
class FrontierLayer:
    tick: int
    states: np.ndarray
    binding_ids: np.ndarray
    parents: np.ndarray
    masks: np.ndarray
    # Accumulated input cost per retained state. Optional so a layer built
    # outside the search loop (tests, recovery suffixes) still constructs.
    costs: np.ndarray | None = None


@dataclass
class BoundedFrontierResult:
    status: str = 'unknown'
    reason: str = 'not_started'
    reached_tick: int = 0
    actions: list = field(default_factory=list)
    trajectory: np.ndarray = field(default_factory=lambda: np.empty((0, 11)))
    target_history: tuple = ()
    terminal_tail: dict | None = None
    verified: bool = False
    original_replay_passed: bool = False
    complete_in_original_game: bool = False
    clock: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    layers: list = field(default_factory=list, repr=False)
    bindings: list = field(default_factory=list, repr=False)
    # Resolved worlds suspended before the next player tick, with ancestry
    # into the retained last layer (including GetHeartPos + SansText together).
    dialogue_entries: list = field(default_factory=list, repr=False)

    def witness(self, index=0):
        """Recover a retained path without crossing any binding's ancestry."""
        word=[];states=[]
        for layer in reversed(self.layers[1:]):
            states.append(layer.states[index]);word.append(int(layer.masks[index]))
            index=int(layer.parents[index])
        if self.layers:states.append(self.layers[0].states[index])
        return word[::-1],np.asarray(states[::-1],dtype=np.float64).reshape(-1,11)


def _last_motion_tick(binding):
    # Suspended rows are previews, not committed player/world transitions.
    preview=binding.pending_target is not None or binding.wave.termination_reason=='dialogue_boundary'
    return len(binding.wave.env_schedule)-1-int(preview)


def _next_environment(binding, tick):
    if binding.complete and tick>=len(binding.wave.env_schedule)-1:return None
    if binding.pending_target is not None and binding.pending_target['tick']<=tick+1:return None
    if not binding.complete and tick>=_last_motion_tick(binding):return None
    env=binding.wave.env_schedule
    return env[tick+1] if tick+1<len(env) else None


def _select(states, width, rng, costs=None):
    if len(states)<=width:return np.arange(len(states),dtype=np.intp)
    order=rng.permutation(len(states))
    # Bins rank candidates only. They are never state-equality or death keys.
    # With costs the seeded permutation stays as the tie order inside one cost
    # level, so equal-cost candidates are still chosen reproducibly per seed.
    if costs is None:
        buckets=build_selection_buckets(states,order)
        first=unique_bucket_indices(buckets)
        first=rng.permutation(first)
    else:
        cost_rows=np.asarray(costs,dtype=np.int64)[order]
        order=order[np.argsort(cost_rows,kind='stable')]
        buckets=build_selection_buckets(states,order)
        first=unique_bucket_indices(buckets)
        first=first[np.argsort(cost_rows[first],kind='stable')]
    if len(first)<width:
        remaining=np.setdiff1d(np.arange(len(states)),first,assume_unique=True)
        if costs is None:
            remaining=rng.permutation(remaining)
        else:
            remaining=remaining[np.argsort(np.asarray(costs,dtype=np.int64)[remaining],kind='stable')]
        first=np.concatenate((first,remaining[:width-len(first)]))
    return order[first[:width]]


@njit(cache=True)
def _held_trace(states, masks, start, stop, env, platforms):
    """Materialize already checked macro edges without changing their states."""
    trace=np.empty((stop-start,len(states),11),np.float64)
    for index in range(len(states)):
        state=states[index].copy()
        for tick in range(start+1,stop+1):
            step_mask_into(state,masks[index],env[tick],platforms[tick],state)
            trace[tick-start-1,index]=state
    return trace


def _recover_frontier(result, controls, width, rng, space_for, deadline, lookback):
    """Try held-input alternatives discarded by earlier width selections.

    Each attempt begins at a real retained layer, uses that row's own known
    world, and checks every microstep through the first failed tick. Unknown
    target/dialogue previews cannot supply future frames. Success replaces a
    suffix with genuine parent-linked microsteps and strictly advances time;
    failure changes neither the frontier nor any claim of feasibility.
    """
    stop=result.reached_tick+1
    maximum=min(lookback,len(result.layers)-1)
    if maximum<1:return False
    # Distances count earlier retained ticks, not the failed extra transition.
    distances=[];distance=1
    while distance<=maximum:
        distances.append(distance);distance*=2
    if distances[-1]!=maximum:distances.append(maximum)
    masks=np.asarray(controls,np.int64);stats=result.stats
    for distance in distances:
        if time.perf_counter()>=deadline:return False
        origin_index=len(result.layers)-1-distance
        origin=result.layers[origin_index];start=origin.tick
        batches=[]
        for bid in dict.fromkeys(int(value) for value in origin.binding_ids):
            if time.perf_counter()>=deadline:return False
            bound=result.bindings[bid]
            # This is the ancestor's binding, never a later resolved history.
            if stop>_last_motion_tick(bound):continue
            if bound.pending_target is not None and bound.pending_target['tick']<=stop:continue
            rows=np.flatnonzero(origin.binding_ids==bid);wave=bound.wave
            stats['recovery_attempts']+=1
            stats['recovery_macro_edges']+=len(rows)*len(masks)
            following,parents,chosen_masks=_expand(origin.states[rows],masks,start,stop-start,
                wave.env_schedule,wave.platform_table,wave.geometry_white,wave.geometry_blue,space_for(bound).payload)
            unique=unique_state_indices(following,_next_environment(bound,stop))
            if len(unique):batches.append((following[unique],rows[parents[unique]],chosen_masks[unique],
                np.full(len(unique),bid,np.int64)))
        if not batches:continue
        if time.perf_counter()>=deadline:return False
        following=np.concatenate([batch[0] for batch in batches])
        parents=np.concatenate([batch[1] for batch in batches])
        chosen_masks=np.concatenate([batch[2] for batch in batches])
        ids=np.concatenate([batch[3] for batch in batches])
        selected=_select(following,width,rng)
        parents=parents[selected];chosen_masks=chosen_masks[selected];ids=ids[selected]
        trace=np.empty((stop-start,len(selected),11),np.float64)
        for bid in dict.fromkeys(int(value) for value in ids):
            if time.perf_counter()>=deadline:return False
            rows=np.flatnonzero(ids==bid);wave=result.bindings[bid].wave
            trace[:,rows]=_held_trace(origin.states[parents[rows]],chosen_masks[rows],start,stop,
                wave.env_schedule,wave.platform_table)
        if time.perf_counter()>=deadline:return False
        if trace[-1].tobytes()!=following[selected].tobytes():
            raise RuntimeError('recovery macro reconstruction mismatch')
        suffix=[];identity=np.arange(len(selected),dtype=np.int64)
        for offset in range(stop-start):
            suffix.append(FrontierLayer(start+offset+1,trace[offset],ids.copy(),
                parents.copy() if offset==0 else identity.copy(),chosen_masks.copy()))
        # Commit only after the entire checked replacement is available.
        result.layers[origin_index+1:]=suffix
        result.reached_tick=stop;result.dialogue_entries=[]
        stats['recovery_count']+=1
        stats['recovery_discarded_states']+=len(following)-len(selected)
        stats['recoveries'].append(dict(start_tick=start,failed_tick=stop,
            retained_states=len(selected),safe_macro_states=len(following)))
        # These counts record search work, including discarded old suffixes;
        # they are not an index of the current reconstructed witness layers.
        stats.setdefault('layer_counts',[]).append(dict(tick=stop,kind='recovery',
            unique_states=len(following),retained_states=len(selected),bindings=len(set(ids))))
        return True
    return False


def _resolve(template, binding, state, tick):
    if binding.pending_target is not None and binding.pending_target['tick']==tick:
        wave=binding.wave
        x,y=(state[0],state[1]) if tick==0 else sample_position(state,wave.env_schedule[tick],wave.platform_table[tick])
        while binding.pending_target is not None and binding.pending_target['tick']==tick:
            binding=template.extend(binding,x,y)
    return binding


def _tail(binding, state, mask, template, explicit_clock):
    if not binding.complete:return None
    if binding.wave.termination_reason=='endattack':return {'status':'proven','reason':'endattack'}
    return complete_eof_tail(binding.wave,state,clock_start_ms=template.clock_start_ms,
        dt_schedule=template.dt_schedule if explicit_clock else None,max_ticks=template.max_ticks,
        last_mask=mask,decision_ticks=1)


def _scalar_verify(path, initial, settings, actions, expected, expected_binding, explicit_clock,
                   initial_target_history=None):
    """Independent monolithic environment and one-tick scalar operators."""
    template=ParametricEnvironment(path,backend='reference',**settings)
    binding=bind_initial_target_history(template,initial_target_history)
    state=initial_state(initial,binding.wave.env_schedule[0])
    binding=_resolve(template,binding,state,0);spaces={};trace=[state.copy()]
    for tick in range(len(actions)+1):
        if tick:
            binding=_resolve(template,binding,state,tick)
            if tick>=len(binding.wave.env_schedule):return False,None,'replay_boundary'
            step_mask_into(state,actions[tick-1],binding.wave.env_schedule[tick],binding.wave.platform_table[tick],state)
            trace.append(state.copy())
        if binding.identity not in spaces:spaces[binding.identity]=bake_cspace(binding.wave,cell_size=8.)
        if not np.isfinite(state).all() or collision_query(binding.wave.geometry_white,binding.wave.geometry_blue,
                tick,state,0.,spaces[binding.identity].payload):return False,None,'replay_collision'
    if np.asarray(trace).tobytes()!=expected.tobytes():return False,None,'replay_state_mismatch'
    if binding.identity!=expected_binding.identity:return False,None,'replay_binding_mismatch'
    if not binding.complete or len(actions)!=len(binding.wave.env_schedule)-1:return False,None,'replay_incomplete'
    tail=_tail(binding,state,actions[-1] if actions else int(state[4]),template,explicit_clock)
    if tail is None or tail.get('status')!='proven':return False,tail,'terminal_invariant_unproven'
    return True,tail,'verified_'+binding.wave.termination_reason


def find_bounded_candidate(path, initial, *, initial_environment=None, initial_arena=None, dt_schedule=None,
                           clock_start_ms=None, controls=tuple(range(16)), width=3000,
                           seconds=30., max_bindings=1, max_ticks=40000, seed=42,
                           selection_seed=42, termination_policy='endattack',
                           environment_backend='resumable', initial_target_history=None,
                           recovery_lookback=256, progress=None):
    """Find and replay a candidate, or return ``unknown`` with a retained prefix.

    Controls are masks 0..31 (default arrows only), applied for one tick each.
    ``max_bindings`` limits the distinct environment histories retained in one
    layer. Observations are sampled from each retained parent's actual state;
    no target is borrowed from a different branch. Width/branch pruning and all
    limits are explicitly counted. A frontier becoming empty is still unknown.
    Before returning frontier_empty, held-input alternatives from at most
    ``recovery_lookback`` earlier retained ticks can recover a discarded path.
    This finite heuristic uses the same time budget; zero disables recovery.

    ``initial_target_history`` declares all already observed tick-zero target
    reads. Only that initial prefix is supplied; later reads still come from
    each parent's actual movement-phase position. None keeps offline behavior.

    ``seconds`` bounds expansion work after environment setup and kernel
    materialization. Checks occur between bounded layer/binding operations;
    an in-flight operation can slightly overrun. Mandatory scalar verification
    is timed separately and cannot be skipped to return an unverified success.
    EndAttack is accepted only at its final tick. EOF also requires the existing
    terminal invariant certificate; unsupported dialogue remains unknown.
    """
    if type(width) is not int or width<1:raise ValueError('width must be a positive integer')
    if type(max_bindings) is not int or max_bindings<1:raise ValueError('max_bindings must be a positive integer')
    if type(recovery_lookback) is not int or recovery_lookback<0:raise ValueError('recovery_lookback must be a nonnegative integer')
    if isinstance(seconds,bool) or not isinstance(seconds,(int,float)) or not math.isfinite(seconds) or seconds<0:
        raise ValueError('seconds must be finite and nonnegative')
    controls=tuple(controls)
    if not controls or any(isinstance(mask,(bool,np.bool_)) or not isinstance(mask,(int,np.integer)) or not 0<=mask<32 for mask in controls):
        raise ValueError('controls must be nonempty integer masks in [0,31]')
    controls=tuple(dict.fromkeys(int(mask) for mask in controls))
    initial=np.asarray(initial,dtype=np.float64).copy()
    if initial.shape not in ((5,),(11,)) or not np.isfinite(initial).all():raise ValueError('finite 5- or 11-field initial state required')
    initial_target_history=normalize_initial_target_history(initial_target_history)
    setup=time.perf_counter()
    template=ParametricEnvironment(path,seed=seed,initial_environment=initial_environment,
        initial_arena=initial_arena,
        clock_start_ms=clock_start_ms,dt_schedule=dt_schedule,max_ticks=max_ticks,
        termination_policy=termination_policy,backend=environment_backend)
    explicit_clock=dt_schedule is not None
    settings=dict(seed=template.seed,initial_environment=template.initial_environment,initial_arena=template.initial_arena,
        clock_start_ms=clock_start_ms,dt_schedule=template.dt_schedule if explicit_clock else None,
        max_ticks=max_ticks,termination_policy=termination_policy)
    result=BoundedFrontierResult()
    result.clock=dict(protocol='explicit_dt_schedule' if explicit_clock else 'native_fixed_240' if clock_start_ms is not None else 'nominal_240',
        decision_ticks=1,original_replay_passed=False)
    if template.dt_schedule is not None:
        result.clock.update(schedule_count=len(template.dt_schedule),
            schedule_sha256=hashlib.sha256(np.asarray(template.dt_schedule,dtype='<f8').tobytes()).hexdigest())
    stats=result.stats
    stats.update(width=width,max_bindings=max_bindings,controls=controls,selection_seed=selection_seed,
        expanded_states=0,safe_transition_rows=0,discarded_states=0,observation_discarded_states=0,
        observation_branches=0,unsupported_states=0,layer_counts=[],layer_counts_scope='expansion_history',
        verification_seconds=0.,search_seconds=0.,
        kernel_materialization_seconds=0.,environment_setup_seconds=0.,recovery_lookback=recovery_lookback,
        recovery_count=0,recovery_attempts=0,recovery_macro_edges=0,recovery_discarded_states=0,
        recovery_seconds=0.,recoveries=[])
    binding=bind_initial_target_history(template,initial_target_history)
    state=initial_state(initial,binding.wave.env_schedule[0])
    binding=_resolve(template,binding,state,0)
    result.bindings.append(binding);binding_ids={binding.identity:0};spaces={}
    def space_for(bound):
        if bound.identity not in spaces:spaces[bound.identity]=bake_cspace(bound.wave,cell_size=8.)
        return spaces[bound.identity]
    space=space_for(binding)
    result.layers.append(FrontierLayer(0,state.reshape(1,11),np.array([0],np.int64),
        np.array([-1],np.int64),np.array([int(state[4])],np.int64),np.zeros(1,np.int64)))
    result.trajectory=state.reshape(1,11).copy();result.target_history=binding.history
    if collision_query(binding.wave.geometry_white,binding.wave.geometry_blue,0,state,0.,space.payload):
        result.reason='initial_collision';stats['environment_setup_seconds']=time.perf_counter()-setup;return result
    stats['environment_setup_seconds']=time.perf_counter()-setup
    # Compile/load kernels without crossing a pending observation or advancing
    # the search. Empty batches have the same signatures as real layers.
    prepare=time.perf_counter()
    prepare_expansion(np.empty((0,11)),np.asarray(controls,np.int64),0,1,binding.wave.env_schedule,
        binding.wave.platform_table,binding.wave.geometry_white,binding.wave.geometry_blue,space.payload)
    unique_state_indices(state.reshape(1,11),_next_environment(binding,0))
    if recovery_lookback:
        _held_trace(np.empty((0,11)),np.empty(0,np.int64),0,1,
            binding.wave.env_schedule,binding.wave.platform_table)
    stats['kernel_materialization_seconds']=time.perf_counter()-prepare
    rng=np.random.default_rng(selection_seed);began=time.perf_counter();reason='tick_budget';chosen=0
    while result.reached_tick<max_ticks:
        tick=result.reached_tick;layer=result.layers[-1]
        result.dialogue_entries=[]
        if time.perf_counter()-began>=seconds:reason='wall_budget';break
        # Verify a completed branch before returning it. Other branches never
        # lend their history or terminal status to this candidate.
        terminal_indices=[]
        for index,bid in enumerate(layer.binding_ids):
            bound=result.bindings[int(bid)]
            if bound.complete and tick>=len(bound.wave.env_schedule)-1:terminal_indices.append(index)
        # Verify the cheapest completing witness first. Selection already prefers
        # cheap states, but the returned route is whichever terminal verifies
        # first, so without this ordering a twitchy arrival that happens to sit
        # earlier in the layer would win over a calm one.
        if layer.costs is not None and terminal_indices:
            terminal_indices=sorted(terminal_indices,key=lambda i:(int(layer.costs[i]),i))
        for index in terminal_indices:
            if time.perf_counter()-began-stats['verification_seconds']>=seconds:
                reason='wall_budget';break
            bound=result.bindings[int(layer.binding_ids[index])]
            preliminary=_tail(bound,layer.states[index],int(layer.masks[index]),template,explicit_clock)
            if preliminary is None or preliminary.get('status')!='proven':continue
            actions,trace=result.witness(index);verify_start=time.perf_counter()
            valid,tail,why=_scalar_verify(path,initial,settings,actions,trace,bound,explicit_clock,
                                         initial_target_history=initial_target_history)
            stats['verification_seconds']+=time.perf_counter()-verify_start
            if valid:
                result.status='candidate_found';result.reason=why;result.verified=True
                result.actions=actions;result.trajectory=trace;result.target_history=bound.history;result.terminal_tail=tail
                record_input_cost(stats,actions)
                stats['search_seconds']=time.perf_counter()-began-stats['verification_seconds'];return result
            if why.startswith('replay_'):
                reason=why;chosen=index;break
        if reason.startswith('replay_') or reason=='wall_budget':break
        batches=[];active_bindings=set();timed_out=False;boundary_reason=None
        for bid in dict.fromkeys(int(value) for value in layer.binding_ids):
            if time.perf_counter()-began>=seconds:timed_out=True;break
            bound=result.bindings[bid];wave=bound.wave
            indices=np.flatnonzero(layer.binding_ids==bid)
            if bound.complete and tick>=len(wave.env_schedule)-1:
                stats['unsupported_states']+=len(indices);boundary_reason='terminal_invariant_unproven';continue
            if bound.pending_target is None and not bound.complete and tick>=_last_motion_tick(bound):
                if wave.termination_reason=='dialogue_boundary':
                    result.dialogue_entries.append((bid,indices))
                stats['unsupported_states']+=len(indices);boundary_reason=wave.termination_reason or 'environment_incomplete';continue
            groups=[]
            if bound.pending_target is not None and bound.pending_target['tick']==tick+1:
                # Choose at most max_bindings real sample histories. Rows with
                # the same sample can share the selected binding, not its state.
                selected={}
                for index in rng.permutation(indices):
                    x,y=sample_position(layer.states[index],wave.env_schedule[tick+1],wave.platform_table[tick+1])
                    sample=struct.pack('<dd',x,y)
                    if sample in selected:selected[sample][1].append(int(index));continue
                    if len(active_bindings)+len(selected)>=max_bindings:
                        stats['observation_discarded_states']+=1;continue
                    selected[sample]=([x,y],[int(index)])
                for sample,rows in selected.values():
                    if time.perf_counter()-began>=seconds:timed_out=True;break
                    child=template.extend(bound,*sample)
                    while child.pending_target is not None and child.pending_target['tick']==tick+1:
                        child=template.extend(child,*sample)
                    stats['observation_branches']+=1
                    groups.append((child,np.asarray(rows,np.int64)))
            else:groups=[(bound,indices)]
            if timed_out:break
            for child,rows in groups:
                if child.identity not in active_bindings and len(active_bindings)>=max_bindings:
                    stats['observation_discarded_states']+=len(rows);continue
                active_bindings.add(child.identity)
                if not child.complete and child.pending_target is None and tick+1>_last_motion_tick(child):
                    if child.wave.termination_reason=='dialogue_boundary':
                        if child.identity not in binding_ids:
                            binding_ids[child.identity]=len(result.bindings);result.bindings.append(child)
                        result.dialogue_entries.append((binding_ids[child.identity],rows))
                    stats['unsupported_states']+=len(rows);boundary_reason=child.wave.termination_reason or 'environment_incomplete';continue
                w=child.wave
                if tick+1>=len(w.env_schedule):
                    stats['unsupported_states']+=len(rows);boundary_reason='unresolved_boundary';continue
                if child.identity not in binding_ids:
                    binding_ids[child.identity]=len(result.bindings);result.bindings.append(child)
                child_id=binding_ids[child.identity];next_env=_next_environment(child,tick+1)
                classes=control_classes(w.env_schedule[tick+1:tick+2],controls,next_environment=next_env)
                masks=np.asarray([group[0] for group in classes],np.int64);space=space_for(child)
                following,parents,chosen_masks=_expand(layer.states[rows],masks,tick,1,w.env_schedule,
                    w.platform_table,w.geometry_white,w.geometry_blue,space.payload)
                stats['expanded_states']+=len(rows);stats['safe_transition_rows']+=len(following)
                unique=unique_state_indices(following,next_env)
                if len(unique):batches.append((following[unique],rows[parents[unique]],chosen_masks[unique],
                    np.full(len(unique),child_id,np.int64)))
        if timed_out:reason='wall_budget';break
        if not batches:
            reason=boundary_reason or 'frontier_empty'
            if reason=='frontier_empty' and recovery_lookback:
                recover_started=time.perf_counter()
                recovered=_recover_frontier(result,controls,width,rng,space_for,
                    began+seconds+stats['verification_seconds'],recovery_lookback)
                stats['recovery_seconds']+=time.perf_counter()-recover_started
                if recovered:reason='tick_budget';continue
                if time.perf_counter()-began-stats['verification_seconds']>=seconds:reason='wall_budget'
            break
        following=np.concatenate([batch[0] for batch in batches])
        parent_rows=np.concatenate([batch[1] for batch in batches]);mask_rows=np.concatenate([batch[2] for batch in batches])
        ids=np.concatenate([batch[3] for batch in batches])
        # Carry the input cost across the edge: a tick that presses anything
        # costs INPUT_HELD_COST, and changing the pressed set costs churn.
        parent_layer=result.layers[-1]
        parent_costs=(parent_layer.costs if parent_layer.costs is not None
                      else np.zeros(len(parent_layer.states),dtype=np.int64))
        cost_rows=(parent_costs[parent_rows]
                   + np.where(mask_rows!=parent_layer.masks[parent_rows],INPUT_CHURN_COST,0)
                   + np.where(mask_rows!=0,INPUT_HELD_COST,0))
        selected=_select(following,width,rng,cost_rows)
        stats['discarded_states']+=len(following)-len(selected)
        result.reached_tick=tick+1
        result.layers.append(FrontierLayer(tick+1,following[selected],ids[selected],parent_rows[selected],mask_rows[selected],cost_rows[selected]))
        stats['layer_counts'].append(dict(tick=tick+1,unique_states=len(following),retained_states=len(selected),bindings=len(set(ids[selected]))))
        # Observation only: one report per completed layer, from counters this
        # loop already maintains. A caller that passes nothing pays nothing and
        # the returned object is unchanged either way.
        if progress is not None:
            # Percent is only honest against the tick this search will actually
            # end on: min(max_ticks, the binding's own wave length). Telemetry
            # must never break a solve, so a failure here falls back to max_ticks.
            try:
                horizon=min(int(max_ticks),len(result.bindings[int(result.layers[-1].binding_ids[0])].wave.env_schedule))
            except Exception:
                horizon=int(max_ticks)
            progress(tick=result.reached_tick,ticks=horizon,alive_states=int(len(selected)),
                     unique_states=int(len(following)),expanded_states=int(stats['expanded_states']),
                     discarded_states=int(stats['discarded_states']))
    result.reason=reason;result.actions,result.trajectory=result.witness(chosen)
    record_input_cost(stats,result.actions)
    result.target_history=result.bindings[int(result.layers[-1].binding_ids[chosen])].history
    stats['search_seconds']=time.perf_counter()-began-stats['verification_seconds']
    return result
