"""Cold native portfolio for fully resolved source worlds, scalar checked."""
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
from .native_backend import search,available_cpu_workers,report_progress,replay_hint,load_backend
from .source_policy import preflight


def verify_candidate(path, initial, settings, actions, expected, binding, initial_target_history=None, progress=None):
    """Rebuild monolithic source environment; use original scalar bodies only."""
    report_progress(progress,phase='verify',tick=0,ticks=len(actions),alive_states=None,
        message='Independent scalar replay')
    player=scalar_module('discrete_operator');collisions=scalar_module('cspace')
    template=ParametricEnvironment(path,backend='reference',**settings)
    rebuilt=bind_initial_target_history(template,initial_target_history)
    state=player.initial_state(initial,rebuilt.wave.env_schedule[0])
    while rebuilt.pending_target is not None and rebuilt.pending_target['tick']==0:
        rebuilt=template.extend(rebuilt,float(state[0]),float(state[1]))
    if not rebuilt.complete or rebuilt.wave.termination_reason not in ('endattack','eof_hazards_drained') or rebuilt.identity!=binding.identity:return False,'replay_binding_mismatch'
    wave=rebuilt.wave
    if len(actions)!=len(wave.env_schedule)-1:return False,'replay_incomplete'
    trace=np.empty((len(actions)+1,11),np.float64);trace[0]=state
    from .source_verification import scalar_collision_checker
    check=scalar_collision_checker(wave)
    next_update=time.perf_counter()+.1
    for tick in range(len(trace)):
        if tick:
            player.step_mask_into(state,int(actions[tick-1]),wave.env_schedule[tick],wave.platform_table[tick],state)
            trace[tick]=state
        if not np.isfinite(state).all() or check(tick,state):return False,'replay_collision'
        if tick==len(actions) or time.perf_counter()>=next_update:
            report_progress(progress,phase='verify',tick=tick,ticks=len(actions),alive_states=None)
            next_update=time.perf_counter()+.1
    if trace.tobytes()!=expected.tobytes():return False,'replay_state_mismatch'
    return True,'verified_'+wave.termination_reason


def find_native_candidate(path, initial, *, width=3000, seconds=30., selection_seed=42,
                          workers=None, memory_mb=64, initial_target_history=None, progress=None,
                          _resolved=None, _defer_verification=False, _terminal_target=None,
                          _preferred_actions=None, _skip_policies=False, **settings):
    if type(width) is not int or width<1:raise ValueError('width must be a positive integer')
    if not isinstance(seconds,(int,float)) or not math.isfinite(seconds) or seconds<0:raise ValueError('seconds must be finite and nonnegative')
    if type(memory_mb) is not int or not 1<=memory_mb<=4096:raise ValueError('memory_mb must be in [1,4096]')
    workers=available_cpu_workers() if workers is None else workers
    if type(workers) is not int or not 1<=workers<=32:raise ValueError('workers must be in [1,32]')
    prepared=time.perf_counter()
    report_progress(progress,phase='bake',tick=0,ticks=None,alive_states=None,
        message='Preparing source world')
    template=ParametricEnvironment(path,**settings) if _resolved is None else _resolved[0]
    binding=bind_initial_target_history(template,initial_target_history) if _resolved is None else _resolved[1]
    player=scalar_module('discrete_operator')
    state=player.initial_state(initial,binding.wave.env_schedule[0])
    while binding.pending_target is not None and binding.pending_target['tick']==0:
        binding=template.extend(binding,float(state[0]),float(state[1]))
    # Only a completed source world may enter this probe; EOF still needs a release invariant.
    if not binding.complete or binding.wave.termination_reason not in ('endattack','eof_hazards_drained'):return None
    wave=binding.wave;env=wave.env_schedule
    if seconds==0:return None
    # A rolling proposal comes only from an earlier window in this request.
    # Re-execute its controls in the newly sampled world before using its end
    # state to seed a short suffix search. Fall back to the full window if this
    # single-state continuation cannot find an escape.
    from .search_preferences import current,input_cost
    config=current()
    if config['objective']!='human_friendly' and _defer_verification and _terminal_target is None and _preferred_actions and load_backend.cache_info().currsize:
        count=min(len(_preferred_actions),len(env)-2)
        if count>0:
            hint_started=time.perf_counter()
            prefix=replay_hint(state,wave,_preferred_actions[:count])
            if prefix is not None:
                names=('env_schedule','platform_table','geometry_white','geometry_blue','geometry_polygons')
                suffix=SimpleNamespace(**{name:getattr(wave,name)[count:] for name in names},
                    termination_reason=wave.termination_reason)
                suffix_binding=SimpleNamespace(wave=suffix,pending_target=None,complete=True,
                    history=binding.history,identity=binding.identity)
                trial=find_native_candidate(path,prefix[-1],width=width,seconds=min(seconds,.004),
                    selection_seed=selection_seed,workers=workers,memory_mb=memory_mb,
                    _resolved=(template,suffix_binding),_defer_verification=True,**settings)
                if trial is not None and trial.status=='proposal_found':
                    trial.actions=list(_preferred_actions[:count])+trial.actions
                    trial.trajectory=np.concatenate((prefix[:-1],trial.trajectory))
                    trial.reached_tick=len(trial.actions);trial.bindings=[binding]
                    trial.stats['continued_proposal_ticks']=count
                    trial.stats['search_seconds']=time.perf_counter()-hint_started
                    report_progress(progress,phase='search',tick=len(env)-1,ticks=len(env)-1,alive_states=1,
                        expanded_states=trial.stats.get('expanded_states',0),
                        discarded_states=trial.stats.get('discarded_states',0),
                        unique_states=sum(row['unique'] for row in trial.stats.get('probe_attempts',())))
                    return trial
            seconds=max(.001,seconds-(time.perf_counter()-hint_started))
    report_progress(progress,phase='search',tick=0,ticks=len(env)-1,alive_states=1,
        expanded_states=0,discarded_states=0,unique_states=0)
    controls=(0,1,2,4,5,6,8,9,10) if config['objective']=='human_friendly' else tuple(range(16))
    quick=preflight(state,wave,seconds) if config['objective']=='balanced' and (config['operation_weight'],config['held_weight'])==(12,1) and not _skip_policies and _terminal_target is None and not load_backend.cache_info().currsize else None
    if quick is None:
        if config['objective']=='human_friendly':
            natural=np.array([0,1,2,4,5,6,8,9,10],np.int64)
            table=np.tile(natural,(len(env)-1,1));counts=np.full(len(env)-1,len(natural),np.int64)
        elif config['objective']=='fewest_operations':
            table=np.tile(np.arange(16,dtype=np.int64),(len(env)-1,1));counts=np.full(len(env)-1,16,np.int64)
        else:table,counts=single_tick_control_table(env,controls)
    else:table=np.empty((len(env)-1,16),np.int64);counts=np.empty(len(table),np.int64)
    # Shared world tensors; private rolling states and compact back-pointers.
    jobs=[(min(width,w),int(selection_seed)+offset*0x9e3779b9)
          for w in (8,32,128) for offset in range(3)]
    jobs=list(dict.fromkeys((w,s&0xffffffff) for w,s in jobs))
    # Budget all job workspaces conservatively, including candidate/hash arrays.
    allowance=memory_mb*1024*1024
    chosen=[];allocated=0
    for w,s in jobs:
        estimate=len(env)*w*(3 if w<=65535 else 4)+w*16*332+w*256+(w*64*48+512 if w>=512 else 0)+len(env)*32
        if allocated+estimate<=allowance:chosen.append((w,s));allocated+=estimate
    if not chosen:return None
    macro_limit=min(width,1024,max(1,(allowance-allocated)//(8*(7000+len(env)*5))))
    macro_width=1
    while macro_width*2<=macro_limit:macro_width*=2
    environment_seconds=time.perf_counter()-prepared
    def search_progress(offsets):
        def publish(**fields):
            fields=dict(fields)
            for name,value in offsets.items():
                if name in fields:fields[name]+=value
            report_progress(progress,**fields)
        return publish
    winner,actions,trace,attempts,metadata=quick if quick is not None else search(state,wave,table,counts,[w for w,s in chosen],
        [s for w,s in chosen],workers,min(seconds,max(.2,len(env)*.0006)),terminal_target=_terminal_target,progress=progress,skip_policies=_skip_policies,race=_defer_verification and len(env)>=1000,macro_width=macro_width)
    first_kernel_seconds=metadata['kernel_load_seconds']
    diagnostic_routes=list(metadata.pop('diagnostic_routes',[]))
    diagnostic_truncated=metadata.pop('diagnostic_truncated',False)
    first_compiled=metadata['compiled']
    peak_workspace=metadata.get('peak_workspace_bytes',sum(item['workspace_bytes'] for item in attempts))
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
            offsets={name:sum(item[key] for item in attempts) for name,key in
                (('expanded_states','expanded'),('discarded_states','discarded'),('unique_states','unique'))}
            second,actions,trace,more,later=search(state,wave,table,counts,[w for w,s in wide],
                [s for w,s in wide],workers,remaining,terminal_target=_terminal_target,
                progress=search_progress(offsets) if progress is not None else None,skip_policies=True,race=_defer_verification and len(env)>=1000)
            diagnostic_routes+=later.pop('diagnostic_routes',[])
            diagnostic_truncated=diagnostic_truncated or later.pop('diagnostic_truncated',False)
            winner=offset+second if second>=0 else second
            peak_workspace=max(peak_workspace,later.get('peak_workspace_bytes',sum(item['workspace_bytes'] for item in more)))
            attempts+=more;chosen+=wide
            total_search_seconds+=later['search_seconds'];total_search_cpu+=later['search_cpu_seconds']
            total_process_cpu+=later['process_cpu_seconds'];total_index_seconds+=later.get('collision_index_seconds') or 0.
            total_hash_rebuilds+=later.get('state_hash_rebuilds',0)
            metadata=dict(later)
    metadata=dict(metadata,kernel_load_seconds=first_kernel_seconds,compiled=first_compiled,
        search_seconds=total_search_seconds,search_cpu_seconds=total_search_cpu,
        process_cpu_seconds=total_process_cpu,collision_index_seconds=total_index_seconds,state_hash_rebuilds=total_hash_rebuilds,
        effective_search_cores=total_search_cpu/total_search_seconds if total_search_seconds else 0.)
    report_progress(progress,phase='search',tick=len(env)-1 if winner>=0 else max((item['reached'] for item in attempts),default=0),
        ticks=len(env)-1,alive_states=1 if winner>=0 else 0,
        expanded_states=sum(item['expanded'] for item in attempts),
        discarded_states=sum(item['discarded'] for item in attempts),unique_states=sum(item['unique'] for item in attempts))
    if winner<0:
        # This world was handled natively. Do not surprise an exhausted request
        # with a second compiler or a retired search path.
        clock=dict(protocol='explicit_dt_schedule' if settings.get('dt_schedule') is not None else 'native_fixed_240' if settings.get('clock_start_ms') is not None else 'nominal_240',decision_ticks=1,original_replay_passed=False)
        if template.dt_schedule is not None:clock.update(schedule_count=len(template.dt_schedule),schedule_sha256=template.schedule_sha256)
        return SimpleNamespace(status='unknown',reason='initial_collision' if winner==-2 else 'native_search_limited',
            verified=False,reached_tick=0,actions=[],trajectory=state.reshape(1,11),target_history=binding.history,
            diagnostic_routes=diagnostic_routes,diagnostic_truncated=diagnostic_truncated,
            bindings=[binding],layers=[],clock=clock,stats=dict(backend='native-portfolio',probe_attempts=attempts,
                expanded_states=sum(item['expanded'] for item in attempts),search_seconds=total_search_seconds,
                kernel_materialization_seconds=first_kernel_seconds,environment_setup_seconds=environment_seconds,
                verification_seconds=0.,native_code=metadata))
    verify_started=time.perf_counter()
    valid,why=(True,'provisional_world') if _defer_verification else verify_candidate(path,initial,settings,actions,trace,binding,initial_target_history,progress)
    if not valid:raise RuntimeError('Native candidate rejected by unchanged scalar replay: '+why)
    word=actions.tolist()
    stats=dict(width=width,controls=controls,selection_seed=selection_seed,
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
        input_cost=input_cost(word,int(state[4])))
    clock=dict(protocol='explicit_dt_schedule' if settings.get('dt_schedule') is not None else 'native_fixed_240' if settings.get('clock_start_ms') is not None else 'nominal_240',decision_ticks=1,original_replay_passed=False)
    if template.dt_schedule is not None:clock.update(schedule_count=len(template.dt_schedule),schedule_sha256=template.schedule_sha256)
    return SimpleNamespace(status='proposal_found' if _defer_verification else 'candidate_found',reason=why,verified=not _defer_verification,reached_tick=len(word),actions=word,
        trajectory=trace,target_history=binding.history,terminal_tail=(dict(status='proven',reason='endattack')
            if wave.termination_reason=='endattack' else dict(status='unknown',reason='release_invariant_required')),
        bindings=[binding],layers=[],stats=stats,clock=clock)
