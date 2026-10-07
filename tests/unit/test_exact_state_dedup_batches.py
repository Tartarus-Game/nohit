"""Exact byte representatives and parent edges across real and large batches."""
import hashlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from nohit.engine.control_quotient import control_classes
from nohit.engine.cspace import bake_cspace
from nohit.engine.exact_state_dedup import unique_state_indices
from nohit.engine.local_relation import _expand


def reference(states, row):
    keys = np.ascontiguousarray(states).copy()
    if row is not None:
        if row[4] != 0. or row[6] != 0.:
            keys[:, 4] = keys[:, 4].astype(np.int64) & (1, 4, 2, 8)[int(row[5])]
        else:
            keys[:, 4] = 0.
    return np.unique(keys.view('V88').ravel(), return_index=True)[1]


@pytest.mark.parametrize('count', [0, 1, 613, 614, 1228, 1229, 4915, 4916])
@pytest.mark.parametrize('kind', ['terminal', 'red', 'slam'])
def test_first_indices_survive_large_unique_and_duplicate_heavy_batches(count, kind):
    row = None if kind == 'terminal' else np.zeros(22)
    if kind == 'slam':
        row[5] = 2.; row[6] = 1.
    states = np.zeros((count, 11), np.float64)
    states[:, 0] = np.arange(count)
    states[:, 4] = np.arange(count) % 16
    duplicates = states.copy()
    duplicates[:, 0] %= 4
    for case in (states, states[::-1], duplicates, np.zeros_like(states)):
        before = case.tobytes()
        expected = reference(case, row)
        actual = unique_state_indices(case, row)
        assert actual.dtype == expected.dtype == np.dtype(np.intp)
        assert actual.tobytes() == expected.tobytes()
        assert case.tobytes() == before


def test_all_43_actual_final_expansions_preserve_first_states_and_parent_edges():
    path = Path(__file__).resolve().parents[1] / 'fixtures' / 'final_width_pruning.npz'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        'cd406ad5987a6256790d8232ecc0efd8ce9a8b16fb92e4dc0b3d775a5985118d')
    with np.load(path, allow_pickle=False) as stored:
        data = {name: stored[name] for name in stored.files}
    wave = SimpleNamespace(env_schedule=data['environment'], geometry_white=data['white'],
        geometry_blue=data['blue'], geometry_polygons=data['polygons'],
        origin=(239, 226), dimensions=(165, 165))
    space = bake_cspace(wave, cell_size=8.)
    nonempty = 0
    for tick in range(43):
        following_env = data['environment'][tick+2]
        controls = np.array([group[0] for group in control_classes(
            data['environment'][tick+1:tick+2], range(16), next_environment=following_env)], np.int64)
        expanded, parents, masks = _expand(data[f'states_{tick}'], controls, tick, 1,
            data['environment'], data['platforms'], data['white'], data['blue'], space.payload)
        before = expanded.tobytes(), parents.tobytes(), masks.tobytes()
        expected = reference(expanded, following_env)
        actual = unique_state_indices(expanded, following_env)
        assert actual.dtype == expected.dtype and actual.tobytes() == expected.tobytes()
        for values in (expanded, parents, masks):
            assert values[actual].tobytes() == values[expected].tobytes()
        assert before == (expanded.tobytes(), parents.tobytes(), masks.tobytes())
        nonempty += bool(len(expanded))
    assert nonempty == 42
