"""Direct local CSV input for the source-model dashboard."""
import hashlib
import math
from pathlib import Path
import tempfile
import time
import uuid

import numpy as np

from nohit.engine.csv_solver import solve_csv

from . import solve_progress


_ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION_PATHS = tuple(sorted(
    [path.relative_to(_ROOT).as_posix() for path in (_ROOT/'nohit/engine').glob('*.py')]
    + ['nohit/dashboard/csv_api.py', 'nohit/dashboard/csv_visualization.py']))


def implementation_hashes():
    return {name: hashlib.sha256((_ROOT/name).read_bytes()).hexdigest()
            for name in IMPLEMENTATION_PATHS}


# A long-running dashboard must not claim newly edited files describe its
# already imported implementation. Restart it when solver sources change.
_LOADED_IMPLEMENTATION = implementation_hashes()


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
        reporter = solve_progress.begin(progress_id, engine='bounded-frontier-with-dialogue',
                                        seconds_budget=data.get('seconds', 30),
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
        result = solve_csv(path, initial, **settings, width=data.get('width', 3000),
            seconds=data.get('seconds', 30), max_bindings=data.get('max_bindings', 1),
            initial_confirm=data.get('initial_confirm',False),
            previous_confirm=data.get('previous_confirm',False),
            initial_target_history=data.get('initial_target_history'), progress=progress)
        result['initial'] = initial.tolist()
        result['initial_environment'] = environment
        if result['status'] == 'candidate_found':
            from .csv_visualization import build_csv_visualization
            if reporter is not None:
                reporter.phase('visualization')
            started = time.perf_counter()
            result['visualization'] = build_csv_visualization(path, result, **settings)
            result['visualization_seconds'] = time.perf_counter()-started
        result['request_seconds'] = time.perf_counter()-began
        if implementation_hashes() != _LOADED_IMPLEMENTATION:
            raise ValueError('Solver source changed during this request; candidate provenance is invalid')
        result['provenance'] = dict(fresh_computation=True, route_cache_hit=False,
            request_id=request_id, implementation_sha256=dict(_LOADED_IMPLEMENTATION))
        if reporter is not None:
            reporter.finish(status=result['status'], reason=result.get('reason'))
        return result
