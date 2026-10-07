"""Regressions for hold-local hazard rows and binding-relative platform rows."""
import numpy as np
import pytest

from nohit.engine.cspace import collision_query
from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.parametric_dag import ParametricRouteIterator


def _search(tmp_path, source, *, blue=False):
    path = tmp_path / 'hold_regression.csv'
    path.write_text(source)
    y = 41.95 if blue else 40.
    initial = [40., y, 0., 0., 0., 0., float(blue), 1., 750., 0., 0.]
    environment = [0, 0, 100, 100, int(blue), 1, 0, 1/240, 750, 0,
                   40, y, 0, 0, 0, 0, 100, 100]
    return ParametricRouteIterator(path, initial, initial_environment=environment,
                                   weights=[0, 0, 0, 0])


@pytest.mark.parametrize('after_target', [False, True])
@pytest.mark.parametrize('hazard_microtick', [None, 1, 2, 3, 4])
def test_advance_checks_each_future_hazard_row(tmp_path, after_target, hazard_microtick):
    source = ('0.033333,GetHeartPos,x,y\n' if after_target else '') + '0.1,EndAttack\n'
    search = _search(tmp_path, source)
    node = search.stack[0]
    if after_target:
        while not node.binding.history:
            node = search._advance(node, 0)
            assert node is not None
    node = search._advance(node, 0)
    assert node is not None and node.tick > 0
    first = int(node.binding.history[-1][0]) if after_target else 0
    assert node.tick - first == 4

    wave = node.binding.wave
    wave.geometry_white = np.full((len(wave.env_schedule), 1, 4), np.nan)
    if hazard_microtick is not None:
        # Only this future row is dangerous. The old fused call checked rows
        # 0..3 of the binding view, missing it despite identical player states.
        wave.geometry_white[node.tick + hazard_microtick, 0] = [35., 35., 45., 45.]
    search.baked.clear()
    before = node.state.tobytes()
    start, view, baked, _ = search._environment(node.binding)
    assert start == first
    state = node.state.copy()
    collision_ticks = []
    for micro in range(1, 5):
        tick = node.tick + micro
        step_mask_into(state, 0, wave.env_schedule[tick], wave.platform_table[tick], state)
        if collision_query(view.geometry_white, view.geometry_blue,
                           tick - start, state, 0., baked.payload):
            collision_ticks.append(micro)
    assert collision_ticks == ([] if hazard_microtick is None else [hazard_microtick])
    assert state.tobytes() == before  # State equality alone cannot detect this bug.

    child = search._advance(node, 0)
    if hazard_microtick is None:
        assert child is not None and child.tick == node.tick + 4
        assert child.state.tobytes() == before
    else:
        assert child is None
    assert node.state.tobytes() == before


@pytest.mark.parametrize('blocked', [False, True])
def test_advance_uses_absolute_active_platform_rows_after_target(tmp_path, blocked):
    # An upward-moving platform carries the heart across a real observation.
    # The old call sliced the unsliced platform table with tick - binding.first,
    # giving it earlier, still-active rows rather than the current platform.
    search = _search(tmp_path, '0,Platform,20,50,40,3,15\n'
                              '0.033333,GetHeartPos,x,y\n0.05,EndAttack\n', blue=True)
    node = search.stack[0]
    while not node.binding.history:
        node = search._advance(node, 0)
        assert node is not None
    first = int(node.binding.history[-1][0])
    assert first == node.tick == 8
    wave = node.binding.wave
    stop = node.tick + 4
    current = wave.platform_table[node.tick + 1:stop + 1, 0]
    stale = wave.platform_table[node.tick + 1 - first:stop + 1 - first, 0]
    assert np.all(current[:, 6] == 1.) and np.all(stale[:, 6] == 1.)
    assert np.all(current[:, 1] != stale[:, 1])
    assert np.all(current[:, 5] == -15.)

    wave.geometry_white = np.full((len(wave.env_schedule), 1, 4), np.nan)
    if blocked:
        # At tick 12 the correctly carried heart is at y=41.2 and touches
        # this bone. Stale platform rows instead let it drift below the bone.
        wave.geometry_white[stop, 0] = [35., 38., 45., 39.205]
    search.baked.clear()
    start, view, baked, _ = search._environment(node.binding)
    before = node.state.tobytes()
    expected = node.state.copy()
    collisions = []
    for tick in range(node.tick + 1, stop + 1):
        step_mask_into(expected, 0, wave.env_schedule[tick], wave.platform_table[tick], expected)
        collisions.append(bool(collision_query(view.geometry_white, view.geometry_blue,
                                               tick - start, expected, 0., baked.payload)))
    assert expected[1] == 41.2 == wave.platform_table[stop, 0, 1] - 8.05
    assert expected[3] == -15.
    assert collisions == [False, False, False, blocked]

    child = search._advance(node, 0)
    if blocked:
        assert child is None
    else:
        assert child is not None and child.tick == stop
        assert child.binding is node.binding
        assert child.state.tobytes() == expected.tobytes()
    assert node.state.tobytes() == before
