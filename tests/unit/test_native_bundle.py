"""Installed native code requires a matching source, CPU and binary hash."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import pytest
from nohit.engine import native_backend


def test_bundle_rejects_changed_source_cpu_or_image(tmp_path,monkeypatch):
    source=tmp_path/'native_frontier.cpp';source.write_bytes(b'original source')
    extension='.dll' if os.name=='nt' else '.dylib' if sys.platform=='darwin' else '.so'
    binary=tmp_path/('_native_frontier'+extension);binary.write_bytes(b'code image')
    manifest=tmp_path/'native-build.json'
    monkeypatch.setattr(native_backend,'_SOURCE',source)
    metadata=dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        source_dependencies=native_backend.source_dependencies(),
        compiler_flags=list(native_backend._FLAGS),cpu_features_sha256=hashlib.sha256(native_backend._CPU_TARGET).hexdigest(),
        system=platform.system(),machine=platform.machine(),binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),compiler=['g++'])
    manifest.write_text(json.dumps(metadata));monkeypatch.setattr(native_backend,'_SOURCE',source)
    assert native_backend._bundled_binary()[0]==binary
    for key in ('source_sha256','cpu_features_sha256','binary_sha256','machine'):
        changed=dict(metadata,**{key:'mismatch'});manifest.write_text(json.dumps(changed))
        assert native_backend._bundled_binary() is None
    manifest.write_text(json.dumps(metadata));binary.write_bytes(b'corrupted')
    assert native_backend._bundled_binary() is None


def test_bundle_rejects_changed_header_and_explicit_simd_mismatch(tmp_path,monkeypatch):
    source=tmp_path/'native_frontier.cpp';source.write_bytes(b'original source')
    header=tmp_path/'native_simd.hpp';header.write_bytes(b'original header')
    monkeypatch.setattr(native_backend,'_SOURCE',source)
    extension='.dll' if os.name=='nt' else '.dylib' if sys.platform=='darwin' else '.so'
    binary=tmp_path/('_native_frontier'+extension);binary.write_bytes(b'image')
    metadata=dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        source_dependencies=native_backend.source_dependencies(),highway=True,
        compiler_flags=list(native_backend._FLAGS),cpu_features_sha256=hashlib.sha256(native_backend._CPU_TARGET).hexdigest(),
        system=platform.system(),machine=platform.machine(),binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),compiler=['g++'])
    (tmp_path/'native-build.json').write_text(json.dumps(metadata))
    monkeypatch.setenv('NOHIT_NATIVE_SIMD','highway')
    assert native_backend._bundled_binary()[0]==binary
    monkeypatch.setenv('NOHIT_NATIVE_SIMD','off')
    assert native_backend._bundled_binary() is None
    monkeypatch.setenv('NOHIT_NATIVE_SIMD','auto')
    header.write_bytes(b'changed header')
    assert native_backend._bundled_binary() is None


def test_installed_bundle_loads_in_fresh_process_without_a_compiler(tmp_path):
    if native_backend._bundled_binary() is None:pytest.skip('optional installed native image is absent')
    root=Path(__file__).resolve().parents[2]
    script='''
import shutil
shutil.which=lambda *a,**k:None
from nohit.engine.native_backend import load_backend
lib,meta=load_backend()
assert meta['bundled'] and not meta['compiled']
'''
    environment=dict(os.environ,NOHIT_NATIVE_CACHE=str(tmp_path));environment.pop('CXX',None)
    run=subprocess.run([sys.executable,'-c',script],cwd=root,env=environment,capture_output=True,text=True)
    assert run.returncode==0,run.stdout+run.stderr
    assert not list(tmp_path.glob('*.so')) and not list(tmp_path.glob('*.dll'))
