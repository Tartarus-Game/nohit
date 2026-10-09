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

_FLAGS = ('-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math', '-shared', '-fPIC', '-pthread')
_SOURCE = Path(__file__).with_name('native_frontier.cpp')
_LOCK = threading.RLock()


class Stats(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in ('expanded', 'generated', 'unique', 'discarded', 'workspace_bytes', 'preview_steps', 'recovery_steps', 'recoveries', 'cpu_nanoseconds')] + [
        ('reached', C.c_int32), ('status', C.c_int32)]


def _ptr(array):
    return C.c_void_p(array.ctypes.data)


@lru_cache(maxsize=1)
def load_backend():
    began = time.perf_counter()
    compiler = shlex.split(os.environ['CXX']) if os.environ.get('CXX') else None
    if compiler is None:
        executable = shutil.which('g++') or shutil.which('clang++')
        if not executable:
            raise RuntimeError('Native CSV backend needs g++ or clang++; install a C++17 compiler or select fixed search')
        compiler = [executable]
    identity = hashlib.sha256(_SOURCE.read_bytes() + repr((_FLAGS, platform.system(), platform.machine(), compiler)).encode()).hexdigest()
    cache = Path(os.environ.get('NOHIT_NATIVE_CACHE', str(Path.home()/'.cache/nohit-native')))
    cache.mkdir(parents=True, exist_ok=True)
    extension = '.dll' if os.name == 'nt' else '.dylib' if sys.platform == 'darwin' else '.so'
    binary = cache / (identity + extension)
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
                result = subprocess.run(compiler + list(_FLAGS) + [str(_SOURCE), '-o', str(temporary)],
                    capture_output=True, text=True, timeout=8)
                if result.returncode:
                    raise RuntimeError('Native kernel build failed: ' + result.stderr[-2000:])
                os.replace(temporary, binary)
            finally:
                temporary.unlink(missing_ok=True)
        if os.name == 'nt':
            lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    library = C.CDLL(str(binary))
    P, I = C.c_void_p, C.c_int
    library.nohit_step.argtypes = [P,I,P,P,P,I,P]
    library.nohit_step.restype = I
    library.nohit_collision.argtypes = [P,I,P,I,P,I,P,I,P]
    library.nohit_collision.restype = I
    library.nohit_expand.argtypes = [P,I,P,I,P,I,P,I,P,I,P,I,P,I,I,I,P,P,P]
    library.nohit_expand.restype = I
    library.nohit_search.argtypes = [P,P,I,P,I,P,I,P,I,P,I,P,P,I,P,P,I,I,C.c_double,P,P,P,P]
    library.nohit_search.restype = I
    if hasattr(library,"nohit_search_goal"):
        library.nohit_search_goal.argtypes=library.nohit_search.argtypes+[P]
        library.nohit_search_goal.restype=I
    if hasattr(library,"nohit_last_index_bytes"):
        library.nohit_last_index_bytes.argtypes=[]
        library.nohit_last_index_bytes.restype=C.c_uint64
    return library, dict(source_sha256=hashlib.sha256(_SOURCE.read_bytes()).hexdigest(),
        code_identity=identity, compiled=compiled, compiler=compiler, compiler_flags=list(_FLAGS),
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


def search(initial, wave, controls, counts, widths, seeds, workers, seconds, *, terminal_target=None):
    if type(workers) is not int or not 1<=workers<=32:raise ValueError('workers must be in [1,32]')
    controls=np.ascontiguousarray(controls,np.int64);counts=np.ascontiguousarray(counts,np.int64)
    initial=np.ascontiguousarray(initial,np.float64)
    arrays=[np.ascontiguousarray(value,np.float64) for value in
            (wave.env_schedule,wave.platform_table,wave.geometry_white,wave.geometry_blue,wave.geometry_polygons)]
    env,platforms,white,blue,polygons=arrays
    widths=np.ascontiguousarray(widths,np.int32);seeds=np.ascontiguousarray(seeds,np.uint32)
    nt=len(env)
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
    winner=invoke(_ptr(initial),_ptr(env),nt,_ptr(platforms),platforms.shape[1],
        _ptr(white),white.shape[1],_ptr(blue),blue.shape[1],_ptr(polygons),polygons.shape[1],
        _ptr(controls),_ptr(counts),controls.shape[1],_ptr(widths),_ptr(seeds),len(widths),workers,seconds,
        _ptr(actions),_ptr(trace),C.cast(stats,C.c_void_p),C.byref(controller_delay),*extra)
    attempts=[dict(width=int(width),seed=int(seed),**{name:int(getattr(stat,name)) for name,_ in Stats._fields_})
              for width,seed,stat in zip(widths,seeds,stats)]
    if controller_delay.value>=0:
        attempts=attempts[:1];attempts[0].update(width=1,controller_delay=controller_delay.value%9,controller_steer=controller_delay.value//9)
        metadata=dict(metadata,controller='ground-contact-jump',controller_delay=controller_delay.value%9,controller_steer=controller_delay.value//9,workers_used=1)
    else:
        portfolio_workers=min(workers,len(widths))
        edge_workers=max(1,workers//portfolio_workers) if np.any(widths>=256) else 1
        metadata=dict(metadata,workers_used=portfolio_workers*edge_workers,
            portfolio_workers=portfolio_workers,edge_workers=edge_workers)
    elapsed=time.perf_counter()-began;process_cpu=time.process_time()-cpu_began
    cpu=sum(item['cpu_nanoseconds'] for item in attempts)/1e9
    return winner,actions,trace,attempts,dict(metadata,search_seconds=elapsed,
        collision_index_bytes=int(library.nohit_last_index_bytes()) if hasattr(library,"nohit_last_index_bytes") else nt*16+int(np.isfinite(polygons[:,:,0]).sum())*192,
        search_cpu_seconds=cpu,process_cpu_seconds=process_cpu,cpu_measurement='native-thread-cpu-clock',effective_search_cores=cpu/elapsed if elapsed else 0.)
