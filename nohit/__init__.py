"""Native CSV route search and independent original-game verification."""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]


def _configure_solver_process():
    """Process entry points only: leave native search in charge of CPU budget.

    These array expressions do not benefit from a second BLAS thread pool.
    Preserve explicit user choices and avoid mutating library callers' settings.
    """
    import os
    for key in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS'):
        os.environ.setdefault(key,'1')
    from .native_runtime import configure_native_runtime
    configure_native_runtime()
