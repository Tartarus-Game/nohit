"""Direct local CSV input for the source-model dashboard."""
import hashlib
import math
import os
import sys
from pathlib import Path
import tempfile
import time
import uuid

import numpy as np

from nohit.engine.csv_solver import solve_csv
from nohit.engine.csv_preparation import prepare_csv_bytes
from nohit.engine.timeline_csv import read_timeline_rows

from . import solve_progress


_ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION_PATHS = tuple(sorted(
    [path.relative_to(_ROOT).as_posix() for path in (_ROOT/'nohit/engine').glob('*.py')]
    + ['nohit/engine/native_frontier.cpp', 'nohit/__init__.py', 'nohit/dashboard/csv_api.py',
       'nohit/dashboard/csv_source.py', 'nohit/dashboard/csv_visualization.py', 'nohit/dashboard/server.py', 'start_dashboard.py']
    + (['tools/distribution_entry.py'] if getattr(sys,'frozen',False) else [])))


def implementation_hashes():
    return {name: hashlib.sha256((_ROOT/name).read_bytes()).hexdigest()
            for name in IMPLEMENTATION_PATHS}


# A long-running dashboard must not claim newly edited files describe its
# already imported implementation. Restart it when solver sources change.
_LOADED_IMPLEMENTATION = implementation_hashes()

_OBSERVATION_OPTIONS = ('observation_chunk_ticks', 'observation_preview_ticks',
                        'observation_preview_reads', 'observation_goal_retries')
_BUDGET_OPTIONS = ('width', 'seconds', 'workers', *_OBSERVATION_OPTIONS)
_AUTO_RETRY_REASONS = {'wall_budget', 'frontier_exhausted', 'native_search_limited',
                       'native_observation_budget'}


def _budget_selection(data, path):
    """Choose existing solver settings from source size, without predicting safety.

    Literal delays are a sizing estimate: jumps, dialogue and dynamic delays can
    change the actual runtime. The solver's complete clock remains authoritative.
    Explicit old API requests keep their manual settings for compatibility.
    """
    mode = data.get('budget_mode')
    if mode is None:
        mode = 'manual' if any(name in data for name in _BUDGET_OPTIONS) else 'auto'
    if mode not in ('auto', 'manual'):
        raise ValueError("budget_mode must be 'auto' or 'manual'")
    duration = 0.; commands = 0; target_reads = 0; dynamic_delays = 0
    for row in read_timeline_rows(path):
        if len(row) < 2:
            continue
        command = row[1].strip().lower()
        commands += bool(command)
        target_reads += command == 'getheartpos'
        try:
            delay = float(row[0] or 0)
            if not math.isfinite(delay) or delay < 0:
                raise ValueError()
            duration += delay
        except ValueError:
            dynamic_delays += 1
    summary = dict(timeline_seconds=duration, command_count=commands,
                   target_reads=target_reads, dynamic_delay_rows=dynamic_delays,
                   duration_is_estimate=True)
    if mode == 'manual':
        selected = dict(width=data.get('width', 3000), seconds=data.get('seconds', 30),
                        workers=data.get('workers'))
        selected.update({name: data[name] for name in _OBSERVATION_OPTIONS if name in data})
        return dict(mode=mode, profile='manual', source_summary=summary, selected=selected,
                    total_search_seconds_limit=selected['seconds'], max_attempts=1, attempts=[])
    if duration >= 120 or commands >= 2000 or target_reads >= 64:
        profile, width, seconds = 'long', 8192, 90
    elif duration >= 30 or commands >= 250 or target_reads >= 8:
        profile, width, seconds = 'medium', 4096, 60
    else:
        profile, width, seconds = 'short', 2048, 30
    selected = dict(width=width, seconds=seconds, workers=min(4, max(1, os.cpu_count() or 1)))
    if profile == 'long' and target_reads:
        selected.update(observation_chunk_ticks=480, observation_preview_ticks=480,
                        observation_preview_reads=128, observation_goal_retries=True)
    return dict(mode=mode, profile=profile, source_summary=summary, selected=selected,
                total_search_seconds_limit=180, max_attempts=2, attempts=[])


def _run_budgeted_csv(path, initial, budget, reporter, **settings):
    """Run at most one wider fresh attempt for bounded auto search failures."""
    selected = dict(budget['selected'])
    allocated = 0.
    started = time.perf_counter()
    deepest_diagnostic=None
    for attempt in range(1, budget['max_attempts'] + 1):
        began = time.perf_counter()
        result = solve_csv(path, initial, **settings, **selected)
        diagnostic=result.get('failure_diagnostics')
        if diagnostic and (deepest_diagnostic is None or (diagnostic.get('last_safe_tick') or 0)>(deepest_diagnostic.get('last_safe_tick') or 0)):
            deepest_diagnostic=diagnostic
        budget['attempts'].append(dict(selected, attempt=attempt, status=result['status'],
            reason=result.get('reason'), wall_seconds=time.perf_counter()-began))
        if budget['mode'] != 'auto':
            break
        allocated += selected['seconds']
        if (result['status'] != 'unknown' or result.get('reason') not in _AUTO_RETRY_REASONS
                or attempt == budget['max_attempts']):
            break
        remaining = min(budget['total_search_seconds_limit']-allocated,
                        budget['total_search_seconds_limit']-(time.perf_counter()-started))
        if remaining < 1:
            break
        selected = dict(selected, width=min(16384, selected['width']*2), seconds=min(90, remaining))
        if reporter is not None:
            reporter.phase('prepare', tick=None, ticks=settings.get('max_ticks'),
                committed_tick=None,
                alive_states=None, peak_alive_states=None, expanded_states=None,
                discarded_states=None, unique_states=None, _seconds_budget=selected['seconds'],
                message='自动增加搜索预算并重新求解')
    result['budget_selection'] = budget
    if result.get('status')=='unknown' and deepest_diagnostic is not None:
        result['failure_diagnostics']=deepest_diagnostic
        result['reached_tick']=deepest_diagnostic.get('last_safe_tick') or 0
        if deepest_diagnostic.get('routes'):
            best=deepest_diagnostic['routes'][0]
            result['diagnostic_prefix_masks']=best['actions']
            result['diagnostic_state']=best['trajectory'][-1] if best['trajectory'] else None
    return result


def solve_csv_request(data):
    """Validate the attempt id, register its telemetry, then run the request.

    The reporter is registered before any other validation, so every failure -
    including a request rejected for a bad initial state or clock - leaves an
    observable ``failed`` snapshot instead of an unregistered attempt.
    """
    progress_id = data.get('progress_id') if isinstance(data, dict) else None
    reporter = None
    if progress_id is not None:
        if not isinstance(progress_id, str) or not progress_id or len(progress_id) > 128:
            raise ValueError('progress_id must be a nonempty string of at most 128 characters')
        reporter = solve_progress.begin(progress_id, engine='native-csv',
                                        seconds_budget=None,
                                        ticks=data.get('max_ticks'))
    try:
        return _solve_csv_request(data, reporter)
    except BaseException as exc:
        if reporter is not None:
            reporter.fail(exc)
        raise


def _solve_csv_request(data, reporter):
    """Solve against a full explicit clock, or a nominal fps clock when omitted.

    A supplied dt_schedule is authoritative even if fps is also present. Its
    full length scopes the clock identity; max_ticks may bound a shorter search.
    Without an explicit budget, a supplied schedule defines that budget.
    """
    if not isinstance(data, dict):
        raise ValueError('Request must be a JSON object')
    visualization_mode = data.get('visualization_mode', 'full')
    if visualization_mode not in ('full', 'entry'):
        raise ValueError("visualization_mode must be 'full' or 'entry'")
    request_id = data.get('request_id', str(uuid.uuid4()))
    if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
        raise ValueError('request_id must be a nonempty string of at most 128 characters')
    if implementation_hashes() != _LOADED_IMPLEMENTATION:
        current = implementation_hashes()
        changed = sorted(name for name in set(current) | set(_LOADED_IMPLEMENTATION)
                         if current.get(name) != _LOADED_IMPLEMENTATION.get(name))
        raise ValueError('Solver source changed after import; restart the dashboard before solving'
                         + (f' (changed: {", ".join(changed)})' if changed else ''))
    local_path, text = data.get('csv_path'), data.get('custom_csv')
    if bool(local_path) == bool(text):
        raise ValueError('Provide exactly one csv_path or custom_csv')
    if local_path and not isinstance(local_path, str) or text and not isinstance(text, str):
        raise ValueError('CSV path and contents must be strings')
    initial = np.asarray(data.get('initial'), dtype=float)
    if initial.shape != (11,) or not np.isfinite(initial).all():
        raise ValueError('initial must contain all 11 finite player fields from the entry state')
    environment = data.get('initial_environment')
    if environment is not None:
        environment = np.asarray(environment, dtype=float)
        if environment.shape != (22,) or not np.isfinite(environment).all():
            raise ValueError('initial_environment must contain 22 finite fields')
        environment = environment.tolist()
    explicit_clock = 'dt_schedule' in data
    if explicit_clock:
        supplied = data['dt_schedule']
        if not isinstance(supplied, (list, tuple)) or not supplied:
            raise ValueError('dt_schedule must be a nonempty array of finite numbers in (0, 1/30]')
        if any(type(value) not in (int, float) for value in supplied):
            raise ValueError('dt_schedule must contain only finite numbers in (0, 1/30]')
        try:
            schedule = [float(value) for value in supplied]
        except (ValueError,OverflowError) as exc:
            raise ValueError('dt_schedule must contain only finite numbers in (0, 1/30]') from exc
        if any(not math.isfinite(value) or not 0 < value <= 1/30 for value in schedule):
            raise ValueError('dt_schedule must contain only finite numbers in (0, 1/30]')
        if environment is not None and schedule[0] != environment[7]:
            raise ValueError('dt_schedule[0] must exactly match initial_environment[7]')
    ticks = data.get('max_ticks', len(schedule) if explicit_clock else 40000)
    if type(ticks) is not int or ticks < 1:
        raise ValueError('max_ticks must be a positive integer')
    if explicit_clock:
        if len(schedule) < ticks:
            raise ValueError('dt_schedule must cover every tick up to max_ticks')
    else:
        fps = data.get('fps', 30)
        if isinstance(fps, bool) or not isinstance(fps, (float, int)) or not math.isfinite(fps) or fps < 30:
            raise ValueError('fps must be finite and at least 30 (the original dt clamp)')
        schedule = [1/fps]*ticks
    settings = dict(initial_environment=environment, initial_arena=data.get('initial_arena'), dt_schedule=schedule,
                    max_ticks=ticks, seed=data.get('seed', 42),
                    termination_policy=data.get('termination_policy','endattack'))
    progress = reporter.update if reporter is not None else None
    began = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='nohit-csv-') as folder:
        path = Path(local_path).expanduser().resolve() if local_path else Path(folder)/'custom.csv'
        if text:
            path.write_bytes(text.encode('utf-8'))
        if path.suffix.lower() != '.csv' or not path.is_file():
            raise ValueError('CSV file does not exist')
        prepared = prepare_csv_bytes(path.read_bytes())
        # Freeze every captured source, including imports needing no cleanup.
        # Budgeting, search and visualization must share these exact bytes.
        path = Path(folder)/path.name
        path.write_bytes(prepared['raw'])
        budget = _budget_selection(data, path)
        if reporter is not None:
            limit = budget['total_search_seconds_limit']
            summary = budget['source_summary']
            duration = summary['timeline_seconds']
            estimated_ticks = None
            if not summary['dynamic_delay_rows'] and duration > 0:
                elapsed_ticks = np.cumsum(schedule[1:ticks], dtype=np.float64)
                # This is a sizing estimate from literal CSV delays, not a
                # terminal certificate. Dialogue and future hazards can add work.
                if len(elapsed_ticks) and duration <= elapsed_ticks[-1]:
                    estimated_ticks = int(np.searchsorted(elapsed_ticks, duration)) + 1
            reporter.update(
                _seconds_budget=limit if type(limit) in (int, float) and math.isfinite(limit) and limit > 0 else None,
                estimated_total_ticks=estimated_ticks,
                estimated_total_ticks_basis='csv_literal_duration_estimate' if estimated_ticks is not None else 'unknown')
        result = _run_budgeted_csv(path, initial, budget, reporter, **settings,
            initial_confirm=data.get('initial_confirm',False),
            previous_confirm=data.get('previous_confirm',False),
            initial_target_history=data.get('initial_target_history'), progress=progress,
            search_strategy=data.get('search_strategy','auto'),memory_mb=data.get('memory_mb',64),
            objective=data.get('objective','balanced'),operation_weight=data.get('operation_weight'),
            analyze_difficulty=data.get('analyze_difficulty'),
            held_weight=data.get('held_weight'),diagnostic_routes=data.get('diagnostic_routes',32))
        result['initial'] = initial.tolist()
        result['initial_environment'] = environment
        result['source_preparation'] = prepared['preparation']
        result['warnings'] = sorted(prepared['warnings']+result.get('warnings',[]), key=lambda row: row['line'])
        result['visualization_mode'] = visualization_mode
        if result['status'] == 'candidate_found':
            from .csv_visualization import build_csv_visualization, build_csv_entry_scene
            if reporter is not None:
                reporter.phase('visualization')
            started = time.perf_counter()
            builder = build_csv_entry_scene if visualization_mode == 'entry' else build_csv_visualization
            result['visualization'] = builder(path, result, **settings)
            result['visualization_seconds'] = time.perf_counter()-started
        result['request_seconds'] = time.perf_counter()-began
        if implementation_hashes() != _LOADED_IMPLEMENTATION:
            raise ValueError('Solver source changed during this request; candidate provenance is invalid')
        result['provenance'] = dict(fresh_computation=True, route_cache_hit=False,
            request_id=request_id, implementation_sha256=dict(_LOADED_IMPLEMENTATION))
        if reporter is not None:
            reporter.finish(status=result['status'], reason=result.get('reason'))
        return result
