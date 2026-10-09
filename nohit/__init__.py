"""
nohit package
=============
Sans Fight Bullet Hell Dead-End Determination & Feasible Solution Verification System.
"""

from __future__ import annotations

def __getattr__(name):
    if name not in ('bake_cspace', 'BakeResult'):
        raise AttributeError(name)
    from importlib import import_module
    value = getattr(import_module('nohit.baker'), name)
    globals()[name] = value
    return value

__version__ = "0.1.0"
__all__ = ["bake_cspace", "BakeResult", "__version__"]


def _configure_solver_process():
    """Process entry points only: leave native search in charge of CPU budget.

    These array expressions do not benefit from a second BLAS thread pool.
    Preserve explicit user choices and avoid mutating library callers' settings.
    """
    import os
    for key in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS'):
        os.environ.setdefault(key,'1')
