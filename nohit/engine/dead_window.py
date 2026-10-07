"""Finite-window Bellman death proofs that consume already-proved dead facts.

The frontier omits known-dead states; it is NOT a complete reachable relation.
Only exhaustion proves death. A surviving exit, unsupported boundary, or budget
limit is unknown. Motion/collision and the exact control congruence are shared
with local_relation; no geometric rounding or new collision rule is introduced.
"""
from dataclasses import dataclass, field
from typing import Mapping, Collection

import numpy as np
from numba import config

from .control_quotient import control_classes
from .cspace import bake_cspace, collision_query
from .local_relation import _expand, _internal_layer_keys, _PARALLEL_MIN_EDGES, _HASH_MIN_STATES
from .exact_state_dedup import unique_state_indices
from .parallel_expansion import expand_parallel


_KEY_DTYPE = np.dtype((np.void, 88))


@dataclass(frozen=True)
class DeadFacts:
    """Trusted proofs for one binding and one control clock.

    Values are the 88-byte state component of ParametricRouteIterator._key,
    already scoped to binding_identity. The fact's control set must cover all
    controls of the new query. Facts must have been proved, never budget misses.
    """
    binding_identity: object
    hold: int
    controls: tuple
    by_tick: Mapping[int, Collection[bytes]]


@dataclass(frozen=True)
class DeadWindowLayer:
    tick: int
    states: np.ndarray
    keys: np.ndarray


@dataclass
class DeadWindowResult:
    status: str
    reason: str
    start_tick: int
    reached_tick: int
    frontier: np.ndarray
    counts: list = field(default_factory=list)
    known_dead_hits: int = 0
    peak_frontier: int = 0
    expanded_states: int = 0
    safe_transition_rows: int = 0
    retained_representatives: int = 0
    _visited_layers: list = field(default_factory=list, repr=False)

    @property
    def memo_layers(self):
        """Only a completed death proof authorizes memoizing every visited key."""
        return tuple(self._visited_layers) if self.status == 'proven_dead' else ()


def _next_row(wave, tick):
    pending = wave.pending_target
    if pending is not None and pending['tick'] <= tick + 1:
        return None
    return wave.env_schedule[min(tick + 1, len(wave.env_schedule) - 1)]


def dag_state_keys(wave, tick, states):
    """Batch the DAG state-key projection, leaving real representatives intact.

    A pending next-tick observation preserves the full physical mask. This
    proof helper conservatively accepts canonical schedules, where a slam
    already sets the row's mode to blue. The player operator and DAG key also
    handle synthetic red-plus-slam rows; this proof domain still refuses them.
    """
    states = np.ascontiguousarray(states, dtype=np.float64).reshape(-1, 11)
    row = _next_row(wave, tick)
    if row is None:
        return states.view(_KEY_DTYPE).ravel().copy()
    if row[4] == 0. and row[6] != 0.:
        raise ValueError('incompatible_slam_key')
    return _internal_layer_keys(states, row)


def _fact_array(values):
    if isinstance(values, np.ndarray) and values.dtype == _KEY_DTYPE:
        return values.reshape(-1)
    packed = [bytes(value) for value in values]
    if any(len(value) != 88 for value in packed):
        raise ValueError('dead fact must contain exactly 88 state bytes')
    return np.frombuffer(b''.join(packed), dtype=_KEY_DTYPE)


def prove_dead_window(wave, start_tick, stop_tick, initial, *, binding_identity,
                      known_dead=None, controls=tuple(range(16)), hold=4,
                      max_states=250_000, max_frontier_states=None, cspace=None, input_latch_quotient=True,
                      control_quotient=True, expansion_backend='auto',
                      dedup_backend='auto', workers=None):
    """Prove every supplied state dead, or return unknown.

    max_states bounds cumulative retained representatives (hence proof storage),
    not just a single frontier. max_frontier_states independently limits each
    deduplicated layer before existing dead facts are filtered out. C-space
    must use the same full-wave tick origin.
    Returned keys are scoped to the supplied binding and control/hold domain;
    callers must not publish a proof under a broader action domain.

    Known facts are checked at decision layers. Every physical tick between
    layers still uses the ordinary collision function. Reaching stop_tick with
    any unproved exit is unknown even when most exits matched existing facts.

    Execution backends and conservative automatic thresholds match the full
    local relation. Select scalar/NumPy explicitly for reference execution.
    Default workers are at most two, with no environment or lasting thread
    changes. Unlike full-relation terminal states, proof keys at stop_tick
    still use the next-step DAG projection unless an observation is pending.
    """
    initial = np.asarray(initial, dtype=np.float64)
    if initial.size == 0 or initial.ndim not in (1, 2) or initial.shape[-1] != 11:
        raise ValueError('initial must contain complete 11-field states')
    states = np.ascontiguousarray(initial.reshape(-1, 11)).copy()
    if not np.isfinite(states).all():
        raise ValueError('initial states must be finite')
    if (type(hold) is not int or hold < 1 or type(max_states) is not int or max_states < 0
            or type(start_tick) is not int or type(stop_tick) is not int):
        raise ValueError('integer ticks, positive hold and nonnegative max_states required')
    if max_frontier_states is not None and (type(max_frontier_states) is not int or max_frontier_states < 0):
        raise ValueError('max_frontier_states must be None or a nonnegative integer')
    if not isinstance(input_latch_quotient, bool) or not isinstance(control_quotient, bool):
        raise ValueError('quotient flags must be boolean')
    if control_quotient and not input_latch_quotient:
        raise ValueError('control quotient requires input latch quotient')
    if expansion_backend not in ('auto', 'scalar', 'parallel'):
        raise ValueError('expansion_backend')
    if dedup_backend not in ('auto', 'numpy', 'hash'):
        raise ValueError('dedup_backend')
    if workers is None:
        workers = min(2, config.NUMBA_NUM_THREADS)
    elif type(workers) is not int or not 1 <= workers <= config.NUMBA_NUM_THREADS:
        raise ValueError(f'workers must be an integer from 1 to {config.NUMBA_NUM_THREADS}')
    controls = tuple(controls)
    if not controls or any(isinstance(mask, (bool, np.bool_)) or
            not isinstance(mask, (int, np.integer)) or not 0 <= mask < 32 for mask in controls):
        raise ValueError('controls must be nonempty integers in [0,31]')
    controls_array = np.asarray(controls, dtype=np.int64)
    result = DeadWindowResult('unknown', 'unproved_exit', start_tick, start_tick, states)
    env = wave.env_schedule
    if not 0 <= start_tick < stop_tick < len(env) - 1:
        result.reason = 'clock_boundary'
        return result
    if (stop_tick - start_tick) % hold:
        result.reason = 'control_boundary'
        return result
    rows = env[start_tick:stop_tick + 2]
    if (env.ndim != 2 or env.shape[1] < 22 or not np.isfinite(rows).all()
            or np.any(rows[:, 7] <= 0.) or np.any(~np.isin(rows[:, 4], [0., 1.]))
            or np.any(~np.isin(rows[:, 5], [0., 1., 2., 3.]))):
        result.reason = 'invalid_clock_or_environment'
        return result
    pending = wave.pending_target
    if pending is not None and pending['tick'] <= stop_tick:
        result.reason = 'observation_boundary'
        return result
    for tick, command, _ in wave.source_events:
        if start_tick < tick <= stop_tick and command.lower() in ('getheartpos', 'sanstext', 'endattack'):
            result.reason = 'event_boundary'
            return result
    if getattr(wave, 'termination_reason', None) == 'dialogue_boundary' and stop_tick >= len(env) - 2:
        result.reason = 'dialogue_boundary'
        return result
    if np.any((rows[:, 4] == 0.) & (rows[:, 6] != 0.)):
        result.reason = 'incompatible_slam_key'
        return result
    if known_dead is not None and (known_dead.binding_identity != binding_identity or
            known_dead.hold != hold or not set(controls).issubset(known_dead.controls)):
        result.reason = 'fact_scope'
        return result
    if max_states == 0:
        result.reason = 'resource_limit'
        return result
    space = bake_cspace(wave) if cspace is None else cspace
    if space.cells.shape[0] != len(env):
        result.reason = 'cspace_tick_origin'
        return result

    def admit(tick, values, safe_rows):
        if dedup_backend == 'hash' or (dedup_backend == 'auto' and len(values) >= _HASH_MIN_STATES):
            next_row = _next_row(wave, tick) if input_latch_quotient else None
            indices = unique_state_indices(values, next_row)
            representatives = values[indices]
            # Facts use the DAG projection even when dedup keeps full masks.
            # Build these keys only for selected representatives on this path.
            keys = dag_state_keys(wave, tick, representatives)
        else:
            keys = dag_state_keys(wave, tick, values)
            dedup_keys = keys if input_latch_quotient else values.view(_KEY_DTYPE).ravel()
            _, indices = np.unique(dedup_keys, return_index=True)
            representatives, keys = values[indices], keys[indices]
        if (result.retained_representatives + len(representatives) > max_states or
                (max_frontier_states is not None and len(representatives) > max_frontier_states)):
            result.reason = 'resource_limit'
            return False
        facts = known_dead.by_tick.get(tick, ()) if known_dead is not None else ()
        hit = np.isin(keys, _fact_array(facts)) if len(facts) else np.zeros(len(keys), dtype=bool)
        count = int(np.count_nonzero(hit))
        result.known_dead_hits += count
        result.retained_representatives += len(representatives)
        result._visited_layers.append(DeadWindowLayer(tick, representatives, keys))
        result.frontier = representatives[~hit]
        result.reached_tick = tick
        result.peak_frontier = max(result.peak_frontier, len(result.frontier))
        result.counts.append(dict(tick=tick, safe_transition_rows=safe_rows,
            representatives=len(representatives), known_dead_hits=count, frontier=len(result.frontier)))
        return True

    # Initial collisions are real operator facts; never manufacture collision
    # geometry from a supplied dead set. Preserve those initial keys for memo.
    collides = np.array([collision_query(wave.geometry_white, wave.geometry_blue,
        start_tick, state, 0., space.payload) for state in states], dtype=bool)
    if not admit(start_tick, states, len(states)):
        return result
    # Projection is a next-step congruence, not an initial-collision quotient.
    # Remove current collisions before any representative can hide a safe one.
    if collides.any():
        safe_keys = set(map(bytes, dag_state_keys(wave, start_tick, states[~collides])))
        keys = dag_state_keys(wave, start_tick, result.frontier)
        result.frontier = result.frontier[np.array([bytes(key) in safe_keys for key in keys], dtype=bool)]
        result.counts[-1]['frontier'] = len(result.frontier)
    for tick in range(start_tick, stop_tick, hold):
        if not len(result.frontier):
            result.status, result.reason = 'proven_dead', 'all_branches_dead'
            return result
        layer_controls = controls_array
        if control_quotient:
            classes = control_classes(env[tick + 1:tick + hold + 1], controls,
                                      next_environment=_next_row(wave, tick + hold))
            layer_controls = np.asarray([group[0] for group in classes], dtype=np.int64)
        result.expanded_states += len(result.frontier)
        parallel = (expansion_backend == 'parallel' or
            (expansion_backend == 'auto' and workers > 1 and
             len(result.frontier) * len(layer_controls) >= _PARALLEL_MIN_EDGES))
        args = (result.frontier, layer_controls, tick, hold, env,
                wave.platform_table, wave.geometry_white, wave.geometry_blue, space.payload)
        if parallel:
            following, parents, masks = expand_parallel(*args, workers=workers)
        else:
            following, parents, masks = _expand(*args)
        del args, parents, masks
        result.safe_transition_rows += len(following)
        if not admit(tick + hold, following, len(following)):
            return result
        del following
    if not len(result.frontier):
        result.status, result.reason = 'proven_dead', 'all_branches_dead'
    return result
