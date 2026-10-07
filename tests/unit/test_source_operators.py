"""Differential kernel checks; these never certify original-game no-hit."""
import numpy as np
import pytest
from nohit.engine.source_compiled import _anchor_clearance, _clearance, _band_select, solve_source_compiled
from nohit.common.types import BakeResult


def test_anchor_lookup_matches_actual_floor_ceil_probes():
    rng = np.random.default_rng(42)
    distance = _clearance(rng.random((3, 9, 11)) < .12)
    packed = _anchor_clearance(distance)
    for y in range(9):
        for x in range(11):
            for dx in (0, 1):
                for dy in (0, 1):
                    xx, yy = min(x + dx, 10), min(y + dy, 8)
                    expected = np.minimum.reduce([distance[:, y, x], distance[:, y, xx],
                                                  distance[:, yy, x], distance[:, yy, xx]])
                    np.testing.assert_array_equal((packed[:, y, x] >> (4*(dx+2*dy))) & 15, expected)


def test_band_selection_preserves_stable_ties_and_overflow():
    rng = np.random.default_rng(123)
    for count in (10, 150, 1000):
        costs = rng.integers(0, 8, count, dtype=np.int64)
        bands = rng.integers(0, 20, count, dtype=np.int32)
        order = np.array(list(dict.fromkeys(bands.tolist())), np.int32)
        for limit in (1, 8, 50, 100):
            quota = max(1, limit // len(order))
            kept = np.zeros(20, np.int32)
            expected = []
            for j in np.argsort(costs, kind='stable'):
                if kept[bands[j]] < quota and len(expected) < limit:
                    kept[bands[j]] += 1
                    expected.append(j)
            actual = _band_select(costs, bands, order, len(order), 20, limit)
            np.testing.assert_array_equal(actual, expected)


@pytest.mark.parametrize('seed', [3, 7, 42])
def test_full_search_parity_under_collisions_and_pruning(seed):
    rng = np.random.default_rng(seed)
    hazards = rng.random((24, 80, 48)) < .006
    hazards[:4] = False
    bake = BakeResult(hazards, [[] for _ in hazards], (24, .05, 0, 1, 0),
                      {'B_blue': rng.random(hazards.shape) < .002})
    options = dict(max_states=32, spatial_margin=0, timing_margin_frames=0, phase_diversity=True)
    baseline = solve_source_compiled(bake, **options)
    for operator in ('a', 'b'):
        result = solve_source_compiled(bake, operator=operator, **options)
        assert result.is_deadlock == baseline.is_deadlock
        assert result.deadlock_frame == baseline.deadlock_frame
        assert result.action_sequence == baseline.action_sequence
        assert result.trajectory == baseline.trajectory
        assert result.stats.alive_states_history == baseline.stats.alive_states_history
