"""Prepare CSV kernel code before serving requests, using synthetic arrays only."""
from types import SimpleNamespace
import time

import numpy as np

from .bounded_frontier import _held_trace
from .compact_wave import _build_geometry_fast_njit
from .cspace import bake_cspace, collision_query
from .discrete_operator import initial_state, sample_position, step_mask_into
from .exact_state_dedup import unique_state_indices
from .expansion_dispatch import prepare_expansion
from .selection_buckets import build_selection_buckets, unique_bucket_indices


def warm_csv_kernels():
    """Materialize shared CSV signatures without loading or solving any CSV.

    Array lengths do not specialize Numba code. These two synthetic ticks have
    the same dtypes, ranks and contiguous layouts as real bounded/dialogue
    calls. Empty frontiers prepare both expansion kernels and held-trace code
    without advancing a player. No world, route or binding is retained.
    """
    began = time.perf_counter()
    stages = {}

    def timed(name, operation):
        started = time.perf_counter()
        result = operation()
        stages[name] = time.perf_counter() - started
        return result

    env = np.tile(np.array([
        0., 0., 100., 100., 0., 1., 0., 1/240, 750., 0., 0., 0., 0., 0.,
        0., 0., 100., 100., 0., 0., 100., 100.,
    ], dtype=np.float64), (2, 1))
    platforms = np.empty((2, 0, 9), dtype=np.float64)
    polygons = np.empty((2, 0, 8), dtype=np.float64)
    state = initial_state(np.array([50., 50., 0., 0., 0.]), env[0])
    states = state.reshape(1, 11)
    masks = np.arange(16, dtype=np.int64)
    flat = np.empty((0, 4), dtype=np.float64)
    counts = np.zeros(2, dtype=np.int32)
    white, blue, _ = timed('geometry', lambda: _build_geometry_fast_njit(
        flat, counts, flat, counts, 2, 0, 0, 0))
    wave = SimpleNamespace(env_schedule=env, geometry_white=white,
        geometry_blue=blue, geometry_polygons=polygons,
        origin=(0, 0), dimensions=(100, 100))
    space = timed('cspace', lambda: bake_cspace(wave, cell_size=8.))
    timed('expansion', lambda: prepare_expansion(states, masks, 0, 1,
        env, platforms, white, blue, space.payload))
    timed('held_trace', lambda: _held_trace(states[:0], masks[:0], 0, 1, env, platforms))
    timed('state_dedup', lambda: unique_state_indices(states, env[1]))
    timed('selection_bucket_builder', lambda: build_selection_buckets(states, np.arange(len(states), dtype=np.intp)))
    timed('selection_buckets', lambda: unique_bucket_indices(np.zeros((1, 5), dtype=np.int64)))

    def scalar():
        # Direct dispatchers are used by verification and target sampling even
        # when equivalent calls have already been inlined into expansion code.
        sample_position(state, env[0], platforms[0])
        step_mask_into(state, 0, env[1], platforms[1], state.copy())
        collision_query(white, blue, 0, state, 0., space.payload)
        # Joint replay uses an empty grid and one-frame views. Cover that
        # direct call shape without retaining an input-dependent world.
        empty_payload = (np.empty((1, 2, 0, 0), dtype=np.uint8), polygons[:1], 0., 0., 1.)
        collision_query(white[:1], blue[:1], 0, state, 0., empty_payload)

    timed('scalar_replay', scalar)
    return {'wall_seconds': time.perf_counter() - began, 'stages_seconds': stages}
