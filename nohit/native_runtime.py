"""Select a locally built code artifact before importing NumPy/Numba.

This stores compiled operators, never environment tensors or action routes.
Source changes require an explicit rebuild instead of surprise request-time JIT.
"""
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / 'build' / 'kernels'
SOURCES = ['nohit/engine/source_compiled.py', 'nohit/common/types.py']


def identity():
    return dict(python=platform.python_version(), machine=platform.machine(),
        packages={p: importlib.metadata.version(p) for p in ('numpy', 'numba', 'llvmlite')},
        sources={p:dict(sha256=hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),
                       mtime_ns=(ROOT/p).stat().st_mtime_ns) for p in SOURCES},
        cpu='host', processor=platform.processor())


def select_built_runtime(required=False):
    manifest_path = ARTIFACT / 'manifest.json'
    if not manifest_path.exists():
        if required:
            raise RuntimeError('Build kernels first: .venv/Scripts/python.exe tools/build_kernels.py')
        return False
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest['identity'] != identity():
        raise RuntimeError('Compiled kernels are stale. Run tools/build_kernels.py before starting.')
    for name, digest in manifest['files'].items():
        path = ARTIFACT / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Compiled kernel artifact is incomplete. Run tools/build_kernels.py.')
    if 'numba' in sys.modules:
        raise RuntimeError('Select the built runtime before importing numba')
    os.environ['NUMBA_CACHE_DIR'] = str(ARTIFACT)
    os.environ.pop('NUMBA_CPU_NAME', None)
    os.environ['NOHIT_BUILT_RUNTIME'] = '1'
    return True
