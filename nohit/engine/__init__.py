"""Source-faithful CSV simulation, native candidate search and verification."""
from pathlib import Path
import hashlib
import json
import sysconfig

_directory=Path(__file__).resolve().parent
_accelerated=('_scalar_discrete_operator','_scalar_cspace','_scalar_entities','_scalar_reference_numeric')
if any((_directory/(name+sysconfig.get_config_var('EXT_SUFFIX'))).exists() for name in _accelerated):
    _manifest=_directory.parents[1]/'build/accelerated/manifest.json'
    if not _manifest.exists():raise ImportError('Missing accelerator manifest; run python -m tools.build_accelerators')
    _metadata=json.loads(_manifest.read_text())
    for _name,_digest in _metadata['sources'].items():
        if hashlib.sha256((_directory/(_name+'.py')).read_bytes()).hexdigest()!=_digest:
            raise ImportError('Stale accelerator for '+_name+'; run python -m tools.build_accelerators (or --remove)')
