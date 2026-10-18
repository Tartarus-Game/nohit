"""Portable native code, compiled once; caches code only, never routes/worlds."""
import ctypes as C
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import threading
import time

import numpy as np

_CPU_TARGET=b''
_TUNE_FLAGS=()
if os.environ.get('NOHIT_NATIVE_TUNE','host')!='portable' and platform.machine().lower() in ('x86_64','amd64'):
    try:
        cpu=Path('/proc/cpuinfo').read_text().split('\n\n',1)[0]
        fields=dict(line.split(':',1) for line in cpu.splitlines() if ':' in line)
        selected=tuple((key,fields.get(key,'')) for key in fields if key.strip() in
            ('vendor_id','cpu family','model','stepping','model name','flags'))
        if any(key.strip()=='flags' for key,value in selected):
            _CPU_TARGET=repr(selected).encode();_TUNE_FLAGS=('-march=native','-mtune=native')
    except OSError:pass
_FLAGS = ('-std=c++17', '-O3', *_TUNE_FLAGS, '-ffp-contract=off', '-fno-fast-math', '-shared', '-fPIC', '-pthread')
_SOURCE = Path(__file__).with_name('native_frontier.cpp')
_LOCK = threading.RLock()


def source_dependencies():
    """Additional build inputs participate in both code-cache and bundle checks."""
    paths=[_SOURCE.with_name('native_simd.hpp')]
    root=Path(__file__).resolve().parents[2]
    paths.extend(root/name for name in ('xmake.lua','vcpkg.json'))
    return {path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in paths if path.is_file()}


class Stats(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in ('expanded', 'generated', 'unique', 'discarded', 'workspace_bytes', 'preview_steps', 'recovery_steps', 'recoveries', 'cpu_nanoseconds')] + [
        ('reached', C.c_int32), ('status', C.c_int32)]


def available_cpu_workers():
    """Respect process affinity and Linux CPU quota; API limit is 32."""
    count=os.cpu_count() or 1
    if hasattr(os,'sched_getaffinity'):
        try:count=min(count,len(os.sched_getaffinity(0)))
        except OSError:pass
    try:
        quota,period=Path('/sys/fs/cgroup/cpu.max').read_text().split()
        if quota!='max':count=min(count,max(1,int(quota)//int(period)))
    except (OSError,ValueError,ZeroDivisionError):pass
    return max(1,min(32,count))


def _ptr(array):
    # ctypes' c_void_p argument converter accepts an integer address directly.
    return array.ctypes.data


def _bundled_binary():
    """Use an installed code image only for its exact source and CPU target."""
    extension='.dll' if os.name=='nt' else '.dylib' if sys.platform=='darwin' else '.so'
    binary=_SOURCE.with_name('_native_frontier'+extension)
    try:
        metadata=json.loads(_SOURCE.with_name('native-build.json').read_text())
        expected=dict(source_sha256=hashlib.sha256(_SOURCE.read_bytes()).hexdigest(),
            compiler_flags=list(_FLAGS),cpu_features_sha256=hashlib.sha256(_CPU_TARGET).hexdigest(),
            system=platform.system(),machine=platform.machine())
        if any(metadata.get(key)!=value for key,value in expected.items()):return None
        if metadata.get('source_dependencies',{})!=source_dependencies():return None
        variant=os.environ.get('NOHIT_NATIVE_SIMD','auto')
        if variant=='off' and metadata.get('highway',False):return None
        if variant=='highway' and not metadata.get('highway',False):return None
        sorter=os.environ.get('NOHIT_NATIVE_SORT','auto')
        if sorter=='std' and metadata.get('pdqsort',False):return None
        if sorter=='pdqsort' and not metadata.get('pdqsort',False):return None
        if metadata.get('binary_sha256')!=hashlib.sha256(binary.read_bytes()).hexdigest():return None
        return binary,metadata
    except (OSError,ValueError,TypeError):return None


@lru_cache(maxsize=1)
def load_backend():
    began = time.perf_counter()
    from nohit.native_runtime import configure_native_runtime
    configure_native_runtime()
    bundled=_bundled_binary() if not os.environ.get('CXX') else None
    compiler = bundled[1]['compiler'] if bundled else shlex.split(os.environ['CXX']) if os.environ.get('CXX') else None
    if compiler is None:
        executable = shutil.which('g++') or shutil.which('clang++')
        if not executable:
            raise RuntimeError('Native CSV backend needs g++ or clang++; install a C++17 compiler')
        compiler = [executable]
    variant=os.environ.get('NOHIT_NATIVE_SIMD','auto')
    if variant not in ('auto','off','highway'):raise ValueError('NOHIT_NATIVE_SIMD must be auto, off or highway')
    sorter=os.environ.get('NOHIT_NATIVE_SORT','auto')
    if sorter not in ('auto','std','pdqsort'):raise ValueError('NOHIT_NATIVE_SORT must be auto, std or pdqsort')
    identity = hashlib.sha256(_SOURCE.read_bytes() + repr((_FLAGS, platform.system(), platform.machine(), compiler,
        source_dependencies(),variant,sorter)).encode()+_CPU_TARGET).hexdigest()
    cache = Path(os.environ.get('NOHIT_NATIVE_CACHE', str(Path.home()/'.cache/nohit-native')))
    cache.mkdir(parents=True, exist_ok=True)
    extension = '.dll' if os.name == 'nt' else '.dylib' if sys.platform == 'darwin' else '.so'
    binary = bundled[0] if bundled else cache / (identity + extension)
    with _LOCK, (cache/(identity+'.lock')).open('a+b') as lock:
        if os.name == 'nt':
            import msvcrt
            if not lock.tell(): lock.write(b'0'); lock.flush()
            lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        compiled = not binary.exists()
        if compiled:
            temporary = cache / (identity + '.' + str(os.getpid()) + '.tmp' + extension)
            try:
                from tools.build_native import build
                metadata=build(temporary,highway=variant!='off',pdqsort=sorter!='std')
                os.replace(temporary, binary)
                binary.with_suffix(binary.suffix+'.json').write_text(json.dumps(metadata))
            finally:
                temporary.unlink(missing_ok=True)
        if os.name == 'nt':
            lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    library = C.CDLL(str(binary))
    P, I = C.c_void_p, C.c_int
    library.nohit_step.argtypes = [P,I,P,P,P,I,P]
    library.nohit_step.restype = I
    library.nohit_rollout.argtypes=[P,P,I,P,I,P];library.nohit_rollout.restype=I
    library.nohit_collision.argtypes = [P,I,P,I,P,I,P,I,P]
    library.nohit_collision.restype = I
    library.nohit_collision_margin.argtypes=library.nohit_collision.argtypes+[C.c_double]
    library.nohit_collision_margin.restype=I
    library.nohit_clearance.argtypes=[P,P,I,P,I,P,I,P];library.nohit_clearance.restype=None
    library.nohit_expand.argtypes = [P,I,P,I,P,I,P,I,P,I,P,I,P,I,I,I,P,P,P]
    library.nohit_expand.restype = I
    library.nohit_search.argtypes = [P,P,I,P,I,P,I,P,I,P,I,P,P,I,P,P,I,I,C.c_double,P,P,P,P]
    library.nohit_search.restype = I
    library.nohit_skip_policies.argtypes=[I];library.nohit_skip_policies.restype=None
    library.nohit_preferences.argtypes=[I,I,I,I];library.nohit_preferences.restype=None
    library.nohit_safety_margin.argtypes=[C.c_double];library.nohit_safety_margin.restype=None
    library.nohit_diagnostic_count.argtypes=[];library.nohit_diagnostic_count.restype=I
    library.nohit_diagnostic_truncated.argtypes=[];library.nohit_diagnostic_truncated.restype=I
    library.nohit_diagnostic_route.argtypes=[I,P,I,P];library.nohit_diagnostic_route.restype=I
    library.nohit_race_probes.argtypes=[I];library.nohit_race_probes.restype=None
    library.nohit_macro_width.argtypes=[I];library.nohit_macro_width.restype=None
    library.nohit_last_macro_width.argtypes=[];library.nohit_last_macro_width.restype=I
    library.nohit_replay.argtypes=[P,P,P,I,P,I,P,I,P,I,P,I,P]
    library.nohit_replay.restype=I
    if hasattr(library,"nohit_search_goal"):
        library.nohit_search_goal.argtypes=library.nohit_search.argtypes+[P]
        library.nohit_search_goal.restype=I
    if hasattr(library,"nohit_search_progress"):
        library.nohit_search_progress.argtypes=library.nohit_search.argtypes+[P,P,P]
        library.nohit_search_progress.restype=I
    if hasattr(library,"nohit_last_index_bytes"):
        library.nohit_last_index_bytes.argtypes=[]
        library.nohit_last_index_bytes.restype=C.c_uint64
    if hasattr(library,"nohit_last_index_seconds"):
        library.nohit_last_index_seconds.argtypes=[];library.nohit_last_index_seconds.restype=C.c_double
    if hasattr(library,"nohit_last_edge_workers"):
        library.nohit_last_edge_workers.argtypes=[];library.nohit_last_edge_workers.restype=I
    if hasattr(library,"nohit_last_portfolio_workers"):
        library.nohit_last_portfolio_workers.argtypes=[];library.nohit_last_portfolio_workers.restype=I
    if hasattr(library,"nohit_last_hash_rebuilds"):
        library.nohit_last_hash_rebuilds.argtypes=[];library.nohit_last_hash_rebuilds.restype=C.c_uint64
    if hasattr(library,"nohit_bones_advance"):
        library.nohit_bones_advance.argtypes=[P,I,C.c_double];library.nohit_bones_advance.restype=I
        library.nohit_bones_geometry.argtypes=[P,I,P];library.nohit_bones_geometry.restype=I
    library.nohit_bones_geometry_clipped.argtypes=[P,I,P,P,P];library.nohit_bones_geometry_clipped.restype=I
    library.nohit_blasters_advance.argtypes=[P,I,C.c_double,P,P];library.nohit_blasters_advance.restype=I
    library.nohit_idle_world.argtypes=[P,I,P,I,P,I,I,P,I,C.c_double,P,P,P,P,P]
    library.nohit_idle_world.restype=I
    build_metadata=bundled[1] if bundled else json.loads(binary.with_suffix(binary.suffix+'.json').read_text())
    return library, dict(build_metadata,source_sha256=hashlib.sha256(_SOURCE.read_bytes()).hexdigest(),
        code_identity=identity, compiled=compiled, compiler=compiler, compiler_flags=list(_FLAGS),
        cpu_target='host' if _CPU_TARGET else 'portable',cpu_features_sha256=hashlib.sha256(_CPU_TARGET).hexdigest(),
        bundled=bool(bundled),binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        kernel_load_seconds=time.perf_counter()-began, route_cache=False, environment_cache=False)


def step_batch(states, masks, environment, platforms):
    states=np.ascontiguousarray(states,dtype=np.float64)
    masks=np.ascontiguousarray(masks,dtype=np.int64)
    environment=np.ascontiguousarray(environment,dtype=np.float64)
    platforms=np.ascontiguousarray(platforms,dtype=np.float64)
    if states.ndim!=2 or states.shape[1]!=11 or masks.shape!=(len(states),):raise ValueError('invalid player batch')
    if environment.shape!=(22,) or platforms.ndim!=2 or platforms.shape[1]!=9:raise ValueError('invalid environment')
    if not np.isfinite(states).all() or not np.isfinite(environment).all() or np.any((masks<0)|(masks>31)):raise ValueError('invalid state or controls')
    output=np.empty_like(states)
    library,_=load_backend()
    library.nohit_step(_ptr(states),len(states),_ptr(masks),_ptr(environment),_ptr(platforms),len(platforms),_ptr(output))
    return output


def expand_batch(states, controls, start, env, platforms, white, blue, polygons, workers=1):
    if type(workers) is not int or not 1<=workers<=32:raise ValueError('workers must be in [1,32]')
    states=np.ascontiguousarray(states,np.float64);controls=np.ascontiguousarray(controls,np.int64)
    arrays=[np.ascontiguousarray(value,np.float64) for value in (env,platforms,white,blue,polygons)]
    env,platforms,white,blue,polygons=arrays;nt=len(env)
    if type(start) is not int or not 0<=start<nt-1:raise ValueError('invalid start tick')
    if states.ndim!=2 or states.shape[1]!=11 or controls.ndim!=1 or np.any(controls<0) or np.any(controls>31):raise ValueError('invalid edge batch')
    if env.shape!=(nt,22) or platforms.ndim!=3 or platforms.shape!=(nt,platforms.shape[1],9):raise ValueError('invalid environment')
    for array,width in ((white,4),(blue,4),(polygons,8)):
        if array.ndim!=3 or array.shape!=(nt,array.shape[1],width):raise ValueError('invalid geometry')
    if not np.isfinite(states).all() or not np.isfinite(env).all():raise ValueError('nonfinite edge inputs')
    capacity=len(states)*len(controls)
    if capacity>10_000_000:raise ValueError('edge buffer exceeds resource limit')
    output=np.empty((capacity,11),np.float64);parents=np.empty(capacity,np.int64);masks=np.empty(capacity,np.int64)
    if capacity==0:return output,parents,masks
    library,_=load_backend()
    count=library.nohit_expand(_ptr(states),len(states),_ptr(controls),len(controls),_ptr(env),nt,
        _ptr(platforms),platforms.shape[1],_ptr(white),white.shape[1],_ptr(blue),blue.shape[1],
        _ptr(polygons),polygons.shape[1],start+1,workers,_ptr(output),_ptr(parents),_ptr(masks))
    if count<0:raise RuntimeError('native edge expansion failed')
    return output[:count],parents[:count],masks[:count]


def collision_batch(states, white, blue, polygons):
    arrays=[np.ascontiguousarray(value,dtype=np.float64) for value in (states,white,blue,polygons)]
    states,white,blue,polygons=arrays
    if states.ndim!=2 or states.shape[1]!=11 or white.ndim!=2 or white.shape[1]!=4 or blue.ndim!=2 or blue.shape[1]!=4 or polygons.ndim!=2 or polygons.shape[1]!=8:raise ValueError('invalid collision batch')
    output=np.empty(len(states),np.uint8)
    library,_=load_backend()
    library.nohit_collision(_ptr(states),len(states),_ptr(white),len(white),_ptr(blue),len(blue),_ptr(polygons),len(polygons),_ptr(output))
    return output


def report_progress(progress, **fields):
    """Telemetry is optional and must never change a solver result."""
    if progress is not None:
        try:
            progress(**fields)
        except Exception:
            pass


def search(initial, wave, controls, counts, widths, seeds, workers, seconds, **options):
    from .search_preferences import current,PREFERENCES,input_cost
    config=current()
    if config['objective']!='human_friendly':
        return _search_native(initial,wave,controls,counts,widths,seeds,workers,seconds,**options)
    began=time.perf_counter();attempts=[];trials=[];cpu=0.;process_cpu=0.;load=0.;compiled=False;peak=0
    index_seconds=0.;hash_rebuilds=0
    levels=(12.,6.,3.,0.)
    for index,margin in enumerate(levels):
        remaining=max(.001,seconds-(time.perf_counter()-began))
        tier_started=time.perf_counter();tier_budget=remaining/(len(levels)-index);best=None;phases=[]
        for fast in (True,False):
            budget=max(0.,tier_budget-(time.perf_counter()-tier_started))
            if not fast and budget<.001:break
            token=PREFERENCES.set(dict(config,_safety_margin_px=margin,_human_fast_trial=fast))
            try:
                winner,actions,trace,probes,metadata=_search_native(initial,wave,controls,counts,
                    widths,seeds,workers,max(.0001,budget*.6 if fast else budget),**options)
            finally:PREFERENCES.reset(token)
            offset=len(attempts);attempts.extend(probes)
            peak=max(peak,sum(p['workspace_bytes'] for p in probes))
            cpu+=metadata['search_cpu_seconds'];process_cpu+=metadata['process_cpu_seconds']
            index_seconds+=metadata.get('collision_index_seconds') or 0.
            hash_rebuilds+=metadata.get('state_hash_rebuilds',0)
            load+=metadata['kernel_load_seconds'];compiled|=metadata['compiled']
            phases.append(dict(kind='safe_candidate' if fast else 'operation_optimization',found=winner>=0,
                search_seconds=metadata['search_seconds']))
            if winner>=0:
                cost=input_cost(actions,int(initial[4]),config)['total']
                if best is None or cost<best[0]:best=(cost,winner+offset,actions,trace,dict(metadata))
            if winner==-2:break  # Initial position already excludes this margin.
        trials.append(dict(margin_px=margin,found=best is not None,phases=phases,
            search_seconds=time.perf_counter()-tier_started))
        if best is not None or index==len(levels)-1:
            if best is not None:_,winner,actions,trace,metadata=best
            metadata.update(search_seconds=time.perf_counter()-began,search_cpu_seconds=cpu,
                process_cpu_seconds=process_cpu,peak_workspace_bytes=peak,
                collision_index_seconds=index_seconds,state_hash_rebuilds=hash_rebuilds,
                effective_search_cores=cpu/max(1e-12,time.perf_counter()-began),
                kernel_load_seconds=load,compiled=compiled,human_margin_trials=trials,
                search_margin_px=margin if best is not None else None,
                portfolio_selection='human-margin-then-lowest-operation-cost-found',
                human_objective_scope='margin_tiers_then_arrow_changes; bounded window heuristic, not global optimum')
            return winner,actions,trace,attempts,metadata


def _search_native(initial, wave, controls, counts, widths, seeds, workers, seconds, *, terminal_target=None, progress=None,skip_policies=False,race=False,macro_width=0):
    if type(workers) is not int or not 1<=workers<=32:raise ValueError('workers must be in [1,32]')
    controls=np.ascontiguousarray(controls,np.int64);counts=np.ascontiguousarray(counts,np.int64)
    initial=np.ascontiguousarray(initial,np.float64)
    arrays=[np.ascontiguousarray(value,np.float64) for value in
            (wave.env_schedule,wave.platform_table,wave.geometry_white,wave.geometry_blue,wave.geometry_polygons)]
    env,platforms,white,blue,polygons=arrays
    widths=np.ascontiguousarray(widths,np.int32);seeds=np.ascontiguousarray(seeds,np.uint32)
    nt=len(env)
    from .search_preferences import current
    config=current()
    if nt*(config['operation_weight']+config['held_weight'])>1_000_000_000:
        raise ValueError('input cost exceeds native integer budget; reduce weights or max_ticks')
    if initial.shape!=(11,) or env.shape!=(nt,22) or controls.ndim!=2 or controls.shape[0]!=nt-1 or counts.shape!=(nt-1,):raise ValueError('invalid search arrays')
    if widths.ndim!=1 or seeds.shape!=widths.shape or not len(widths) or np.any(widths<=0) or np.any(widths>100000):raise ValueError('invalid probes')
    if np.any(counts<1) or np.any(counts>controls.shape[1]) or np.any(controls<0) or np.any(controls>31):raise ValueError('invalid controls')
    if not np.isfinite(initial).all() or not np.isfinite(env).all():raise ValueError('nonfinite search inputs')
    if platforms.shape!=(nt,platforms.shape[1],9) or white.shape!=(nt,white.shape[1],4) or blue.shape!=(nt,blue.shape[1],4) or polygons.shape!=(nt,polygons.shape[1],8):raise ValueError('invalid geometry')
    actions=np.empty(nt-1,np.int64);trace=np.empty((nt,11),np.float64);stats=(Stats*len(widths))()
    load_started=time.perf_counter();miss=load_backend.cache_info().currsize==0
    library,metadata=load_backend()
    metadata=dict(metadata,compiled=bool(miss and metadata['compiled']),kernel_load_seconds=time.perf_counter()-load_started)
    began=time.perf_counter();cpu_began=time.process_time()
    controller_delay=C.c_int32(-1)
    goal=None if terminal_target is None else np.ascontiguousarray(terminal_target,np.float64)
    if goal is not None:
        if goal.shape not in ((2,),(4,)) or not np.isfinite(goal).all():raise ValueError('invalid terminal target')
        if goal.shape==(2,):goal=np.concatenate((goal,np.ones(2)))
        if np.any(goal[2:]<0):raise ValueError('invalid terminal weights')
    invoke=library.nohit_search if goal is None else library.nohit_search_goal
    extra=[] if goal is None else [_ptr(goal)]
    callback=None
    if progress is not None and hasattr(library,'nohit_search_progress'):
        probes={}
        signature=C.CFUNCTYPE(None,C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_uint64,C.c_uint64,C.c_uint64)
        def publish(context,job,tick,alive,expanded,discarded,unique):
            probes[job]=(tick,alive,expanded,discarded,unique)
            report_progress(progress,phase='search',tick=max(row[0] for row in probes.values()),ticks=nt-1,
                alive_states=sum(row[1] for row in probes.values()),
                expanded_states=sum(row[2] for row in probes.values()),
                discarded_states=sum(row[3] for row in probes.values()),
                unique_states=sum(row[4] for row in probes.values()))
        callback=signature(publish)
        invoke=library.nohit_search_progress
        extra=[None if goal is None else _ptr(goal),C.cast(callback,C.c_void_p),None]
    fast_human=config.get('_human_fast_trial',False)
    library.nohit_skip_policies(int(skip_policies or ((config['operation_weight'],config['held_weight'])!=(12,1) and not fast_human)))
    library.nohit_race_probes(int(race))
    library.nohit_macro_width(int(macro_width))
    library.nohit_safety_margin(config.get('_safety_margin_px',0.))
    mode=(3 if fast_human else 2) if config['objective']=='human_friendly' else int(config['objective']=='fewest_operations')
    library.nohit_preferences(mode,config['operation_weight'],
        config['held_weight'],config['diagnostic_routes'])
    winner=invoke(_ptr(initial),_ptr(env),nt,_ptr(platforms),platforms.shape[1],
        _ptr(white),white.shape[1],_ptr(blue),blue.shape[1],_ptr(polygons),polygons.shape[1],
        _ptr(controls),_ptr(counts),controls.shape[1],_ptr(widths),_ptr(seeds),len(widths),workers,seconds,
        _ptr(actions),_ptr(trace),C.cast(stats,C.c_void_p),C.byref(controller_delay),*extra)
    attempts=[dict(width=int(width),seed=int(seed),**{name:int(getattr(stat,name)) for name,_ in Stats._fields_})
              for width,seed,stat in zip(widths,seeds,stats)]
    diagnostics=[]
    if winner<0:
        for index in range(library.nohit_diagnostic_count()):
            reason=C.c_int32();word=np.empty(nt-1,np.int64)
            count=library.nohit_diagnostic_route(index,_ptr(word),len(word),C.byref(reason))
            if count>=0:diagnostics.append(dict(actions=word[:count].tolist(),
                stop_kind=('retained_frontier_collision','search_budget','initial_collision')[reason.value]))
    metadata=dict(metadata,diagnostic_routes=diagnostics,
        diagnostic_truncated=bool(library.nohit_diagnostic_truncated()))
    if controller_delay.value>=1000:
        macro_hold=controller_delay.value%1000;macro_width=int(library.nohit_last_macro_width())
        attempts=attempts[:1];attempts[0].update(width=macro_width,macro_hold_ticks=macro_hold)
        metadata=dict(metadata,controller='held-control-frontier',macro_hold_ticks=macro_hold,macro_width=macro_width,
            workers_used=max(1,int(library.nohit_last_portfolio_workers())) if controller_delay.value>=2000 else 1)
    elif controller_delay.value>=0:
        attempts=attempts[:1];attempts[0].update(width=1,controller_delay=controller_delay.value%9,controller_steer=controller_delay.value//9)
        metadata=dict(metadata,controller='ground-contact-jump',controller_delay=controller_delay.value%9,controller_steer=controller_delay.value//9,workers_used=1)
    else:
        portfolio_workers=library.nohit_last_portfolio_workers() if hasattr(library,'nohit_last_portfolio_workers') else min(workers,len(widths))
        edge_workers=library.nohit_last_edge_workers() if hasattr(library,"nohit_last_edge_workers") else max(1,workers//portfolio_workers) if np.any(widths>=256) else 1
        metadata=dict(metadata,workers_used=min(workers,portfolio_workers*edge_workers),
            edge_scheduling="idle-portfolio-slots" if hasattr(library,"nohit_last_edge_workers") else "fixed",
            portfolio_workers=portfolio_workers,edge_workers=edge_workers)
    elapsed=time.perf_counter()-began;process_cpu=time.process_time()-cpu_began
    cpu=sum(item['cpu_nanoseconds'] for item in attempts)/1e9
    return winner,actions,trace,attempts,dict(metadata,search_seconds=elapsed,portfolio_selection='lowest-input-cost-found' if config['objective'] in ('fewest_operations','human_friendly') else 'first-valid' if race else 'ordered',
        state_hash_rebuilds=int(library.nohit_last_hash_rebuilds()) if hasattr(library,'nohit_last_hash_rebuilds') else 0,
        state_hash_mode='avalanche-full-bit-equality' if hasattr(library,'nohit_last_hash_rebuilds') else 'original-fnv',
        collision_index_seconds=library.nohit_last_index_seconds() if hasattr(library,'nohit_last_index_seconds') else None,
        collision_index_bytes=int(library.nohit_last_index_bytes()) if hasattr(library,"nohit_last_index_bytes") else nt*16+int(np.isfinite(polygons[:,:,0]).sum())*192,
        search_cpu_seconds=cpu,process_cpu_seconds=process_cpu,cpu_measurement='native-thread-cpu-clock',effective_search_cores=cpu/elapsed if elapsed else 0.)


def neutral_rollout(initial,frames):
    """Batch a speculative neutral forecast; it does not certify safety."""
    if not frames:return initial.copy()
    if not load_backend.cache_info().currsize:
        # A cheap forecast must not force a compiler on an otherwise scalar
        # preflight request. Once search loads the kernel, use its batch path.
        from .source_oracle import scalar_module
        player=scalar_module('discrete_operator');state=initial.tolist()
        for frame in frames:player.step_mask_into(state,0,frame.env.tolist(),frame.platforms.tolist(),state)
        return np.asarray(state,np.float64)
    env=np.asarray([frame.env for frame in frames],np.float64)
    count=max(len(frame.platforms) for frame in frames)
    platforms=np.zeros((len(frames),count,9),np.float64)
    for tick,frame in enumerate(frames):platforms[tick,:len(frame.platforms)]=frame.platforms
    initial=np.ascontiguousarray(initial,np.float64);output=np.empty(11,np.float64)
    library,_=load_backend()
    library.nohit_rollout(_ptr(initial),_ptr(env),len(frames),_ptr(platforms),count,_ptr(output))
    return output


def replay_hint(initial,wave,actions):
    actions=np.ascontiguousarray(actions,np.int64)
    if actions.ndim!=1 or np.any(actions<0) or np.any(actions>15):raise ValueError('invalid hint actions')
    nt=len(actions)+1
    if nt>len(wave.env_schedule):raise ValueError('hint exceeds world')
    initial=np.ascontiguousarray(initial,np.float64)
    if initial.shape!=(11,) or not np.isfinite(initial).all():raise ValueError('invalid hint initial')
    arrays=[np.ascontiguousarray(getattr(wave,name)[:nt],np.float64) for name in
        ('env_schedule','platform_table','geometry_white','geometry_blue','geometry_polygons')]
    env,platforms,white,blue,polygons=arrays
    trace=np.empty((nt,11),np.float64);library,_=load_backend()
    reached=library.nohit_replay(_ptr(initial),_ptr(actions),_ptr(env),nt,_ptr(platforms),platforms.shape[1],
        _ptr(white),white.shape[1],_ptr(blue),blue.shape[1],_ptr(polygons),polygons.shape[1],_ptr(trace))
    return trace if reached==nt else None


def _bones_advance(rows,count,dt):
    library,_=load_backend()
    return library.nohit_bones_advance(_ptr(rows),count,dt)


def frame_clearance(frame,state):
    arrays=[np.ascontiguousarray(a,np.float64) for a in (state,frame.white,frame.blue,frame.polygons)]
    point,white,blue,polygons=arrays;output=np.empty(4,np.float64);library,_=load_backend()
    library.nohit_clearance(_ptr(point),_ptr(white),len(white),_ptr(blue),len(blue),
        _ptr(polygons),len(polygons),_ptr(output))
    return output


def _idle_world(bones,blasters,platforms,dt,delay,elapsed):
    library,_=load_backend()
    dt=np.ascontiguousarray(dt,np.float64)
    boxes=np.empty((len(dt),bones.count,4),np.float64)
    polygons=np.empty((len(dt),blasters.count,8),np.float64)
    platform_frames=np.empty((len(dt),platforms.count,9),np.float64)
    sizes=np.empty((len(dt),4),np.int32);clock=C.c_double(elapsed)
    ticks=library.nohit_idle_world(_ptr(bones.rows),bones.count,_ptr(blasters.rows),blasters.count,
        _ptr(platforms.rows),platforms.count,len(platforms.rows),_ptr(dt),len(dt),delay,
        C.byref(clock),_ptr(boxes),_ptr(polygons),_ptr(platform_frames),_ptr(sizes))
    return ticks,clock.value,boxes[:ticks],polygons[:ticks],platform_frames[:ticks],sizes[:ticks]


def _blasters_advance(rows,count,dt):
    library,_=load_backend();polygons=np.empty((count,8),np.float64);size=C.c_int32()
    alive=library.nohit_blasters_advance(_ptr(rows),count,dt,_ptr(polygons),C.byref(size))
    return alive,polygons[:size.value]


def _bones_geometry(rows,count,bounds=None):
    library,_=load_backend();boxes=np.empty((count,4),np.float64)
    if bounds is not None:
        bounds=np.asarray(bounds,np.float64);blues=C.c_int32()
        if bounds.shape!=(4,):raise ValueError('collision bounds need four coordinates')
        whites=library.nohit_bones_geometry_clipped(_ptr(rows),count,_ptr(boxes),_ptr(bounds),C.byref(blues))
        return boxes[:whites],boxes[count-blues.value:][::-1]
    whites=library.nohit_bones_geometry(_ptr(rows),count,_ptr(boxes))
    return boxes[:whites],boxes[whites:]
