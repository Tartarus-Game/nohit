"""Safe, incomplete route receipts. Never an acceptance certificate or proof of UNSAT."""
import hashlib
from pathlib import Path

import numpy as np

from . import resumable_wave as world
from .source_oracle import scalar_module
from .source_verification import scalar_frame_collision
from .search_preferences import input_cost
from .timeline_csv import read_timeline_rows


def _position(state, rows, executed, tick):
    pc = state.data['pc']
    line = state.request.get('line') if state.phase.startswith('await_') and state.request else pc+1
    eof = line > len(rows)
    row = None if eof else rows[line-1]
    recent=[]
    for item in reversed(executed):
        if item['tick']!=tick:break
        recent.append(item)
    return dict(line=None if eof else line, column=2 if row and len(row)>1 else 1,
                row=row, at_eof=eof, timeline_running=bool(state.data['running']),
                last_executed=executed[-1] if executed else None,
                executed_this_tick=list(reversed(recent)),
                semantics='execution_cursor_not_proven_hazard_origin')


def replay_prefix(path, initial, settings, route, *, initial_confirm=False,
                  previous_confirm=False, initial_target_history=None, config=None):
    """Re-execute this word under its OWN real observations and dialogue inputs.

    Retain safe frames only, stopping before a collision or resource boundary.
    A speculative search-world trajectory is deliberately never trusted here.
    """
    rows=read_timeline_rows(path)
    actions=[int(mask) for mask in route.get('actions',())]
    if any(mask<0 or mask>15 for mask in actions):raise ValueError('invalid diagnostic controls')
    confirms=route.get('confirm_sequence',[False]*len(actions))
    if len(confirms)!=len(actions) or any(type(value) is not bool for value in confirms):
        raise ValueError('invalid diagnostic Confirm sequence')
    state=world._enable_bone_arrays(world.initialize(path,**settings),native=False)
    executed=[]
    state.source_observer=lambda tick,line,command:executed.append(dict(tick=tick,line=line,command=command))
    player=scalar_module('discrete_operator')
    physical=np.asarray(initial,np.float64).copy()
    observations=None if initial_target_history is None else iter(initial_target_history)
    trace=[];dt=[];history=[];elapsed=0.;last_csv=None;stop=None;coupled=False
    # One extra SOURCE frame locates the first unresolved transition. It is
    # not added to the safe route and no invented future action is simulated.
    for tick in range(len(actions)+2):
        confirm=initial_confirm if tick==0 else confirms[tick-1] if tick<=len(actions) else tick%2==0
        options={} if coupled else dict(previous_confirm=previous_confirm,previous_cancel=False)
        edge=world._advance_with_dialogue_input_owned(state,confirm=confirm,cancel=False,**options)
        coupled=True
        while isinstance(edge,world.NeedTarget):
            if tick==0 and observations is not None:
                row=next(observations,None)
                if row is None or tuple(row[:2])!=(0,edge.request['line']):
                    raise ValueError('diagnostic initial target history mismatch')
                xy=row[2:]
            elif tick==0:xy=physical[:2]
            else:xy=player.sample_position(physical,*world._observation_sampling_arrays(edge))
            state=world._supply_target_owned(edge.state,xy)
            edge=world._advance_with_dialogue_input_owned(state,confirm=confirm,cancel=False)
        state=edge.state
        csv=_position(state,rows,executed,tick)
        if not isinstance(edge,(world.TickCommitted,world.Terminal)) or edge.frame is None:
            stop=dict(tick=tick,seconds=elapsed,csv=csv,kind=getattr(edge,'reason','source_boundary'),
                      seconds_exact=False)
            break
        frame=edge.frame
        next_elapsed=elapsed+(float(frame.env[7]) if tick else 0.)
        if tick>len(actions):
            stop=dict(tick=tick,seconds=next_elapsed,csv=csv,kind=route.get('stop_kind','unsearched_transition'),
                      seconds_exact=True)
            break
        if tick==0:physical=player.initial_state(initial,frame.env)
        else:player.step_mask_into(physical,actions[tick-1],frame.env.tolist(),frame.platforms.tolist(),physical)
        if not np.isfinite(physical).all() or scalar_frame_collision(frame,physical):
            stop=dict(tick=tick,seconds=next_elapsed,csv=csv,kind='physical_collision',seconds_exact=True)
            break
        trace.append(physical.copy().tolist());dt.append(float(frame.env[7]));history.extend(frame.target_history)
        elapsed=next_elapsed;last_csv=csv
        if isinstance(edge,world.Terminal):
            stop=dict(tick=tick,seconds=elapsed,csv=csv,kind='source_terminal_without_completion_proof',seconds_exact=True)
            break
    count=max(0,len(trace)-1)
    cost=input_cost(actions[:count],int(trace[0][4]) if trace else int(initial[4]),config)
    return dict(actions=actions[:count],confirm_sequence=list(confirms[:count]),trajectory=trace,
        dt_sequence=dt,reached_tick=count,game_seconds=elapsed,input_cost=cost,
        prefix_verified=bool(trace),complete=False,original_replay_passed=False,
        target_history=[list(row) for row in history],last_safe_csv=last_csv,stop=stop)


def diagnose_failure(path, initial, settings, reason, routes=(), *, truncated=False,
                     initial_confirm=False, previous_confirm=False, initial_target_history=None, config):
    """Bounded export of deepest retained routes, independently replayed."""
    raw=list(routes) or [dict(actions=[],stop_kind=reason)]
    raw.sort(key=lambda row:-len(row.get('actions',())))
    seen=set();verified=[];steps=0;errors=[]
    for route in raw:
        key=(tuple(route.get('actions',())),tuple(route.get('confirm_sequence',())))
        if key in seen:continue
        seen.add(key)
        if len(verified)>=config['diagnostic_routes'] or (steps and steps+len(key[0])>200000):
            truncated=True;break
        steps+=len(key[0])+1
        try:
            receipt=replay_prefix(path,initial,settings,route,initial_confirm=initial_confirm,
                previous_confirm=previous_confirm,initial_target_history=initial_target_history,config=config)
        except (ValueError,RuntimeError) as exc:
            errors.append(str(exc));continue
        if receipt['trajectory'] or not verified:verified.append(receipt)
    # Deduplicate after replay too: speculative branches may hit the same
    # earlier actual source collision and reduce to the same safe word.
    unique={}
    for row in verified:
        key=(tuple(row['actions']),tuple(row['confirm_sequence']))
        unique.setdefault(key,row)
    verified=sorted(unique.values(),key=lambda row:(-row['reached_tick'],row['input_cost']['total']))
    source_hash=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    for route in verified:route['csv_sha256']=source_hash
    best=verified[0] if verified else None
    deepest=best['reached_tick'] if best else 0
    return dict(schema_version=1,reason=reason,scope='bounded_retained_search_routes',
        csv_sha256=source_hash,
        initial=np.asarray(initial,dtype=float).tolist(),
        initial_environment=None if settings.get('initial_environment') is None else np.asarray(settings['initial_environment'],dtype=float).tolist(),
        initial_arena=settings.get('initial_arena'),seed=settings.get('seed',42),
        initial_confirm=initial_confirm,previous_confirm=previous_confirm,
        initial_target_history=None if initial_target_history is None else [list(row) for row in initial_target_history],
        last_safe_tick=deepest if best and best['prefix_verified'] else None,
        last_safe_seconds=best['game_seconds'] if best and best['prefix_verified'] else None,
        failure=best['stop'] if best else None,routes=verified,route_limit=config['diagnostic_routes'],
        routes_truncated=bool(truncated),exhaustive=False,deadlock_proven=False,
        replay_errors=errors,verification_step_budget=200000)
