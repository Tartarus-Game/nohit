"""Defer Numba import for optional scalar verification kernels until their first use."""
import threading

_LOCK = threading.RLock()


class DeferredKernel:
    def __init__(self, function, options):
        self.py_func = function
        self.options = options
        self.dispatcher = None
        self.__name__ = function.__name__
        self.__doc__ = function.__doc__

    def _load(self):
        if self.dispatcher is None:
            with _LOCK:
                if self.dispatcher is None:
                    from numba import njit as compile_kernel
                    # Replace all siblings before Numba inspects their globals.
                    # This preserves dispatcher-to-dispatcher calls in verification code.
                    namespace = self.py_func.__globals__
                    kernels = [value for value in namespace.values()
                               if isinstance(value, DeferredKernel)]
                    for kernel in kernels:
                        if kernel.dispatcher is None:
                            kernel.dispatcher = compile_kernel(**kernel.options)(kernel.py_func)
                    for kernel in kernels:
                        namespace[kernel.__name__] = kernel.dispatcher
        return self.dispatcher

    def __call__(self, *args, **kwargs):
        return self._load()(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._load(), name)


def njit(**options):
    return lambda function: DeferredKernel(function, options)
