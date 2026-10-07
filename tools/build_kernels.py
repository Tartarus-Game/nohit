"""Build host-CPU operator code ahead of gameplay. No wave or route data.

Artifacts are local to the pinned Python/Numba and source version; distribute
them with that runtime or rebuild on the destination machine.
"""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nohit.native_runtime import ARTIFACT, identity

started = time.perf_counter()
ARTIFACT.mkdir(parents=True, exist_ok=True)
os.environ['NUMBA_CACHE_DIR'] = str(ARTIFACT)
os.environ.pop('NUMBA_CPU_NAME', None)
from numba import types
from nohit.engine.source_compiled import _search, _clearance, _clearance_anchors

print('Building geometry operators...', flush=True)
_clearance.compile((types.Array(types.boolean, 3, 'C'),))
_clearance_anchors.compile((types.Array(types.boolean, 3, 'C'),))
for dtype in (types.uint8, types.uint16):
    print(f'Building DAG operators ({dtype})...', flush=True)
    _search.compile((types.Array(types.boolean, 3, 'C'), types.Array(types.boolean, 3, 'C'),
        types.Array(dtype, 3, 'C'), types.Array(dtype, 3, 'C'), types.boolean,
        types.float64, types.int64, types.int64, types.boolean,
        types.Array(types.float64, 3, 'C'), types.float64, types.float64, types.int64))
manifest = dict(identity=identity(), build_ms=(time.perf_counter()-started)*1000,
    contains_routes=False, contains_geometry=False, files={})
for path in ARTIFACT.rglob('*'):
    if path.suffix in ('.nbc', '.nbi'):
        manifest['files'][str(path.relative_to(ARTIFACT))] = hashlib.sha256(path.read_bytes()).hexdigest()
(ARTIFACT/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(f"Built {len(manifest['files'])} code artifacts in {manifest['build_ms']:.1f}ms", flush=True)
