"""Recovered candidates keep real ancestry, clock rows and preview boundaries."""
from types import SimpleNamespace

import numpy as np
import pytest

import nohit.engine.bounded_frontier as module
from nohit.engine.cspace import bake_cspace, collision_query
from nohit.engine.discrete_operator import sample_position, step_mask_into
from nohit.engine.parametric_environment import ParametricEnvironment


INITIAL = np.array([320., 304., 0., 0., 0., 0., 0., 1., 750., 0., 0.])


def _retained(tmp_path, words, text='1,EndAttack\n', dt_schedule=None):
    """Build a small retained tree entirely from actual scalar transitions."""
    path = tmp_path / 'recovery.csv'
    path.write_text('0,HeartMode,0\n' + text, encoding='utf-8')
    dt = tuple(dt_schedule) if dt_schedule is not None else (1 / 30,) * 100
    template = ParametricEnvironment(path, dt_schedule=dt, max_ticks=len(dt))
    result = module.BoundedFrontierResult()
    result.stats.update(recovery_attempts=0, recovery_macro_edges=0,
                        recovery_count=0, recovery_discarded_states=0, recoveries=[])
    binding = template.bind()
    result.bindings.append(binding)
    ids = {binding.identity: 0}
    spaces = {}

    def space_for(bound):
        if bound.identity not in spaces:
            spaces[bound.identity] = bake_cspace(bound.wave, cell_size=8.)
        return spaces[bound.identity]

    result.layers.append(module.FrontierLayer(
        0, INITIAL.reshape(1, 11).copy(), np.array([0], np.int64),
        np.array([-1], np.int64), np.array([0], np.int64)))
    prior_prefixes = {(): 0}
    for tick in range(1, len(words[0]) + 1):
        prefixes = dict.fromkeys(tuple(word[:tick]) for word in words)
        states, bids, parents, masks = [], [], [], []
        previous = result.layers[-1]
        for prefix in prefixes:
            parent = prior_prefixes[prefix[:-1]]
            state = previous.states[parent].copy()
            bound = result.bindings[int(previous.binding_ids[parent])]
            if bound.pending_target is not None and bound.pending_target['tick'] == tick:
                x, y = sample_position(state, bound.wave.env_schedule[tick],
                                       bound.wave.platform_table[tick])
                while bound.pending_target is not None and bound.pending_target['tick'] == tick:
                    bound = template.extend(bound, x, y)
            assert tick <= module._last_motion_tick(bound)
            if bound.identity not in ids:
                ids[bound.identity] = len(result.bindings)
                result.bindings.append(bound)
            step_mask_into(state, prefix[-1], bound.wave.env_schedule[tick],
                           bound.wave.platform_table[tick], state)
            assert not collision_query(bound.wave.geometry_white, bound.wave.geometry_blue,
                                       tick, state, 0., space_for(bound).payload)
            states.append(state)
            bids.append(ids[bound.identity])
            parents.append(parent)
            masks.append(prefix[-1])
        result.layers.append(module.FrontierLayer(
            tick, np.asarray(states), np.asarray(bids, np.int64),
            np.asarray(parents, np.int64), np.asarray(masks, np.int64)))
        prior_prefixes = {prefix: index for index, prefix in enumerate(prefixes)}
    result.reached_tick = result.layers[-1].tick
    result.actions, result.trajectory = result.witness()
    return result, path, dt, space_for, spaces


def _snapshot(result):
    return (result.reached_tick, tuple(id(layer) for layer in result.layers),
            tuple((layer.states.tobytes(), layer.parents.tobytes(),
                   layer.binding_ids.tobytes(), layer.masks.tobytes())
                  for layer in result.layers), tuple(result.dialogue_entries))


def _recover(result, space_for, *, controls=(0,), lookback=256, width=20, deadline=float('inf')):
    return module._recover_frontier(result, controls, width,
                                    np.random.default_rng(42), space_for, deadline, lookback)


def test_recovered_rows_replay_from_their_own_nonzero_parent_and_history(tmp_path):
    dt = (0.013, 0.027, 0.019, 0.031, 0.017, 0.023) * 20
    result, path, dt, space_for, _ = _retained(
        tmp_path, [(1, 1, 4, 0), (2, 2, 8, 0), (1, 1, 8, 0)],
        '0.04,GetHeartPos,x,y\n0,BoneV,$x,100,10,0,0\n1,EndAttack\n', dt)
    old_tick = result.reached_tick
    ancestor = result.layers[-2]
    assert len(set(ancestor.binding_ids)) == 2
    assert ancestor.binding_ids[0] == ancestor.binding_ids[2]
    assert ancestor.binding_ids[0] != ancestor.binding_ids[1]
    original = _snapshot(result)

    assert _recover(result, space_for, controls=(4, 8), lookback=1)
    assert result.reached_tick == old_tick + 1
    assert result.layers[ancestor.tick] is ancestor
    assert set(result.layers[ancestor.tick + 1].parents) == {0, 1, 2}
    assert len(result.layers) == result.reached_tick + 1
    assert tuple(id(layer) for layer in result.layers[:ancestor.tick + 1]) == original[1][:ancestor.tick + 1]

    for index in range(len(result.layers[-1].states)):
        actions, trace = result.witness(index)
        reference = ParametricEnvironment(path, dt_schedule=dt, max_ticks=len(dt), backend='reference')
        bound = reference.bind()
        state = INITIAL.copy()
        spaces = {}
        for tick, mask in enumerate(actions, 1):
            if bound.pending_target is not None and bound.pending_target['tick'] == tick:
                x, y = sample_position(state, bound.wave.env_schedule[tick], bound.wave.platform_table[tick])
                while bound.pending_target is not None and bound.pending_target['tick'] == tick:
                    bound = reference.extend(bound, x, y)
            step_mask_into(state, mask, bound.wave.env_schedule[tick], bound.wave.platform_table[tick], state)
            if bound.identity not in spaces:
                spaces[bound.identity] = bake_cspace(bound.wave, cell_size=8.)
            assert not collision_query(bound.wave.geometry_white, bound.wave.geometry_blue,
                                       tick, state, 0., spaces[bound.identity].payload)
            assert state.tobytes() == trace[tick].tobytes()
        recovered = result.bindings[int(result.layers[-1].binding_ids[index])]
        assert bound.identity == recovered.identity
        assert bound.history == recovered.history
    assert result.status == 'unknown' and not result.verified


@pytest.mark.parametrize('boundary', ['target', 'dialogue', 'clock'])
def test_recovery_cannot_consume_unresolved_or_absent_future_rows(tmp_path, monkeypatch, boundary):
    text = {'target': '0.1,GetHeartPos,x,y\n1,EndAttack\n',
            'dialogue': '0.1,SansText,waiting\n1,EndAttack\n',
            'clock': '10,EndAttack\n'}[boundary]
    dt = (1 / 30,) * (3 if boundary == 'clock' else 100)
    result, _, _, space_for, _ = _retained(tmp_path, [(0, 0)], text, dt)
    bound = result.bindings[0]
    assert module._last_motion_tick(bound) == result.reached_tick
    before = _snapshot(result)

    def no_expansion(*args, **kwargs):
        pytest.fail('recovery crossed an unresolved or exhausted environment boundary')

    monkeypatch.setattr(module, '_expand', no_expansion)
    assert not _recover(result, space_for)
    assert _snapshot(result) == before
    assert result.stats['recovery_attempts'] == 0
    assert result.status == 'unknown' and not result.verified


def test_recovery_rejects_an_intermediate_collision_even_when_endpoint_is_safe(tmp_path):
    result, _, _, space_for, spaces = _retained(tmp_path, [(2, 2, 2, 2)])
    wave = result.bindings[0].wave
    wave.geometry_white = np.full((len(wave.env_schedule), 1, 4), np.nan)
    # The retained rightward path is safe. The shorter recovery hits tick 5;
    # the longer leftward recovery ends safely but crosses the tick 4 bone.
    wave.geometry_white[4, 0] = [323., 302., 327., 306.]
    wave.geometry_white[5, 0] = [328., 302., 332., 306.]
    spaces.clear()
    payload = space_for(result.bindings[0]).payload
    assert not collision_query(wave.geometry_white, wave.geometry_blue, 4,
                               result.layers[-1].states[0], 0., payload)
    state = result.layers[2].states[0].copy()
    collision_ticks = []
    for tick in range(3, 6):
        step_mask_into(state, 1, wave.env_schedule[tick], wave.platform_table[tick], state)
        if collision_query(wave.geometry_white, wave.geometry_blue, tick, state, 0., payload):
            collision_ticks.append(tick)
    assert collision_ticks == [4]
    before = _snapshot(result)
    assert not _recover(result, space_for, controls=(1,), lookback=2)
    assert _snapshot(result) == before


def test_older_rows_cannot_borrow_a_later_resolved_binding(tmp_path, monkeypatch):
    result, _, _, space_for, spaces = _retained(
        tmp_path, [(1, 1, 1, 1), (2, 2, 2, 2)],
        '0.1,GetHeartPos,x,y\n1,EndAttack\n')
    assert result.bindings[0].pending_target['tick'] == 3
    assert len(result.bindings) == 3
    assert len(set(result.layers[3].binding_ids)) == 2
    for bound in result.bindings[1:]:
        assert bound.complete and len(bound.history) == 1
        wave = bound.wave
        wave.geometry_white = np.full((len(wave.env_schedule), 1, 4), np.nan)
        wave.geometry_white[5, 0] = [0., 0., 640., 480.]
    spaces.clear()
    original = module._expand
    calls = []

    def counted(states, masks, start, hold, env, *args):
        calls.append((start, hold, id(env)))
        return original(states, masks, start, hold, env, *args)

    monkeypatch.setattr(module, '_expand', counted)
    before = _snapshot(result)
    assert not _recover(result, space_for, lookback=2)
    # Resolved tick-3 branches may try their own worlds. Tick-2 ancestors still
    # have an unobserved target, even though later worlds exist in the registry.
    assert {(start, hold) for start, hold, _ in calls} == {(3, 2)}
    assert {env_id for _, _, env_id in calls} == {
        id(bound.wave.env_schedule) for bound in result.bindings[1:]}
    assert len(calls) == 2
    assert _snapshot(result) == before


@pytest.mark.parametrize('expire_after', ['before', 'expansion', 'reconstruction'])
def test_deadline_does_not_publish_a_partially_recovered_suffix(tmp_path, monkeypatch, expire_after):
    result, _, _, space_for, _ = _retained(tmp_path, [(0, 0)])
    result.dialogue_entries = [('untouched', (0,))]
    before = _snapshot(result)
    clock = [2. if expire_after == 'before' else 0.]
    monkeypatch.setattr(module, 'time', SimpleNamespace(perf_counter=lambda: clock[0]))
    if expire_after != 'before':
        name = '_expand' if expire_after == 'expansion' else '_held_trace'
        original = getattr(module, name)

        def expire(*args, **kwargs):
            value = original(*args, **kwargs)
            clock[0] = 2.
            return value

        monkeypatch.setattr(module, name, expire)
    assert not _recover(result, space_for, deadline=1.)
    assert _snapshot(result) == before
    assert result.stats['recovery_count'] == 0
    assert result.stats['recoveries'] == []


def test_lookback_attempts_are_finite_and_never_turn_failure_into_unsat(tmp_path, monkeypatch):
    result, _, _, space_for, spaces = _retained(tmp_path, [(0,) * 12])
    wave = result.bindings[0].wave
    wave.geometry_white = np.full((len(wave.env_schedule), 1, 4), np.nan)
    wave.geometry_white[13, 0] = [0., 0., 640., 480.]
    spaces.clear()
    original = module._expand
    calls = []

    def counted(states, masks, start, hold, *args):
        calls.append((start, hold))
        return original(states, masks, start, hold, *args)

    monkeypatch.setattr(module, '_expand', counted)
    before = _snapshot(result)
    assert not _recover(result, space_for, lookback=5)
    assert calls == [(11, 2), (10, 3), (8, 5), (7, 6)]
    assert _snapshot(result) == before
    assert result.status == 'unknown' and not result.verified
    assert not hasattr(result, 'dead')


@pytest.mark.parametrize('lookback', [-1, True, 1.5])
def test_recovery_lookback_requires_a_nonnegative_integer(tmp_path, lookback):
    path = tmp_path / 'invalid.csv'
    path.write_text('0.1,EndAttack\n')
    with pytest.raises(ValueError, match='recovery_lookback'):
        module.find_bounded_candidate(path, INITIAL, recovery_lookback=lookback)
