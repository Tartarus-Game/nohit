"""Physical CSV completion, with a separately checked released EOF tail."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np

from .discrete_operator import step_mask_into
from .execution_schedule import execution_schedule
from .terminal_completion import complete_eof_tail
from .terminal_invariant import EMPTY_PLATFORMS, certify_release_invariant
from .timeline_csv import read_timeline_rows


AUDITED_NO_ACTION_COMMANDS = frozenset(('score', 'mus_zz_megalovania'))
NO_ACTION_SOURCE_AUDIT = 'jcw87-absent-function-registry-20261007'

# ``DamagePlayer`` is a native Function, not an attack. Battle.xml's
# ``On function "DamagePlayer"`` block does exactly three things:
#     LastDamageTime = time
#     HP -= Function.Param(0)
#     KR += Function.Param(1)
# and then plays PlayerDamaged. It reads and writes no world geometry, spawns no
# hazard and moves no player, so the kinematic model may carry it as a no-op.
# It does change the player's vitality, so it must NOT be folded into the
# no-action audit: rows that call it are reported through
# :func:`vitality_events` and every candidate that contains a positive one is
# marked as scripting real damage.
AUDITED_VITALITY_COMMANDS = frozenset(('damageplayer',))
VITALITY_SOURCE_AUDIT = 'battle-xml-damageplayer-onfunction-20261007'


def _numeric_cell(args, index):
    """Return the literal value of a cell, or None when it is an expression."""
    if index >= len(args):
        return None
    cell = args[index].strip()
    if not cell:
        return None
    try:
        return float(cell)
    except ValueError:
        return None


def vitality_events(path):
    """Scripted HP/KR mutations written in the CSV, in source order.

    A positive ``damage`` is real HP loss. A negative one is a heal: the original
    event sheet clamps ``HP`` back to ``MaxHP`` every tick, so a heal at full HP
    cannot raise it. ``kr`` follows the same sign convention. A cell that holds an
    expression instead of a literal is reported as unresolved rather than guessed.
    """
    events = []
    for number, row in enumerate(read_timeline_rows(path), 1):
        if len(row) < 2 or row[1].strip().lower() != 'damageplayer':
            continue
        args = [cell.strip() for cell in row[2:]]
        damage = _numeric_cell(args, 0)
        kr = _numeric_cell(args, 1)
        events.append(dict(
            line=number, delay=row[0].strip(),
            damage=damage, kr=kr,
            resolution='literal' if damage is not None else 'unresolved_expression',
            source_audit=VITALITY_SOURCE_AUDIT))
    return events


def wave_terminal(wave):
    if not wave.complete:
        raise ValueError('complete source environment required')
    return dict(reason=wave.termination_reason, tick=len(wave.env_schedule)-1,
                eof_tick=wave.eof_tick, environment=wave.env_schedule[-1].copy(),
                details=deepcopy(wave.terminal_details))


def controlled_terminal(binding, template):
    """Read obligations from the actual committed controlled continuation."""
    state=binding.state;data=state.data
    if binding.status!='terminal' or binding.frame is None or state.phase!='committed':
        raise ValueError('committed controlled terminal required')
    dialogue=state.dialogue
    pending_dialogue=dict(vars(dialogue)) if dialogue is not None and dialogue.alive else None
    callbacks=deepcopy(data['unproven_callbacks'])
    if data['end_resize'] is not None:
        callbacks.append(dict(data['end_resize'],status='awaiting_arena_settle'))
    if state.dialogue_blocked_callback:
        callbacks.append(dict(function=state.dialogue_blocked_callback,status='execution_unproven'))
    details={name:len(data[name]) for name in
             ('active_bones','active_stabs','active_blasters','active_platforms')}
    details.update(timeline_exhausted=data['pc']>=len(state.program.parsed) and
                   data['loaded_line'] is None and state.request is None and pending_dialogue is None,
                   pending_dialogue=pending_dialogue,pending_callbacks=callbacks,
                   arena_settled=data['cz']==data['tgt_cz'],end_resize=deepcopy(data['end_resize']),
                   initial_callback_contract='explicit_initial_arena' if template.initial_arena is not None
                   else 'assumed_none_not_encoded_in_initial_environment')
    return dict(reason=binding.reason,tick=binding.frame.tick,eof_tick=data['eof_tick'],
                environment=binding.frame.env.copy(),details=details)


def clock_sequence(template):
    return (np.full(template.max_ticks,1./240.) if template.dt_schedule is None
            else np.asarray(template.dt_schedule,dtype=np.float64))


def csv_eof_tail(terminal, state, sequence, max_ticks):
    """Reuse the EOF proof, then actually consume at least two neutral ticks.

    The one-frame view shifts the existing completion operator's clock origin
    to the actual source terminal. Its returned tick coordinates are restored
    before publishing. No state latch is changed without a physical step.
    """
    if terminal['reason']!='eof_hazards_drained':
        return None
    start=terminal['tick'];sequence=np.asarray(sequence,dtype=np.float64)
    if not 0<=start<min(max_ticks,len(sequence)):
        return dict(status='unknown',reasons=['terminal_clock_boundary'])
    local=sequence[start:min(max_ticks,len(sequence))]
    env=np.asarray(terminal['environment'],dtype=np.float64)
    if local[0]!=env[7]:
        return dict(status='unknown',reasons=['terminal_dt_mismatch'])
    if terminal['details'].get('end_resize') is not None:
        return dict(status='unknown',reasons=['pending_resize_callback'])
    view=SimpleNamespace(termination_reason='eof_hazards_drained',complete=True,
                         env_schedule=env.reshape(1,22),terminal_details=terminal['details'])
    tail=complete_eof_tail(view,state,dt_schedule=local,max_ticks=len(local),
                          last_mask=int(state[4]),decision_ticks=1)
    if tail['status']!='proven':
        return tail
    current=np.asarray(tail['states'][-1],dtype=np.float64)
    static=np.asarray(tail['static_environment'],dtype=np.float64).copy()
    while len(tail['actions'])<2:
        index=len(tail['actions'])+1
        if index>=len(local):
            return dict(status='unknown',reasons=['neutral_release_clock_exhausted'])
        static[7]=local[index];following=np.empty(11,dtype=np.float64)
        step_mask_into(current,0,static,EMPTY_PLATFORMS,following)
        if not np.isfinite(following).all() or following[10]!=0.:
            return dict(status='unknown',reasons=['invalid_neutral_release'])
        tail['actions'].append(0);tail['dt_sequence'].append(float(local[index]))
        tail['states'].append(following.tolist());current=following
    certificate=certify_release_invariant(current,static,terminal['details'])
    if (certificate['status']!='proven' or current[4]!=0. or
            np.asarray(certificate.get('invariant_state',[])).tobytes()!=current.tobytes()):
        return dict(status='unknown',reasons=['released_fixed_point_unproven'])
    tail.update(certificate=certificate,start_tick=start,release_after_tick=start,
                static_environment=static.tolist())
    return tail


def compose_csv_completion(actions, confirms, trajectory, terminal, sequence, max_ticks):
    """Return one complete public execution or an explicit unproved tail."""
    trace=np.asarray(trajectory,dtype=np.float64)
    start=terminal['tick'];actions=[int(mask) for mask in actions];confirms=list(confirms)
    if len(actions)!=start or trace.shape!=(start+1,11) or len(confirms)!=start:
        raise ValueError('source terminal witness length mismatch')
    completion=dict(schema_version=1,kind='endattack',tick=start,
                    model_verified=True,native_verified=False)
    if terminal['reason']=='endattack':
        return dict(status='proven',actions=actions,confirm_sequence=confirms,
                    trajectory=trace,completion=completion)
    tail=csv_eof_tail(terminal,trace[-1],sequence,max_ticks)
    if tail is None or tail['status']!='proven':
        return dict(status='unknown',reasons=['unsupported_source_terminal'] if tail is None else tail['reasons'])
    if np.asarray(tail['states'][0]).tobytes()!=trace[-1].tobytes():
        raise ValueError('EOF tail does not belong to the finite witness')
    raw=dict(status='candidate_found',actions=actions,control_ticks=1,
             trajectory=trace.tolist(),dt_sequence=list(sequence[:start+1]),terminal_tail=tail)
    execution=execution_schedule(raw)
    full_trace=np.concatenate((trace,np.asarray(tail['states'])[1:]))
    n=len(execution['actions'])
    certificate=deepcopy(tail['certificate'])
    certificate.update(policy_confirm=False,static_environment=tail['static_environment'],
                       terminal_details=deepcopy(terminal['details']))
    completion.update(kind='eof_invariant',tick=n,eof_tick=terminal['eof_tick'],
                      drain_tick=start,release_start_tick=start+1,release_tick_count=n-start,
                      certificate=certificate)
    return dict(status='proven',actions=execution['actions'],
                confirm_sequence=confirms+[False]*(n-start),trajectory=full_trace,
                completion=completion)
