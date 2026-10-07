"""Independent relation audit: observable exits and their concrete witnesses."""
import numpy as np
import pytest

from nohit.engine.compact_wave import compile_wave
from nohit.engine.cspace import bake_cspace, collision_query
from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.local_relation import full_local_relation
from nohit.engine.red_joint_frontier import AxisFrontier, advance_joint, _joint_kernel


def scene(tmp_path):
    p = tmp_path / 'audit.csv'
    p.write_text('0,HeartMode,0\n0,BoneV,328,280,22,0,0\n0.2,EndAttack\n')
    return compile_wave(p)


def state(x=320., y=304., dx=0., dy=0., mask=0.):
    return np.array([x, y, dx, dy, mask, 0., 0., 1., 750., 0., 0.])


@pytest.mark.parametrize('controls', [tuple(range(16)), tuple(range(32)), (3, 12, 15, 16, 19, 28, 31), (5, 10)])
@pytest.mark.parametrize('hold', [1, 4])
def test_nonuniform_dt_all_terminal_alias_witnesses(tmp_path, controls, hold):
    w = scene(tmp_path)
    # The operator consumes each actual source dt; it must not substitute 1/240.
    w.env_schedule[1:hold * 3 + 1, 7] = np.resize([.0031, .0042, .0067, .0048], hold * 3)
    space = bake_cspace(w)
    initial = np.array([state(), state(np.nextafter(320., np.inf), 305., -75., 150., 15.)])
    layers = [AxisFrontier.from_states(initial)]
    for tick in range(0, hold * 3, hold):
        status, front, _ = advance_joint(w, layers[-1], controls, tick, hold, space)
        assert status == 'complete'
        layers.append(front)
    reference = full_local_relation(w, 0, hold * 3, initial, controls=controls, hold=hold, cspace=space)
    assert {s.tobytes() for s in front.terminal_states()} == {s.tobytes() for s in reference.states}
    # Recover every terminal mask, not merely each resident representative.
    representatives = {s[:4].tobytes(): i for i, s in enumerate(front.representative_states())}
    for expected in front.terminal_states():
        index = representatives[expected[:4].tobytes()]
        word = []
        for layer in layers[:0:-1]:
            word.append(int(layer.mask[index]))
            index = int(layer.parents[index])
        word.reverse()
        word[-1] = int(expected[4])
        s = initial[layers[0].parents[index]].copy()
        for frame, mask in enumerate(word):
            for micro in range(hold):
                tick = frame * hold + micro + 1
                step_mask_into(s, mask, w.env_schedule[tick], w.platform_table[tick], s)
                assert not collision_query(w.geometry_white, w.geometry_blue, tick, s, 0., space.payload)
        assert s.tobytes() == expected.tobytes()


def test_joint_relation_does_not_cartesianize_axis_marginals(tmp_path):
    w = scene(tmp_path)
    status, front, _ = advance_joint(w, AxisFrontier.from_states([state()]), (5, 10), 0, 2, bake_cspace(w))
    assert status == 'complete'
    assert len(front.x) == len(front.y) == 2
    assert len(front.joint) == 2  # Cartesian closure would falsely invent 4.


@pytest.mark.parametrize('which', ['top', 'right', 'large_dt'])
def test_cross_axis_contact_and_multistep_are_explicit_unknown(tmp_path, which):
    w = scene(tmp_path)
    s = state(dx=150., dy=-150.)
    if which == 'top':
        s[1] = w.env_schedule[1, 1] + 13.
    elif which == 'right':
        s[0] = w.env_schedule[1, 2] - 13.
    else:
        w.env_schedule[1, 7] = 1 / 30
    front = AxisFrontier.from_states([s])
    before = front.representative_states().tobytes()
    status, following, _ = advance_joint(w, front, tuple(range(16)), 0, 4, bake_cspace(w))
    assert status == 'unsupported' and following is None
    assert front.representative_states().tobytes() == before


@pytest.mark.parametrize('boundary', ['pending_target', 'observed_target', 'dialogue'])
def test_observation_boundaries_are_not_fixed_environment_edges(tmp_path, boundary):
    w = scene(tmp_path)
    stop = 4
    if boundary == 'pending_target':
        w.pending_target = {'tick': 2}
    elif boundary == 'observed_target':
        w.source_events = [(2, 'getheartpos', ())]
    else:
        w.termination_reason = 'dialogue_boundary'
        stop = len(w.env_schedule) - 1
    status, following, _ = advance_joint(w, AxisFrontier.from_states([state()]), (0,), 0, stop, bake_cspace(w))
    assert status == 'unsupported' and following is None


@pytest.mark.parametrize('unsafe_first', [False, True])
def test_union_shortcut_requires_an_already_safe_witness(unsafe_first):
    # Two incoming paths converge to one endpoint, but only one is safe.
    # This probes the union kernel directly: marking a key on an unsafe
    # encounter would erase the second valid path, while retaining a later
    # unsafe parent would invalidate the emitted witness.
    first_x = [100., 200.] if unsafe_first else [200., 100.]
    tx = np.zeros((1, 2, 2, 2))
    tx[0, :, 0, 0] = first_x
    tx[0, :, 1, 0] = 300.
    ty = np.zeros((1, 1, 2, 2))
    ty[0, 0, :, 0] = 304.
    white = np.array([[[95., 295., 105., 313.]]] * 3)
    blue = np.empty((3, 0, 4))
    payload = (np.empty((3, 2, 0, 0), np.uint8), np.empty((3, 0, 8)), 0., 0., 1.)
    env = np.zeros((3, 22))
    done, keys, parents, masks, _ = _joint_kernel(
        np.array([0, 1], np.uint64), 1, state(), np.array([0], np.int64),
        tx, ty, np.zeros((1, 2), np.int64), np.zeros((1, 1), np.int64),
        1, 0, 2, env, white, blue, payload, 1, 1)
    assert done and keys.tolist() == [0] and masks.tolist() == [0]
    assert parents.tolist() == [int(unsafe_first)]
