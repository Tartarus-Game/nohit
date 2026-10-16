"""Configure the native compiler and its DLLs for local process entry points."""
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
_dll_directories = []
_configured = False


def configure_native_runtime():
    """Keep generated code local and retain Windows DLL directory handles."""
    global _configured
    if _configured:
        return
    cache = Path(os.environ.setdefault('NOHIT_NATIVE_CACHE', str(ROOT / 'build' / 'native')))
    cache.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        compiler = shutil.which('g++') or shutil.which('clang++')
        if compiler is None and not os.environ.get('CXX'):
            for directory in (Path('C:/msys64/ucrt64/bin'), Path('C:/msys64/mingw64/bin')):
                candidate = directory / 'g++.exe'
                if candidate.is_file():
                    os.environ['PATH'] = str(directory) + os.pathsep + os.environ.get('PATH', '')
                    compiler = str(candidate)
                    break
        if compiler and hasattr(os, 'add_dll_directory'):
            _dll_directories.append(os.add_dll_directory(str(Path(compiler).parent)))
        # GCC uses TEMP during compilation; keep those generated files together.
        temporary = ROOT / 'build' / 'tmp'
        temporary.mkdir(parents=True, exist_ok=True)
        os.environ['TEMP'] = os.environ['TMP'] = str(temporary)
    _configured = True
