"""Public first-slice solver: fresh environment, native search, explicit limits."""
import hashlib
import time
from pathlib import Path

import numpy as np

from .compact_wave import ROOT, CSV_HASH, compile_wave, prepare_collision_native
from .compact_lattice import native_micro_into, search_frs_dp_bellman, reconstruct_native


def _cache_state(function):
    return (len(function.signatures),sum(function._cache_hits.values()),sum(function._cache_misses.values()))


def _load_mode(function,before):
    after=_cache_state(function)
    if after[2]>before[2]:
        return 'compiled'
    if after[1]>before[1]:
        return 'disk_build_cache'
    return 'already_loaded'


def solve_platforms4hard(path=None, max_expansions=10000000, max_dead=4000000, margin_x=1.0, margin_y=2.0, anticipation=12, initial_product=True, deadband=6.0, h_toggle_weight=0.01, max_states=30000, max_beam=0, exact=True):
    if max_expansions<1 or max_dead<1 or max_states<1 or max_beam<0:
        raise ValueError('resource limits must be positive')
    if not np.isfinite(margin_x) or not np.isfinite(margin_y) or min(margin_x,margin_y)<0 or not 0<=anticipation<=438:
        raise ValueError('margins must be finite and nonnegative; anticipation must be within the wave')
    path=Path(path) if path else ROOT/'c2-sans-fight/sans_platforms4hard.csv'
    if path.name != 'sans_platforms4hard.csv' or hashlib.sha256(path.read_bytes()).hexdigest() != CSV_HASH:
        raise ValueError('unsupported_mechanism: legacy kernel only supports the exact Platforms4Hard CSV')
    start=time.perf_counter()
    schedule,geometry,initial=compile_wave(path,legacy_calibrated=True)
    compiled=time.perf_counter()
    collision_cache=_cache_state(prepare_collision_native)
    mask=prepare_collision_native(geometry,margin_x=margin_x,margin_y=margin_y)
    prepared=time.perf_counter()
    starts=initial.copy()
    if initial_product:
        starts=np.tile(initial,9)
        for group in range(3):
            starts[group*15+8]=.75
            starts[group*15+13]=0.
    search_cache=_cache_state(search_frs_dp_bellman)
    status,frame,expansions,visits,actions=search_frs_dp_bellman(mask,schedule,starts,max_states=max_states,deadband=deadband,h_toggle_weight=h_toggle_weight,max_beam=max_beam,anticipation=anticipation,exact=exact,max_expansions=max_expansions)
    searched=time.perf_counter()
    reconstruction_cache=_cache_state(reconstruct_native)
    trace_arr=reconstruct_native(initial,actions,schedule)
    trace=trace_arr.tolist()
    done=time.perf_counter()
    return {'status':['candidate_found','exhausted_in_declared_model','resource_limit','search_limited'][status],
        'wave':path.name,'kernel_id':'compact-float64-platforms-product-v3','operator':'topological-frs-dp',
        'model_scope':'audited Platforms4Hard CSV; calibrated clock; initial speed product 58.5/0.75/0 and three balanced microclock profiles; 438 frames',
        'collision_model':'conservative_bbox_fractional_cell_cover','margin_x':margin_x,'margin_y':margin_y,'anticipation':anticipation,'deadband':deadband,'h_toggle_weight':h_toggle_weight,'no_beam_pruning':max_beam==0,
        'exact_state_folding':bool(exact),'max_states':max_states,'max_beam':max_beam,'max_expansions':max_expansions,
        'complete_search_configuration':bool(exact and max_beam==0),
        'route_optimality':'minimum_declared_cost_in_retained_graph' if status==0 else None,
        'enumeration_exhausted':status==1,'actions':actions.tolist(),'trajectory':trace,
        'initial_states':starts.reshape((-1,5)).tolist(),'frame':int(frame),'expansions':int(expansions),'visits':visits.tolist(),
        'original_replay_passed':False,'realtime_passed_three':False,
        'environment_cache_hit':False,'route_cache_hit':False,
        'kernel_load':{'collision':_load_mode(prepare_collision_native,collision_cache),
            'search':_load_mode(search_frs_dp_bellman,search_cache),
            'reconstruction':_load_mode(reconstruct_native,reconstruction_cache)},
        'csv_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'kernel_sha256':hashlib.sha256((ROOT/'nohit/engine/compact_lattice.py').read_bytes()).hexdigest(),
        'clock_sha256':hashlib.sha256((ROOT/'tests/fixtures/platforms4hard-clock.json').read_bytes()).hexdigest(),
        'timing_ms':{'csv_compile':(compiled-start)*1000,'collision_prepare_including_load':(prepared-compiled)*1000,
            'search_including_load':(searched-prepared)*1000,'reconstruction':(done-searched)*1000,
            'first_route_wall':(done-start)*1000}}
