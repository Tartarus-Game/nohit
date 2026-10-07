"""Small exhaustive counterexamples for the production FRS transition path."""
import itertools

import numpy as np

from nohit.engine.compact_lattice import blocked_xy, product_micro_into, search_frs_dp_bellman


def narrow_exit():
    schedule = np.tile(np.array([160., 370., 31., 10., 0., 0., 1 / 240]), (9, 1))
    initial = np.array([201., 300., 0., 0., 0.])
    mask = np.zeros((9, 160, 7), np.uint64)
    # Only a right/right path can reach this exit. Neutral and right share
    # the old 4px bin after frame one, but have different future reachability.
    for x in range(113, 204):
        xx = x - 113
        mask[8, :, xx // 64] |= np.uint64(1) << np.uint64(xx % 64)
    return mask, schedule, initial


def survives(mask, schedule, initial, route):
    state = initial.copy()
    for frame, (ux, up) in enumerate(route):
        for micro in range(4):
            tick = frame * 4 + micro + 1
            product_micro_into(state, ux, up, schedule[tick], state, tick)
            if any(blocked_xy(mask, tick, state[m], state[m + 1])
                   for m in range(0, state.size, 5)):
                return False
    return True


def test_full_frs_preserves_subpixel_exit_found_by_exhaustive_enumeration():
    mask, schedule, initial = narrow_exit()
    actions = list(itertools.product((-1, 0, 1), (0, 1)))
    witnesses = [route for route in itertools.product(actions, repeat=2)
                 if survives(mask, schedule, initial, route)]
    assert witnesses, 'Fixture must have a genuine route in the native dynamics'
    status, frame, _, _, route = search_frs_dp_bellman(
        mask, schedule, initial, max_states=100, max_beam=100)
    assert status == 0, 'FRS discarded a viable route despite ample resources'
    assert frame == 2 and survives(mask, schedule, initial, route)


def test_lossy_search_failure_is_not_an_exhaustive_verdict():
    mask, schedule, initial = narrow_exit()
    status, _, _, _, route = search_frs_dp_bellman(
        mask, schedule, initial, max_states=100, max_beam=100, exact=False)
    assert status == 3 and len(route) == 0


def test_small_frontier_capacity_reports_resource_limit():
    mask, schedule, initial = narrow_exit()
    status, _, _, _, route = search_frs_dp_bellman(
        mask, schedule, initial, max_states=1)
    assert status == 2 and len(route) == 0


def test_full_frs_reports_exhaustion_only_when_every_action_is_blocked():
    mask, schedule, initial = narrow_exit()
    mask[1:] = np.uint64(0xffffffffffffffff)
    status, _, _, _, route = search_frs_dp_bellman(
        mask, schedule, initial, max_states=100)
    assert status == 1 and len(route) == 0


def test_exact_folding_keeps_all_product_members_and_horizontal_velocity():
    mask, schedule, initial = narrow_exit()
    product = np.tile(initial, 9)
    # Slightly different dy values exercise all clock profiles and product bits.
    product[8::5] = np.linspace(0., .07, 8)
    status, frame, _, _, route = search_frs_dp_bellman(
        mask, schedule, product, max_states=100)
    assert status == 0 and frame == 2
    assert survives(mask, schedule, product, route)
