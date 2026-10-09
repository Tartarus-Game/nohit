"""Speculate on observed worlds; accept only actual, scalar-replayed inputs.

No observed target is borrowed from another trajectory. A rejected speculative
world only proposes a new input word; it never establishes reachability.
"""
import time
import struct
from types import SimpleNamespace
import numpy as np

from .native_candidate import find_native_candidate
from .parametric_environment import ParametricEnvironment
from .initial_target_history import bind_initial_target_history
from .source_oracle import scalar_module
from . import resumable_wave as world
from .csv_completion import wave_terminal, controlled_terminal


def _world(path, initial, settings, proposal, initial_confirm, previous_confirm,
           initial_target_history, deadline, _setup=None):
    if _setup is None:
        template=ParametricEnvironment(path,**settings)
        state=world.initialize(path,**settings)
        first=bind_initial_target_history(template,initial_target_history)
    else:
        template,initial_world,first=_setup
        state=initial_world.clone()
    player=scalar_module('discrete_operator');collision=scalar_module('joint_transition').frame_collision
    # Frame-zero coordinates are already observed after the native physics tick.
    physical=player.initial_state(initial,first.wave.env_schedule[0])
    frames=[];trace=[];confirms=[];history=[];safe=True;coupled=False;word=[]
    observations=None if initial_target_history is None else iter(initial_target_history)
    while True:
        if time.perf_counter()>deadline:return None
        tick=state.data['tick'];confirm=initial_confirm if tick==0 else tick%2==0
        options={} if coupled else dict(previous_confirm=previous_confirm,previous_cancel=False)
        result=world._advance_with_dialogue_input_owned(state,confirm=confirm,cancel=False,**options);coupled=True
        while isinstance(result,world.NeedTarget):
            if tick==0 and observations is not None:
                row=next(observations,None)
                if row is None or tuple(row[:2])!=(0,result.request['line']):
                    raise ValueError('initial_target_history omits a frame-zero source read')
                xy=row[2:]
            elif tick==0:xy=physical[:2]
            else:xy=player.sample_position(physical,*world._observation_sampling_arrays(result))
            supplied=world._supply_target_owned(result.state,xy)
            result=world._advance_with_dialogue_input_owned(supplied,confirm=confirm,cancel=False)
        if not isinstance(result,(world.TickCommitted,world.Terminal)) or result.frame is None:return None
        state=result.state;frame=result.frame;frames.append(frame);history.extend(frame.target_history)
        if tick:
            mask=int(proposal(physical,frame.env,tick)) if callable(proposal) else int(proposal[tick-1]) if tick<=len(proposal) else 0
            word.append(mask)
            player.step_mask_into(physical,mask,frame.env,frame.platforms,physical)
            confirms.append(confirm)
        trace.append(physical.copy())
        if safe and (not np.isfinite(physical).all() or collision(frame,physical)):safe=False
        if isinstance(result,world.Terminal):
            if result.reason!='endattack':return None
            break
    if observations is not None and next(observations,None) is not None:
        raise ValueError('initial_target_history contains an unused source read')
    # Native search consumes the separate white/blue tensors. The combined
    # display tensor would be another full copy of every dense hazard.
    wave=template._materialize(frames,state,tuple(history),None,None,'endattack',(),True,
        include_combined_geometry=False)
    return template,SimpleNamespace(wave=wave,history=tuple(history),identity=b'',pending_target=None,complete=True),np.asarray(trace),confirms,safe,word


def _controlled_tick_owned(state,control,physical,identity_parts,previous_control=None):
    """Replay one certificate tick; retain no branch cache or mutable parent."""
    from .dialogue_operator import split_control
    mask,confirm,cancel=split_control(control)
    if cancel:raise ValueError('Cancel is not legal in this input domain')
    options={}
    if not state.dialogue_coupled:
        _,old_confirm,old_cancel=split_control(previous_control)
        options=dict(previous_confirm=old_confirm,previous_cancel=old_cancel)
    identity_parts.append(b'I'+struct.pack('<B',control))
    result=world._advance_with_dialogue_input_owned(state,confirm=confirm,cancel=cancel,**options)
    player=scalar_module('discrete_operator')
    while isinstance(result,world.NeedTarget):
        xy=player.sample_position(physical,*world._observation_sampling_arrays(result))
        state=world._supply_target_owned(result.state,xy)
        identity_parts.append(b'T'+struct.pack('<dd',*state.supplied_target))
        result=world._advance_with_dialogue_input_owned(state,confirm=confirm,cancel=cancel)
    return result


def _certify(path,initial,settings,actions,expected,confirms,initial_confirm,
             previous_confirm,initial_target_history,has_dialogue):
    """Original scalar replay; one owned continuation for the committed word."""
    if not has_dialogue:
        from .source_verification import certify_observed
        return certify_observed(path,initial,settings,actions,expected,initial_target_history)
    player=scalar_module('discrete_operator');joint=scalar_module('joint_transition')
    from .source_verification import compile_observed_prefix,scalar_collision_checker
    reference=compile_observed_prefix(path,settings,expected,initial_target_history)
    if reference is None:return None
    template=ParametricEnvironment(path,backend='resumable',**settings)
    binding=template.bind_history_once(reference.target_history)
    if binding.wave.termination_reason!=reference.termination_reason:return None
    reference_check=scalar_collision_checker(reference)
    state=player.initial_state(initial,binding.wave.env_schedule[0]);controlled=None
    base=None;first=None;history=[];primed=False;identity_parts=[];previous_control=None
    for tick in range(len(actions)+1):
        result=None
        if controlled is None:
            if binding.pending_target is not None:return None
            if binding.wave.termination_reason=='dialogue_boundary' and binding.resume_state.request['tick']==tick:
                base=binding;history=list(binding.history);first=max(1,tick)
                prior_confirm=previous_confirm if tick==0 else initial_confirm if tick==1 else confirms[tick-2]
                previous_control=int(state[4])|(32 if prior_confirm else 0)
                controlled=binding.resume_state.clone()
                identity_parts=[b'NOHIT-CONTROLLED\x01',struct.pack('<Q',len(binding.identity)),
                    binding.identity,struct.pack('<B',previous_control)]
                if tick==0:
                    primed=True
                    result=_controlled_tick_owned(controlled,int(state[4])|(32 if initial_confirm else 0),
                        state,identity_parts,previous_control)
            else:
                if tick>=len(reference.env_schedule):return None
                if tick:player.step_mask_into(state,actions[tick-1],reference.env_schedule[tick],reference.platform_table[tick],state)
                if reference_check(tick,state):return None
        if controlled is not None:
            if tick:
                result=_controlled_tick_owned(controlled,int(actions[tick-1])|(32 if confirms[tick-1] else 0),
                    state,identity_parts,previous_control)
            if not isinstance(result,(world.TickCommitted,world.Terminal)) or result.frame is None:return None
            controlled=result.state;frame=result.frame
            if tick:player.step_mask_into(state,actions[tick-1],frame.env,frame.platforms,state)
            if joint.frame_collision(frame,state) or frame.tick!=tick:return None
            rows=frame.target_history
            if tick==max(0,first-1) and primed:rows=rows[len([r for r in history if r[0]==tick]):]
            elif tick==first:rows=rows[len([r for r in history if r[0]==tick]):]
            history.extend(rows)
        if not np.isfinite(state).all() or state.tobytes()!=expected[tick].tobytes():return None
    if controlled is not None:
        if not isinstance(result,world.Terminal) or result.reason!='endattack':return None
        terminal=SimpleNamespace(state=controlled,status='terminal',frame=result.frame,reason=result.reason)
        return base,tuple(history),controlled_terminal(terminal,template),b''.join(identity_parts),first-1,primed
    if not binding.complete or len(binding.wave.env_schedule)!=len(actions)+1:return None
    return binding,binding.history,wave_terminal(binding.wave),None,None,False


def _merge_segments(last,segment_stats):
    last.stats['segments']=segment_stats
    for key in ('expanded_states','safe_transition_rows','discarded_states','search_seconds','kernel_materialization_seconds'):
        last.stats[key]=sum(item.get(key,0) for item in segment_stats)
    last.stats['workspace_bytes']=max(item.get('workspace_bytes',0) for item in segment_stats)
    last.stats['workspace_allocated_bytes_cumulative']=sum(item.get('workspace_allocated_bytes_cumulative',0) for item in segment_stats)
    native=[item['native_code'] for item in segment_stats if not item.get('native_code',{}).get('scalar_preflight')]
    code=dict(native[-1] if native else last.stats['native_code'])
    code['compiled']=any(item.get('native_code',{}).get('compiled') for item in segment_stats)
    code['kernel_load_seconds']=last.stats['kernel_materialization_seconds']
    code['search_seconds']=last.stats['search_seconds']
    code['search_cpu_seconds']=sum(item.get('native_code',{}).get('search_cpu_seconds',0) for item in segment_stats)
    code['process_cpu_seconds']=sum(item.get('native_code',{}).get('process_cpu_seconds',0) for item in segment_stats)
    code['workers_used']=max(item.get('native_code',{}).get('workers_used',1) for item in segment_stats)
    code['effective_search_cores']=code['search_cpu_seconds']/code['search_seconds'] if code['search_seconds'] else 0.
    last.stats['native_code']=code


def _segmented(path,initial,settings,width,workers,memory_mb,selection_seed,initial_target_history,deadline):
    # Commit inputs only up to the next actual observation. Every later world
    # is rebuilt from that committed player's sampling position.
    template=ParametricEnvironment(path,**settings)
    binding=bind_initial_target_history(template,initial_target_history)
    player=scalar_module('discrete_operator')
    state=player.initial_state(initial,binding.wave.env_schedule[0]);word=[];last=None;segment_stats=[];traces=[state.reshape(1,11).copy()]
    for segment in range(256):
        while binding.pending_target is not None and binding.pending_target['tick']<=len(word)+1:
            request=binding.pending_target;tick=request['tick'];wave=binding.wave
            xy=state[:2] if tick==0 else player.sample_position(state,wave.env_schedule[tick],wave.platform_table[tick])
            binding=template.extend(binding,float(xy[0]),float(xy[1]))
        wave=binding.wave;stop=binding.pending_target['tick'] if binding.pending_target is not None else len(wave.env_schedule)
        if stop<=len(word)+1:
            return None
        part=SimpleNamespace(**{name:getattr(wave,name)[len(word):stop] for name in
            ('env_schedule','platform_table','geometry_white','geometry_blue','geometry_polygons')},
            complete=True,termination_reason='endattack')
        resolved=SimpleNamespace(wave=part,pending_target=None,complete=True,history=binding.history,identity=b'')
        remaining=deadline-time.perf_counter()
        if remaining<=0:return None
        last=find_native_candidate(path,state,width=width,seconds=remaining,workers=workers,
            memory_mb=memory_mb,selection_seed=selection_seed+segment,_resolved=(template,resolved),
            _defer_verification=True,**settings)
        if last is None:return None
        if last.status!='proposal_found':
            segment_stats.append(dict(last.stats));_merge_segments(last,segment_stats)
            last.actions=word;last.trajectory=np.concatenate(traces);last.reached_tick=len(word)
            last.stats['search_deepest_tick']=len(word)+max((item['reached'] for item in last.stats.get('probe_attempts',[])),default=0)
            return last
        segment_stats.append(dict(last.stats))
        traces.append(last.trajectory[1:].copy());word.extend(last.actions);state=last.trajectory[-1].copy()
        if binding.complete:
            last.actions=word;last.reached_tick=len(word)
            _merge_segments(last,segment_stats)
            return last
        if binding.wave.termination_reason!='pending_target':return None
    return None


def _segmented_coupled(path,initial,settings,width,workers,memory_mb,selection_seed,
                       initial_confirm,previous_confirm,initial_target_history,deadline):
    """Commit only through the next real observation under explicit dialogue.

    Confirm follows the same declared alternating sequence as the portfolio.
    Every later target uses the committed player's true sampling position.
    Search remains bounded and may prune useful earlier observation branches.
    """
    template=ParametricEnvironment(path,**settings)
    environment=world.initialize(path,**settings)
    first=bind_initial_target_history(template,initial_target_history)
    player=scalar_module('discrete_operator')
    physical=player.initial_state(initial,first.wave.env_schedule[0])
    frames=[];trace_parts=[physical.reshape(1,11).copy()];word=[];confirms=[];history=[]
    observations=None if initial_target_history is None else iter(initial_target_history)
    coupled=False;last=None;segment_stats=[];segment=0
    def commit():
        nonlocal physical,frames,last,segment
        if len(frames)<2:return True
        remaining=deadline-time.perf_counter()
        if remaining<=0:return False
        part=template._materialize(frames,environment,tuple(history),None,None,'endattack',(),True,
            include_combined_geometry=False)
        resolved=SimpleNamespace(wave=part,pending_target=None,complete=True,history=tuple(history),identity=b'')
        last=find_native_candidate(path,physical,width=width,seconds=remaining,workers=workers,
            memory_mb=memory_mb,selection_seed=selection_seed+segment,_resolved=(template,resolved),
            _defer_verification=True,**settings)
        if last is None:return False
        segment_stats.append(dict(last.stats))
        if last.status!='proposal_found':return False
        word.extend(last.actions);trace_parts.append(last.trajectory[1:].copy())
        physical=last.trajectory[-1].copy();frames=frames[-1:];segment+=1
        return True
    while time.perf_counter()<deadline:
        tick=environment.data['tick'];confirm=initial_confirm if tick==0 else tick%2==0
        options={} if coupled else dict(previous_confirm=previous_confirm,previous_cancel=False)
        result=world._advance_with_dialogue_input_owned(environment,confirm=confirm,cancel=False,**options)
        coupled=True
        while isinstance(result,world.NeedTarget):
            environment=result.state
            if not commit():return None
            if tick==0 and observations is not None:
                row=next(observations,None)
                if row is None or tuple(row[:2])!=(0,result.request['line']):
                    raise ValueError('initial_target_history omits a frame-zero source read')
                xy=row[2:]
            elif tick==0:xy=physical[:2]
            else:xy=player.sample_position(physical,*world._observation_sampling_arrays(result))
            world._supply_target_owned(environment,xy)
            result=world._advance_with_dialogue_input_owned(environment,confirm=confirm,cancel=False)
        if not isinstance(result,(world.TickCommitted,world.Terminal)) or result.frame is None:return None
        environment=result.state;frames.append(result.frame);history.extend(result.frame.target_history)
        if tick:confirms.append(confirm)
        if isinstance(result,world.Terminal):
            if result.reason!='endattack' or not commit() or last is None:return None
            if observations is not None and next(observations,None) is not None:
                raise ValueError('initial_target_history contains an unused source read')
            actual=np.concatenate(trace_parts)
            verification_started=time.perf_counter()
            verified=_certify(path,initial,settings,word,actual,confirms,initial_confirm,
                previous_confirm,initial_target_history,True)
            if verified is None:return None
            base,actual_history,terminal,identity,first_tick,primed=verified
            if actual_history!=tuple(history):return None
            last.status='candidate_found';last.verified=True;last.reason='verified_endattack'
            last.actions=word;last.trajectory=actual;last.reached_tick=len(word)
            last.target_history=actual_history;last.bindings=[base];last.base_target_history=base.history
            last.confirm_sequence=confirms;last.source_terminal=terminal;last.controlled_identity=identity
            last.dialogue_start_tick=first_tick;last.primed_initial_frame=primed
            _merge_segments(last,segment_stats)
            last.stats.update(backend='native-coupled-segments',route_cache=False,
                verification_seconds=time.perf_counter()-verification_started,
                retained_trace_bytes=actual.nbytes,committed_observation_segments=segment)
            churn=sum(mask!=(word[i-1] if i else 0) for i,mask in enumerate(word))
            held=sum(mask!=0 for mask in word)
            last.stats['input_cost']=dict(frames=len(word),churn=churn,held_frames=held,
                churn_weight=12,held_weight=1,total=12*churn+held)
            return last
    return None


def _static_coupled_candidate(path,initial,settings,width,workers,memory_mb,selection_seed,
                              initial_confirm,previous_confirm,initial_target_history,deadline):
    """A dialogue clock with no player reads needs one world, not speculation."""
    if initial_target_history:return None
    began=time.perf_counter();template=ParametricEnvironment(path,**settings)
    state=world.initialize(path,**settings);frames=[];confirms=[];coupled=False
    while time.perf_counter()<deadline:
        tick=state.data['tick'];confirm=initial_confirm if tick==0 else tick%2==0
        options={} if coupled else dict(previous_confirm=previous_confirm,previous_cancel=False)
        result=world._advance_with_dialogue_input_owned(state,confirm=confirm,cancel=False,**options);coupled=True
        if not isinstance(result,(world.TickCommitted,world.Terminal)) or result.frame is None:return None
        state=result.state;frames.append(result.frame)
        if tick:confirms.append(confirm)
        if isinstance(result,world.Terminal):
            if result.reason!='endattack':return None
            break
    else:return None
    wave=template._materialize(frames,state,(),None,None,'endattack',(),True,include_combined_geometry=False)
    resolved=SimpleNamespace(wave=wave,history=(),identity=b'',pending_target=None,complete=True)
    source_seconds=time.perf_counter()-began;remaining=deadline-time.perf_counter()
    if remaining<=0:return None
    last=find_native_candidate(path,initial,width=width,seconds=remaining,workers=workers,memory_mb=memory_mb,
        selection_seed=selection_seed,_resolved=(template,resolved),_defer_verification=True,**settings)
    if last is None or last.status!='proposal_found':return last
    verification_started=time.perf_counter()
    verified=_certify(path,initial,settings,last.actions,last.trajectory,confirms,initial_confirm,
        previous_confirm,initial_target_history,True)
    if verified is None:return None
    base,history,terminal,identity,first_tick,primed=verified
    last.status='candidate_found';last.verified=True;last.reason='verified_endattack'
    last.target_history=history;last.bindings=[base];last.base_target_history=base.history
    last.confirm_sequence=confirms;last.source_terminal=terminal;last.controlled_identity=identity
    last.dialogue_start_tick=first_tick;last.primed_initial_frame=primed
    last.stats.update(backend='native-static-dialogue',actual_world_seconds=source_seconds,
        verification_seconds=time.perf_counter()-verification_started,observation_iterations=0,route_cache=False)
    return last


def find_dynamic_candidate(path,initial,*,width=3000,seconds=8.,selection_seed=42,
        workers=None,memory_mb=64,initial_confirm=False,previous_confirm=False,
        initial_target_history=None,progress=None,**settings):
    if settings.get('termination_policy','endattack')!='endattack' or seconds<=0:return None
    from .timeline_csv import parse_timeline_rows
    rows=parse_timeline_rows(path.read_text(encoding='utf-8-sig'))
    names={str(row[1]).lower().strip() for row in rows if len(row)>1}
    has_dialogue='sanstext' in names
    if not has_dialogue and 'getheartpos' not in names:return None
    started=time.perf_counter();deadline=started+seconds
    proposal=[];attempts=[];last=None;world_seconds=0.
    if has_dialogue and 'getheartpos' not in names:
        static=_static_coupled_candidate(path,initial,settings,width,workers,memory_mb,selection_seed,
            initial_confirm,previous_confirm,initial_target_history,deadline)
        if static is not None:
            static.stats['dynamic_wall_seconds']=time.perf_counter()-started
            return static
    if has_dialogue and 'getheartpos' in names:
        segmented=_segmented_coupled(path,initial,settings,width,workers,memory_mb,selection_seed,
            initial_confirm,previous_confirm,initial_target_history,deadline)
        if segmented is not None:
            segmented.stats['dynamic_wall_seconds']=time.perf_counter()-started
            return segmented
    if not has_dialogue and last is None:
        segmented=_segmented(path,initial,settings,width,workers,memory_mb,selection_seed,initial_target_history,deadline)
        if segmented is not None:
            if segmented.status!='proposal_found':return segmented
            last=segmented;proposal=last.actions
    replay_template=ParametricEnvironment(path,**settings)
    replay_setup=(replay_template,world.initialize(path,**settings),
        bind_initial_target_history(replay_template,initial_target_history))
    for iteration in range(64):
        replay_started=time.perf_counter()
        built=_world(path,initial,settings,proposal,initial_confirm,previous_confirm,initial_target_history,deadline,
            _setup=replay_setup)
        world_seconds+=time.perf_counter()-replay_started
        if built is None:break
        template,binding,actual,confirms,safe,word=built
        # A proposed word is accepted only under its own actual observations.
        if last is not None and len(proposal)==len(actual)-1 and safe:
            certify_started=time.perf_counter()
            verified=_certify(path,initial,settings,proposal,actual,confirms,initial_confirm,
                              previous_confirm,initial_target_history,has_dialogue)
            if verified is not None:
                base,history,terminal,identity,first,primed=verified
                last.status='candidate_found';last.verified=True;last.reason='verified_endattack'
                last.trajectory=actual;last.target_history=history;last.bindings=[base]
                last.confirm_sequence=confirms;last.source_terminal=terminal
                last.base_target_history=base.history;last.controlled_identity=identity
                last.dialogue_start_tick=first;last.primed_initial_frame=primed
                churn=sum(mask!=(proposal[i-1] if i else 0) for i,mask in enumerate(proposal))
                held=sum(mask!=0 for mask in proposal)
                last.stats['input_cost']=dict(frames=len(proposal),churn=churn,held_frames=held,churn_weight=12,held_weight=1,total=12*churn+held)
                last.stats['retained_trace_bytes']=actual.nbytes
                last.stats['verification_seconds']=time.perf_counter()-certify_started
                last.stats['actual_world_seconds']=world_seconds
                last.stats.update(backend='native-observed-portfolio',observation_iterations=iteration,
                    dynamic_wall_seconds=time.perf_counter()-started,route_cache=False,
                    speculative_attempts=attempts)
                return last
        remaining=deadline-time.perf_counter()
        if remaining<=0:break
        last=find_native_candidate(path,initial,width=width,seconds=remaining,selection_seed=selection_seed+iteration,
            workers=workers,memory_mb=memory_mb,progress=progress,_resolved=(template,binding),
            _defer_verification=True,**settings)
        if last is None:break
        attempts.append(dict(status=last.status,stats=dict(last.stats)))
        if last.status!='proposal_found':return last
        proposal=last.actions
    if last is not None:
        last.status='unknown';last.verified=False;last.reason='native_observation_budget'
        last.stats['dynamic_wall_seconds']=time.perf_counter()-started
    if last is None:
        last=SimpleNamespace(status='unknown',verified=False,reason='native_observation_budget',
            reached_tick=0,actions=[],trajectory=np.asarray(initial,dtype=np.float64).reshape(1,11),
            target_history=(),bindings=[],layers=[],stats=dict(backend='native-observed-portfolio',
            dynamic_wall_seconds=time.perf_counter()-started),clock=dict(protocol=
            'explicit_dt_schedule' if settings.get('dt_schedule') is not None else
            'native_fixed_240' if settings.get('clock_start_ms') is not None else 'nominal_240',
            decision_ticks=1,original_replay_passed=False))
    return last
