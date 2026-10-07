"""Sufficient infinite-tail certificates for the audited discrete player operator.

An unknown result is not an impossibility result. Environment exhaustion is an
explicit caller obligation; an empty current collision raster is insufficient.
"""
from numbers import Integral

import numpy as np

from .discrete_operator import clamp_to_arena, direction_xy, heart_solid, step_mask_into


EMPTY_PLATFORMS = np.zeros((0, 9), dtype=np.float64)


def _inputs(state, environment, details, *, stationary_environment=True):
    reasons = []
    try:
        s = np.asarray(state, dtype=np.float64).copy()
        e = np.asarray(environment, dtype=np.float64).copy()
    except (TypeError, ValueError):
        return None, None, ['invalid_numeric_state']
    if s.shape != (11,) or e.shape != (22,):
        return None, None, ['complete_state11_and_environment22_required']
    if not np.isfinite(s).all() or not np.isfinite(e).all():
        return None, None, ['nonfinite_state']
    if not isinstance(details, dict):
        return s, e, ['terminal_details_required']
    if details.get('timeline_exhausted') is not True:
        reasons.append('timeline_exhaustion_unproven')
    if details.get('pending_callbacks') not in ([], ()):
        reasons.append('callback_exhaustion_unproven')
    if 'pending_dialogue' not in details or details['pending_dialogue'] is not None:
        reasons.append('dialogue_exhaustion_unproven')
    for key in ('active_bones', 'active_stabs', 'active_blasters', 'active_platforms'):
        count = details.get(key)
        if not isinstance(count, Integral) or isinstance(count, bool) or count != 0:
            reasons.append(key + '_not_zero')
    if details.get('arena_settled') is not True:
        reasons.append('arena_not_settled')
    if s[4] != int(s[4]) or not 0 <= s[4] < 32:
        reasons.append('invalid_previous_input')
    if s[5] not in (0., 1.) or s[6] not in (0., 1.) or s[7] not in (0., 1., 2., 3.):
        reasons.append('unsupported_player_mode')
    if s[8] < 0. or s[9] != 0. or s[10] != 0.:
        reasons.append('unsupported_fall_or_damage_state')
    if (s[6], s[7], s[8], s[9]) != (e[4], e[5], e[8], e[12]):
        reasons.append('state_environment_disagreement')
    if not 0. < e[7] <= 1. / 30.:
        reasons.append('invalid_native_dt')
    l, t, r, b = e[:4]
    if r-l < 26. or b-t < 26.:
        reasons.append('invalid_arena')
    if not (l+13. <= s[0] <= r-13. and t+13. <= s[1] <= b-13.):
        reasons.append('outside_arena_inner_bounds')
    if stationary_environment:
        if not np.array_equal(e[:4], e[14:18]) or not np.array_equal(e[:4], e[18:22]):
            reasons.append('arena_phase_not_stationary')
        if e[6] != 0. or e[9] != 0. or e[13] != 0.:
            reasons.append('one_shot_pulse_present')
    return s, e, reasons


def certify_release_invariant(state, environment, terminal_details):
    """Prove all future mask-0 ticks safe, or return ``unknown``.

    The static-environment facts in terminal_details must already be established
    by the compiler/native audit. No tolerance, rounded state key, or finite
    rollout is used as a substitute for the fixed-point argument.
    """
    s, e, reasons = _inputs(state, environment, terminal_details)
    if reasons:
        return {'status': 'unknown', 'reasons': reasons}
    if s[2] != 0. or s[3] != 0.:
        return {'status': 'unknown', 'reasons': ['nonzero_velocity']}
    if clamp_to_arena(s[0], s[1], e, 0) != (s[0], s[1]):
        return {'status': 'unknown', 'reasons': ['clamp_changes_position']}
    if s[6] == 1.:
        gx, gy = direction_xy(s[7])
        if not heart_solid(s[0], s[1], 0., s[7], e, EMPTY_PLATFORMS, gx*.2, gy*.2):
            return {'status': 'unknown', 'reasons': ['gravity_not_suppressed']}
    invariant = s.copy()
    invariant[4] = 0.
    return {'status': 'proven', 'reasons': [], 'policy_mask': 0,
            'proof': 'static-empty-release-fixed-point-v1',
            'invariant_state': invariant.tolist(),
            'input_release_only': bool(s[4] != 0.)}


def settle_release_to_invariant(state, final_environment, terminal_details, dt_sequence, *, max_steps=4096):
    """Check a finite mask-0 bridge, then require the analytic infinite-tail proof.

    dt_sequence is supplied by the caller's exact clock model. The input arrays
    are never changed. Each returned action corresponds to ONE physical tick;
    keep this prefix distinct from four-tick controller actions when replaying.
    """
    s, e, reasons = _inputs(state, final_environment, terminal_details, stationary_environment=False)
    result = {'status': 'unknown', 'reasons': reasons, 'control_ticks': 1,
              'actions': [], 'states': [] if s is None else [s.tolist()], 'dt_sequence': []}
    if reasons:
        return result
    if not isinstance(max_steps, Integral) or isinstance(max_steps, bool) or max_steps < 0:
        result['reasons'] = ['invalid_step_budget']
        return result
    try:
        dts = np.asarray(dt_sequence, dtype=np.float64)
    except (TypeError, ValueError):
        result['reasons'] = ['invalid_dt_sequence']
        return result
    if dts.ndim != 1 or not np.isfinite(dts).all() or np.any(dts <= 0.) or np.any(dts > 1./30.):
        result['reasons'] = ['invalid_dt_sequence']
        return result
    # EOF is already observed. Its last row's pulses must NOT be replayed.
    e[6] = e[9] = e[13] = 0.
    e[14:18] = e[:4]
    e[18:22] = e[:4]
    result['static_environment'] = e.tolist()
    for tick in range(min(max_steps, len(dts)) + 1):
        certificate = certify_release_invariant(s, e, terminal_details)
        if certificate['status'] == 'proven':
            result.update(status='proven', reasons=[], certificate=certificate)
            return result
        if tick == min(max_steps, len(dts)):
            break
        e[7] = dts[tick]
        out = np.empty(11, dtype=np.float64)
        step_mask_into(s, 0, e, EMPTY_PLATFORMS, out)
        result['actions'].append(0)
        result['dt_sequence'].append(float(dts[tick]))
        result['states'].append(out.tolist())
        if out[10] != 0. or not np.isfinite(out).all():
            result['reasons'] = ['damage_or_invalid_transition']
            return result
        s = out
    result['reasons'] = ['step_budget_exhausted' if max_steps <= len(dts) else 'dt_sequence_exhausted']
    return result
