"""Finite attack witnesses require a separately certified infinite EOF tail."""
import numpy as np

from .compact_wave import native_fixed_dt
from .discrete_operator import step_mask_into
from .terminal_invariant import EMPTY_PLATFORMS, _inputs, settle_release_to_invariant


def complete_eof_tail(wave, state, *, clock_start_ms=None, max_ticks=40000,
                      max_tail_ticks=4096, last_mask=0, decision_ticks=4, dt_schedule=None):
    if wave.termination_reason != 'eof_hazards_drained':
        return None
    if not wave.complete:
        return {'status':'unknown','reasons':['environment_incomplete']}
    if type(decision_ticks) is not int or decision_ticks not in (1,4):
        return {'status':'unknown','reasons':['invalid_decision_ticks']}
    count=len(wave.env_schedule)
    current_tick=count-1
    carry=(-current_tick)%decision_ticks
    remaining=max(0,min(int(max_ticks)-count,int(max_tail_ticks)))
    if dt_schedule is not None:
        if clock_start_ms is not None:
            raise ValueError('supply either clock_start_ms or dt_schedule')
        schedule=np.asarray(dt_schedule,dtype=np.float64)
        if schedule.ndim!=1 or not len(schedule) or not np.isfinite(schedule).all() or np.any(schedule<=0):
            raise ValueError('invalid dt_schedule')
        future=schedule[count:count+remaining].copy()
        remaining=len(future)
    elif clock_start_ms is None:
        # The compiler's declared nominal clock; no native-clock claim.
        future=np.full(remaining,1./240.,dtype=np.float64)
    else:
        future=native_fixed_dt(clock_start_ms,count+remaining,
                               wave.env_schedule[0,7])[count:]
    s,e,reasons=_inputs(state,wave.env_schedule[-1],wave.terminal_details,
                        stationary_environment=False)
    result={'status':'unknown','reasons':reasons,'control_ticks':1,'actions':[],
            'states':[] if s is None else [s.tolist()],'dt_sequence':[]}
    if not reasons:
        if not isinstance(last_mask,(int,np.integer)) or not 0<=last_mask<32:
            result['reasons']=['invalid_last_mask']
        elif carry and int(s[4])!=last_mask:
            result['reasons']=['last_mask_state_disagreement']
        elif remaining<carry:
            result['reasons']=['control_grid_completion_exceeds_budget']
        else:
            # The last four-tick input block may extend beyond the drained
            # environment. Finish that SAME input before releasing on-grid.
            e[6]=e[9]=e[13]=0.
            e[14:18]=e[:4];e[18:22]=e[:4]
            for i in range(carry):
                e[7]=future[i]
                out=np.empty(11,dtype=np.float64)
                step_mask_into(s,last_mask,e,EMPTY_PLATFORMS,out)
                result['actions'].append(int(last_mask))
                result['dt_sequence'].append(float(future[i]))
                result['states'].append(out.tolist())
                if out[10]!=0. or not np.isfinite(out).all():
                    result['reasons']=['damage_or_invalid_control_grid_transition']
                    break
                s=out
            else:
                tail=settle_release_to_invariant(s,e,wave.terminal_details,
                                                future[carry:],max_steps=remaining-carry)
                prefix_actions=result['actions'];prefix_states=result['states'];prefix_dt=result['dt_sequence']
                result=tail
                result['actions']=prefix_actions+tail['actions']
                result['states']=prefix_states+tail['states'][1:]
                result['dt_sequence']=prefix_dt+tail['dt_sequence']
    result.update(start_tick=current_tick,carry_ticks=carry,
                  release_after_tick=current_tick+carry,control_grid_ticks=decision_ticks,
                  scope='declared_compiler_environment_and_clock',
                  initial_callback_contract=wave.terminal_details.get('initial_callback_contract'),
                  original_replay_passed=False)
    return result
