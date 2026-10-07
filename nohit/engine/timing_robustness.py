"""Exact input-boundary uncertainty in the declared fixed-step model.

A radius r permits each 60 Hz command boundary to move independently by any
integer in [-r, r] 240 Hz ticks. The first boundary is clipped at attack start.
For r <= 2 adjacent boundaries cannot reverse order. All disturbance histories
are propagated; identical complete physical states alone may be merged.

This is NOT a probability estimate or a certificate for arbitrary native dt.
The transition is also the state-bundle operator needed by a robust search.
"""
import numpy as np
from numba import njit
from .canonical_lattice import step_into, collision


@njit(cache=True)
def advance_bundle(white, blue, env, platforms, states, frame, old_x, old_y,
                   new_x, new_y, radius, max_states=100000):
    """Return (status, reachable bundle): 0 safe, 1 hit, 2 resource limit.

    Each search edge must be safe for ALL allowed boundary offsets. A resource
    limit is unknown, never evidence that a route fails the uncertainty model.
    """
    first=max(0,frame*4-radius)
    layers=(len(env)-1+3)//4
    last=len(env)-1 if frame==layers-1 else (frame+1)*4-radius
    delays=radius+1 if frame==0 else 2*radius+1
    if new_x==old_x and new_y==old_y:
        delays=1
    out=np.empty((min(max_states,len(states)*delays),5),np.float64)
    seen=set()
    count=0
    for s in states:
        for delay in range(delays):
            q=s.copy()
            for i in range(last-first):
                tick=first+i+1
                ux=new_x if i>=delay else old_x
                uy=new_y if i>=delay else old_y
                step_into(q,ux,uy,env[tick],platforms[tick],q)
                if collision(white,blue,tick,q,0.):
                    return 1,out[:0]
            bits=q.view(np.uint64)
            key=(bits[0],bits[1],bits[2],bits[3],bits[4])
            if key not in seen:
                if count==max_states:
                    return 2,out[:0]
                seen.add(key)
                out[count]=q
                count+=1
    return 0,out[:count]


def certify_timing_radius(wave, initial, actions, radius, max_states=100000):
    """Certify every independent jitter combination, with explicit bounds."""
    if radius not in (0,1,2):
        raise ValueError('radius must be 0, 1 or 2 microticks')
    actions=np.asarray(actions,dtype=np.int8)
    layers=(len(wave.env_schedule)-1+3)//4
    if actions.shape!=(layers,2):
        raise ValueError('a complete route is required')
    states=np.asarray(initial,dtype=np.float64).reshape(1,5)
    status=1 if collision(wave.geometry_white,wave.geometry_blue,0,states[0],0.) else 0
    old_x=old_y=0
    peak=1
    frame=-1
    if status==0:
        for frame,(ux,uy) in enumerate(actions):
            status,states=advance_bundle(wave.geometry_white,wave.geometry_blue,
                wave.env_schedule,wave.platform_table,states,frame,old_x,old_y,
                int(ux),int(uy),radius,max_states)
            if status: break
            peak=max(peak,len(states))
            old_x,old_y=int(ux),int(uy)
    return dict(status=('certified','counterexample','resource_limit')[status],
        radius_microticks=radius,radius_ms=radius*1000/240,
        frame=frame,peak_uncertainty_states=peak,
        uncertainty_model='independent integer command-boundary shifts; fixed 240Hz physics',
        native_dt_robustness_proven=False,execution_probability=None)
