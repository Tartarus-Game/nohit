"""First selection-bucket representatives in NumPy's exact void40 byte order.

These keys rank bounded candidates; they do not establish state equivalence.
Hashing locates representatives and full five-word equality resolves collisions.
Only unique keys need sorting, using the original NumPy byte comparator.
"""
import numpy as np
from numba import njit


def _numpy_selection_buckets(states, order):
    rows = states[order]
    return np.ascontiguousarray(np.column_stack((np.floor(rows[:, 0] / 5),
        np.floor(rows[:, 1] / 5), np.floor(rows[:, 2] / 30),
        np.floor(rows[:, 3] / 30), rows[:, 5])).astype(np.int64))


@njit(cache=True, fastmath=False)
def _checked_selection_buckets(states, order):
    buckets = np.empty((len(order), 5), np.int64)
    for index in range(len(order)):
        source = order[index]
        for column in range(4):
            divisor = 5. if column < 2 else 30.
            value = np.floor(states[source, column] / divisor)
            # Exceptional casts retain NumPy's values and warning/error policy.
            if not np.isfinite(value) or value < -9223372036854775808. or value >= 9223372036854775808.:
                return buckets, False
            buckets[index, column] = np.int64(value)
        value = states[source, 5]
        if not np.isfinite(value) or value < -9223372036854775808. or value >= 9223372036854775808.:
            return buckets, False
        buckets[index, 4] = np.int64(value)
    return buckets, True


def build_selection_buckets(states, order):
    """Build unchanged five-word buckets for a valid RNG permutation of states.

    Native float64 states use direct indexed reads, avoiding a full eleven-field
    gather and column-stack temporaries. Other dtypes and exceptional casts keep
    the original NumPy arithmetic, precision and warning/error behavior.
    """
    if (not isinstance(states, np.ndarray) or states.dtype != np.dtype(np.float64)
            or states.ndim != 2 or states.shape[1] < 6 or np.geterr()['under'] != 'ignore'):
        return _numpy_selection_buckets(states, order)
    buckets, valid = _checked_selection_buckets(states, order)
    return buckets if valid else _numpy_selection_buckets(states, order)


@njit(inline='always')
def _hash(raw, index, hash_mask):
    value = np.uint64(0xcbf29ce484222325)
    for column in range(5):
        value = (value ^ raw[index, column]) * np.uint64(0x100000001b3)
    value ^= value >> np.uint64(30)
    value *= np.uint64(0xbf58476d1ce4e5b9)
    value ^= value >> np.uint64(27)
    value *= np.uint64(0x94d049bb133111eb)
    value ^= value >> np.uint64(31)
    return value & hash_mask


@njit(inline='always')
def _equal(raw, left, right):
    for column in range(5):
        if raw[left, column] != raw[right, column]:
            return False
    return True


@njit(cache=True)
def _first_representatives(raw, hash_mask, initial_capacity):
    capacity = 8
    while capacity < initial_capacity:
        capacity *= 2
    table = np.full(capacity, -1, np.int64)
    first = np.empty(len(raw), np.intp)
    count = 0
    for index in range(len(raw)):
        bucket = np.int64(_hash(raw, index, hash_mask) & np.uint64(capacity - 1))
        while table[bucket] >= 0:
            if _equal(raw, index, table[bucket]):
                break
            bucket = (bucket + 1) & (capacity - 1)
        if table[bucket] >= 0:
            continue
        table[bucket] = index
        first[count] = index
        count += 1
        if count * 10 > capacity * 6:
            capacity *= 2
            table = np.full(capacity, -1, np.int64)
            for prior in first[:count]:
                bucket = np.int64(_hash(raw, prior, hash_mask) & np.uint64(capacity - 1))
                while table[bucket] >= 0:
                    bucket = (bucket + 1) & (capacity - 1)
                table[bucket] = prior
    return first[:count]


def unique_bucket_indices(buckets, *, hash_mask=np.uint64(0xffffffffffffffff), initial_capacity=1024):
    """Return exactly ``np.unique(buckets.view('V40'), return_index=True)[1]``.

    Each row contains five 64-bit integers. Preserve its bytes even for swapped
    endian inputs; numeric tuple sorting would change the reference ordering.
    Collision/capacity overrides support adversarial equality checks without
    affecting which first representatives are returned or their order.
    """
    buckets = np.asarray(buckets)
    if (buckets.ndim != 2 or buckets.shape[1] != 5
            or buckets.dtype.kind not in 'iu' or buckets.dtype.itemsize != 8):
        raise ValueError('five 64-bit integer words per bucket required')
    if type(initial_capacity) is not int or initial_capacity < 1:
        raise ValueError('initial_capacity must be positive')
    buckets = np.ascontiguousarray(buckets)
    first = _first_representatives(buckets.view(np.uint64), np.uint64(hash_mask), initial_capacity)
    keys = buckets[first].view('V40').ravel()
    return first[np.argsort(keys, kind='stable')]
