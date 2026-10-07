"""Measured execution policy for the exact, ordered local edge relation.

The serial and parallel implementations return the same state/parent/control
bytes. Batch size changes execution cost only; no search state is discarded.
"""
import os

from numba import config

from .local_relation import _expand
from .parallel_expansion import expand_parallel


# Active OpenMP workers can spin while the caller deduplicates/selects states.
# Full-request measurements favor two workers in that case. A launcher that
# selects passive waiting BEFORE importing Numba can use the faster eight-
# worker team for large batches without that main-thread interference.
_MAX_WORKERS = 8 if os.environ.get('OMP_WAIT_POLICY','').upper() == 'PASSIVE' else 2


def expansion_workers(edge_count):
    """Return zero for the scalar kernel, otherwise the bounded worker count."""
    if type(edge_count) is not int or edge_count < 0:
        raise ValueError('edge_count must be a nonnegative integer')
    if edge_count < 64:
        return 0
    if edge_count < 512:
        return 1
    if edge_count < 2048:
        return min(2, _MAX_WORKERS, config.NUMBA_NUM_THREADS)
    return min(_MAX_WORKERS, config.NUMBA_NUM_THREADS)


def expand_dispatch(states,controls,start,hold,env,platforms,white,blue,payload):
    """Match ``local_relation._expand`` with a size-selected exact backend.

    Thread masks are restored by ``expand_parallel``. This policy never changes
    the process environment, thread-pool capacity, or OpenMP waiting policy.
    """
    args = (states,controls,start,hold,env,platforms,white,blue,payload)
    workers = expansion_workers(len(states)*len(controls))
    if workers == 0:
        return _expand(*args)
    return expand_parallel(*args,workers=workers)


def prepare_expansion(states,controls,start,hold,env,platforms,white,blue,payload):
    """Materialize both kernels before the caller starts its search budget.

    Empty batches preserve the real input signatures without advancing any
    player or reading a future environment row. The parallel call also prepares
    the bounded worker team and restores the caller's original thread mask.
    """
    args = (states[:0],controls,start,hold,env,platforms,white,blue,payload)
    _expand(*args)
    expand_parallel(*args,workers=min(_MAX_WORKERS,config.NUMBA_NUM_THREADS))
