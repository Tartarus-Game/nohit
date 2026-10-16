"""Fast CSV candidate discovery with independently verified dialogue completion.

This is an existential candidate path. Width limits and fixed Confirm choices
make failure unknown; every accepted route is independently replayed.
"""
import hashlib
from pathlib import Path
import time

import numpy as np

from .source_contract import model_issues
from .parametric_environment import ParametricEnvironment
from .initial_target_history import normalize_initial_target_history
from .compact_wave import normalize_initial_arena
from .csv_completion import (AUDITED_NO_ACTION_COMMANDS, NO_ACTION_SOURCE_AUDIT,
    wave_terminal, clock_sequence, compose_csv_completion)


def solve_csv(path, initial, *, initial_environment=None, initial_arena=None, dt_schedule=None, clock_start_ms=None,
              width=3000, seconds=30., max_ticks=40000, seed=42,
              selection_seed=42,
              initial_confirm=False, previous_confirm=False, initial_target_history=None,
              termination_policy='endattack', progress=None, search_strategy='auto', workers=None, memory_mb=64,
              allow_scripted_healing=False,allow_scripted_damage=False,
              observation_chunk_ticks=0, observation_preview_ticks=0, observation_preview_reads=128,
              observation_goal_style=None, observation_goal_retries=False, fixed_prefix=None):
    """Return a verified source-model candidate, or an explicit unknown result.

Inputs use arrows only. Confirm is emitted separately for every physical tick.
The caller must execute both sequences under the returned clock. Original-game
acceptance and optimality are never inferred from the mathematical replay.
``seconds`` bounds candidate search; compilation, world preparation and
mandatory verification are included separately in the returned wall time.
``initial_target_history`` is an optional complete list of actual tick-zero
GetHeartPos reads, [0, source_line, x, y]. These samples can precede a late arena
clamp and differ from ``initial``. Future samples must not be supplied here.
``observation_chunk_ticks`` and ``observation_preview_ticks`` enable short
committed segments with speculative guidance; 480/480 and 128 preview reads
are useful starting points for long input-dependent CSVs. ``fixed_prefix``
locks a same-source input/trajectory prefix. Final scalar verification checks
that entire prefix again before any complete candidate is returned.
"""
    for name,value in (('observation_chunk_ticks',observation_chunk_ticks),
                       ('observation_preview_ticks',observation_preview_ticks),
                       ('observation_preview_reads',observation_preview_reads)):
        if type(value) is not int or value<0:raise ValueError(name+' must be a nonnegative integer')
    if observation_goal_style is not None and (type(observation_goal_style) is not int or not 0<=observation_goal_style<=15):
        raise ValueError('observation_goal_style must be an integer in [0,15] or None')
    if type(observation_goal_retries) is not bool:raise ValueError('observation_goal_retries must be boolean')
    if fixed_prefix is not None and not isinstance(fixed_prefix,dict):raise ValueError('fixed_prefix must be a witness object')
    if search_strategy not in ('auto','native'):
        raise ValueError('invalid search_strategy')
    if type(allow_scripted_healing) is not bool:
        raise ValueError('allow_scripted_healing must be boolean')
    if type(allow_scripted_damage) is not bool:
        raise ValueError('allow_scripted_damage must be boolean')
    if type(initial_confirm) is not bool or type(previous_confirm) is not bool:
        raise ValueError('initial_confirm and previous_confirm must be boolean')
    if termination_policy not in ('endattack','eof_hazards_drained'):
        raise ValueError('invalid termination_policy')
    initial_target_history=normalize_initial_target_history(initial_target_history)
    initial_arena=normalize_initial_arena(initial_arena)
    began=time.perf_counter();path=Path(path)
    result=dict(status='unknown',planner='native-csv',wave=path.name,
        csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),actions=[],confirm_sequence=[],
        seed=int(seed)&0xffffffff,max_ticks=max_ticks,
        initial_target_history=None if initial_target_history is None else [list(row) for row in initial_target_history],
        initial_arena=initial_arena,
        initial_confirm=initial_confirm,previous_confirm=previous_confirm,
        trajectory=[],control_ticks=1,action_format='keymask-lrud-cancel',
        search_complete=False,search_limited=True,deadlock_proven=False,optimality_proven=False,
        original_replay_passed=False,complete_in_original_game=False,verified=False)
    result['termination_policy']=termination_policy
    result['no_action_source_audit']=NO_ACTION_SOURCE_AUDIT
    result['health_model']='scripted_damage_native_replay_required' if allow_scripted_damage else 'native_replay_required' if allow_scripted_healing else 'no_scripted_healing_admitted'
    issues=[issue for issue in model_issues(path,allow_player_history=True,termination_policy=termination_policy,
                                          allow_scripted_healing=allow_scripted_healing,allow_scripted_damage=allow_scripted_damage)
            if not (issue.get('reason')=='mechanism_not_validated' and
                    issue.get('command','').strip().lower() in AUDITED_NO_ACTION_COMMANDS)]
    if issues:return dict(result,reason='unsupported_mechanism',issues=issues)
    settings=dict(seed=seed,initial_environment=initial_environment,initial_arena=initial_arena,dt_schedule=dt_schedule,
                  clock_start_ms=clock_start_ms,max_ticks=max_ticks,termination_policy=termination_policy)
    clock=ParametricEnvironment(path,**settings)
    if dt_schedule is not None:settings['dt_schedule']=clock.dt_schedule
    sequence=clock.dt_schedule
    hz=240 if sequence is None else 1./sequence[0] if all(dt==sequence[0] for dt in sequence) else None
    protocol='explicit_dt_schedule' if dt_schedule is not None else 'native_fixed_240' if clock_start_ms is not None else 'nominal_240'
    result.update(physics_hz=hz,control_hz=hz,clock_protocol=protocol,clock_start_ms=clock_start_ms,
                  clock=dict(protocol=protocol,decision_ticks=1,original_replay_passed=False))
    if sequence is not None:
        result['clock'].update(schedule_count=len(sequence),
            schedule_sha256=hashlib.sha256(np.asarray(sequence,dtype='<f8').tobytes()).hexdigest())
    if progress is not None:progress(phase='search')
    frontier=None
    from .native_candidate import find_native_candidate
    from .native_dynamic import find_dynamic_candidate
    try:
        if fixed_prefix is None and not (observation_chunk_ticks or observation_preview_ticks):
            frontier=find_native_candidate(path,initial,**settings,width=width,seconds=seconds,
                selection_seed=selection_seed,workers=workers,memory_mb=memory_mb,
                initial_target_history=initial_target_history,progress=progress)
        if frontier is None:
            frontier=find_dynamic_candidate(path,initial,**settings,width=width,seconds=seconds,
                selection_seed=selection_seed,workers=workers,memory_mb=memory_mb,
                initial_target_history=initial_target_history,initial_confirm=initial_confirm,
                previous_confirm=previous_confirm,progress=progress,
                observation_chunk_ticks=observation_chunk_ticks,
                observation_preview_ticks=observation_preview_ticks,
                observation_preview_reads=observation_preview_reads,
                observation_goal_style=observation_goal_style,
                observation_goal_retries=observation_goal_retries,fixed_prefix=fixed_prefix)
    except (OSError,RuntimeError) as exc:
        if search_strategy=='native':raise
        return dict(result,reason='native_backend_unavailable',native_error=str(exc),
                    search_strategy=search_strategy,wall_seconds=time.perf_counter()-began)
    if frontier is None:
        return dict(result,reason='native_scope_or_resource_limit',search_strategy=search_strategy,
                    wall_seconds=time.perf_counter()-began)
    result['search_strategy']=search_strategy
    result.update(reason=frontier.reason,reached_tick=frontier.reached_tick,
                  search_stats=frontier.stats,clock=frontier.clock)
    # Input-cost ranking is a preference, never a safety or completeness claim:
    # it only decides which equally-safe candidates survive the width cut.
    result['input_cost']=frontier.stats.get('input_cost')
    actions=frontier.actions;trace=frontier.trajectory;history=frontier.target_history
    base_history=getattr(frontier,'base_target_history',history)
    controlled_identity=getattr(frontier,'controlled_identity',None)
    confirms=getattr(frontier,'confirm_sequence',[False]*len(actions))
    valid=frontier.status=='candidate_found' and frontier.verified
    terminal=None
    if valid:
        terminal=getattr(frontier,'source_terminal',None)
        if terminal is None:terminal=wave_terminal(next(item.wave for item in frontier.bindings if item.history==history))
        if controlled_identity is not None:
            result['dialogue_start_tick']=frontier.dialogue_start_tick
            if frontier.primed_initial_frame:
                result['primed_initial_frame']=True
                result['initial_frame_control']=int(trace[0,4])|(32 if initial_confirm else 0)
    if valid:
        if progress is not None:progress(phase='completion')
        completion=compose_csv_completion(actions,confirms,trace,terminal,
            clock_sequence(clock),max_ticks)
        if completion['status']!='proven':
            valid=False;result['reason']='terminal_invariant_unproven'
            result['terminal_reasons']=completion['reasons']
        else:
            actions=completion['actions'];confirms=completion['confirm_sequence'];trace=completion['trajectory']
            result['completion']=completion['completion'];result['reached_tick']=len(actions)
    if valid:
        result.update(status='candidate_found',reason='verified_model_'+result['completion']['kind'],verified=True,
            actions=[int(x) for x in actions],confirm_sequence=[bool(x) for x in confirms],
            trajectory=np.asarray(trace).tolist(),target_history=[[int(row[0]),int(row[1]),float(row[2]),float(row[3])] for row in history])
        result['source_terminal']=dict(terminal,environment=np.asarray(terminal['environment']).tolist())
        result['scripted_damage_events']=getattr(frontier,'scripted_damage_events',[])
        result['environment_binding_identity']=next(
            item.identity.hex() for item in frontier.bindings if item.history==base_history)
        if controlled_identity is not None:
            result['controlled_environment_binding_identity']=controlled_identity.hex()
            result['environment_provenance']=dict(kind='controlled',
                base_binding_identity=result['environment_binding_identity'],
                base_target_history=[[int(row[0]),int(row[1]),float(row[2]),float(row[3])] for row in base_history],
                final_binding_identity=controlled_identity.hex())
        result['unified_controls']=[mask|(32 if confirm else 0) for mask,confirm in zip(result['actions'],confirms)]
    else:
        result['diagnostic_prefix_masks']=[int(x) for x in actions]
        result['diagnostic_state']=trace[-1].tolist() if len(trace) else None
    sequence=clock.dt_schedule
    if sequence is None:
        hz=240
    else:
        hz=1./sequence[0] if all(dt==sequence[0] for dt in sequence) else None
    result.update(physics_hz=hz,control_hz=hz,clock_protocol=frontier.clock['protocol'],
                  clock_start_ms=clock_start_ms)
    if valid:
        result['dt_sequence']=list(sequence[:len(actions)+1]) if sequence is not None else [1/240]*(len(actions)+1)
        result['game_seconds']=sum(result['dt_sequence'][1:])
    result['wall_seconds']=time.perf_counter()-began
    return result
