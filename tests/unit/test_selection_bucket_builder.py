"""Bucket arithmetic preserves native NumPy bytes and exceptional cast behavior."""
import warnings

import numpy as np
import pytest

from nohit.engine.selection_buckets import build_selection_buckets


def reference(states, order):
    rows = states[order]
    return np.ascontiguousarray(np.column_stack((np.floor(rows[:, 0]/5), np.floor(rows[:, 1]/5),
        np.floor(rows[:, 2]/30), np.floor(rows[:, 3]/30), rows[:, 5])).astype(np.int64))


def observed(method, states, order):
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter('always')
        try:
            value, error = method(states, order), None
        except (ValueError, FloatingPointError, TypeError) as caught:
            value, error = None, (type(caught), str(caught))
    return value, [(type(item.message), str(item.message)) for item in seen], error


def assert_same(states, order):
    before = states.tobytes(), order.tobytes()
    expected, old_warnings, old_error = observed(reference, states, order)
    actual, new_warnings, new_error = observed(build_selection_buckets, states, order)
    assert old_warnings == new_warnings and old_error == new_error
    if old_error is None:
        assert actual.dtype == expected.dtype == np.dtype(np.int64)
        assert actual.shape == expected.shape and actual.flags.c_contiguous
        assert actual.tobytes() == expected.tobytes()
    assert before == (states.tobytes(), order.tobytes())


@pytest.mark.parametrize('column', [0, 1, 2, 3, 5])
def test_valid_floor_boundaries_and_fractional_mask_field_keep_original_bytes(column):
    values = [0., -0., np.nextafter(0., 1.), np.nextafter(0., -1.),
              np.finfo(np.float64).tiny, -np.finfo(np.float64).tiny, -1.9, 1.9]
    for divisor in (5., 30.):
        for multiple in (-2**60, -2**40, -1001, -1, 1, 1001, 2**40, 2**60):
            value = divisor * multiple
            values.extend((np.nextafter(value, -np.inf), value, np.nextafter(value, np.inf)))
    values.extend((float(-2**63), np.nextafter(float(2**63), -np.inf)))
    legal = []
    for value in values:
        projected = np.floor(value/(5. if column < 2 else 30.)) if column < 4 else value
        if np.isfinite(projected) and -2**63 <= projected < 2**63:
            legal.append(value)
    # Keep this batch entirely valid: mixing invalid casts would hide compiled
    # boundary arithmetic behind the whole-array NumPy fallback.
    states = np.zeros((len(legal), 11), np.float64)
    states[:, column] = legal
    order = np.random.default_rng(42).permutation(len(states))
    assert_same(states, order)
    assert_same(states[::-1], order)


@pytest.mark.parametrize('error_policy', ['warn', 'raise', 'ignore'])
@pytest.mark.parametrize('column', [0, 1, 2, 3, 5])
def test_nonfinite_and_out_of_range_casts_keep_numpy_values_warnings_and_errors(column, error_policy):
    states = np.zeros((8, 11), np.float64)
    states[:, column] = [np.nan, np.inf, -np.inf, np.finfo(np.float64).max,
        -np.finfo(np.float64).max, np.nextafter(float(-2**63), -np.inf), float(2**63), 1.]
    with np.errstate(invalid=error_policy):
        assert_same(states, np.arange(len(states), dtype=np.intp))


@pytest.mark.parametrize('underflow', ['ignore', 'warn', 'raise'])
def test_underflow_policy_is_not_silently_changed(underflow):
    states = np.zeros((3, 11), np.float64)
    states[:, 0] = [np.nextafter(0., 1.), np.nextafter(0., -1.), 5.]
    with np.errstate(under=underflow):
        assert_same(states, np.arange(3, dtype=np.intp))


@pytest.mark.parametrize('dtype', ['f4', '>f8', 'i8'])
def test_other_dtypes_keep_original_numpy_precision(dtype):
    states = np.zeros((4, 11), np.float64)
    states[:, :4] = np.array([[np.nextafter(-5., -np.inf), 5., -30., 30.]])
    states[:, 5] = [-1.9, 1.9, -0., 0.]
    assert_same(states.astype(dtype), np.array([3, 1, 2, 0], np.intp))


@pytest.mark.parametrize('count', [0, 1, 128])
def test_shape_order_and_input_immutability(count):
    states = np.random.default_rng(12).normal(size=(count, 11))
    assert_same(states, np.random.default_rng(42).permutation(count))


def test_random_valid_float64_bit_patterns_keep_division_and_cast_bytes():
    rng = np.random.default_rng(146)
    states = rng.integers(0, np.iinfo(np.uint64).max, (2048, 11), dtype=np.uint64).view(np.float64)
    states[~np.isfinite(states)] = 0.
    projected = np.column_stack((np.floor(states[:, 0]/5), np.floor(states[:, 1]/5),
        np.floor(states[:, 2]/30), np.floor(states[:, 3]/30), states[:, 5]))
    states = states[np.all(np.isfinite(projected) & (projected >= -2**63) & (projected < 2**63), axis=1)]
    assert len(states) > 20
    assert_same(states, rng.permutation(len(states)))
