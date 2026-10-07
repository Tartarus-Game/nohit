"""Motion relation under one explicit, bounded Confirm policy.

The controlled world advances on every dialogue tick. Unknown observations or
callbacks are not guessed, and exhausting a fixed policy never means global
UNSAT. A selected EndAttack witness must pass independent joint replay.
Optional width selection finds candidates without claiming full coverage.
"""
from dataclasses import dataclass, field
import math
from types import SimpleNamespace
import time

import numpy as np

from .bounded_frontier import _select
from .control_quotient import control_classes
from .cspace import bake_cspace, collision_query
from .exact_state_dedup import unique_state_indices
from .joint_transition import JointState, begin_joint, step_joint
from .expansion_dispatch import expand_dispatch as _expand, prepare_expansion
from .csv_completion import controlled_terminal, csv_eof_tail, clock_sequence


@dataclass
class DialogueFrontierResult:
    status: str = 'unknown'
    reason: str = 'not_started'
    start_tick: int = -1
    end_tick: int = -1
    origin_index: int | None = None
    actions: list = field(default_factory=list)
    confirm: list = field(default_factory=list)
    controls: list = field(default_factory=list)
    trajectory: np.ndarray = field(default_factory=lambda:np.empty((0,11)))
    layers: list = field(default_factory=list, repr=False)
    parents: list = field(default_factory=list, repr=False)
    masks: list = field(default_factory=list, repr=False)
    initial_indices: np.ndarray = field(default_factory=lambda:np.empty(0,np.int64),repr=False)
    source_events: tuple = ()
    primed_initial_frame: bool = False
    initial_frame_control: int | None = None
    initial_frame: object = field(default=None, repr=False)
    stats: dict = field(default_factory=dict)
    verified: bool = False
    original_replay_passed: bool = False
    complete_in_original_game: bool = False
    source_terminal: dict | None = None
    target_history: tuple = ()
    controlled_binding_identity: bytes = b''


def _padded(rows, width, *, platforms=False):
    shape=(len(rows),max(len(row) for row in rows),width)
    out=np.zeros(shape) if platforms else np.full(shape,np.nan)
    for index,row in enumerate(rows):out[index,:len(row)]=row
    return out


def solve_dialogue_frontier(template, binding, initial_states, *, previous_confirm=False,
                            controls=tuple(range(16)), confirm_policy='alternating',
                            max_ticks=256, max_states=100000, seconds=30.,
                            initial_frame_control=None, width=None, selection_seed=42,
                            progress=None):
    """Resolve a known dialogue boundary under a fixed Confirm sequence.

    ``initial_states`` are complete players immediately before the pending
    dialogue tick, all belonging to ``binding``. Masks are arrows only: Cancel
    would make the world depend on the motion choice. Confirm is either the
    deterministic alternating policy (release, press, ...) or a finite boolean
    sequence. The actual previous Confirm edge is supplied separately.

    At a tick-zero boundary, ``initial_frame_control`` instead declares that
    the supplied players were already observed AFTER that physical tick.
    Replay only its world phase with the recorded control and prior Confirm;
    never move these players again. Returned actions then begin at tick one.
    The option is rejected at later boundaries and for Cancel inputs. The
    caller must supply a world initialization valid before source tick zero;
    this option cannot recover earlier world state from arbitrary snapshots.

    With ``width=None``, no motion state is dropped except by exact next-step
    congruence or a real collision. Otherwise each deduplicated layer uses the
    bounded candidate search's diversity selection; discarded alternatives
    are counted and never entered into a dead-state cache. ``max_states`` is
    checked before width selection, bounding the complete deduplicated batch.
    Time is checked between world ticks and expansion layers; kernel preparation
    and mandatory joint verification are separately timed. Player observations
    branch into exact controlled worlds; unsupported callbacks,
    and every resource limit return unknown, never an impossibility claim.
    EOF is accepted only with the explicit policy and a checked release tail.
    """
    if type(previous_confirm) is not bool:raise ValueError('previous_confirm must be boolean')
    if type(max_ticks) is not int or max_ticks<0 or type(max_states) is not int or max_states<0:
        raise ValueError('max_ticks and max_states must be nonnegative integers')
    if width is not None and (type(width) is not int or width<1):
        raise ValueError('width must be None or a positive integer')
    if isinstance(seconds,bool) or not isinstance(seconds,(float,int)) or not math.isfinite(seconds) or seconds<0:
        raise ValueError('seconds must be finite and nonnegative')
    controls=tuple(controls)
    if not controls or any(isinstance(mask,(bool,np.bool_)) or not isinstance(mask,(int,np.integer)) or not 0<=mask<16 for mask in controls):
        raise ValueError('controls must be arrow masks in [0,15]')
    controls=tuple(dict.fromkeys(int(mask) for mask in controls))
    if isinstance(confirm_policy,str):
        if confirm_policy!='alternating':raise ValueError('unknown confirm_policy')
        policy=None
    else:
        policy=tuple(confirm_policy)
        if any(type(value) is not bool for value in policy):raise ValueError('Confirm sequence must contain booleans')
    initial=np.asarray(initial_states,dtype=np.float64)
    if initial.ndim not in (1,2) or initial.shape[-1]!=11 or not initial.size or not np.isfinite(initial).all():
        raise ValueError('initial_states must contain finite complete players')
    initial=np.ascontiguousarray(initial.reshape(-1,11)).copy()
    if np.any(initial[:,4]!=initial[:,4].astype(np.int64)) or np.any((initial[:,4]<0)|(initial[:,4]>=32)):
        raise ValueError('invalid previous player masks')
    if initial_frame_control is not None:
        if type(initial_frame_control) is not int or not 0<=initial_frame_control<64:
            raise ValueError('initial_frame_control must be an integer control in [0,63]')
        if initial_frame_control&16:
            raise ValueError('initial frame Cancel is outside this input domain')
        if np.any(initial[:,4]!=(initial_frame_control&31)):
            raise ValueError('initial frame control must match every observed player mask')
    # Ownership and backend checks are performed by the shared binding API.
    parent=template.begin_controlled(binding,previous_input_code=int(initial[0,4])|(32 if previous_confirm else 0))
    result=DialogueFrontierResult()
    result.stats=dict(world_ticks=0,world_seconds=0.,relation_seconds=0.,verification_seconds=0.,
        kernel_materialization_seconds=0.,
        expanded_states=0,safe_transition_rows=0,counts=[],motion_states_discarded_by_width=0,
        width=width,selection_seed=selection_seed)
    if binding.pending_target is not None:result.reason='need_target';return result
    if binding.wave.termination_reason!='dialogue_boundary':result.reason='not_dialogue_boundary';return result
    first=int(parent.state.request['tick']);result.start_tick=first-1;result.end_tick=first-1
    if initial_frame_control is not None and first!=0:
        raise ValueError('initial_frame_control requires a tick zero dialogue boundary')
    if len(initial)>max_states:result.reason='state_budget';return result
    if parent.state.data['unproven_callbacks']:result.reason='unknown_callbacks';return result
    began=time.perf_counter();frames=[];confirms=[];ended=False;pending=None
    if initial_frame_control is not None:
        if time.perf_counter()-began>=seconds:result.reason='wall_budget';return result
        parent=template.step_controlled(parent,initial_frame_control)
        if parent.status=='need_target':result.reason='need_pre_tick_zero_observation';return result
        if parent.status in ('unknown','need_input') or parent.state.data['unproven_callbacks']:
            result.reason=parent.reason or 'unknown_callbacks';return result
        if parent.frame is None:result.reason='missing_committed_frame';return result
        if parent.frame.tick!=0:result.reason='clock_discontinuity';return result
        result.primed_initial_frame=True;result.initial_frame_control=initial_frame_control
        result.initial_frame=parent.frame;result.stats['world_ticks']+=1
        first=1;result.start_tick=0;result.end_tick=0
        if parent.status=='terminal':
            if parent.reason!='endattack' and template.termination_policy!='eof_hazards_drained':
                result.reason='unsupported_eof';return result
            ended=True
    for index in range(max_ticks):
        if ended:break
        if time.perf_counter()-began>=seconds:result.reason='wall_budget';return result
        if policy is not None and index>=len(policy):result.reason='confirm_policy_exhausted';return result
        confirm=bool(index%2) if policy is None else policy[index]
        parent=template.step_controlled(parent,32 if confirm else 0)
        if parent.status=='need_target':pending=parent;break
        if parent.status in ('unknown','need_input') or parent.state.data['unproven_callbacks']:
            result.reason=parent.reason or 'unknown_callbacks';return result
        if parent.frame is None:result.reason='missing_committed_frame';return result
        if parent.frame.tick!=first+index:result.reason='clock_discontinuity';return result
        frames.append(parent.frame);confirms.append(confirm)
        result.stats['world_ticks']+=1
        # Observation only, and deliberately cheap: one report per dialogue tick
        # so a long intro no longer freezes the live solve display. The counters
        # are the ones this loop already maintains.
        if progress is not None:
            # No ``ticks``: the dialogue tail is bounded by its wall budget, not
            # by a known horizon, so a tick-based fraction here would invent a
            # percentage. The client falls back to the budget basis instead.
            progress(phase='dialogue',tick=first+index+1,
                     alive_states=len(initial_states),expanded_states=int(result.stats['world_ticks']),
                     discarded_states=result.stats.get('discarded_states'))
        if parent.status=='terminal':
            if parent.reason!='endattack' and template.termination_policy!='eof_hazards_drained':
                result.reason='unsupported_eof';return result
            ended=True;break
    result.stats['world_seconds']=time.perf_counter()-began
    if not ended and pending is None:result.reason='tick_budget';return result
    wave=binding.wave;prior=max(0,first-1)
    initial_frame=result.initial_frame or SimpleNamespace(env=wave.env_schedule[prior],
        platforms=wave.platform_table[prior],white=wave.geometry_white[prior],
        blue=wave.geometry_blue[prior],polygons=wave.geometry_polygons[prior])
    env=np.vstack([initial_frame.env]+[frame.env for frame in frames])
    platforms=_padded([initial_frame.platforms]+[frame.platforms for frame in frames],9,platforms=True)
    white=_padded([initial_frame.white]+[frame.white for frame in frames],4)
    blue=_padded([initial_frame.blue]+[frame.blue for frame in frames],4)
    polygons=_padded([initial_frame.polygons]+[frame.polygons for frame in frames],8)
    left,top=np.floor(np.min(env[:,:2],axis=0));right,bottom=np.ceil(np.max(env[:,2:4],axis=0))
    view=SimpleNamespace(env_schedule=env,geometry_white=white,geometry_blue=blue,
        geometry_polygons=polygons,origin=(int(left),int(top)),dimensions=(int(bottom-top),int(right-left)))
    space=bake_cspace(view,cell_size=8.)
    # At tick zero there is no committed prior frame. Its hazards belong to
    # the first controlled transition and are checked after that transition.
    safe=np.array([state[10]==0. and (first==0 or not collision_query(white,blue,0,state,0.,space.payload)) for state in initial])
    result.initial_indices=np.flatnonzero(safe);states=initial[safe]
    result.layers=[states];result.stats['counts']=[(first-1,len(states))]
    if not len(states):result.reason='initial_collision';return result
    prepare=time.perf_counter()
    prepare_expansion(states,np.asarray(controls,np.int64),0,1,env,platforms,white,blue,space.payload)
    result.stats['kernel_materialization_seconds']=time.perf_counter()-prepare
    began+=result.stats['kernel_materialization_seconds']
    relation_start=time.perf_counter();rng=np.random.default_rng(selection_seed) if width is not None else None
    for tick in range(len(frames)):
        if time.perf_counter()-began>=seconds:
            result.reason='wall_budget';result.stats['relation_seconds']=time.perf_counter()-relation_start;return result
        row=env[tick+2] if tick+1<len(frames) else None
        classes=control_classes(env[tick+1:tick+2],controls,next_environment=row)
        masks=np.asarray([group[0] for group in classes],np.int64)
        args=(states,masks,tick,1,env,platforms,white,blue,space.payload)
        following,parents,used_masks=_expand(*args)
        indices=unique_state_indices(following,row)
        result.stats['expanded_states']+=len(states);result.stats['safe_transition_rows']+=len(following)
        if len(indices)>max_states:
            result.reason='state_budget';result.stats['relation_seconds']=time.perf_counter()-relation_start;return result
        if width is not None and len(indices)>width:
            selected=_select(following[indices],width,rng)
            result.stats['motion_states_discarded_by_width']+=len(indices)-len(selected)
            indices=indices[selected]
        states=following[indices];result.layers.append(states)
        result.parents.append(parents[indices]);result.masks.append(used_masks[indices])
        result.end_tick=first+tick;result.stats['counts'].append((result.end_tick,len(states)))
        del following,parents,used_masks,args
        if not len(states):
            result.reason='empty_fixed_policy_relation';result.stats['relation_seconds']=time.perf_counter()-relation_start;return result
    result.stats['relation_seconds']=time.perf_counter()-relation_start
    if pending is not None:
        from .dialogue_target_frontier import continue_dialogue_targets
        return continue_dialogue_targets(template,binding,initial,result,pending,
            confirms=confirms,controls=controls,policy=policy,max_ticks=max_ticks,
            max_states=max_states,seconds=seconds,began=began,previous_confirm=previous_confirm,
            width=width,rng=rng)
    terminal=controlled_terminal(parent,template)
    index=0
    if terminal['reason']!='endattack':
        last_reasons=['unsupported_source_terminal']
        for candidate,player in enumerate(states):
            tail=csv_eof_tail(terminal,player,clock_sequence(template),template.max_ticks)
            if tail is not None and tail['status']=='proven':
                index=candidate;break
            if tail is not None:last_reasons=tail['reasons']
        else:
            result.reason='terminal_invariant_unproven'
            result.stats['terminal_reasons']=last_reasons
            return result
    actions=[];trace=[states[index]]
    for layer,parents,masks in zip(reversed(result.layers[:-1]),reversed(result.parents),reversed(result.masks)):
        actions.append(int(masks[index]));index=int(parents[index]);trace.append(layer[index])
    result.origin_index=int(result.initial_indices[index]);result.actions=actions[::-1]
    result.confirm=confirms;result.controls=[mask|(32 if confirm else 0) for mask,confirm in zip(result.actions,confirms)]
    result.trajectory=np.asarray(trace[::-1])
    event_frames=([result.initial_frame] if result.primed_initial_frame else [])+frames
    result.source_events=tuple(event for frame in event_frames for event in frame.events)
    verify=time.perf_counter();origin=initial[result.origin_index]
    joint=begin_joint(template,binding,origin,previous_input_code=int(origin[4])|(32 if previous_confirm else 0))
    if result.primed_initial_frame:
        replay_world=template.step_controlled(joint.environment,initial_frame_control)
        if replay_world.frame is None or replay_world.frame.tick!=0 or replay_world.status not in ('ready','terminal'):
            result.reason='joint_replay_initial_frame';return result
        joint=JointState(joint.player,replay_world)
    for index,control in enumerate(result.controls,1):
        edge=step_joint(template,joint,control)
        if edge.state is None:
            result.reason='joint_replay_'+str(edge.reason or edge.status);result.stats['verification_seconds']=time.perf_counter()-verify;return result
        joint=edge.state
        if np.asarray(joint.player).tobytes()!=result.trajectory[index].tobytes():
            result.reason='joint_replay_state_mismatch';result.stats['verification_seconds']=time.perf_counter()-verify;return result
    result.stats['verification_seconds']=time.perf_counter()-verify
    if joint.environment.status!='terminal' or joint.environment.reason!=terminal['reason']:
        result.reason='joint_replay_incomplete';return result
    replay_terminal=controlled_terminal(joint.environment,template)
    if (replay_terminal['tick']!=terminal['tick'] or
            replay_terminal['details']!=terminal['details'] or
            replay_terminal['environment'].tobytes()!=terminal['environment'].tobytes()):
        result.reason='joint_replay_terminal_mismatch';return result
    if terminal['reason']!='endattack':
        tail=csv_eof_tail(replay_terminal,np.asarray(joint.player),clock_sequence(template),template.max_ticks)
        if tail is None or tail['status']!='proven':result.reason='joint_replay_terminal_unproven';return result
    result.source_terminal=replay_terminal
    result.target_history=tuple(binding.history)
    result.controlled_binding_identity=joint.environment.identity
    result.status='candidate_found';result.reason='verified_'+terminal['reason'];result.verified=True
    return result
