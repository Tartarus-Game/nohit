"""Route-conditioned execution metrics, not a proof of human feasibility.

Timing probes rerun the source with their OWN observations. A surviving local
probe certifies only that tested prefix; it says nothing about its later suffix.
"""
import math
import time
import numpy as np
from . import resumable_wave as world
from .source_oracle import scalar_module
from .source_verification import scalar_frame_collision
from .native_backend import frame_clearance
from .failure_diagnostics import _position
from .timeline_csv import read_timeline_rows


def _tick(state,physical,tick,mask,confirm,initial,previous_confirm,initial_history=None):
    player=scalar_module('discrete_operator')
    options={} if state.dialogue_coupled else dict(previous_confirm=previous_confirm,previous_cancel=False)
    edge=world._advance_with_dialogue_input_owned(state,confirm=confirm,cancel=False,**options)
    observations=iter(initial_history or ()) if tick==0 else None
    while isinstance(edge,world.NeedTarget):
        if tick==0 and initial_history is not None:
            row=next(observations,None)
            if row is None or tuple(row[:2])!=(0,edge.request['line']):raise ValueError('analysis initial target mismatch')
            xy=row[2:]
        elif tick==0:xy=physical[:2]
        else:xy=player.sample_position(physical,*world._observation_sampling_arrays(edge))
        state=world._supply_target_owned(edge.state,xy)
        edge=world._advance_with_dialogue_input_owned(state,confirm=confirm,cancel=False)
    if not isinstance(edge,(world.TickCommitted,world.Terminal)) or edge.frame is None:
        return edge,None,physical
    frame=edge.frame
    if tick==0:physical=player.initial_state(initial,frame.env)
    else:player.step_mask_into(physical,mask,frame.env.tolist(),frame.platforms.tolist(),physical)
    return edge,frame,physical


def _walk(path,initial,settings,result,observer=None):
    state=world._enable_bone_arrays(world.initialize(path,**settings),native=False)
    if observer is not None:state.source_observer=observer
    physical=np.asarray(initial,np.float64).copy()
    for tick in range(len(result['actions'])+1):
        confirm=result['initial_confirm'] if tick==0 else result['confirm_sequence'][tick-1]
        edge,frame,physical=_tick(state,physical,tick,0 if tick==0 else result['actions'][tick-1],
            confirm,initial,result['previous_confirm'],result.get('initial_target_history'))
        state=edge.state
        if frame is None:break
        expected=np.asarray(result['trajectory'][tick],np.float64)
        if frame.tick!=tick or physical.tobytes()!=expected.tobytes():raise ValueError('analysis route/source mismatch')
        yield state,physical,frame
        if isinstance(edge,world.Terminal):break


def _events(actions,confirms,previous):
    events=[];last=previous
    for i,mask in enumerate(actions):
        if mask!=last:events.append(dict(tick=i+1,kind='arrows',before=last,after=mask))
        last=mask
    # Shift an entire Confirm pulse, rather than erasing a one-tick press by
    # moving its rising edge past its unchanged release edge.
    for i,value in enumerate(confirms):
        if value and (i==0 or not confirms[i-1]):
            end=i+1
            while end<len(confirms) and confirms[end]:end+=1
            events.append(dict(tick=i+1,kind='confirm',end_tick=end+1))
    return sorted(events,key=lambda e:(e['tick'],e['kind']))


def _probe(checkpoint,event,shift,result,initial,stop,rows,prior_csv):
    state,physical=checkpoint[0].clone(),checkpoint[1].copy()
    # Branch probes must not mutate the main replay's CSV cursor observer.
    executed=[] if prior_csv.get('last_executed') is None else [prior_csv['last_executed']]
    state.source_observer=lambda tick,line,command:executed.append(dict(tick=tick,line=line,command=command))
    begin=event['tick'];kind=event['kind']
    for tick in range(state.data['tick'],stop+1):
        if tick==0:raise ValueError('timing probe cannot change the observed frame-zero input')
        mask=result['actions'][tick-1];confirm=result['confirm_sequence'][tick-1]
        if kind=='arrows':
            if shift>0 and begin<=tick<begin+shift:mask=event['before']
            elif shift<0 and begin+shift<=tick<begin:mask=event['after']
        else:
            end=event['end_tick']
            if begin<=tick<end:confirm=False
            if begin+shift<=tick<end+shift:confirm=True
        edge,frame,physical=_tick(state,physical,tick,mask,confirm,initial,result['previous_confirm'])
        state=edge.state
        if frame is None:return dict(status='unknown',reason=getattr(edge,'reason','source_boundary'),tick=tick,
            csv=_position(state,rows,executed,tick))
        if not np.isfinite(physical).all() or scalar_frame_collision(frame,physical):
            return dict(status='collision',tick=tick,csv=_position(state,rows,executed,tick))
        if isinstance(edge,world.Terminal):return dict(status='survived_local_prefix',through_tick=tick)
    return dict(status='survived_local_prefix',through_tick=stop)


def analyze_route(path,initial,settings,result,*,event_limit=24,horizon_seconds=.5,shift_ticks=4,probe_budget_seconds=5.):
    if type(event_limit) is not int or not 0<=event_limit<=256:raise ValueError('invalid timing event limit')
    if type(shift_ticks) is not int or not 1<=shift_ticks<=16:raise ValueError('invalid timing shift limit')
    if not math.isfinite(horizon_seconds) or horizon_seconds<=0:raise ValueError('invalid probe horizon')
    if not math.isfinite(probe_budget_seconds) or probe_budget_seconds<0:raise ValueError('invalid probe budget')
    if not result.get('verified'):return dict(status='unavailable',reason='no_verified_complete_route')
    began=time.perf_counter();rows=read_timeline_rows(path);executed=[];samples=[];effective_confirms=[]
    elapsed=0.
    def observe(tick,line,command):executed.append(dict(tick=tick,line=line,command=command))
    for state,physical,frame in _walk(path,initial,settings,result,observe):
        if frame.tick:elapsed+=float(frame.env[7])
        clearance,kind,index,locked=frame_clearance(frame,physical)
        if (frame.tick and result['confirm_sequence'][frame.tick-1] and frame.dialogue and frame.dialogue.interactive
                and any(e.get('kind')=='dialogue_destroyed' for e in frame.callback_events)):
            effective_confirms.append(frame.tick)
        samples.append(dict(tick=frame.tick,seconds=elapsed,
            clearance_px=float(clearance) if math.isfinite(clearance) else None,
            hazard_kind=('white','moving_blue','polygon')[int(kind)] if kind>=0 else None,
            hazard_index=int(index) if index>=0 else None,blue_motion_lock=bool(locked),
            csv=_position(state,rows,executed,frame.tick)))
    if not samples:raise ValueError('analysis could not replay the verified route')
    n=len(samples)-1;dt=result['dt_sequence'];times=np.cumsum([0.]+list(dt[1:]))
    events=_events(result['actions'],result['confirm_sequence'],int(result['trajectory'][0][4]))
    valid_events=[e for e in events if 1<=e['tick']<=n]
    def risk(event):
        t=event['tick'];near=samples[max(0,t-4):min(n,t+12)+1]
        margin=min((s['clearance_px'] for s in near if s['clearance_px'] is not None),default=64.)
        if any(s['blue_motion_lock'] for s in near):margin=min(margin,0.)
        return margin,event['tick'],event['kind']
    ranked=sorted(valid_events,key=risk);chosen=[]
    # Avoid spending every probe on adjacent changes in the same difficult
    # second. Reserve part of the bounded sample for the rest of the attack.
    for event in ranked:
        if len(chosen)>=event_limit*2//3:break
        if not any(e['kind']==event['kind'] and abs(times[e['tick']]-times[event['tick']])<.5 for e in chosen):chosen.append(event)
    if event_limit:
        strata=np.linspace(0,n+1,event_limit+1)
        for left,right in zip(strata[:-1],strata[1:]):
            bucket=[e for e in ranked if left<=e['tick']<right and e not in chosen]
            if bucket and len(chosen)<event_limit:chosen.append(bucket[0])
        for event in ranked:
            if len(chosen)>=event_limit:break
            if event not in chosen:chosen.append(event)
    else:chosen=[]
    starts={max(0,e['tick']-shift_ticks-1) for e in chosen};checkpoints={}
    if starts:
        for state,physical,frame in _walk(path,initial,settings,result):
            if frame.tick in starts:checkpoints[frame.tick]=(state.clone(),physical.copy())
            if len(checkpoints)==len(starts):break
    timing=[];deadline=time.perf_counter()+probe_budget_seconds;truncated=False
    arrow_ticks=[e['tick'] for e in valid_events if e['kind']=='arrows']
    for event in chosen:
        if time.perf_counter()>=deadline:truncated=True;break
        tick=event['tick'];checkpoint=checkpoints[max(0,tick-shift_ticks-1)]
        stop=min(n,tick+240,int(np.searchsorted(times,times[tick]+horizon_seconds)))
        neighbors=[t for t in arrow_ticks if t!=tick] if event['kind']=='arrows' else []
        low=max([0]+[t for t in neighbors if t<tick]);high=min([n+1]+[t for t in neighbors if t>tick])
        probes=[]
        for direction in (-1,1):
            for amount in range(1,shift_ticks+1):
                shift=direction*amount
                if time.perf_counter()>=deadline:truncated=True;break
                if tick+shift<1 or not low<tick+shift<high:
                    probes.append(dict(shift_ticks=shift,status='not_tested',reason='input_boundary_or_neighbor'));continue
                outcome=_probe(checkpoint,event,shift,result,initial,stop,rows,
                    samples[max(0,tick-shift_ticks-1)]['csv'])
                if 'tick' in outcome:outcome['seconds']=float(times[outcome['tick']])
                probes.append(dict(shift_ticks=shift,shift_ms=float((times[tick+shift]-times[tick])*1000),**outcome))
        indexed={p['shift_ticks']:p for p in probes}
        def contiguous(direction):
            count=0
            for amount in range(1,shift_ticks+1):
                if indexed.get(direction*amount,{}).get('status')!='survived_local_prefix':break
                count=amount
            return count
        early,late=contiguous(-1),contiguous(1)
        exact=all(indexed.get(d,{}).get('status')=='collision' for d in (-1,1))
        timing.append(dict(event,seconds=float(times[tick]),csv=samples[tick]['csv'],
            early_safe_ticks_tested=early,late_safe_ticks_tested=late,
            early_safe_ms_tested=float((times[tick]-times[tick-early])*1000),
            late_safe_ms_tested=float((times[tick+late]-times[tick])*1000),
            frame_exact_locally=exact,probes=probes))
    finite=[s for s in samples if s['clearance_px'] is not None]
    min_margin=min((s['clearance_px'] for s in finite),default=None)
    hard=[]
    for sample in sorted(finite,key=lambda s:(s['clearance_px'],s['tick'])):
        if any(abs(sample['seconds']-s['seconds'])<.5 for s in hard):continue
        hard.append(sample)
        if len(hard)>=10:break
    times_events=[float(times[e['tick']]) for e in valid_events];left=0;peak=0
    for right,stamp in enumerate(times_events):
        while stamp-times_events[left]>1.:left+=1
        peak=max(peak,right-left+1)
    runs=[];last=0
    for event in valid_events:
        if event['kind']=='arrows':
            if event['tick']>last:runs.append(float(times[event['tick']]-times[last]))
            last=event['tick']
    exact_count=sum(t['frame_exact_locally'] for t in timing)
    arrows=result['actions'];previous=int(result['trajectory'][0][4])
    key_edges=sum((mask^(arrows[i-1] if i else previous)).bit_count() for i,mask in enumerate(arrows))
    opposed=sum((mask&3)==3 or (mask&12)==12 for mask in arrows)
    one_side=sum(any(p['status']=='collision' and abs(p['shift_ticks'])==1 for p in t['probes']) for t in timing)
    spatial=0 if min_margin is None else 40 if min_margin<=.5 else 32 if min_margin<=3 else 22 if min_margin<=6 else 10 if min_margin<=12 else 0
    precision_while_moving=any(s['clearance_px'] is not None and s['clearance_px']<=3 and
        (result['trajectory'][s['tick']][2]!=0. or result['trajectory'][s['tick']][3]!=0.) for s in samples)
    if not precision_while_moving:spatial=min(spatial,12)
    score=min(100,spatial+(32 if exact_count else 24 if one_side else 0)+min(20,peak*2))
    if precision_while_moving:score=max(score,70)
    if exact_count:score=max(score,90)
    label='极限' if score>=80 else '高难' if score>=60 else '困难' if score>=40 else '一般' if score>=20 else '宽松'
    flags=[]
    if min_margin is not None and min_margin<=3:flags.append('路线存在不超过 3px 的单侧空间余量')
    if exact_count:flags.append('抽测中存在提前或延后一 tick 均碰撞的操作')
    if one_side and not exact_count:flags.append('抽测中存在提前或延后一 tick 即碰撞的操作')
    if peak>=8:flags.append('路线存在一秒内至少八次输入事件')
    if opposed:flags.append('路线包含同时按住相反方向的组合')
    demanding=precision_while_moving or exact_count or one_side or peak>=8 or opposed>0
    informative=not valid_events or (timing and not truncated and all(any(p['status']=='survived_local_prefix' for p in t['probes']) for t in timing))
    hypothesis='manual_play_extremely_demanding' if demanding else 'manual_play_plausible_in_tested_windows' if informative else 'uncertain'
    locked_windows=[]
    for sample in samples:
        if not sample['blue_motion_lock']:continue
        if locked_windows and locked_windows[-1]['end_tick']==sample['tick']-1:
            locked_windows[-1].update(end_tick=sample['tick'],end_seconds=sample['seconds'])
        else:locked_windows.append(dict(start_tick=sample['tick'],end_tick=sample['tick'],
            start_seconds=sample['seconds'],end_seconds=sample['seconds'],csv=sample['csv']))
    return dict(schema_version=1,status='analyzed',scope='this_verified_route_only',
        score=score,label=label,score_kind='heuristic_v1_not_empirically_calibrated',
        minimum_clearance_px=min_margin,clearance_definition='additional L-infinity expansion per side of the 4x4 hitbox; sampled ticks, current blue activation',
        hard_points=hard,timing_events=sorted(timing,key=lambda t:(not t['frame_exact_locally'],min(t['early_safe_ticks_tested'],t['late_safe_ticks_tested']),t['tick'])),
        operations=dict(arrow_changes=sum(e['kind']=='arrows' for e in events),confirm_presses=sum(e['kind']=='confirm' for e in events),
            individual_arrow_key_transitions=key_edges,max_simultaneous_arrows=max((m.bit_count() for m in arrows),default=0),
            opposed_direction_frames=opposed,
            effective_dialogue_confirms=len(effective_confirms),
            redundant_confirm_presses=max(0,sum(e['kind']=='confirm' for e in events)-len(effective_confirms)),
            peak_events_per_second=peak,shortest_arrow_run_ms=min(runs)*1000 if runs else None),
        blue_motion_lock_ticks=sum(s['blue_motion_lock'] for s in samples),
        blue_motion_lock_windows=locked_windows[:20],
        timing_coverage=dict(total_events=len(events),tested_events=len(timing),event_limit=event_limit,truncated=truncated or len(timing)<len(valid_events),
            requested_horizon_seconds=horizon_seconds,max_horizon_ticks=240,max_shift_ticks=shift_ticks,
            selection='spatial risk with time separation, then temporal strata',
            scope='local_prefix_only; each probe reexecutes source and its own GetHeartPos',full_suffix_verified=False),
        human_feasibility=dict(estimate=hypothesis,flags=flags,actual_human_clear_verified=False,
            probability=None,impossibility_proven=False,alternative_easier_route_may_exist=True),
        coverage=dict(source_ticks=len(samples),route_ticks=len(result['actions'])+1,release_tail_excluded=len(result['actions'])-n),
        analysis_seconds=time.perf_counter()-began,
        limitations=['Spatial clearance is instantaneous, not a guarantee under velocity/input errors.',
            'Only selected input events and bounded local timing shifts were tested.',
            'A hard found route does not prove the attack is humanly impossible.'])
