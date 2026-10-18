"""Freeze the dashboard, native kernels and game; test the extracted archive."""
import argparse
import hashlib
import importlib.metadata
import json
import lzma
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-mb', type=float, default=20.)
    args = parser.parse_args()
    if platform.system() not in ('Windows', 'Linux'):
        raise SystemExit('Only Windows and Linux distributions are supported')
    environment = dict(os.environ, NOHIT_NATIVE_TUNE='portable')
    suffix = '.dll' if os.name == 'nt' else '.so'
    engine = ROOT/'nohit/engine'
    metadata = json.loads((engine/'native-build.json').read_text())
    if metadata.get('cpu_target') != 'portable':
        raise SystemExit('Rebuild with NOHIT_NATIVE_TUNE=portable before packaging')
    from tools.build_accelerators import SCALARS
    import sysconfig
    ext = sysconfig.get_config_var('EXT_SUFFIX')
    for name in SCALARS:
        if not (engine/('_scalar_'+name+ext)).exists():
            raise SystemExit('All four scalar accelerators must be built first')
    staging = ROOT/'build/portable'
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
        '--onedir', '--console', '--noupx', '--name', 'nohit',
        '--distpath', str(staging/'dist'), '--workpath', str(staging/'work'),
        '--specpath', str(staging), '--paths', str(ROOT)]
    if os.name != 'nt':
        command.append('--strip')
    for name in ('numba','llvmlite','Cython','setuptools','pytest','scipy','pandas',
                 'matplotlib','IPython','tkinter','numpy.f2py','numpy.testing',
                 'numpy.random','numpy.fft','yaml'):
        command += ['--exclude-module', name]
    # These exact source bytes participate in source-admission, binding and
    # accelerator validation even in a frozen executable. Never replace them.
    for path in sorted((ROOT/'nohit').rglob('*')):
        if path.suffix in ('.py','.cpp','.hpp','.html','.js','.css'):
            command += ['--add-data', str(path)+':'+str(path.parent.relative_to(ROOT))]
    for relative in ('xmake.lua','vcpkg.json','nohit/engine/native-build.json',
                     'build/accelerated/manifest.json','c2-sans-fight','third_party','data'):
        path = ROOT/relative
        destination = str(path.parent.relative_to(ROOT)) if path.is_file() else relative
        command += ['--add-data', str(path)+':'+destination]
    command += ['--add-binary', str(engine/('_native_frontier'+suffix))+':nohit/engine']
    for name in SCALARS:
        command += ['--hidden-import', 'nohit.engine._scalar_'+name]
    command.append(str(ROOT/'tools/distribution_entry.py'))
    subprocess.run(command, cwd=ROOT, env=environment, check=True)
    package = staging/'dist/nohit'
    licenses = package/'licenses'
    licenses.mkdir(exist_ok=True)
    for name in ('numpy','pyinstaller'):
        distribution = importlib.metadata.distribution(name)
        for path in distribution.files:
            if '.dist-info/' in str(path) and Path(path).name.lower().startswith(('license','copying')):
                shutil.copyfile(distribution.locate_file(path),licenses/(name+'-'+Path(path).name))
    (package/'START.txt').write_text(
        'NOHIT portable\n\nExtract the whole archive to a writable folder.\n'
        'Windows: double-click nohit.exe. Linux: chmod +x nohit; ./nohit\n'
        'Open http://127.0.0.1:8080 in your browser.\n'
        'No Python, C++ compiler, xmake or vcpkg installation is required.\n'
        'Keep _internal beside the executable. Optional port: nohit 8081\n'
        'Linux extraction: tar -xf nohit-linux-x64.tar.xz\n'
        'Windows 10/11 x64; Linux x86_64.\n'
        f'Linux build glibc baseline: {platform.libc_ver()[1] or "not applicable"}.\n', encoding='utf-8')
    release = ROOT/'build/releases'
    release.mkdir(parents=True, exist_ok=True)
    label = 'windows-x64' if os.name == 'nt' else 'linux-x64'
    for previous in release.glob(f'nohit-{label}.*'):
        previous.unlink()
    archive = release/(f'nohit-{label}.zip' if os.name=='nt' else f'nohit-{label}.tar.xz')
    if os.name == 'nt':
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as output:
            for path in sorted(package.rglob('*')):
                if path.is_file():
                    output.write(path, Path('nohit')/path.relative_to(package))
    else:
        # Preserve PyInstaller's library symlinks instead of storing duplicate
        # OpenBLAS/Fortran images. xz is supported by standard Linux tar.
        filters = [dict(id=lzma.FILTER_X86), dict(id=lzma.FILTER_LZMA2,preset=9)]
        with lzma.open(archive,'wb',filters=filters) as compressed:
            with tarfile.open(fileobj=compressed,mode='w|') as output:
                output.add(package, arcname='nohit')
    with tempfile.TemporaryDirectory(prefix='nohit-release-test-') as directory:
        if os.name == 'nt':
            with zipfile.ZipFile(archive) as source:
                assert source.testzip() is None
                source.extractall(directory)
        else:
            with tarfile.open(archive) as source:
                source.extractall(directory, filter='data')
        executable = Path(directory)/'nohit'/('nohit.exe' if os.name=='nt' else 'nohit')
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        subprocess.run([str(executable),'--self-test'], cwd=directory,
                       env=environment, check=True, timeout=90)
    size = archive.stat().st_size
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    report = dict(platform=label,bytes=size,mb=size/1_000_000,
                  limit_bytes=int(args.max_mb*1_000_000),sha256=digest,
                  extracted_smoke_test='passed')
    (release/f'nohit-{label}.json').write_text(json.dumps(report,indent=2)+'\n')
    (release/f'nohit-{label}.sha256').write_text(f'{digest}  {archive.name}\n')
    print(json.dumps(report), flush=True)
    if size > report['limit_bytes']:
        raise SystemExit(f'Package exceeds {args.max_mb:g} MB: {size/1_000_000:.2f} MB')


if __name__ == '__main__':
    main()
