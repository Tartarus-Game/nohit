"""Speculate on observed worlds; accept only actual, scalar-replayed inputs.

No observed target is borrowed from another trajectory. A rejected speculative
world only proposes a new input word; it never establishes reachability.
"""
import time
from types import SimpleNamespace
import numpy as np

from .native_candidate import find_native_candidate
from .parametric_environment import ParametricEnvironment
from .initial_target_history import bind_initial_target_history
from .source_oracle import scalar_module
from . import resumable_wave as world
from .csv_completion import wave_terminal, controlled_terminal


def _world(path, initial, settings, proposal, initial_confirm, previous_confirm,
           initial_target_history, deadline):
    template=ParametricEnvironment(path,**settings)
    state=world.initialize(path,**settings)
    player=scalar_module('discrete_operator');collision=scalar_module('joint_transition').frame_collision
    # Frame-zero coordinates are already observed after the native physics tick.
    first=bind_initial_target_history(template,initial_target_history)
    physical=player.initial_state(initial,first.wave.env_schedule[0])
    frames=[];trace=[];confirms=[];history=[];safe=True;coupled=False;word=[]
    observations=None if initial_target_history is None else iter(initial_target_history)
    while True:
        if time.perf_counter()>deadline:return None
        tick=state.data['tick'];confirm=initial_confirm if tick==0 else tick%2==0
        options={} if coupled else dict(previous_confirm=previous_confirm,previous_cancel=False)
        result=world._advance_with_dialogue_input_owned(state,confirm=confirm,cancel=False,**options);coupled=True
        while isinstance(result,world.NeedTarget):
            context=world.preview_observation_frame(result)
            if tick==0 and observations is not None:
                row=next(observations,None)
                if row is None or tuple(row[:2])!=(0,result.request['line']):
                    raise ValueError('initial_target_history omits a frame-zero source read')
                xy=row[2:]
            elif tick==0:xy=physical[:2]
            else:xy=player.sample_position(physical,context.env,context.platforms)
            supplied=world.supply_target(result,xy)
            result=world._advance_with_dialogue_input_owned(supplied,confirm=confirm,cancel=False)
        if not isinstance(result,(world.TickCommitted,world.Terminal)) or result.frame is None:return None
        state=result.state;frame=result.frame;frames.append(frame);history.extend(frame.target_history)
        if tick:
            mask=int(proposal(physical,frame.env,tick)) if callable(proposal) else int(proposal[tick-1]) if tick<=len(proposal) else 0
            word.append(mask)
            player.step_mask_into(physical,mask,frame.env,frame.platforms,physical)
            confirms.append(confirm)
        trace.append(physical.copy())
        if not np.isfinite(physical).all() or collision(frame,physical):safe=False
        if isinstance(result,world.Terminal):
            if result.reason!='endattack':return None
            break
    if observations is not None and next(observations,None) is not None:
        raise ValueError('initial_target_history contains an unused source read')
    wave=template._materialize(frames,state,tuple(history),None,None,'endattack',(),True)
    return template,SimpleNamespace(wave=wave,history=tuple(history),identity=b'',pending_target=None,complete=True),np.asarray(trace),confirms,safe,word


def _certify(path,initial,settings,actions,expected,confirms,initial_confirm,
             previous_confirm,initial_target_history,has_dialogue):
    """Original source operator replay with exact suspension-time observations."""
    if not has_dialogue:
        from .source_verification import certify_observed
        return certify_observed(path,initial,settings,actions,expected,initial_target_history)
    player=scalar_module('discrete_operator');joint=scalar_module('joint_transition')
    template=ParametricEnvironment(path,backend='resumable' if has_dialogue else 'reference',**settings)
    binding=bind_initial_target_history(template,initial_target_history)
    state=player.initial_state(initial,binding.wave.env_schedule[0]);controlled=None
    base=None;first=None;history=[];primed=False
    for tick in range(len(actions)+1):
        if controlled is None:
            while binding.pending_target is not None and binding.pending_target['tick']==tick:
                frame=binding.wave
                xy=state[:2] if tick==0 else player.sample_position(state,frame.env_schedule[tick],frame.platform_table[tick])
                binding=template.extend(binding,float(xy[0]),float(xy[1]))
            if binding.wave.termination_reason=='dialogue_boundary' and binding.resume_state.request['tick']==tick:
                base=binding;history=list(binding.history);first=max(1,tick)
                prior_confirm=previous_confirm if tick==0 else initial_confirm if tick==1 else confirms[tick-2]
                controlled=template.begin_controlled(binding,previous_input_code=int(state[4])|(32 if prior_confirm else 0))
                if tick==0:
                    primed=True
                    controlled=template.step_controlled(controlled,int(state[4])|(32 if initial_confirm else 0))
                    if controlled.frame is None or controlled.status not in ('ready','terminal'):return None
            if controlled is None:
                if tick>=len(binding.wave.env_schedule):return None
                wave=binding.wave
                frame=SimpleNamespace(env=wave.env_schedule[tick],platforms=wave.platform_table[tick],
                    white=wave.geometry_white[tick],blue=wave.geometry_blue[tick],polygons=wave.geometry_polygons[tick])
                if tick:player.step_mask_into(state,actions[tick-1],frame.env,frame.platforms,state)
                if joint.frame_collision(frame,state):return None
        if controlled is not None:
            if tick:
                edge=joint.step_joint(template,joint.JointState(tuple(state),controlled),
                    int(actions[tick-1])|(32 if confirms[tick-1] else 0))
                if edge.state is None:return None
                controlled=edge.state.environment;state=np.asarray(edge.state.player)
            elif joint.frame_collision(controlled.frame,state):return None
            if controlled.frame.tick!=tick:return None
            rows=controlled.frame.target_history
            if tick==max(0,first-1) and primed:rows=rows[len([r for r in history if r[0]==tick]):]
            elif tick==first:rows=rows[len([r for r in history if r[0]==tick]):]
            history.extend(rows)
        if state.tobytes()!=expected[tick].tobytes():return None
    if controlled is not None:
        if controlled.status!='terminal' or controlled.reason!='endattack':return None
        return base,tuple(history),controlled_terminal(controlled,template),controlled.identity,first-1,primed
    if not binding.complete or len(binding.wave.env_schedule)!=len(actions)+1:return None
    return binding,binding.history,wave_terminal(binding.wave),None,None,False


def _merge_segments(last,segment_stats):
    last.stats['segments']=segment_stats
    for key in ('expanded_states','safe_transition_rows','discarded_states','search_seconds','kernel_materialization_seconds'):
        last.stats[key]=sum(item.get(key,0) for item in segment_stats)
    last.stats['workspace_bytes']=max(item.get('workspace_bytes',0) for item in segment_stats)
    code=dict(last.stats['native_code'])
    code['compiled']=any(item.get('native_code',{}).get('compiled') for item in segment_stats)
    code['kernel_load_seconds']=last.stats['kernel_materialization_seconds']
    code['search_seconds']=last.stats['search_seconds']
    code['search_cpu_seconds']=sum(item.get('native_code',{}).get('search_cpu_seconds',0) for item in segment_stats)
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
    if not has_dialogue and last is None:
        segmented=_segmented(path,initial,settings,width,workers,memory_mb,selection_seed,initial_target_history,deadline)
        if segmented is not None:
            if segmented.status!='proposal_found':return segmented
            last=segmented;proposal=last.actions
    for iteration in range(64):
        replay_started=time.perf_counter()
        built=_world(path,initial,settings,proposal,initial_confirm,previous_confirm,initial_target_history,deadline)
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
