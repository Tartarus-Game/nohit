"""Exact per-tick scene data for a verified CSV model candidate.

Rebuild the candidate's own environment history and controlled dialogue world.
No grid, coordinate rounding, frame skipping, or native-acceptance inference is
used. Mismatched provenance or a failed physical replay rejects visualization.
"""
import hashlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from nohit.engine.discrete_operator import sample_position, step_mask_into
from nohit.engine.joint_transition import frame_collision, JointState, step_joint
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.initial_target_history import bind_initial_target_history
from nohit.engine.environment_state_key import encode_typed
from nohit.engine.csv_completion import (wave_terminal, controlled_terminal,
    clock_sequence, compose_csv_completion)


def _finite_rows(values, width):
    rows=np.asarray(values,dtype=np.float64).reshape(-1,width)
    padding=np.isnan(rows).all(axis=1)
    rows=rows[~padding]
    if not np.isfinite(rows).all():raise ValueError('nonfinite scene geometry')
    return rows


def _scene(tick, elapsed, frame, player, confirm=False):
    env=np.asarray(frame.env,dtype=np.float64)
    if env.ndim!=1 or len(env)<22 or not np.isfinite(env).all():raise ValueError('invalid environment frame')
    platforms=np.asarray(frame.platforms,dtype=np.float64).reshape(-1,9)
    platforms=platforms[platforms[:,6]!=0.]
    if not np.isfinite(platforms).all():raise ValueError('nonfinite active platform')
    return dict(tick=tick,time_seconds=elapsed,dt=float(env[7]),player=player.tolist(),
        env=env.tolist(),bounds=env[:4].tolist(),white=_finite_rows(frame.white,4).tolist(),
        blue=_finite_rows(frame.blue,4).tolist(),polygons=_finite_rows(frame.polygons,8).tolist(),
        platforms=platforms.tolist(),confirm=bool(confirm))


def _wave_frame(wave,tick):
    return SimpleNamespace(env=wave.env_schedule[tick],platforms=wave.platform_table[tick],
        white=_finite_rows(wave.geometry_white[tick],4),blue=_finite_rows(wave.geometry_blue[tick],4),
        polygons=_finite_rows(wave.geometry_polygons[tick],8))


def build_csv_visualization(path, result, *, initial_environment=None, initial_arena=None, dt_schedule=None,
                            clock_start_ms=None, seed=None, max_ticks=None, termination_policy=None):
    """Return JSON-ready exact scenes; reject unverified or mismatched inputs.

    Supply the same initial environment and full explicit dt schedule used by
    ``solve_csv``. Seed and resource clock length default to its recorded values.
    A native timestamp clock may be recovered from its recorded start timestamp.
    The returned native-replay flag remains false: this function verifies the
    declared source model only. Dialogue frames include all moving hazards.
    """
    if result.get('status')!='candidate_found' or result.get('verified') is not True:
        raise ValueError('verified candidate required')
    path=Path(path);source_hash=hashlib.sha256(path.read_bytes()).hexdigest()
    if source_hash!=result.get('csv_sha256'):raise ValueError('CSV identity mismatch')
    expected_identity=result.get('environment_binding_identity')
    if not isinstance(expected_identity,str) or not expected_identity:
        raise ValueError('environment binding identity required')
    actions=result.get('actions');confirms=result.get('confirm_sequence')
    if not isinstance(actions,(list,tuple)) or any(type(mask) is not int or not 0<=mask<16 for mask in actions):
        raise ValueError('arrow action sequence required')
    if not isinstance(confirms,(list,tuple)) or len(confirms)!=len(actions) or any(type(value) is not bool for value in confirms):
        raise ValueError('one boolean Confirm value per action required')
    n=len(actions);trace=np.asarray(result.get('trajectory'),dtype=np.float64)
    if trace.shape!=(n+1,11) or not np.isfinite(trace).all():raise ValueError('trajectory tick count mismatch')
    if result.get('reached_tick')!=n:raise ValueError('terminal tick mismatch')
    completion=result.get('completion')
    if not isinstance(completion,dict) or completion.get('kind') not in ('endattack','eof_invariant'):
        raise ValueError('explicit completion kind required')
    if completion.get('tick')!=n:raise ValueError('completion tick mismatch')
    eof=completion['kind']=='eof_invariant'
    drain=completion.get('drain_tick') if eof else n
    if type(drain) is not int or not 0<=drain<=n:raise ValueError('invalid source terminal tick')
    expected_dt=np.asarray(result.get('dt_sequence'),dtype=np.float64)
    if expected_dt.shape!=(n+1,) or not np.isfinite(expected_dt).all() or np.any(expected_dt<=0.):
        raise ValueError('complete positive per-tick clock required')
    if 'unified_controls' in result and result['unified_controls']!=[mask|(32 if confirm else 0) for mask,confirm in zip(actions,confirms)]:
        raise ValueError('unified control mismatch')
    clock=result.get('clock',{});protocol=clock.get('protocol')
    if protocol=='explicit_dt_schedule' and dt_schedule is None:
        raise ValueError('full explicit dt_schedule required')
    if protocol=='native_fixed_240' and clock_start_ms is None:clock_start_ms=result.get('clock_start_ms')
    actual_protocol='explicit_dt_schedule' if dt_schedule is not None else 'native_fixed_240' if clock_start_ms is not None else 'nominal_240'
    if actual_protocol!=protocol:raise ValueError('clock protocol mismatch')
    seed=result.get('seed',42) if seed is None else seed
    max_ticks=result.get('max_ticks',40000) if max_ticks is None else max_ticks
    initial_arena=result.get('initial_arena') if initial_arena is None else initial_arena
    policy=result.get('termination_policy','endattack')
    if termination_policy is not None and termination_policy!=policy:
        raise ValueError('termination policy mismatch')
    if eof and policy!='eof_hazards_drained':raise ValueError('EOF policy required')
    template=ParametricEnvironment(path,seed=seed,initial_environment=initial_environment,
        initial_arena=initial_arena,
        dt_schedule=dt_schedule,clock_start_ms=clock_start_ms,max_ticks=max_ticks,termination_policy=policy)
    if clock_sequence(template)[:n+1].tobytes()!=expected_dt.tobytes():
        raise ValueError('candidate dt is not the exact full-clock prefix')
    if template.dt_schedule is not None:
        digest=hashlib.sha256(np.asarray(template.dt_schedule,dtype='<f8').tobytes()).hexdigest()
        if clock.get('schedule_count')!=len(template.dt_schedule) or clock.get('schedule_sha256')!=digest:
            raise ValueError('full clock identity mismatch')
    history=tuple(tuple(row) for row in result.get('target_history',()))
    provenance=result.get('environment_provenance')
    controlled_identity=result.get('controlled_environment_binding_identity')
    base_history=history
    if provenance is not None or controlled_identity is not None:
        if (not isinstance(provenance,dict) or provenance.get('kind')!='controlled' or
                provenance.get('base_binding_identity')!=expected_identity or
                not isinstance(controlled_identity,str) or not controlled_identity or
                provenance.get('final_binding_identity')!=controlled_identity or
                not isinstance(provenance.get('base_target_history'),(list,tuple))):
            raise ValueError('controlled environment provenance mismatch')
        base_history=tuple(tuple(row) for row in provenance['base_target_history'])
        if encode_typed(history[:len(base_history)])!=encode_typed(base_history):
            raise ValueError('controlled target history prefix mismatch')
    final_binding=template.bind(base_history)
    if final_binding.identity.hex()!=expected_identity:raise ValueError('environment binding identity mismatch')
    wave=final_binding.wave
    primed=result.get('primed_initial_frame') is True
    controlled=None
    replay_history=list(base_history)
    first_controlled_frame=True
    def append_targets(frame):
        nonlocal first_controlled_frame
        rows=tuple(frame.target_history)
        if first_controlled_frame:
            already=tuple(row for row in base_history if row[0]==frame.tick)
            if encode_typed(rows[:len(already)])!=encode_typed(already):
                raise ValueError('controlled frame target prefix mismatch')
            rows=rows[len(already):]
            first_controlled_frame=False
        replay_history.extend(rows)
    if wave.termination_reason=='dialogue_boundary':
        first=int(final_binding.resume_state.request['tick'])
        if first==0 and primed:
            initial_control=result.get('initial_frame_control')
            expected_control=int(trace[0,4])|(32 if result.get('initial_confirm') else 0)
            if initial_control!=expected_control:raise ValueError('initial control mismatch')
            controlled=template.begin_controlled(final_binding,
                previous_input_code=int(trace[0,4])|(32 if result.get('previous_confirm') else 0))
            controlled=template.step_controlled(controlled,initial_control)
            if controlled.status not in ('ready','terminal') or controlled.frame is None or controlled.frame.tick!=0:
                raise ValueError('unresolved initial world frame')
            append_targets(controlled.frame)
            first=1
        elif first<1 or primed:raise ValueError('unsupported initial tick alignment')
        if result.get('dialogue_start_tick')!=first-1:raise ValueError('dialogue boundary mismatch')
        prefix_last=first-1
    elif wave.complete and wave.termination_reason==('eof_hazards_drained' if eof else 'endattack'):
        first=None;prefix_last=drain
        if len(wave.env_schedule)!=drain+1:raise ValueError('source terminal tick count mismatch')
    else:raise ValueError('unsupported terminal boundary')
    if prefix_last>n:raise ValueError('candidate stops before dialogue boundary')
    scenes=[];elapsed=0.;state=trace[0].copy()
    current=bind_initial_target_history(template,result.get('initial_target_history'))
    for tick in range(prefix_last+1):
        if current.pending_target is not None and current.pending_target['tick']==tick:
            w=current.wave
            x,y=state[:2] if tick==0 else sample_position(state,w.env_schedule[tick],w.platform_table[tick])
            while current.pending_target is not None and current.pending_target['tick']==tick:
                current=template.extend(current,float(x),float(y))
        if tick>=len(current.wave.env_schedule):raise ValueError('unresolved prefix boundary')
        frame=controlled.frame if primed and tick==0 else _wave_frame(current.wave,tick)
        if tick:
            step_mask_into(state,actions[tick-1],frame.env,frame.platforms,state)
            elapsed+=float(frame.env[7])
        if state.tobytes()!=trace[tick].tobytes() or frame_collision(frame,state):
            raise ValueError('candidate prefix replay mismatch or collision')
        scenes.append(_scene(tick,elapsed,frame,state,confirms[tick-1] if tick else result.get('initial_confirm',False)))
    # GetHeartPos can run immediately before SansText on the next, still
    # uncommitted tick. Validate its sample without advancing the player or
    # consuming the first dialogue control.
    if first is not None and prefix_last+1==first and current.pending_target is not None and current.pending_target['tick']==first:
        w=current.wave
        x,y=sample_position(state,w.env_schedule[first],w.platform_table[first])
        while current.pending_target is not None and current.pending_target['tick']==first:
            current=template.extend(current,float(x),float(y))
    if current.identity!=final_binding.identity:raise ValueError('target history does not match player samples')
    if first is not None:
        previous_confirm=confirms[first-2] if first>=2 else False
        if not primed:
            controlled=template.begin_controlled(final_binding,
                previous_input_code=int(state[4])|(32 if previous_confirm else 0))
        for tick in range(first,drain+1):
            control=actions[tick-1]|(32 if confirms[tick-1] else 0)
            edge=step_joint(template,JointState(tuple(state),controlled),control)
            if edge.state is None or edge.status not in ('ready','terminal'):
                raise ValueError('unresolved controlled environment boundary')
            controlled=edge.state.environment
            if controlled.frame.tick!=tick:raise ValueError('controlled clock discontinuity')
            frame=controlled.frame
            append_targets(frame)
            state=np.asarray(edge.state.player,dtype=np.float64)
            if state.tobytes()!=trace[tick].tobytes():
                raise ValueError('candidate dialogue replay mismatch or collision')
            elapsed+=float(frame.env[7]);scenes.append(_scene(tick,elapsed,frame,state,confirms[tick-1]))
            if controlled.status=='terminal' and tick!=drain:raise ValueError('actions continue after source terminal')
        if controlled.status!='terminal' or controlled.reason!=('eof_hazards_drained' if eof else 'endattack'):
            raise ValueError('candidate has no real model '+('EOF' if eof else 'EndAttack'))
        if encode_typed(tuple(replay_history))!=encode_typed(history):
            raise ValueError('controlled target history does not match player samples')
        if controlled_identity is not None and controlled.identity.hex()!=controlled_identity:
            raise ValueError('controlled environment identity mismatch')
        terminal=controlled_terminal(controlled,template)
    else:
        if provenance is not None:raise ValueError('controlled provenance on ordinary wave')
        terminal=wave_terminal(wave)
    if 'source_terminal' in result:
        reported=result['source_terminal']
        rebuilt_terminal=dict(terminal,environment=np.asarray(terminal['environment']).tolist())
        if encode_typed(reported)!=encode_typed(rebuilt_terminal):
            raise ValueError('source terminal does not match the replayed world')
    rebuilt=compose_csv_completion(actions[:drain],confirms[:drain],trace[:drain+1],
                                   terminal,clock_sequence(template),max_ticks)
    if (rebuilt['status']!='proven' or rebuilt['actions']!=actions or
            rebuilt['confirm_sequence']!=confirms or
            np.asarray(rebuilt['trajectory']).tobytes()!=trace.tobytes() or
            rebuilt['completion']!=completion):
        raise ValueError('completion certificate or release execution mismatch')
    if eof:
        static=np.asarray(rebuilt['completion']['certificate']['static_environment']).copy()
        for tick in range(drain+1,n+1):
            static[7]=expected_dt[tick]
            frame=SimpleNamespace(env=static.copy(),platforms=np.empty((0,9)),
                white=np.empty((0,4)),blue=np.empty((0,4)),polygons=np.empty((0,8)))
            step_mask_into(state,actions[tick-1],frame.env,frame.platforms,state)
            if state.tobytes()!=trace[tick].tobytes():raise ValueError('EOF release replay mismatch')
            elapsed+=float(frame.env[7]);scenes.append(_scene(tick,elapsed,frame,state,confirms[tick-1]))
    if len(scenes)!=n+1:raise ValueError('scene tick count mismatch')
    if np.asarray([frame['dt'] for frame in scenes]).tobytes()!=expected_dt.tobytes():
        raise ValueError('per-tick dt mismatch')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=source_hash:raise ValueError('CSV changed during scene rebuild')
    return dict(schema_version=1,frame_count=len(scenes),scope='verified_source_model',
        csv_sha256=source_hash,environment_binding_identity=expected_identity,
        original_replay_passed=False,complete_in_original_game=False,end_reason=completion['kind'],frames=scenes)
