"""Cold native portfolio for fully resolved EndAttack worlds, scalar checked."""
import hashlib
import math
import os
import time
from types import SimpleNamespace
import numpy as np

from .control_quotient import control_classes, single_tick_control_table
from .initial_target_history import bind_initial_target_history
from .parametric_environment import ParametricEnvironment
from .source_oracle import scalar_module
from .native_backend import search,available_cpu_workers
from .source_policy import preflight


def verify_candidate(path, initial, settings, actions, expected, binding, initial_target_history=None):
    """Rebuild monolithic source environment; use original scalar bodies only."""
    player=scalar_module('discrete_operator');collisions=scalar_module('cspace')
    template=ParametricEnvironment(path,backend='reference',**settings)
    rebuilt=bind_initial_target_history(template,initial_target_history)
    state=player.initial_state(initial,rebuilt.wave.env_schedule[0])
    while rebuilt.pending_target is not None and rebuilt.pending_target['tick']==0:
        rebuilt=template.extend(rebuilt,float(state[0]),float(state[1]))
    if not rebuilt.complete or rebuilt.wave.termination_reason!='endattack' or rebuilt.identity!=binding.identity:return False,'replay_binding_mismatch'
    wave=rebuilt.wave
    if len(actions)!=len(wave.env_schedule)-1:return False,'replay_incomplete'
    trace=np.empty((len(actions)+1,11),np.float64);trace[0]=state
    from .source_verification import scalar_collision_checker
    check=scalar_collision_checker(wave)
    for tick in range(len(trace)):
        if tick:
            player.step_mask_into(state,int(actions[tick-1]),wave.env_schedule[tick],wave.platform_table[tick],state)
            trace[tick]=state
        if not np.isfinite(state).all() or check(tick,state):return False,'replay_collision'
    if trace.tobytes()!=expected.tobytes():return False,'replay_state_mismatch'
    return True,'verified_endattack'


def find_native_candidate(path, initial, *, width=3000, seconds=30., selection_seed=42,
                          workers=None, memory_mb=64, initial_target_history=None, progress=None,
                          _resolved=None, _defer_verification=False, _terminal_target=None, **settings):
    if type(width) is not int or width<1:raise ValueError('width must be a positive integer')
    if not isinstance(seconds,(int,float)) or not math.isfinite(seconds) or seconds<0:raise ValueError('seconds must be finite and nonnegative')
    if type(memory_mb) is not int or not 1<=memory_mb<=4096:raise ValueError('memory_mb must be in [1,4096]')
    workers=available_cpu_workers() if workers is None else workers
    if type(workers) is not int or not 1<=workers<=32:raise ValueError('workers must be in [1,32]')
    prepared=time.perf_counter()
    template=ParametricEnvironment(path,**settings) if _resolved is None else _resolved[0]
    binding=bind_initial_target_history(template,initial_target_history) if _resolved is None else _resolved[1]
    player=scalar_module('discrete_operator')
    state=player.initial_state(initial,binding.wave.env_schedule[0])
    while binding.pending_target is not None and binding.pending_target['tick']==0:
        binding=template.extend(binding,float(state[0]),float(state[1]))
    # No borrowed observations, EOF shortcut or early-success prefix.
    if not binding.complete or binding.wave.termination_reason!='endattack':return None
    wave=binding.wave;env=wave.env_schedule
    if seconds==0:return None
    controls=tuple(range(16))
    quick=preflight(state,wave,seconds) if _terminal_target is None else None
    if quick is None:table,counts=single_tick_control_table(env,controls)
    else:table=np.empty((len(env)-1,16),np.int64);counts=np.empty(len(table),np.int64)
    # Shared world tensors; private rolling states and compact back-pointers.
    jobs=[(min(width,8),selection_seed),(min(width,32),selection_seed),(min(width,128),selection_seed)]
    jobs += [(min(width,128),int(selection_seed)+offset*0x9e3779b9) for offset in range(1,6)]
    jobs=list(dict.fromkeys((w,s&0xffffffff) for w,s in jobs))
    # Budget all job workspaces conservatively, including candidate/hash arrays.
    allowance=memory_mb*1024*1024
    chosen=[];allocated=0
    for w,s in jobs:
        estimate=len(env)*w*(3 if w<=65535 else 4)+w*16*332+w*256+(w*64*48+512 if w>=512 else 0)+len(env)*32
        if allocated+estimate<=allowance:chosen.append((w,s));allocated+=estimate
    if not chosen:return None
    environment_seconds=time.perf_counter()-prepared
    winner,actions,trace,attempts,metadata=quick if quick is not None else search(state,wave,table,counts,[w for w,s in chosen],
        [s for w,s in chosen],workers,min(seconds,0.5),terminal_target=_terminal_target)
    first_kernel_seconds=metadata['kernel_load_seconds']
    first_compiled=metadata['compiled']
    peak_workspace=sum(item['workspace_bytes'] for item in attempts)
    total_search_seconds=metadata['search_seconds'];total_search_cpu=metadata['search_cpu_seconds']
    total_process_cpu=metadata['process_cpu_seconds'];total_index_seconds=metadata.get('collision_index_seconds') or 0.
    total_hash_rebuilds=metadata.get('state_hash_rebuilds',0)
    if winner<0:
        # Wider native fallback shares the same budget and immutable world.
        max_fitting=min(width,65535,max(1,(allowance-len(env)*32)//(len(env)*3+16*332+256+64*48)))
        wide_jobs=list(dict.fromkeys((min(width,w),int(selection_seed)&0xffffffff)
                                     for w in (512,1024,width,max_fitting)))
        wide_jobs += [(min(width,512),(int(selection_seed)+i*0x9e3779b9)&0xffffffff) for i in range(1,6)]
        wide=[];allocated=0
        for w,s in wide_jobs:
            estimate=len(env)*w*(3 if w<=65535 else 4)+w*16*332+w*256+(w*64*48+512 if w>=512 else 0)+len(env)*32
            if allocated+estimate<=allowance:wide.append((w,s));allocated+=estimate
        remaining=seconds-total_search_seconds
        if wide and remaining>0:
            offset=len(attempts)
            second,actions,trace,more,later=search(state,wave,table,counts,[w for w,s in wide],
                [s for w,s in wide],workers,remaining,terminal_target=_terminal_target)
            winner=offset+second if second>=0 else second
            peak_workspace=max(peak_workspace,sum(item['workspace_bytes'] for item in more))
            attempts+=more;chosen+=wide
            total_search_seconds+=later['search_seconds'];total_search_cpu+=later['search_cpu_seconds']
            total_process_cpu+=later['process_cpu_seconds'];total_index_seconds+=later.get('collision_index_seconds') or 0.
            total_hash_rebuilds+=later.get('state_hash_rebuilds',0)
            metadata=dict(later)
    metadata=dict(metadata,kernel_load_seconds=first_kernel_seconds,compiled=first_compiled,
        search_seconds=total_search_seconds,search_cpu_seconds=total_search_cpu,
        process_cpu_seconds=total_process_cpu,collision_index_seconds=total_index_seconds,state_hash_rebuilds=total_hash_rebuilds,
        effective_search_cores=total_search_cpu/total_search_seconds if total_search_seconds else 0.)
    if winner<0:
        # This world was handled natively. Do not surprise an exhausted request
        # with a second heavyweight JIT pass; an explicit fixed run is available.
        clock=dict(protocol='explicit_dt_schedule' if settings.get('dt_schedule') is not None else 'native_fixed_240' if settings.get('clock_start_ms') is not None else 'nominal_240',decision_ticks=1,original_replay_passed=False)
        if template.dt_schedule is not None:clock.update(schedule_count=len(template.dt_schedule),schedule_sha256=hashlib.sha256(np.asarray(template.dt_schedule,dtype='<f8').tobytes()).hexdigest())
        return SimpleNamespace(status='unknown',reason='initial_collision' if winner==-2 else 'native_search_limited',
            verified=False,reached_tick=0,actions=[],trajectory=state.reshape(1,11),target_history=binding.history,
            bindings=[binding],layers=[],clock=clock,stats=dict(backend='native-portfolio',probe_attempts=attempts,
                expanded_states=sum(item['expanded'] for item in attempts),search_seconds=total_search_seconds,
                kernel_materialization_seconds=first_kernel_seconds,environment_setup_seconds=environment_seconds,
                verification_seconds=0.,native_code=metadata))
    verify_started=time.perf_counter()
    valid,why=(True,'provisional_world') if _defer_verification else verify_candidate(path,initial,settings,actions,trace,binding,initial_target_history)
    if not valid:raise RuntimeError('Native candidate rejected by unchanged scalar replay: '+why)
    word=actions.tolist();churn=sum(mask!=(word[i-1] if i else 0) for i,mask in enumerate(word));held=sum(mask!=0 for mask in word)
    stats=dict(width=width,max_bindings=1,controls=controls,selection_seed=selection_seed,
        expanded_states=sum(item['expanded'] for item in attempts),safe_transition_rows=sum(item['generated'] for item in attempts),
        discarded_states=sum(item['discarded'] for item in attempts),observation_discarded_states=0,
        environment_setup_seconds=environment_seconds,verification_seconds=time.perf_counter()-verify_started,
        kernel_materialization_seconds=metadata['kernel_load_seconds'],search_seconds=metadata['search_seconds'],
        backend='native-portfolio',workers=metadata.get('workers_used',min(workers,len(chosen))),probe_attempts=attempts,winning_probe=winner,
        winning_probe_width=attempts[winner]['width'],workspace_bytes=peak_workspace,workspace_allocated_bytes_cumulative=sum(item['workspace_bytes'] for item in attempts),
        workspace_budget_bytes=allowance,shared_world_bytes=sum(array.nbytes for array in
            (wave.env_schedule,wave.platform_table,wave.geometry_white,wave.geometry_blue,wave.geometry_polygons)),
        retained_trace_bytes=trace.nbytes,layer_counts_scope='retained_native_witness',layer_counts=[],
        route_cache=False,environment_cache=False,native_code=metadata,
        input_cost=dict(frames=len(word),churn=churn,held_frames=held,churn_weight=12,held_weight=1,total=churn*12+held))
    clock=dict(protocol='explicit_dt_schedule' if settings.get('dt_schedule') is not None else 'native_fixed_240' if settings.get('clock_start_ms') is not None else 'nominal_240',decision_ticks=1,original_replay_passed=False)
    if template.dt_schedule is not None:clock.update(schedule_count=len(template.dt_schedule),schedule_sha256=hashlib.sha256(np.asarray(template.dt_schedule,dtype='<f8').tobytes()).hexdigest())
    if progress is not None:progress(tick=len(word),ticks=len(env),alive_states=1,expanded_states=stats['expanded_states'],workers=stats['workers'])
    return SimpleNamespace(status='proposal_found' if _defer_verification else 'candidate_found',reason=why,verified=not _defer_verification,reached_tick=len(word),actions=word,
        trajectory=trace,target_history=binding.history,terminal_tail={'status':'proven','reason':'endattack'},
        bindings=[binding],layers=[],stats=stats,clock=clock)
