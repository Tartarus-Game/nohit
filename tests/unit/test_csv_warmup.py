"""Startup preparation loads code without borrowing a real source or route."""
import runpy
import sys
import types
from pathlib import Path

from nohit.engine import csv_warmup


def test_warmup_loads_only_native_code_without_reading_a_source(monkeypatch):
    from nohit.engine import compact_wave, csv_solver, parametric_environment, timeline_csv, native_backend

    def no_route(*args, **kwargs):
        raise AssertionError('startup preparation may not read a CSV or solve a route')

    monkeypatch.setattr(csv_solver, 'solve_csv', no_route)
    monkeypatch.setattr(compact_wave, 'compile_wave', no_route)
    monkeypatch.setattr(compact_wave.TimelineVM, 'run', no_route)
    monkeypatch.setattr(parametric_environment.ParametricEnvironment, '__init__', no_route)
    monkeypatch.setattr(timeline_csv, 'read_timeline_rows', no_route)
    metadata = {'source_sha256': 'test-code', 'route_cache': False}
    monkeypatch.setattr(native_backend, 'load_backend', lambda: (object(), metadata))
    result = csv_warmup.warm_csv_kernels()
    assert result['backend'] == 'native'
    assert result['native_code'] is metadata
    assert set(result['stages_seconds']) == {'native_code'}
    assert result['wall_seconds'] >= 0


def test_launcher_warms_native_interface_before_binding_server(monkeypatch):
    calls = []

    def module(name, **attributes):
        value = types.ModuleType(name)
        value.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, value)

    class Server:
        def serve_forever(self):
            calls.append('serve')

    def start_server(*, port):
        assert port == 8123
        calls.append('bind')
        return Server()

    module('nohit.native_runtime', configure_native_runtime=lambda: calls.append('runtime'))
    module('nohit.dashboard.server', start_server=start_server)
    module('nohit.engine.csv_warmup', warm_csv_kernels=lambda: calls.append('csv') or {'wall_seconds': 0.})
    monkeypatch.setattr(sys, 'argv', ['start_dashboard.py', '8123'])
    runpy.run_path(str(Path(__file__).resolve().parents[2]/'start_dashboard.py'), run_name='__main__')
    assert calls == ['runtime', 'csv', 'bind', 'serve']
