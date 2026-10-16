"""Read-only live progress for one CSV solve attempt.

A solve is a single blocking request, so a browser cannot observe anything until
the response returns. This module keeps a small, lock-guarded registry with the
latest snapshot per attempt id; the page polls it through
``GET /api/progress/<id>`` (see :mod:`nohit.dashboard.server`).

Nothing here influences the solve. The reporter only records numbers the solver
already maintains, every call is O(1) under a lock, and a request without a
``progress_id`` behaves exactly as it did before telemetry existed.

``fraction`` is the best honest estimate and is never invented: when the search
is bounded by its tick horizon the fraction is ``tick / ticks`` and
``fraction_basis`` is ``tick_horizon``; otherwise, with a wall-clock search
budget, it is ``elapsed / seconds`` with basis ``wall_budget``; with neither it
stays ``null`` and the basis is ``unknown``.
"""
from __future__ import annotations

import math
import threading
import time

SCHEMA_VERSION = 1
MAX_ENTRIES = 64
TTL_SECONDS = 900.0
_MESSAGE_LIMIT = 500
# Counters are published as finite integers or as null. Anything else (NaN,
# +-inf, a non-integral float, a string) is reported as unknown rather than
# serialised: the route uses plain json.dumps, so one non-finite value would
# emit `NaN` and the page's response.json() would fail to parse.
_NUMERIC_FIELDS = ('tick', 'ticks', 'alive_states', 'peak_alive_states',
                   'expanded_states', 'discarded_states', 'unique_states',
                   'committed_tick', 'estimated_total_ticks')

_LOCK = threading.Lock()
_ENTRIES: dict[str, dict] = {}

_SNAPSHOT_FIELDS = ('schema_version', 'progress_id', 'state', 'phase', 'engine',
                    'elapsed_seconds', 'tick', 'ticks', 'alive_states',
                    'peak_alive_states', 'expanded_states', 'discarded_states',
                    'states_per_second', 'fraction', 'fraction_basis', 'updated_at',
                    'message', 'committed_tick', 'estimated_total_ticks',
                    'estimated_total_ticks_basis', 'eta_seconds', 'eta_basis')


def _now():
    # perf_counter, not monotonic: Windows' monotonic() has ~15.6 ms granularity,
    # which makes a same-tick update look like zero elapsed time. It is used for
    # elapsed time and expiry only; the published `updated_at` is epoch seconds
    # so a browser can compare it against Date.now().
    return time.perf_counter()


def _epoch():
    return time.time()


def _finite_counts(value):
    """Returns a finite Python int, or None when the value cannot be published."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            return None
    return int(value)


def _expire_locked():
    now = _now()
    for key in [key for key, entry in _ENTRIES.items()
                if now - entry.get('_updated_mono', entry['updated_at']) > TTL_SECONDS]:
        _ENTRIES.pop(key, None)
    while len(_ENTRIES) > MAX_ENTRIES:
        _ENTRIES.pop(min(_ENTRIES, key=lambda key: _ENTRIES[key].get('_updated_mono', _ENTRIES[key]['updated_at'])), None)


def _public(entry):
    result = {key: entry.get(key) for key in _SNAPSHOT_FIELDS}
    if entry['state'] == 'running':
        # Polling advances the elapsed clock, never the solver's counters or
        # last-update timestamp. Finished snapshots retain their final timing.
        result.update(_timing_fields(entry))
    return result


def _timing_fields(entry):
    now = _now()
    elapsed = now - entry['_began']
    if not math.isfinite(elapsed) or elapsed < 0:
        elapsed = 0.0
    expanded = entry.get('expanded_states')
    result = dict(elapsed_seconds=round(elapsed, 6),
        states_per_second=round(expanded / elapsed, 3) if isinstance(expanded, int) and elapsed > 0 else None)
    tick, ticks = entry.get('tick'), entry.get('ticks')
    budget = entry['_seconds_budget']
    if isinstance(ticks, int) and ticks > 0 and isinstance(tick, int):
        result.update(fraction=round(min(1.0, max(0.0, tick / float(ticks))), 6),fraction_basis='tick_horizon')
    elif budget:
        result.update(fraction=round(min(1.0, max(0.0, elapsed / budget)), 6),fraction_basis='wall_budget')
    elif isinstance(ticks, int) and ticks > 0:
        result.update(fraction=0.0,fraction_basis='tick_horizon')
    else:
        result.update(fraction=None,fraction_basis='unknown')
    result.update(_eta_fields(entry,now))
    return result


def _eta_stage(phase):
    # Source baking and native search alternate in every observation window.
    # They share one source-progress rate; scalar verification starts anew.
    return 'source' if phase in ('bake','search') else 'verify' if phase=='verify' else None


def _eta_fields(entry,now):
    unknown=dict(eta_seconds=None,eta_basis='unknown')
    if entry['state']!='running':return unknown
    stage=entry.get('_eta_stage')
    if stage=='source':
        tick,total=entry.get('committed_tick'),entry.get('estimated_total_ticks')
        basis=entry.get('estimated_total_ticks_basis')
        if basis!='csv_literal_duration_estimate':return unknown
        # Reaching a literal estimate does not establish a source terminal.
        if not isinstance(total,int) or not isinstance(tick,int) or tick>=total:return unknown
    elif stage=='verify':
        tick,total=entry.get('tick'),entry.get('ticks');basis='scalar_replay_tick_rate'
    else:return unknown
    if not isinstance(total,int) or total<=0 or not isinstance(tick,int) or not 0<=tick<=total:return unknown
    advanced=tick-entry.get('_eta_start_tick',0);elapsed=now-entry['_eta_began']
    if advanced<=0 or elapsed<=0:return unknown
    try:seconds=(total-tick)*elapsed/advanced
    except (OverflowError,ZeroDivisionError):return unknown
    if not math.isfinite(seconds) or seconds<0:return unknown
    return dict(eta_seconds=round(seconds,3),eta_basis=basis)


def unknown_snapshot(progress_id):
    """The explicit 'nothing was ever registered here' answer."""
    return dict(schema_version=SCHEMA_VERSION, progress_id=progress_id, state='unknown',
                phase=None, engine=None, elapsed_seconds=None, tick=None, ticks=None,
                alive_states=None, peak_alive_states=None, expanded_states=None,
                discarded_states=None, states_per_second=None, fraction=None,
                fraction_basis='unknown', updated_at=_epoch(), message=None,
                committed_tick=None,estimated_total_ticks=None,estimated_total_ticks_basis=None,
                eta_seconds=None,eta_basis='unknown')


class ProgressReporter:
    """Records the latest snapshot for one attempt. Never raises into the solve."""

    def __init__(self, progress_id, engine=None, seconds_budget=None, ticks=None,
                 estimated_total_ticks=None,estimated_total_ticks_basis=None):
        self.progress_id = str(progress_id)
        self._began = _now()
        entry = dict(schema_version=SCHEMA_VERSION, progress_id=self.progress_id,
                     state='running', phase='prepare', engine=engine, elapsed_seconds=0.0,
                     tick=None, ticks=ticks, alive_states=None, peak_alive_states=None,
                     expanded_states=None, discarded_states=None, states_per_second=None,
                     fraction=None, fraction_basis='unknown', updated_at=_epoch(),
                     message=None,committed_tick=None,
                     estimated_total_ticks=_finite_counts(estimated_total_ticks),
                     estimated_total_ticks_basis=estimated_total_ticks_basis,
                     eta_seconds=None,eta_basis='unknown')
        entry['_began'] = self._began
        entry['_updated_mono'] = self._began
        entry['_seconds_budget'] = float(seconds_budget) if seconds_budget else None
        entry.update(_eta_stage=None,_eta_began=self._began,_eta_start_tick=0,_eta_last_tick=None,
            _eta_verify_baseline=False)
        with _LOCK:
            _ENTRIES[self.progress_id] = entry
            _expire_locked()
        # Resolve fraction/fraction_basis now, so a fresh attempt already
        # reports the basis it is being measured against.
        self._write()

    def _write(self, **fields):
        with _LOCK:
            entry = _ENTRIES.get(self.progress_id)
            if entry is None:
                return
            # A terminal snapshot is immutable: a late phase() or a second
            # finish() must not resurrect a finished attempt.
            if entry['state'] in ('done', 'failed'):
                return
            if 'phase' in fields and fields['phase'] != entry['phase'] and 'message' not in fields:
                fields['message'] = None
            for key in _NUMERIC_FIELDS:
                if key in fields:
                    fields[key] = _finite_counts(fields[key])
            entry.update(fields)
            now=_now();stage=_eta_stage(entry['phase'])
            stage_tick=entry.get('committed_tick' if stage=='source' else 'tick')
            previous_tick=entry.get('_eta_last_tick')
            if (stage!=entry['_eta_stage'] or fields.get('phase')=='prepare' or
                    isinstance(stage_tick,int) and isinstance(previous_tick,int) and stage_tick<previous_tick):
                entry.update(_eta_stage=stage,_eta_began=now,
                    _eta_start_tick=stage_tick if isinstance(stage_tick,int) else 0,_eta_last_tick=None,
                    _eta_verify_baseline=False)
            if stage=='verify' and isinstance(stage_tick,int) and stage_tick>0 and not entry['_eta_verify_baseline']:
                # The first advancing sample follows an opaque source rebuild.
                # Measure scalar replay only between actual advancing samples.
                entry.update(_eta_began=now,_eta_start_tick=stage_tick,_eta_verify_baseline=True)
            if isinstance(stage_tick,int):entry['_eta_last_tick']=stage_tick
            entry['updated_at'] = _epoch()
            entry['_updated_mono'] = _now()
            alive = entry.get('alive_states')
            peak = entry.get('peak_alive_states')
            if isinstance(alive, int) and (peak is None or alive > peak):
                entry['peak_alive_states'] = alive
            entry.update(_timing_fields(entry))

    def phase(self, name, **fields):
        self._write(**dict(fields, phase=str(name), state='running'))

    def update(self, **fields):
        fields.pop('elapsed_seconds', None)
        self._write(**fields)

    def finish(self, state='done', message=None, **fields):
        """Marks the attempt terminal. Extra fields become a readable message."""
        if message is None and fields:
            message = ', '.join(f'{key}={value}' for key, value in fields.items())
        self._write(state=str(state), message=message)

    def fail(self, message):
        self._write(state='failed', message=str(message)[:_MESSAGE_LIMIT])


def begin(progress_id, engine=None, seconds_budget=None, ticks=None,
          estimated_total_ticks=None,estimated_total_ticks_basis=None):
    """Registers a fresh running attempt and returns its reporter."""
    return ProgressReporter(progress_id, engine=engine, seconds_budget=seconds_budget, ticks=ticks,
        estimated_total_ticks=estimated_total_ticks,estimated_total_ticks_basis=estimated_total_ticks_basis)


def snapshot(progress_id):
    """Returns the JSON-ready snapshot for ``progress_id`` (never a 404)."""
    with _LOCK:
        _expire_locked()
        entry = _ENTRIES.get(progress_id)
        if entry is None:
            return unknown_snapshot(progress_id)
        return _public(entry)


__all__ = ['SCHEMA_VERSION', 'ProgressReporter', 'begin', 'snapshot', 'unknown_snapshot']
