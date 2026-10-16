"""Speculate on observed worlds; accept only actual, scalar-replayed inputs.

No observed target is borrowed from another trajectory. A rejected speculative
world only proposes a new input word; it never establishes reachability.
"""
import time
import hashlib
from pathlib import Path
import struct
from types import SimpleNamespace
import numpy as np

from .native_candidate import find_native_candidate
from .parametric_environment import ParametricEnvironment
from .initial_target_history import bind_initial_target_history
from .source_oracle import scalar_module
from . import resumable_wave as world
from .csv_completion import wave_terminal, controlled_terminal
from .source_verification import scalar_frame_collision


def _unknown_candidate(initial, settings, reason):
    protocol=('explicit_dt_schedule' if settings.get('dt_schedule') is not None else
              'native_fixed_240' if settings.get('clock_start_ms') is not None else 'nominal_240')
    clock=dict(protocol=protocol,decision_ticks=1,original_replay_passed=False)
    sequence=settings.get('dt_schedule')
    if sequence is not None:
        clock.update(schedule_count=len(sequence),
            schedule_sha256=hashlib.sha256(np.asarray(sequence,dtype='<f8').tobytes()).hexdigest())
    return SimpleNamespace(status='unknown',verified=False,reason=reason,reached_tick=0,
        actions=[],trajectory=np.asarray(initial,dtype=np.float64).reshape(1,11),
        target_history=(),bindings=[],layers=[],stats=dict(backend='native-observed-portfolio'),clock=clock)


def _proposal_frame(frame):
    """Bounded search window only; acceptance always replays all source bodies.

    Artificial outer walls prevent a proposal from reaching omitted geometry.
    They may prune valid distant routes, never establish global infeasibility.
    Public environment bindings and independent certificates keep all hazards.
    """
    if len(frame.white)+len(frame.blue)<256:return frame
    e=frame.env
    if min(e[0],e[14],e[18])<-48. or max(e[2],e[16],e[20])>688.:return frame
    if min(e[1],e[15],e[19])<-48. or max(e[3],e[17],e[21])>528.:return frame
    from dataclasses import replace
    def inside(rows):
        return rows[(rows[:,0]<=706.)&(rows[:,2]>=-66.)&
                    (rows[:,1]<=546.)&(rows[:,3]>=-66.)]
    white=inside(frame.white);blue=inside(frame.blue)
    if len(white)==len(frame.white) and len(blue)==len(frame.blue):return frame
    walls=np.array([[-np.inf,-np.inf,-64.,np.inf],[704.,-np.inf,np.inf,np.inf],
                    [-np.inf,-np.inf,np.inf,-64.],[-np.inf,544.,np.inf,np.inf]])
    return replace(frame,white=np.concatenate((white,walls)),blue=blue)


def _world(path, initial, settings, proposal, initial_confirm, previous_confirm,
           initial_target_history, deadline, _setup=None):
    if _setup is None:
        template=ParametricEnvironment(path,**settings)
        state=world._enable_bone_arrays(world.initialize(path,**settings),native=True)
        first=bind_initial_target_history(template,initial_target_history)
    else:
        template,initial_world,first=_setup
        state=initial_world.clone()
    player=scalar_module('discrete_operator');collision=scalar_frame_collision
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
        state=result.state;frame=result.frame;frames.append(_proposal_frame(frame));history.extend(frame.target_history)
        if tick:
            mask=int(proposal(physical,frame.env,tick)) if callable(proposal) else int(proposal[tick-1]) if tick<=len(proposal) else 0
            word.append(mask)
            player.step_mask_into(physical,mask,frame.env,frame.platforms,physical)
            confirms.append(confirm)
        trace.append(physical.copy())
        if safe and (not np.isfinite(physical).all() or collision(frame,physical)):safe=False
        if isinstance(result,world.Terminal):
            if result.reason not in ('endattack','eof_hazards_drained'):return None
            break
    if observations is not None and next(observations,None) is not None:
        raise ValueError('initial_target_history contains an unused source read')
    # Native search consumes the separate white/blue tensors. The combined
    # display tensor would be another full copy of every dense hazard.
    wave=template._materialize(frames,state,tuple(history),None,None,result.reason,(),True,
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
    damage_events=[];prefix_damage={}
    for event in reference.source_events:
        if event[1]=="damageplayer":prefix_damage.setdefault(event[0],[]).append(event)
    for tick in range(len(actions)+1):
        result=None
        if controlled is None:
            if binding.pending_target is not None:return None
            if binding.wave.termination_reason=='dialogue_boundary' and binding.resume_state.request['tick']==tick:
                base=binding;history=list(binding.history);first=max(1,tick)
                prior_confirm=previous_confirm if tick==0 else initial_confirm if tick==1 else confirms[tick-2]
                previous_control=int(state[4])|(32 if prior_confirm else 0)
                controlled=world._enable_bone_arrays(binding.resume_state.clone())
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
            if scalar_frame_collision(frame,state) or frame.tick!=tick:return None
            rows=frame.target_history
            if tick==max(0,first-1) and primed:rows=rows[len([r for r in history if r[0]==tick]):]
            elif tick==first:rows=rows[len([r for r in history if r[0]==tick]):]
            history.extend(rows)
        if not np.isfinite(state).all() or state.tobytes()!=expected[tick].tobytes():return None
        events=frame.events if controlled is not None else prefix_damage.get(tick,())
        for source_tick,command,args in events:
            if command=='damageplayer':
                damage_events.append(dict(tick=source_tick,amount=float(args[0]),kr=float(args[1] or 0.)))
    if controlled is not None:
        if not isinstance(result,world.Terminal) or result.reason not in ('endattack','eof_hazards_drained'):return None
        terminal=SimpleNamespace(state=controlled,status='terminal',frame=result.frame,reason=result.reason)
        source_terminal=controlled_terminal(terminal,template);source_terminal["scripted_damage_events"]=damage_events
        return base,tuple(history),source_terminal,b''.join(identity_parts),first-1,primed
    if not binding.complete or len(binding.wave.env_schedule)!=len(actions)+1:return None
    source_terminal=wave_terminal(binding.wave);source_terminal["scripted_damage_events"]=damage_events
    return binding,binding.history,source_terminal,None,None,False


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
    code['state_hash_rebuilds']=sum(item.get('native_code',{}).get('state_hash_rebuilds',0) for item in segment_stats)
    code['collision_index_seconds']=sum(item.get('native_code',{}).get('collision_index_seconds') or 0. for item in segment_stats)
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
                       initial_confirm,previous_confirm,initial_target_history,deadline,_goal_style=None,_preview_ticks=0,_audit=None,_chunk_ticks=0,_preview_reads=128,_goal_retries=False,_fixed_prefix=None):
    """Commit only through the next real observation under explicit dialogue.

    Confirm follows the same declared alternating sequence as the portfolio.
    Every later target uses the committed player's true sampling position.
    Search remains bounded and may prune useful earlier observation branches.
    """
    template=ParametricEnvironment(path,**settings)
    environment=world._enable_bone_arrays(world.initialize(path,**settings),native=True)
    first=bind_initial_target_history(template,initial_target_history)
    player=scalar_module('discrete_operator')
    physical=player.initial_state(initial,first.wave.env_schedule[0])
    frames=[];trace_parts=[physical.reshape(1,11).copy()];word=[];confirms=[];history=[]
    observations=None if initial_target_history is None else iter(initial_target_history)
    coupled=False;last=None;segment_stats=[];segment=0
    fixed_actions=[];fixed_trace=None;fixed_confirms=[]
    if _fixed_prefix is not None:
        supplied_hash=_fixed_prefix.get('csv_sha256',_fixed_prefix.get('source_sha256'))
        if supplied_hash!=hashlib.sha256(Path(path).read_bytes()).hexdigest():
            raise ValueError('fixed prefix must identify this CSV source hash')
        fixed_actions=list(_fixed_prefix['actions'])
        fixed_trace=np.asarray(_fixed_prefix['trajectory'],dtype=np.float64)
        fixed_confirms=list(_fixed_prefix['confirm_sequence'])
        # Custom emits arrows only. The observed frame-zero input latch is
        # preserved independently and may still contain a prior Cancel bit.
        if (fixed_trace.shape!=(len(fixed_actions)+1,11) or not np.isfinite(fixed_trace).all() or
                len(fixed_confirms)!=len(fixed_actions) or
                any(type(mask) is not int or not 0<=mask<=15 for mask in fixed_actions) or
                any(type(value) is not bool for value in fixed_confirms) or
                fixed_trace[0].tobytes()!=physical.tobytes()):
            raise ValueError('invalid fixed prefix witness')
    def commit(suspension=None):
        nonlocal physical,frames,last,segment
        if len(frames)<2:return True
        remaining=deadline-time.perf_counter()
        if remaining<=0:return False
        committed_count=len(frames)-1
        if fixed_trace is not None and len(word)<len(fixed_actions):
            prefix_end=min(len(fixed_actions),len(word)+committed_count)
            if physical.tobytes()!=fixed_trace[len(word)].tobytes():
                raise ValueError('fixed prefix state disagrees with its reconstructed world')
            if confirms[:prefix_end]!=fixed_confirms[:prefix_end]:
                raise ValueError('fixed prefix Confirm sequence disagrees with the declared policy')
            count=prefix_end-len(word)
            trace_parts.append(fixed_trace[len(word)+1:prefix_end+1].copy())
            word.extend(fixed_actions[len(word):prefix_end])
            physical=fixed_trace[prefix_end].copy();frames=frames[count:];segment+=1
            committed_count=len(frames)-1
            if not committed_count:return True
        search_frames=frames;preview_reads=0
        if suspension is not None and _preview_ticks and committed_count>4:
            preview=suspension.state.clone();guess=physical.copy();preview_reads=0
            for old_frame in frames[1:]:
                player.step_mask_into(guess,0,old_frame.env,old_frame.platforms,guess)
            search_frames=list(frames);stop=preview.data['tick']+_preview_ticks
            while preview.data['tick']<stop and time.perf_counter()<deadline:
                future_tick=preview.data['tick'];future_confirm=initial_confirm if future_tick==0 else future_tick%2==0
                future=world._advance_with_dialogue_input_owned(preview,confirm=future_confirm,cancel=False)
                while isinstance(future,world.NeedTarget):
                    preview_reads+=1
                    xy=guess[:2] if future_tick==0 else player.sample_position(guess,*world._observation_sampling_arrays(future))
                    preview=world._supply_target_owned(future.state,xy)
                    future=world._advance_with_dialogue_input_owned(preview,confirm=future_confirm,cancel=False)
                if preview_reads>_preview_reads:break
                if not isinstance(future,(world.TickCommitted,world.Terminal)) or future.frame is None:break
                preview=future.state;search_frames.append(_proposal_frame(future.frame))
                if future_tick:player.step_mask_into(guess,0,future.frame.env,future.frame.platforms,guess)
                if isinstance(future,world.Terminal):break
        part=template._materialize(search_frames,environment,tuple(history),None,None,'endattack',(),True,
            include_combined_geometry=False)
        resolved=SimpleNamespace(wave=part,pending_target=None,complete=True,history=tuple(history),identity=b'')
        target=None
        if _goal_style is not None:
            # Relative goals are policies, not saved routes or observed worlds.
            fractions=((.15,.15),(.85,.15),(.85,.85),(.15,.85),(.5,.15),(.85,.5),(.5,.85),(.15,.5))
            slot=_goal_style if _goal_style<8 else (_goal_style-8+len(word)//30)%8
            u,v=fractions[slot];bounds=part.env_schedule[-1,:4]
            target=(bounds[0]+13.+u*max(0.,bounds[2]-bounds[0]-26.),
                    bounds[1]+13.+v*max(0.,bounds[3]-bounds[1]-26.))
        goals=[target]
        if _goal_retries:
            bounds=part.env_schedule[-1,:4]
            for u,v in ((.5,.5),(.15,.15),(.85,.15),(.85,.85),(.15,.85)):
                point=(bounds[0]+13.+u*max(0.,bounds[2]-bounds[0]-26.),
                       bounds[1]+13.+v*max(0.,bounds[3]-bounds[1]-26.))
                if point not in goals:goals.append(point)
        for attempt,goal in enumerate(goals):
            remaining=deadline-time.perf_counter()
            if remaining<=0:return False
            budget=min(remaining,4. if attempt==0 else 1.5) if _goal_retries else remaining
            last=find_native_candidate(path,physical,width=width,seconds=budget,workers=workers,
                memory_mb=memory_mb,selection_seed=selection_seed+segment+attempt*0x9e3779b9,
                _resolved=(template,resolved),_defer_verification=True,_terminal_target=goal,**settings)
            if last is not None and last.status=='proposal_found':break
        if last is None:return False
        if _audit is not None:
            probes=last.stats.get('probe_attempts',())
            _audit.append(dict(origin_tick=len(word),goal_style=_goal_style,preview_ticks=_preview_ticks,
                preview_target_reads=preview_reads,preview_frame_count=len(search_frames)-len(frames),
                status=last.status,search_seconds=last.stats.get('search_seconds',0.),
                expanded_states=last.stats.get('expanded_states',0),
                safe_transition_rows=last.stats.get('safe_transition_rows',0),
                workspace_bytes=last.stats.get('workspace_bytes',0),
                search_cpu_seconds=last.stats.get('native_code',{}).get('search_cpu_seconds',0.),
                kernel_materialization_seconds=last.stats.get('kernel_materialization_seconds',0.),
                deepest_tick=len(word)+max((v['reached'] for v in probes),default=last.reached_tick)))
        segment_stats.append(dict(last.stats))
        if last.status!='proposal_found':return False
        # Only the actual pre-observation prefix is committed. Speculative
        # future targets rank choices but are discarded and never certified.
        word.extend(last.actions[:committed_count]);trace_parts.append(last.trajectory[1:committed_count+1].copy())
        physical=last.trajectory[committed_count].copy();frames=frames[-1:];segment+=1
        return True
    while time.perf_counter()<deadline:
        tick=environment.data['tick'];confirm=initial_confirm if tick==0 else fixed_confirms[tick-1] if tick<=len(fixed_confirms) else tick%2==0
        options={} if coupled else dict(previous_confirm=previous_confirm,previous_cancel=False)
        result=world._advance_with_dialogue_input_owned(environment,confirm=confirm,cancel=False,**options)
        coupled=True
        while isinstance(result,world.NeedTarget):
            environment=result.state
            if not commit(result):return None
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
        environment=result.state;frames.append(_proposal_frame(result.frame));history.extend(result.frame.target_history)
        if tick:confirms.append(confirm)
        if _chunk_ticks and len(frames)>_chunk_ticks and not isinstance(result,world.Terminal):
            if not commit(SimpleNamespace(state=environment)):return None
        if isinstance(result,world.Terminal):
            if result.reason not in ('endattack','eof_hazards_drained') or not commit():return None
            if len(word)<len(fixed_actions):return None
            if last is None:
                # An empty source or an entirely fixed word still needs a
                # terminal collision check and the same full scalar certificate.
                part=template._materialize(frames[-1:],environment,tuple(history),None,None,
                    'endattack',(),True,include_combined_geometry=False)
                resolved=SimpleNamespace(wave=part,pending_target=None,complete=True,
                    history=tuple(history),identity=b'')
                last=find_native_candidate(path,physical,width=width,seconds=max(.001,deadline-time.perf_counter()),
                    workers=workers,memory_mb=memory_mb,selection_seed=selection_seed,
                    _resolved=(template,resolved),_defer_verification=True,**settings)
                if last is None or last.status!='proposal_found':return None
                segment_stats.append(dict(last.stats))
            if observations is not None and next(observations,None) is not None:
                raise ValueError('initial_target_history contains an unused source read')
            actual=np.concatenate(trace_parts)
            verification_started=time.perf_counter()
            verified=_certify(path,initial,settings,word,actual,confirms,initial_confirm,
                previous_confirm,initial_target_history,True)
            if verified is None:return None
            base,actual_history,terminal,identity,first_tick,primed=verified
            last.scripted_damage_events=terminal.pop("scripted_damage_events",[])
            if actual_history!=tuple(history):return None
            last.status='candidate_found';last.verified=True;last.reason='verified_endattack'
            last.actions=word;last.trajectory=actual;last.reached_tick=len(word)
            last.target_history=actual_history;last.bindings=[base];last.base_target_history=base.history
            last.confirm_sequence=confirms;last.source_terminal=terminal;last.controlled_identity=identity
            last.dialogue_start_tick=first_tick;last.primed_initial_frame=primed
            _merge_segments(last,segment_stats)
            last.stats.update(backend='native-coupled-segments',route_cache=False,
                verification_seconds=time.perf_counter()-verification_started,
                retained_trace_bytes=actual.nbytes,committed_observation_segments=segment,
                observation_goal_style=_goal_style,observation_preview_ticks=_preview_ticks,observation_chunk_ticks=_chunk_ticks,observation_preview_reads=_preview_reads,
                observation_goal_retries=_goal_retries,fixed_prefix_ticks=len(fixed_actions))
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
    state=world._enable_bone_arrays(world.initialize(path,**settings),native=True);frames=[];confirms=[];coupled=False;peak_source_bodies=0
    while time.perf_counter()<deadline:
        tick=state.data['tick'];confirm=initial_confirm if tick==0 else tick%2==0
        options={} if coupled else dict(previous_confirm=previous_confirm,previous_cancel=False)
        result=world._advance_with_dialogue_input_owned(state,confirm=confirm,cancel=False,**options);coupled=True
        if isinstance(result,world.ResourceLimit):return _unknown_candidate(initial,settings,result.reason)
        if not isinstance(result,(world.TickCommitted,world.Terminal)) or result.frame is None:return None
        state=result.state;peak_source_bodies=max(peak_source_bodies,len(result.frame.white)+len(result.frame.blue));frames.append(_proposal_frame(result.frame))
        if tick:confirms.append(confirm)
        if isinstance(result,world.Terminal):
            if result.reason not in ('endattack','eof_hazards_drained'):return None
            break
    else:return None
    wave=template._materialize(frames,state,(),None,None,result.reason,(),True,include_combined_geometry=False)
    resolved=SimpleNamespace(wave=wave,history=(),identity=b'',pending_target=None,complete=True)
    frames.clear()
    source_seconds=time.perf_counter()-began;remaining=deadline-time.perf_counter()
    if remaining<=0:return None
    last=None;guided_stats=[]
    if peak_source_bodies>=256:
        bounds=wave.env_schedule[-1,:4]
        for target in ((bounds[2]-13.,(bounds[1]+bounds[3])*.5,1.,0.),
                       ((bounds[0]+bounds[2])*.5,bounds[1]+13.,0.,1.)):
            remaining=deadline-time.perf_counter()
            if remaining<=0:break
            last=find_native_candidate(path,initial,width=min(width,128),seconds=min(1.5,remaining),
                workers=workers,memory_mb=memory_mb,selection_seed=selection_seed,
                _resolved=(template,resolved),_defer_verification=True,_terminal_target=target,**settings)
            if last is not None:guided_stats.append(dict(last.stats))
            if last is not None and last.status=='proposal_found':break
    if last is None or last.status!='proposal_found':
        remaining=deadline-time.perf_counter()
        if remaining<=0:return last
        last=find_native_candidate(path,initial,width=width,seconds=remaining,workers=workers,memory_mb=memory_mb,
            selection_seed=selection_seed,_resolved=(template,resolved),_defer_verification=True,**settings)
        if last is not None:guided_stats.append(dict(last.stats))
    if last is None or last.status!='proposal_found':return last
    if guided_stats:_merge_segments(last,guided_stats)
    last.stats['static_guidance_attempts']=len(guided_stats)
    last.stats['proposal_geometry_scope']='bounded window with artificial outer walls; full source replay required'
    last.bindings=[];del resolved,wave
    verification_started=time.perf_counter()
    verified=_certify(path,initial,settings,last.actions,last.trajectory,confirms,initial_confirm,
        previous_confirm,initial_target_history,True)
    if verified is None:return None
    base,history,terminal,identity,first_tick,primed=verified
    last.scripted_damage_events=terminal.pop("scripted_damage_events",[])
    last.status='candidate_found';last.verified=True;last.reason='verified_endattack'
    last.target_history=history;last.bindings=[base];last.base_target_history=base.history
    last.confirm_sequence=confirms;last.source_terminal=terminal;last.controlled_identity=identity
    last.dialogue_start_tick=first_tick;last.primed_initial_frame=primed
    last.stats.update(backend='native-static-dialogue',actual_world_seconds=source_seconds,
        verification_seconds=time.perf_counter()-verification_started,observation_iterations=0,route_cache=False)
    return last


def find_dynamic_candidate(path,initial,*,width=3000,seconds=8.,selection_seed=42,
        workers=None,memory_mb=64,initial_confirm=False,previous_confirm=False,
        initial_target_history=None,progress=None,observation_chunk_ticks=0,
        observation_preview_ticks=0,observation_preview_reads=128,observation_goal_style=None,
        observation_goal_retries=False,fixed_prefix=None,**settings):
    for name,value in (('observation_chunk_ticks',observation_chunk_ticks),
                       ('observation_preview_ticks',observation_preview_ticks),
                       ('observation_preview_reads',observation_preview_reads)):
        if type(value) is not int or value<0:raise ValueError(name+' must be a nonnegative integer')
    if observation_goal_style is not None and (type(observation_goal_style) is not int or not 0<=observation_goal_style<=15):
        raise ValueError('observation_goal_style must be an integer in [0,15] or None')
    if type(observation_goal_retries) is not bool:raise ValueError('observation_goal_retries must be boolean')
    if seconds<=0:return None
    from .timeline_csv import parse_timeline_rows
    rows=parse_timeline_rows(path.read_text(encoding='utf-8-sig'))
    names={str(row[1]).lower().strip() for row in rows if len(row)>1}
    has_dialogue='sanstext' in names
    explicit_segments=bool(observation_chunk_ticks or observation_preview_ticks or fixed_prefix is not None)
    if not has_dialogue and 'getheartpos' not in names and not explicit_segments:return None
    started=time.perf_counter();deadline=started+seconds
    proposal=[];attempts=[];last=None;world_seconds=0.;policy_audit=[];directed_attempts=[]
    if explicit_segments:
        candidate=_segmented_coupled(path,initial,settings,width,workers,memory_mb,selection_seed,
            initial_confirm,previous_confirm,initial_target_history,deadline,
            _goal_style=observation_goal_style,_preview_ticks=observation_preview_ticks,
            _audit=policy_audit,_chunk_ticks=observation_chunk_ticks,
            _preview_reads=observation_preview_reads,_goal_retries=observation_goal_retries,
            _fixed_prefix=fixed_prefix)
        if candidate is not None:
            candidate.stats['dynamic_wall_seconds']=time.perf_counter()-started
            candidate.stats['observation_search_audit']=policy_audit
            return candidate
        return None
    if has_dialogue and 'getheartpos' not in names:
        static=_static_coupled_candidate(path,initial,settings,width,workers,memory_mb,selection_seed,
            initial_confirm,previous_confirm,initial_target_history,deadline)
        if static is not None:
            static.stats['dynamic_wall_seconds']=time.perf_counter()-started
            return static
    if not has_dialogue:
        direct=_segmented(path,initial,settings,width,workers,memory_mb,selection_seed,initial_target_history,deadline)
        if direct is not None and direct.status=='proposal_found':
            built=_world(path,initial,settings,direct.actions,initial_confirm,previous_confirm,
                initial_target_history,float('inf'))
            if built is not None and built[4]:
                _,_,actual,confirms,_,_=built
                verify_started=time.perf_counter()
                verified=_certify(path,initial,settings,direct.actions,actual,confirms,initial_confirm,
                    previous_confirm,initial_target_history,False)
                if verified is not None:
                    base,history,terminal,identity,first,primed=verified
                    direct.status='candidate_found';direct.verified=True;direct.reason='verified_endattack'
                    direct.trajectory=actual;direct.target_history=history;direct.bindings=[base]
                    direct.confirm_sequence=confirms;direct.source_terminal=terminal
                    direct.base_target_history=base.history;direct.controlled_identity=identity
                    direct.dialogue_start_tick=first;direct.primed_initial_frame=primed
                    direct.stats.update(dynamic_wall_seconds=time.perf_counter()-started,
                        verification_seconds=time.perf_counter()-verify_started)
                    return direct
    if 'getheartpos' in names:
        directed_attempts=[]
        for goal_style,preview_ticks in ((None,0),(None,60),(None,240),(1,240),(0,60),(1,60),(2,240),(3,240),(8,120),(9,120)):
            remaining=deadline-time.perf_counter()
            if remaining<=0:break
            trial_started=time.perf_counter()
            trial_deadline=min(deadline,trial_started+(max(3.,min(15.,seconds/2)) if preview_ticks>=120 else max(.5,min(2.,seconds/6))))
            segmented=_segmented_coupled(path,initial,settings,width,workers,memory_mb,selection_seed,
                initial_confirm,previous_confirm,initial_target_history,trial_deadline,_goal_style=goal_style,_preview_ticks=preview_ticks,_audit=policy_audit,_preview_reads=observation_preview_reads)
            directed_attempts.append(dict(goal_style=goal_style,preview_ticks=preview_ticks,seconds=time.perf_counter()-trial_started,
                found=segmented is not None))
            if segmented is not None:
                segmented.stats['dynamic_wall_seconds']=time.perf_counter()-started
                segmented.stats['observation_policy_attempts']=directed_attempts
                segmented.stats['observation_search_audit']=policy_audit
                for key in ('search_seconds','expanded_states','safe_transition_rows','kernel_materialization_seconds'):
                    segmented.stats[key]=sum(v[key] for v in policy_audit)
                segmented.stats['native_code']['search_cpu_seconds']=sum(v['search_cpu_seconds'] for v in policy_audit)
                segmented.stats['native_code']['search_seconds']=segmented.stats['search_seconds']
                segmented.stats['native_code']['effective_search_cores']=segmented.stats['native_code']['search_cpu_seconds']/segmented.stats['search_seconds'] if segmented.stats['search_seconds'] else 0.
                return segmented
    if not has_dialogue and last is None:
        segmented=_segmented(path,initial,settings,width,workers,memory_mb,selection_seed,initial_target_history,deadline)
        if segmented is not None:
            if segmented.status!='proposal_found':
                segmented.stats.update(observation_policy_attempts=directed_attempts,observation_search_audit=policy_audit,dynamic_wall_seconds=time.perf_counter()-started)
                return segmented
            last=segmented;proposal=last.actions
    replay_template=ParametricEnvironment(path,**settings)
    replay_setup=(replay_template,world._enable_bone_arrays(world.initialize(path,**settings),native=True),
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
                last.scripted_damage_events=terminal.pop("scripted_damage_events",[])
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
        if last.status!='proposal_found':
            last.stats.update(observation_policy_attempts=directed_attempts,observation_search_audit=policy_audit,dynamic_wall_seconds=time.perf_counter()-started)
            if policy_audit:last.stats['search_deepest_tick']=max(v['deepest_tick'] for v in policy_audit)
            return last
        proposal=last.actions
    if last is not None:
        last.status='unknown';last.verified=False;last.reason='native_observation_budget'
        last.stats['dynamic_wall_seconds']=time.perf_counter()-started
    if last is None:
        last=_unknown_candidate(initial,settings,'native_observation_budget')
        last.stats['dynamic_wall_seconds']=time.perf_counter()-started
    last.stats.update(observation_policy_attempts=directed_attempts,observation_search_audit=policy_audit)
    if policy_audit:last.stats['search_deepest_tick']=max(v['deepest_tick'] for v in policy_audit)
    return last
