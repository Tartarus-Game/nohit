"""Load reusable native CSV kernel code without retaining a world or route."""
import time


def warm_csv_kernels(backend='native'):
    if backend != 'native':
        raise ValueError('invalid warmup backend')
    from .native_backend import load_backend
    began = time.perf_counter()
    _, metadata = load_backend()
    elapsed = time.perf_counter() - began
    return dict(wall_seconds=elapsed, stages_seconds={'native_code': elapsed},
                backend='native', native_code=metadata)
