"""Fast CSV candidate discovery with independently verified dialogue completion.

This is an existential candidate path. Width limits and fixed Confirm choices
make failure unknown; the complete DAG remains a separate proof mechanism.
"""
import hashlib
from pathlib import Path
import time

import numpy as np

from .bounded_frontier import find_bounded_candidate
from .canonical_solver import model_issues
from .cspace import bake_cspace, collision_query
from .discrete_operator import initial_state, sample_position, step_mask_into
from .parametric_environment import ParametricEnvironment
from .initial_target_history import bind_initial_target_history, normalize_initial_target_history
from .compact_wave import normalize_initial_arena
from .csv_completion import (AUDITED_NO_ACTION_COMMANDS, AUDITED_VITALITY_COMMANDS,
    NO_ACTION_SOURCE_AUDIT, VITALITY_SOURCE_AUDIT, vitality_events,
    wave_terminal, clock_sequence, compose_csv_completion)


def _verify_prefix(path, initial, settings, actions, expected, history, initial_target_history=None):
    template=ParametricEnvironment(path,backend='reference',**settings)
    binding=bind_initial_target_history(template,initial_target_history)
    state=initial_state(initial,binding.wave.env_schedule[0]);trace=[state.copy()];spaces={}
    for tick in range(len(actions)+1):
        if binding.pending_target is not None and binding.pending_target['tick']==tick:
            wave=binding.wave
            x,y=state[:2] if tick==0 else sample_position(state,wave.env_schedule[tick],wave.platform_table[tick])
            while binding.pending_target is not None and binding.pending_target['tick']==tick:
                binding=template.extend(binding,float(x),float(y))
        wave=binding.wave
        if tick>=len(wave.env_schedule):return False
        if tick:
            step_mask_into(state,actions[tick-1],wave.env_schedule[tick],wave.platform_table[tick],state)
            trace.append(state.copy())
        if binding.identity not in spaces:spaces[binding.identity]=bake_cspace(wave)
        if collision_query(wave.geometry_white,wave.geometry_blue,tick,state,0.,spaces[binding.identity].payload):
            return False
    # A target read can precede SansText on the uncommitted next tick. It
    # samples this same parent before movement, so validate that observation
    # without consuming a dialogue input or borrowing another state's target.
    tick=len(actions)+1
    if len(binding.history)<len(history) and binding.pending_target is not None and binding.pending_target['tick']==tick:
        wave=binding.wave
        x,y=sample_position(state,wave.env_schedule[tick],wave.platform_table[tick])
        while binding.pending_target is not None and binding.pending_target['tick']==tick:
            binding=template.extend(binding,float(x),float(y))
    return (binding.history==history and np.asarray(trace).tobytes()==np.asarray(expected).tobytes())


def solve_csv(path, initial, *, initial_environment=None, initial_arena=None, dt_schedule=None, clock_start_ms=None,
              width=3000, seconds=30., max_bindings=1, max_ticks=40000, seed=42,
              selection_seed=42, dialogue_max_ticks=None, dialogue_max_states=100000,
              initial_confirm=False, previous_confirm=False, initial_target_history=None,
              termination_policy='endattack', progress=None):
    """Return a verified source-model candidate, or an explicit unknown result.

Inputs use arrows only. Confirm is emitted separately for every physical tick.
The caller must execute both sequences under the returned clock. Original-game
acceptance and optimality are never inferred from the mathematical replay.
``seconds`` bounds candidate search; compilation, world preparation and
mandatory verification are included separately in the returned wall time.
``initial_target_history`` is an optional complete list of actual tick-zero
GetHeartPos reads, [0, source_line, x, y]. These samples can precede a late arena
clamp and differ from ``initial``. Future samples must not be supplied here.
"""
    if type(initial_confirm) is not bool or type(previous_confirm) is not bool:
        raise ValueError('initial_confirm and previous_confirm must be boolean')
    if termination_policy not in ('endattack','eof_hazards_drained'):
        raise ValueError('invalid termination_policy')
    initial_target_history=normalize_initial_target_history(initial_target_history)
    initial_arena=normalize_initial_arena(initial_arena)
    began=time.perf_counter();path=Path(path)
    result=dict(status='unknown',planner='bounded-frontier-with-dialogue',wave=path.name,
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
    # Scripted vitality is reported, never silently absorbed: a CSV that writes a
    # positive DamagePlayer scripts real HP loss that no player input can avoid.
    result['vitality_source_audit']=VITALITY_SOURCE_AUDIT
    result['scripted_vitality_events']=vitality_events(path)
    result['scripted_damage_present']=any(
        event['damage'] is not None and event['damage']>0 for event in result['scripted_vitality_events'])
    audits=AUDITED_NO_ACTION_COMMANDS|AUDITED_VITALITY_COMMANDS
    issues=[issue for issue in model_issues(path,allow_player_history=True,termination_policy=termination_policy)
            if not (issue.get('reason')=='mechanism_not_validated' and
                    issue.get('command','').strip().lower() in audits)]
    if issues:return dict(result,reason='unsupported_mechanism',issues=issues)
    settings=dict(seed=seed,initial_environment=initial_environment,initial_arena=initial_arena,dt_schedule=dt_schedule,
                  clock_start_ms=clock_start_ms,max_ticks=max_ticks,termination_policy=termination_policy)
    if progress is not None:progress(phase='search')
    frontier=find_bounded_candidate(path,initial,**settings,width=width,seconds=seconds,
        max_bindings=max_bindings,selection_seed=selection_seed,initial_target_history=initial_target_history,
        progress=progress)
    result.update(reason=frontier.reason,reached_tick=frontier.reached_tick,
                  search_stats=frontier.stats,clock=frontier.clock)
    # Input-cost ranking is a preference, never a safety or completeness claim:
    # it only decides which equally-safe candidates survive the width cut.
    result['input_cost']=frontier.stats.get('input_cost')
    actions=frontier.actions;trace=frontier.trajectory;history=frontier.target_history
    base_history=history;controlled_identity=None
    confirms=[False]*len(actions)
    valid=frontier.status=='candidate_found' and frontier.verified
    terminal=None
    if valid:
        terminal=wave_terminal(next(item.wave for item in frontier.bindings if item.history==history))
    if not valid and frontier.reason=='dialogue_boundary':
        if progress is not None:progress(phase='dialogue')
        from .dialogue_frontier import solve_dialogue_frontier
        template=ParametricEnvironment(path,**settings)
        layer=frontier.layers[-1]
        for bid,indices in frontier.dialogue_entries:
            remaining=seconds-(time.perf_counter()-began)
            if remaining<=0:result['reason']='wall_budget';break
            original_binding=frontier.bindings[bid]
            if original_binding.wave.termination_reason!='dialogue_boundary':continue
            binding=template.bind(original_binding.history)
            if binding.identity != original_binding.identity:
                result['reason']='source_or_clock_changed';break
            first=binding.resume_state.request['tick']
            prime=first==0
            tail_limit=max_ticks-max(0,first-1) if dialogue_max_ticks is None else dialogue_max_ticks
            tail=solve_dialogue_frontier(template,binding,layer.states[indices],
                max_ticks=tail_limit,max_states=dialogue_max_states,seconds=remaining,
                width=width,selection_seed=selection_seed,
                previous_confirm=previous_confirm if prime else False,
                initial_frame_control=(int(layer.states[indices[0],4])|(32 if initial_confirm else 0)) if prime else None,
                progress=progress)
            result['dialogue_stats']=tail.stats
            result['reason']=tail.reason
            if tail.status!='candidate_found' or not tail.verified:continue
            origin=int(indices[tail.origin_index])
            prefix,prefix_trace=frontier.witness(origin)
            if (tail.start_tick != len(prefix) or
                np.asarray(tail.trajectory[0]).tobytes() != prefix_trace[-1].tobytes()):
                result['reason']='dialogue_boundary_mismatch';break
            verify_began=time.perf_counter()
            if not _verify_prefix(path,initial,settings,prefix,prefix_trace,binding.history,
                                  initial_target_history=initial_target_history):
                result['reason']='prefix_verification_failed';break
            result['prefix_verification_seconds']=time.perf_counter()-verify_began
            actions=prefix+list(tail.actions)
            confirms=[False]*len(prefix)+list(tail.confirm)
            trace=np.concatenate((prefix_trace,np.asarray(tail.trajectory)[1:]))
            base_history=binding.history;history=tail.target_history
            controlled_identity=tail.controlled_binding_identity
            result['dialogue_start_tick']=tail.start_tick
            if tail.primed_initial_frame:
                result['primed_initial_frame']=True
                result['initial_frame_control']=tail.initial_frame_control
            result['reached_tick']=tail.end_tick
            terminal=tail.source_terminal
            valid=True
            break
    if valid:
        if progress is not None:progress(phase='completion')
        completion=compose_csv_completion(actions,confirms,trace,terminal,
            clock_sequence(ParametricEnvironment(path,**settings)),max_ticks)
        if completion['status']!='proven':
            valid=False;result['reason']='terminal_invariant_unproven'
            result['terminal_reasons']=completion['reasons']
        else:
            actions=completion['actions'];confirms=completion['confirm_sequence'];trace=completion['trajectory']
            result['completion']=completion['completion'];result['reached_tick']=len(actions)
    if valid:
        result.update(status='candidate_found',reason='verified_model_'+result['completion']['kind'],verified=True,
            actions=[int(x) for x in actions],confirm_sequence=[bool(x) for x in confirms],
            trajectory=np.asarray(trace).tolist(),target_history=[list(row) for row in history])
        result['source_terminal']=dict(terminal,environment=np.asarray(terminal['environment']).tolist())
        result['environment_binding_identity']=next(
            item.identity.hex() for item in frontier.bindings if item.history==base_history)
        if controlled_identity is not None:
            result['controlled_environment_binding_identity']=controlled_identity.hex()
            result['environment_provenance']=dict(kind='controlled',
                base_binding_identity=result['environment_binding_identity'],
                base_target_history=[list(row) for row in base_history],
                final_binding_identity=controlled_identity.hex())
        result['unified_controls']=[mask|(32 if confirm else 0) for mask,confirm in zip(result['actions'],confirms)]
    else:
        result['diagnostic_prefix_masks']=[int(x) for x in actions]
        result['diagnostic_state']=trace[-1].tolist() if len(trace) else None
    clock=ParametricEnvironment(path,**settings)
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
