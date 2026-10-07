"""Selection preserves first byte keys, V40 order and the complete RNG stream."""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from nohit.engine.bounded_frontier import _select
from nohit.engine.control_quotient import control_classes
from nohit.engine.cspace import bake_cspace
from nohit.engine.exact_state_dedup import unique_state_indices
from nohit.engine.local_relation import _expand
from nohit.engine.selection_buckets import unique_bucket_indices


def test_first_representatives_keep_void_byte_order_including_negative_words():
    values = np.array([0, 256, -1, 1, -256, 2**63-1, -2**63], np.int64)
    buckets = np.column_stack([np.roll(values, offset) for offset in range(5)])
    buckets = np.concatenate((buckets, buckets[::-1], buckets[:3]))
    before = buckets.tobytes()
    expected = np.unique(buckets.view('V40').ravel(), return_index=True)[1]
    actual = unique_bucket_indices(buckets)
    assert actual.dtype == expected.dtype == np.dtype(np.intp)
    assert actual.tobytes() == expected.tobytes()
    assert buckets.tobytes() == before


@pytest.mark.parametrize('dtype', ['<i8', '>i8', '<u8', '>u8'])
@pytest.mark.parametrize('count', [0, 1, 80])
def test_forced_hash_collisions_growth_endian_and_strides_preserve_first_keys(dtype, count):
    buckets = np.arange(count * 5).reshape(count, 5).astype(dtype)
    buckets = np.concatenate((buckets, buckets, buckets[:4]))[::-1]
    expected = np.unique(np.ascontiguousarray(buckets).view('V40').ravel(), return_index=True)[1]
    before = buckets.tobytes()
    actual = unique_bucket_indices(buckets, hash_mask=np.uint64(0), initial_capacity=1)
    assert actual.dtype == expected.dtype and actual.tobytes() == expected.tobytes()
    assert buckets.tobytes() == before


@pytest.mark.parametrize('buckets', [np.zeros((3, 4), np.int64), np.zeros((3, 5)),
                                     np.zeros((3, 5), np.int32), np.zeros(5, np.int64)])
def test_invalid_key_layout_is_rejected(buckets):
    with pytest.raises(ValueError, match='five 64-bit'):
        unique_bucket_indices(buckets)


@pytest.mark.parametrize('capacity', [0, -1, True, 1.5])
def test_invalid_initial_capacity_is_rejected(capacity):
    with pytest.raises(ValueError, match='initial_capacity'):
        unique_bucket_indices(np.zeros((3, 5), np.int64), initial_capacity=capacity)


def reference_select(states, width, rng):
    """Frozen original NumPy selection policy, including its RNG consumption."""
    if len(states) <= width:
        return np.arange(len(states), dtype=np.intp)
    order = rng.permutation(len(states))
    rows = states[order]
    buckets = np.ascontiguousarray(np.column_stack((np.floor(rows[:, 0] / 5),
        np.floor(rows[:, 1] / 5), np.floor(rows[:, 2] / 30),
        np.floor(rows[:, 3] / 30), rows[:, 5])).astype(np.int64))
    _, first = np.unique(buckets.view('V40').ravel(), return_index=True)
    first = rng.permutation(first)
    if len(first) < width:
        remaining = np.setdiff1d(np.arange(len(states)), first, assume_unique=True)
        first = np.concatenate((first, rng.permutation(remaining)[:width-len(first)]))
    return order[first[:width]]


def rng_state(rng):
    return json.dumps(rng.bit_generator.state, sort_keys=True,
        default=lambda value: value.tolist() if isinstance(value, np.ndarray) else int(value))


def assert_same_selection(states, width, seed=42, generator=np.random.PCG64):
    old = np.random.Generator(generator(seed))
    new = copy.deepcopy(old)
    before = states.tobytes()
    expected = reference_select(states, width, old)
    actual = _select(states, width, new)
    assert actual.dtype == expected.dtype and actual.tobytes() == expected.tobytes()
    assert rng_state(old) == rng_state(new)
    assert states.tobytes() == before


@pytest.mark.parametrize('count', [0, 1, 9, 128, 1001])
@pytest.mark.parametrize('generator', [np.random.PCG64, np.random.MT19937])
def test_selection_and_rng_preserve_floor_boundaries_early_return_and_fill(count, generator):
    rng = np.random.default_rng(29)
    edge = np.array([-30., -5., -0., 0., 5., 30.,
        np.nextafter(-5., -np.inf), np.nextafter(-5., np.inf),
        np.nextafter(5., -np.inf), np.nextafter(5., np.inf)])
    states = np.zeros((count, 11), np.float64)
    for column in range(4):
        states[:, column] = rng.choice(edge, count)
    states[:, 5] = rng.integers(0, 2, count)
    unique = states.copy()
    unique[:, 0] = np.arange(count) * 5.
    for case in (states, states[::-1], unique, np.zeros_like(states)):
        for width in sorted({1, max(1, count // 2), max(1, count), count + 1}):
            assert_same_selection(case, width, generator=generator)


def test_all_43_real_final_batches_preserve_selected_bytes_and_rng_after_expansion():
    # Captured parents must be expanded and deduplicated first. Selecting their
    # retained width1000 arrays directly at width1000 would only test early return.
    path = Path(__file__).resolve().parents[1] / 'fixtures' / 'final_width_pruning.npz'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        'cd406ad5987a6256790d8232ecc0efd8ce9a8b16fb92e4dc0b3d775a5985118d')
    with np.load(path, allow_pickle=False) as saved:
        data = {name: saved[name] for name in saved.files}
    wave = SimpleNamespace(env_schedule=data['environment'], geometry_white=data['white'],
        geometry_blue=data['blue'], geometry_polygons=data['polygons'],
        origin=(239, 226), dimensions=(165, 165))
    space = bake_cspace(wave, cell_size=8.)
    selected_batches = 0
    for tick in range(43):
        following_env = data['environment'][tick+2]
        controls = np.array([group[0] for group in control_classes(
            data['environment'][tick+1:tick+2], range(16), next_environment=following_env)], np.int64)
        expanded, _, _ = _expand(data[f'states_{tick}'], controls, tick, 1, data['environment'],
            data['platforms'], data['white'], data['blue'], space.payload)
        states = expanded[unique_state_indices(expanded, following_env)]
        selected_batches += len(states) > 1000
        for width in (1, 1000, max(1, len(states)-1), len(states)+1):
            for seed in (0, 1, 42):
                assert_same_selection(states, width, seed)
    assert selected_batches == 40
