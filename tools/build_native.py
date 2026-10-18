"""Build native code with xmake; resolve third-party dependencies with vcpkg.

First run `vcpkg install --triplet x64-linux`, then
`python -m tools.build_native --install`. No package download occurs at runtime.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / 'nohit/engine'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output, *, highway=True, pdqsort=True, installed=None, triplet=None, xmake=None):
    from nohit.engine.native_backend import _FLAGS, _CPU_TARGET, source_dependencies
    executable = xmake or os.environ.get('XMAKE') or shutil.which('xmake')
    if not executable:
        raise RuntimeError('xmake is required to build native code; set XMAKE or install xmake')
    if triplet is None:
        machine = 'arm64' if platform.machine().lower() in ('aarch64', 'arm64') else 'x64'
        triplet = machine + ('-windows-static' if os.name == 'nt' else '-osx' if sys.platform == 'darwin' else '-linux')
    installed = Path(installed or os.environ.get('NOHIT_VCPKG_INSTALLED', ROOT / 'vcpkg_installed')).resolve()
    if highway and not (installed / triplet / 'include/hwy/highway.h').is_file():
        raise RuntimeError(f'Highway is missing: run vcpkg install --triplet {triplet}; '
                           'set NOHIT_VCPKG_INSTALLED for a nondefault installation root')
    if pdqsort and not (installed / triplet / 'include/pdqsort/pdqsort.h').is_file():
        raise RuntimeError(f'pdqsort is missing: run vcpkg install --triplet {triplet}')
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    began = time.perf_counter()
    environment = dict(os.environ)
    # xmake explicitly requires this acknowledgement for root/container builds.
    if hasattr(os, 'geteuid') and os.geteuid() == 0:
        environment.setdefault('XMAKE_ROOT', 'y')
    version = re.sub(r'\x1b\[[0-9;]*m', '', subprocess.check_output(
        [executable, '--version'], env=environment, text=True, encoding='utf-8', errors='replace')).splitlines()[0]
    with tempfile.TemporaryDirectory(prefix='nohit-xmake-', dir=output.parent) as temporary:
        staging = Path(temporary)
        (staging / 'nohit/engine').mkdir(parents=True)
        for name in ('native_frontier.cpp', 'native_simd.hpp'):
            shutil.copyfile(ENGINE / name, staging / 'nohit/engine' / name)
        shutil.copyfile(ROOT / 'xmake.lua', staging / 'xmake.lua')
        configure = [executable, 'f', '-y', '-m', 'release', '-P', str(staging),
            '--highway=' + ('y' if highway else 'n'),
            '--pdqsort=' + ('y' if pdqsort else 'n'),
            '--host_tune=' + ('y' if _CPU_TARGET else 'n'),
            '--vcpkg_installed=' + str(installed), '--vcpkg_triplet=' + triplet,
            '--builddir=' + str(staging / 'build')]
        if os.environ.get('CXX'):
            configure.append('--cxx=' + os.environ['CXX'])
        for command in (configure, [executable, '-y', '-P', str(staging), 'native_frontier']):
            process = subprocess.run(command, cwd=staging, env=environment, capture_output=True,
                                     text=True, encoding='utf-8', errors='replace', timeout=180)
            if process.returncode:
                raise RuntimeError('xmake native build failed:\n' + process.stdout[-6000:] + process.stderr[-6000:])
        candidates = [p for p in (staging / 'build').rglob('*native_frontier.*')
                      if p.suffix in ('.so', '.dll', '.dylib')]
        if len(candidates) != 1:
            raise RuntimeError(f'Expected one native image, found {candidates}; xmake output:\n{process.stdout}\n{process.stderr}')
        # Publish atomically so another process never observes half a code image.
        staged_image = output.with_name(output.name + f'.{os.getpid()}.tmp')
        try:
            shutil.copyfile(candidates[0], staged_image)
            os.replace(staged_image, output)
        finally:
            staged_image.unlink(missing_ok=True)
    metadata = dict(source_sha256=digest(ENGINE / 'native_frontier.cpp'),
        source_dependencies=source_dependencies(), compiler_flags=list(_FLAGS),
        cpu_features_sha256=hashlib.sha256(_CPU_TARGET).hexdigest(),
        cpu_target='host' if _CPU_TARGET else 'portable', system=platform.system(), machine=platform.machine(),
        compiler=[os.environ.get('CXX') or shutil.which('g++') or shutil.which('clang++') or 'cl'],
        build_system='xmake', build_system_version=version, highway=highway, pdqsort=pdqsort,
        vcpkg_triplet=triplet if highway or pdqsort else None,
        vcpkg_manifest_sha256=digest(ROOT / 'vcpkg.json'),
        binary_sha256=digest(output), build_seconds=time.perf_counter()-began)
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument('--install', action='store_true')
    destination.add_argument('--output', type=Path)
    parser.add_argument('--highway', choices=('on', 'off'), default='on')
    parser.add_argument('--pdqsort', choices=('on', 'off'), default='on')
    parser.add_argument('--vcpkg-installed', type=Path)
    parser.add_argument('--triplet')
    parser.add_argument('--xmake')
    args = parser.parse_args()
    suffix = '.dll' if os.name == 'nt' else '.dylib' if sys.platform == 'darwin' else '.so'
    output = args.output or ENGINE / ('_native_frontier' + suffix)
    metadata = build(output, highway=args.highway == 'on', pdqsort=args.pdqsort == 'on', installed=args.vcpkg_installed,
                     triplet=args.triplet, xmake=args.xmake)
    manifest = ENGINE / 'native-build.json' if args.install else output.with_suffix(output.suffix + '.json')
    manifest.write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps(dict(output=str(output), **metadata)))


if __name__ == '__main__':
    main()
