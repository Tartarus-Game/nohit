"""Startup preparation loads code without borrowing a real source or route."""
import runpy
import sys
import types
from pathlib import Path

from numba import get_num_threads

from nohit.engine import csv_warmup


def test_synthetic_warmup_preserves_thread_mask_and_materializes_reusable_signatures(monkeypatch):
    from nohit.engine import compact_wave, cspace, discrete_operator, exact_state_dedup
    from nohit.engine import local_relation, parallel_expansion, selection_buckets
    from nohit.engine import bounded_frontier, csv_solver, parametric_environment, timeline_csv

    def no_route(*args, **kwargs):
        raise AssertionError('startup preparation may not read a CSV, build a binding or solve a route')

    monkeypatch.setattr(csv_solver, 'solve_csv', no_route)
    monkeypatch.setattr(bounded_frontier, 'find_bounded_candidate', no_route)
    monkeypatch.setattr(compact_wave, 'compile_wave', no_route)
    monkeypatch.setattr(compact_wave.TimelineVM, 'run', no_route)
    monkeypatch.setattr(parametric_environment.ParametricEnvironment, '__init__', no_route)
    monkeypatch.setattr(timeline_csv, 'read_timeline_rows', no_route)
    kernels = (compact_wave._build_geometry_fast_njit, cspace._bake,
        local_relation._expand, parallel_expansion._expand_parallel_kernel,
        bounded_frontier._held_trace, exact_state_dedup._unique_first,
        selection_buckets._checked_selection_buckets, selection_buckets._first_representatives, discrete_operator.sample_position,
        discrete_operator.step_mask_into, cspace.collision_query)
    previous_threads = get_num_threads()
    result = csv_warmup.warm_csv_kernels()
    assert get_num_threads() == previous_threads
    assert set(result['stages_seconds']) == {
        'geometry', 'cspace', 'expansion', 'held_trace', 'state_dedup',
        'selection_bucket_builder', 'selection_buckets', 'scalar_replay',
    }
    assert all(value >= 0 for value in result['stages_seconds'].values())
    assert result['wall_seconds'] >= sum(result['stages_seconds'].values())
    signatures = tuple(tuple(kernel.signatures) for kernel in kernels)
    assert all(signatures)

    # Repeated startup preparation must not introduce a new specialization or
    # leave a different thread mask; this deliberately avoids timing thresholds.
    csv_warmup.warm_csv_kernels()
    assert tuple(tuple(kernel.signatures) for kernel in kernels) == signatures
    assert get_num_threads() == previous_threads


def test_launcher_warms_both_interfaces_before_binding_server(monkeypatch):
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

    module('nohit.native_runtime', select_built_runtime=lambda: calls.append('runtime'))
    module('nohit.dashboard.server', start_server=start_server)
    module('nohit.engine.canonical_solver', warm_kernel=lambda: calls.append('canonical') or 0.)
    module('nohit.engine.csv_warmup', warm_csv_kernels=lambda: calls.append('csv') or {'wall_seconds': 0.})
    monkeypatch.setattr(sys, 'argv', ['start_dashboard.py', '8123'])
    runpy.run_path(str(Path(__file__).resolve().parents[2]/'start_dashboard.py'), run_name='__main__')
    assert calls == ['runtime', 'canonical', 'csv', 'bind', 'serve']
