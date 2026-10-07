"""A dead-window proof may use dead facts, but never turns unknown into death."""
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import pytest

from nohit.engine.compact_wave import compile_wave
from nohit.engine.cspace import bake_cspace
from nohit.engine.local_relation import full_local_relation
from nohit.engine.dead_window import DeadFacts, dag_state_keys, prove_dead_window


def fixture(tmp_path, *, fatal_tick=None):
    path = tmp_path / 'window.csv'
    path.write_text('0,HeartMode,0\n0.2,EndAttack\n')
    wave = compile_wave(path)
    if fatal_tick is not None:
        wave.geometry_white = np.full((len(wave.env_schedule), 1, 4), np.nan)
        wave.geometry_white[fatal_tick, 0] = [0., 0., 640., 480.]
    state = np.array([320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.])
    return wave, state, bake_cspace(wave)


def facts_from_exit(wave, space, state, *, omit_one=False):
    exits = full_local_relation(wave, 0, 4, state, cspace=space).states
    keys = set(map(bytes, dag_state_keys(wave, 4, exits)))
    if omit_one:
        keys.pop()
    return DeadFacts('binding-a', 4, tuple(range(16)), {4: keys})


def test_known_dead_suffix_short_circuits_a_real_complete_death_proof(tmp_path):
    wave, state, space = fixture(tmp_path, fatal_tick=8)
    brute = full_local_relation(wave, 0, 8, state, cspace=space)
    assert brute.status == 'exhausted'
    facts = facts_from_exit(wave, space, state)
    # These are actual dead facts: every listed exit dies in the full suffix.
    exits = full_local_relation(wave, 0, 4, state, cspace=space).states
    assert full_local_relation(wave, 4, 8, exits, cspace=space).status == 'exhausted'
    result = prove_dead_window(wave, 0, 8, state, binding_identity='binding-a',
                              known_dead=facts, cspace=space)
    assert result.status == 'proven_dead'
    assert result.reached_tick == 4 and result.known_dead_hits > 0
    assert result.expanded_states == 1
    assert result.memo_layers and result.memo_layers[0].tick == 0
    assert result.memo_layers[0].states[0].tobytes() == state.tobytes()
    assert bytes(result.memo_layers[0].keys[0]) == bytes(dag_state_keys(wave, 0, state.reshape(1,11))[0])


@pytest.mark.parametrize('quotient', [False, True])
def test_no_facts_matches_full_operator_exhaustion(tmp_path, quotient):
    wave, state, space = fixture(tmp_path, fatal_tick=8)
    result = prove_dead_window(wave, 0, 8, state, binding_identity='a', cspace=space,
                              input_latch_quotient=quotient, control_quotient=quotient)
    assert result.status == 'proven_dead' and result.known_dead_hits == 0
    for layer in result.memo_layers:
        if layer.tick < 8:
            assert full_local_relation(wave, layer.tick, 8, layer.states, cspace=space).status == 'exhausted'


def test_an_unproved_exit_stays_unknown_and_nothing_is_memoizable(tmp_path):
    wave, state, space = fixture(tmp_path, fatal_tick=8)
    result = prove_dead_window(wave, 0, 4, state, binding_identity='binding-a', cspace=space,
                              known_dead=facts_from_exit(wave, space, state, omit_one=True))
    assert result.status == 'unknown' and result.reason == 'unproved_exit'
    assert len(result.frontier) > 0 and result.known_dead_hits > 0
    assert result.memo_layers == ()


def test_budget_truncation_never_becomes_a_dead_proof(tmp_path):
    wave, state, space = fixture(tmp_path, fatal_tick=8)
    result = prove_dead_window(wave, 0, 8, state, binding_identity='a', cspace=space, max_states=1)
    assert result.status == 'unknown' and result.reason == 'resource_limit'
    assert result.memo_layers == () and result.reached_tick == 0


def test_frontier_budget_is_independent_of_the_cumulative_proof_budget(tmp_path):
    wave, state, space = fixture(tmp_path, fatal_tick=8)
    result = prove_dead_window(wave,0,8,state,binding_identity='binding-a',cspace=space,
        known_dead=facts_from_exit(wave,space,state),max_states=250000,max_frontier_states=1)
    # Even if every oversized exit matches a trusted fact, the frontier cap
    # must not be bypassed or interpreted as an empty proved-dead frontier.
    assert result.status == 'unknown' and result.reason == 'resource_limit'
    assert result.reached_tick == 0 and result.memo_layers == ()


@pytest.mark.parametrize('kind', ['last_row', 'misaligned_hold', 'zero_budget'])
def test_window_and_resource_boundaries_cannot_be_used_as_death(tmp_path, kind):
    wave, state, space = fixture(tmp_path, fatal_tick=4)
    facts = DeadFacts('a',4,tuple(range(16)),{0:set(map(bytes,dag_state_keys(wave,0,state.reshape(1,11))))})
    stop = len(wave.env_schedule)-1 if kind == 'last_row' else 5 if kind == 'misaligned_hold' else 4
    result = prove_dead_window(wave,0,stop,state,binding_identity='a',known_dead=facts,
                              cspace=space,max_states=0 if kind == 'zero_budget' else 1000)
    assert result.status == 'unknown' and result.memo_layers == ()


@pytest.mark.parametrize('boundary', ['observation', 'dialogue', 'clock', 'endattack', 'red_slam'])
def test_uncertain_or_incompatible_boundary_is_unknown_even_with_dead_facts(tmp_path, boundary):
    wave, state, space = fixture(tmp_path, fatal_tick=4)
    facts = DeadFacts('a', 4, tuple(range(16)), {0: set(map(bytes, dag_state_keys(wave,0,state.reshape(1,11))))})
    if boundary == 'observation':
        wave.pending_target = {'tick': 4}
    elif boundary == 'dialogue':
        wave.source_events = ((4, 'sanstext', ()),)
    elif boundary == 'clock':
        wave.env_schedule[2,7] = 0.
    elif boundary == 'endattack':
        wave.source_events = ((4, 'endattack', ()),)
    else:
        wave.env_schedule[1,4] = 0.
        wave.env_schedule[1,6] = 1.
    result = prove_dead_window(wave, 0, 4, state, binding_identity='a', known_dead=facts, cspace=space)
    assert result.status == 'unknown' and result.memo_layers == ()


@pytest.mark.parametrize('change', [{'binding_identity':'other'}, {'hold':1}, {'controls':(0,)}])
def test_facts_must_belong_to_the_same_binding_and_cover_the_input_domain(tmp_path, change):
    wave, state, space = fixture(tmp_path)
    facts = DeadFacts('a',4,tuple(range(16)),{0:set(map(bytes,dag_state_keys(wave,0,state.reshape(1,11))))})
    result = prove_dead_window(wave,0,4,state,binding_identity='a',known_dead=replace(facts,**change),cspace=space)
    assert result.status == 'unknown' and result.reason == 'fact_scope'
    assert result.memo_layers == ()


def test_batch_projection_matches_dag_key_and_preserves_next_observation_mask(tmp_path):
    from nohit.engine.parametric_dag import ParametricRouteIterator, _Node
    wave, state, space = fixture(tmp_path)
    search = SimpleNamespace(bindings={}, environment_state_quotient=False, future_history_key=None)
    states = np.tile(state,(16,1));states[:,4] = np.arange(16)
    for pending in (None, {'tick':5}):
        wave.pending_target = pending
        binding = SimpleNamespace(identity=b'fixed',pending_target=pending,wave=wave)
        expected = [ParametricRouteIterator._key(search,_Node(4,s,binding,int(s[4])))[2] for s in states]
        assert list(map(bytes,dag_state_keys(wave,4,states))) == expected
    assert len(set(map(bytes,dag_state_keys(wave,4,states)))) == 16
    assert np.array_equal(states[:,4],np.arange(16))


def test_next_observation_prevents_alias_controls_hiding_an_unproved_mask(tmp_path):
    wave, state, space = fixture(tmp_path)
    wave.pending_target = {'tick':5}
    exits = full_local_relation(wave,0,4,state,controls=(0,3),cspace=space).states
    assert len(exits) == 2  # Neither key and opposing horizontal keys move identically.
    keys = dag_state_keys(wave,4,exits)
    proved = {bytes(key) for key,row in zip(keys,exits) if row[4] == 0.}
    facts = DeadFacts('a',4,(0,3),{4:proved})
    before = wave.geometry_white.tobytes(), space.cells.tobytes()
    result = prove_dead_window(wave,0,4,state,binding_identity='a',known_dead=facts,
                              controls=(0,3),cspace=space)
    assert result.status == 'unknown' and result.known_dead_hits == 1
    assert len(result.frontier) == 1 and result.frontier[0,4] == 3.
    assert result.memo_layers == ()
    assert (wave.geometry_white.tobytes(),space.cells.tobytes()) == before


def test_blue_slam_latch_and_real_representatives_survive_quotients(tmp_path):
    wave, state, space = fixture(tmp_path, fatal_tick=8)
    wave.env_schedule[5:,4] = 1.
    wave.env_schedule[5:,5] = 2.
    wave.env_schedule[5,6] = 1.
    result = prove_dead_window(wave,0,8,state,binding_identity='a',cspace=space)
    assert result.status == 'proven_dead'
    brute = full_local_relation(wave,0,4,state,cspace=space)
    at_four = next(layer for layer in result.memo_layers if layer.tick == 4)
    assert {s.tobytes() for s in at_four.states} <= {s.tobytes() for s in brute.states}
    assert set(map(bytes,at_four.keys)) == set(map(bytes,dag_state_keys(wave,4,brute.states)))
