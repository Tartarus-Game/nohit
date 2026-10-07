"""Exact target-dependent continuation of an already expanded dialogue prefix.

World transactions run once per incoming world/observation; their committed
frames expand entire player batches. Arrows are applied only by the player
operator. Historical evidence is recovered from the selected player's ancestry.
"""
from collections import Counter
import time

import numpy as np

from .bounded_frontier import _select
from .control_quotient import control_classes
from .csv_completion import controlled_terminal, csv_eof_tail, clock_sequence
from .discrete_operator import sample_position
from .environment_state_key import encode_typed
from .exact_state_dedup import unique_state_indices
from .expansion_dispatch import expand_dispatch
from .joint_transition import JointState, begin_joint, step_joint
from .resumable_wave import preview_observation_frame, state_environment_key


def _array_key(array):
    return (array.dtype.str,array.shape,array.tobytes())


class _WorldScope:
    """Exact dynamic keys in one owned immutable program/clock scope.

    The shared program retains complete source/operator bytes and clock suffix.
    Arrows are absent because step_controlled consumes only Confirm/Cancel;
    player11 retains its full mask. Frame bytes are also required: future-only
    equality does not preserve unconsumed teleport pulses/platform rows.
    """
    def __init__(self,environment):
        state=environment.state
        self.program=state.program
        self.max_ticks=state.max_ticks
        self.termination_policy=state.vm.termination_policy

    def key(self,environment):
        state=environment.state
        if (state.program is not self.program or state.max_ticks!=self.max_ticks or
                state.vm.termination_policy!=self.termination_policy):
            raise ValueError('controlled world belongs to another source/clock scope')
        if state.phase!='committed' or environment.frame is None:
            raise ValueError('only committed worlds may be grouped')
        parts=(state.clock_timestamp,state.initial_dt,environment.status,environment.reason,
               environment.input_code&48,state_environment_key(state))
        current=environment.frame
        parts+=tuple(_array_key(value) for value in
                     (current.env,current.platforms,current.white,current.blue,current.polygons))
        return encode_typed(parts)


def _frame_arrays(frame):
    # Expansion at row zero consumes row one, never these duplicated priors.
    env=np.stack((frame.env,frame.env))
    platforms=np.stack((frame.platforms,frame.platforms))
    white=np.stack((frame.white,frame.white))
    blue=np.stack((frame.blue,frame.blue))
    polygons=np.stack((frame.polygons,frame.polygons))
    # Empty raster selects exact rectangles and beam quads.
    payload=(np.empty((2,2,0,0),np.uint8),polygons,0.,0.,1.)
    return env,platforms,white,blue,payload


def continue_dialogue_targets(template,binding,initial,result,pending,*,confirms,
                              controls,policy,max_ticks,max_states,seconds,began,
                              previous_confirm,width,rng):
    """Continue a real target boundary without redoing its known prefix.

    Published layers are complete. Each group owns an exact world and player
    indices. Target reads sample every incoming player before exact grouping;
    no representative player's observation is borrowed by another branch.
    """
    stats=result.stats
    stats.update(target_dependent=True,target_observations=0,target_player_transactions=0,
                 world_group_counts=[],world_frame_groups=0,unknown_world_branches=0,
                 world_key_seconds=0.,world_key_bytes=0)
    scope=_WorldScope(pending)
    states=result.layers[-1]
    groups=[(pending,np.arange(len(states),dtype=np.intp))]
    unknown=Counter();confirms=list(confirms)
    continuation_start=time.perf_counter();relation_start=stats['relation_seconds']
    extra_world_seconds=0.

    def expired():return time.perf_counter()-began>=seconds

    def finish(reason):
        result.reason=reason
        stats['world_seconds']+=extra_world_seconds
        stats['relation_seconds']=relation_start+time.perf_counter()-continuation_start-extra_world_seconds
        stats['unknown_world_reasons']=dict(unknown)
        return result

    def key(world):
        started=time.perf_counter();value=scope.key(world)
        stats['world_key_seconds']+=time.perf_counter()-started
        stats['world_key_bytes']+=len(value)
        return value

    def note_unknown(reason,count):
        unknown[reason]+=count;stats['unknown_world_branches']+=count

    for index in range(len(confirms),max_ticks):
        if expired():return finish('wall_budget')
        if policy is not None and index>=len(policy):return finish('confirm_policy_exhausted')
        confirm=bool(index%2) if policy is None else policy[index]
        input_code=32 if confirm else 0;frame_groups={}

        def add_frame(world,indices):
            if world.status in ('unknown','need_input') or world.state.data['unproven_callbacks']:
                note_unknown(world.reason or 'unknown_callbacks',len(indices));return
            if world.frame is None:
                note_unknown('missing_committed_frame',len(indices));return
            if world.frame.tick!=result.start_tick+index+1:
                note_unknown('clock_discontinuity',len(indices));return
            identity=key(world)
            if identity not in frame_groups:frame_groups[identity]=[world,[]]
            frame_groups[identity][1].append(np.asarray(indices,dtype=np.intp))

        for world,indices in groups:
            if expired():return finish('wall_budget')
            started=time.perf_counter()
            current=world if world.status=='need_target' else template.step_controlled(world,input_code)
            extra_world_seconds+=time.perf_counter()-started
            stats['world_ticks']+=int(world.status!='need_target')
            if current.status!='need_target':
                add_frame(current,indices);continue
            # Arrows are a late player phase: resolve this incoming player's
            # world once, then expand all its permitted masks in one batch.
            for player_index in indices:
                if expired():return finish('wall_budget')
                transaction=current;player=states[player_index]
                stats['target_player_transactions']+=1
                started=time.perf_counter()
                while transaction.status=='need_target':
                    if expired():return finish('wall_budget')
                    preview=preview_observation_frame(transaction.state)
                    x,y=sample_position(player,preview.env,preview.platforms)
                    transaction=template.supply_controlled_target(transaction,float(x),float(y))
                    stats['target_observations']+=1
                extra_world_seconds+=time.perf_counter()-started
                add_frame(transaction,[player_index])

        stats['world_frame_groups']+=len(frame_groups)
        chunks=[];parent_chunks=[];mask_chunks=[];world_chunks=[];count=0
        for world,parent_indices in frame_groups.values():
            if expired():return finish('wall_budget')
            parent_indices=np.concatenate(parent_indices);row=None
            # Use the existing control/latch quotient only if this world's
            # next physical environment is fully known. A target preview is
            # not enough. The lookahead is reused by the controlled cache.
            if world.status=='ready' and index+1<max_ticks and (policy is None or index+1<len(policy)):
                following_confirm=bool((index+1)%2) if policy is None else policy[index+1]
                started=time.perf_counter()
                peek=template.step_controlled(world,32 if following_confirm else 0)
                extra_world_seconds+=time.perf_counter()-started
                if peek.status in ('ready','terminal') and peek.frame is not None and not peek.state.data['unproven_callbacks']:
                    row=peek.frame.env
            classes=control_classes(world.frame.env[None,:],controls,next_environment=row)
            masks=np.asarray([group[0] for group in classes],np.int64)
            env,platforms,white,blue,payload=_frame_arrays(world.frame)
            following,parents,used=expand_dispatch(states[parent_indices],masks,0,1,
                                                   env,platforms,white,blue,payload)
            chosen=unique_state_indices(following,row)
            stats['expanded_states']+=len(parent_indices)
            stats['safe_transition_rows']+=len(following)
            count+=len(chosen)
            if count>max_states:return finish('state_budget')
            if len(chosen):
                chunks.append(following[chosen]);parent_chunks.append(parent_indices[parents[chosen]])
                mask_chunks.append(used[chosen]);world_chunks.append((world,len(chosen)))
        if not count:return finish('unknown_world_transition' if unknown else 'empty_fixed_policy_relation')
        following=np.concatenate(chunks);parents=np.concatenate(parent_chunks);masks=np.concatenate(mask_chunks)
        labels=np.concatenate([np.full(n,i,np.intp) for i,(_,n) in enumerate(world_chunks)])
        chosen=np.arange(count,dtype=np.intp)
        if width is not None and count>width:
            chosen=_select(following,width,rng)
            stats['motion_states_discarded_by_width']+=count-len(chosen)
        states=following[chosen];labels=labels[chosen]
        result.layers.append(states);result.parents.append(parents[chosen]);result.masks.append(masks[chosen])
        result.end_tick=result.start_tick+index+1
        stats['counts'].append((result.end_tick,len(states)));confirms.append(confirm)
        groups=[(world,np.flatnonzero(labels==i)) for i,(world,_) in enumerate(world_chunks)
                if np.any(labels==i)]
        stats['world_group_counts'].append((result.end_tick,len(groups)))
        for world,indices in groups:
            if world.status!='terminal':continue
            terminal=controlled_terminal(world,template)
            for candidate in indices:
                tail=(None if terminal['reason']=='endattack' else
                      csv_eof_tail(terminal,states[candidate],clock_sequence(template),template.max_ticks))
                if terminal['reason']!='endattack' and (tail is None or tail['status']!='proven'):
                    note_unknown('terminal_invariant_unproven',1);continue
                finish('candidate_replay')
                return _verify_selected(template,binding,initial,result,int(candidate),confirms,
                                        world,scope,previous_confirm)
        groups=[(world,indices) for world,indices in groups if world.status!='terminal']
        if not groups:return finish('terminal_invariant_unproven')
    return finish('tick_budget')


def _verify_selected(template,binding,initial,result,index,confirms,world,scope,previous_confirm):
    actions=[];trace=[result.layers[-1][index]]
    for layer,parents,masks in zip(reversed(result.layers[:-1]),reversed(result.parents),reversed(result.masks)):
        actions.append(int(masks[index]));index=int(parents[index]);trace.append(layer[index])
    result.origin_index=int(result.initial_indices[index]);result.actions=actions[::-1]
    result.confirm=confirms
    result.controls=[mask|(32 if confirm else 0) for mask,confirm in zip(result.actions,confirms)]
    result.trajectory=np.asarray(trace[::-1])
    started=time.perf_counter();origin=initial[result.origin_index]
    node=begin_joint(template,binding,origin,previous_input_code=int(origin[4])|(32 if previous_confirm else 0))
    histories=list(binding.history);events=[]
    boundary_tick=int(binding.resume_state.request['tick'])
    inflight_prefix=tuple(row for row in binding.history if row[0]==boundary_tick)
    first_frame=True

    def fail(reason):
        result.reason=reason;result.stats['verification_seconds']=time.perf_counter()-started
        return result

    def record_frame(frame):
        nonlocal first_frame
        local=tuple(frame.target_history)
        if first_frame:
            if frame.tick!=boundary_tick:return False
            # A target preceding SansText on the suspended physical tick is
            # already in base history and again in that tick's committed frame.
            # Verify and skip only this exact prefix; never set-dedup history.
            if encode_typed(local[:len(inflight_prefix)])!=encode_typed(inflight_prefix):return False
            local=local[len(inflight_prefix):];first_frame=False
        histories.extend(local);events.extend(frame.events)
        return True

    if result.primed_initial_frame:
        prime=template.step_controlled(node.environment,result.initial_frame_control)
        if prime.status not in ('ready','terminal') or prime.frame is None or prime.frame.tick!=0:
            return fail('joint_replay_initial_frame')
        node=JointState(node.player,prime)
        if not record_frame(prime.frame):return fail('joint_replay_history_prefix_mismatch')
    for offset,control in enumerate(result.controls,1):
        edge=step_joint(template,node,control)
        if edge.state is None:return fail('joint_replay_'+str(edge.reason or edge.status))
        node=edge.state
        if np.asarray(node.player).tobytes()!=result.trajectory[offset].tobytes():
            return fail('joint_replay_state_mismatch')
        if not record_frame(node.environment.frame):return fail('joint_replay_history_prefix_mismatch')
    if node.environment.status!='terminal':return fail('joint_replay_incomplete')
    if scope.key(node.environment)!=scope.key(world):return fail('joint_replay_world_mismatch')
    terminal=controlled_terminal(node.environment,template)
    if terminal['reason']!='endattack':
        tail=csv_eof_tail(terminal,np.asarray(node.player),clock_sequence(template),template.max_ticks)
        if tail is None or tail['status']!='proven':return fail('joint_replay_terminal_unproven')
    result.source_terminal=terminal
    result.target_history=tuple(histories);result.source_events=tuple(events)
    result.controlled_binding_identity=node.environment.identity
    result.status='candidate_found';result.reason='verified_'+terminal['reason'];result.verified=True
    result.stats['verification_seconds']=time.perf_counter()-started
    return result
