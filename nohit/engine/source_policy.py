"""Bounded scalar preflight; avoid compiling a search that is not needed.

Generic ground-contact policies only. Every tick uses the original player and
continuous collision bodies; failure is just a handoff to the native frontier.
"""
import hashlib
import math
from pathlib import Path
import time

import numpy as np

from .source_oracle import scalar_module


def preflight(initial,wave,seconds):
    nt=len(wave.env_schedule)
    if nt>512 or seconds<=0:return None
    began=time.perf_counter();cpu=time.thread_time();deadline=began+min(.05,seconds)
    player=scalar_module('discrete_operator');collision=scalar_module('cspace')
    payload=(np.empty((nt,2,0,0),np.uint8),wave.geometry_polygons,0.,0.,1.)
    if collision.collision_query(wave.geometry_white,wave.geometry_blue,0,initial,0.,payload):return None
    actions=np.empty(nt-1,np.int64);trace=np.empty((nt,11),np.float64);steps=0
    neutral=np.empty(11,np.float64);following=np.empty(11,np.float64)
    for delay in range(9):
        state=initial.copy();trace[0]=state;grounded=0;safe=True
        for tick in range(1,nt):
            if steps>=2048 or time.perf_counter()>=deadline:return None
            row=wave.env_schedule[tick];platforms=wave.platform_table[tick];mask=0
            player.step_mask_into(state,0,row,platforms,neutral)
            if neutral[6]!=0.:
                direction=neutral[7];angle=direction*(math.pi/2.)
                gx=math.cos(angle);gy=math.sin(angle)
                jump=1 if direction==0. else 4 if direction==1. else 2 if direction==2. else 8
                if row[6]:grounded=0
                touching=player.heart_solid(neutral[0],neutral[1],neutral[3],direction,row,platforms,gx,gy)
                if touching:
                    grounded+=1
                    if not int(state[4])&jump and grounded>delay:mask=jump
                else:
                    grounded=0
                    if int(state[4])&jump:mask=jump
            player.step_mask_into(state,mask,row,platforms,following);steps+=1
            if collision.collision_query(wave.geometry_white,wave.geometry_blue,tick,following,0.,payload):safe=False;break
            state,following=following,state;actions[tick-1]=mask;trace[tick]=state
        if not safe:continue
        elapsed=time.perf_counter()-began;raw_cpu_seconds=max(0.,time.thread_time()-cpu)
        # Windows GetThreadTimes can advance by 15.625 ms during a sub-ms
        # single-thread probe. Preserve that raw observation, but identify the
        # physically bounded estimate rather than reporting dozens of cores.
        resolution_limited=raw_cpu_seconds>elapsed
        cpu_seconds=min(raw_cpu_seconds,elapsed)
        source=Path(__file__).with_name('native_frontier.cpp')
        stats=dict(width=1,seed=0,expanded=nt-1,generated=nt-1,unique=nt-1,discarded=0,
            workspace_bytes=trace.nbytes+actions.nbytes+3*88,preview_steps=0,recovery_steps=0,
            recoveries=0,cpu_nanoseconds=int(cpu_seconds*1e9),reached=nt-1,status=1,controller_delay=delay)
        metadata=dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),compiled=False,
            compiler=None,compiler_flags=[],kernel_load_seconds=0.,route_cache=False,environment_cache=False,
            scalar_preflight=True,controller='ground-contact-jump',controller_delay=delay,workers_used=1,
            search_seconds=elapsed,search_cpu_seconds=cpu_seconds,process_cpu_seconds=cpu_seconds,
            cpu_measurement='python-thread-cpu-clock',effective_search_cores=cpu_seconds/elapsed if elapsed else 0.,
            thread_cpu_clock_raw_seconds=raw_cpu_seconds,cpu_measurement_resolution_limited=resolution_limited,
            search_cpu_seconds_kind='single_thread_wall_upper_bound' if resolution_limited else 'thread_cpu_clock',
            preflight_steps=steps)
        return 0,actions.copy(),trace.copy(),[stats],metadata
    return None
