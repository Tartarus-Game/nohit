"""Exact axis-table acceleration, retaining coupled reachability and safety.

An edge whose axis tables do not certify strict interior uses the complete
operator. No coordinate rounding, endpoint pruning, or Cartesian reachability
assumption is used. This independent experimental module is not integrated.
"""
import math
import numpy as np
from numba import njit
from .discrete_operator import step_mask_into
from .cspace import collision_query


def supported(wave,start,hold,states):
    rows=wave.env_schedule[start+1:start+hold+1]
    if len(rows)!=hold or rows.shape[1]!=22:return False
    if not np.isfinite(rows).all() or not np.isfinite(states).all():return False
    if np.any(rows[:,4]!=0) or np.any(rows[:,6]!=0) or np.any(rows[:,9]!=0):return False
    b=rows[0,:4]
    if not all(np.all(rows[:,j:j+4]==b) for j in (0,14,18)):return False
    if b[2]-b[0]<=26 or b[3]-b[1]<=26:return False
    if np.any(wave.platform_table[start+1:start+hold+1,:,6:8]):return False
    if np.any(states[:,5]!=0) or np.any(states[:,10]!=0):return False
    return True


@njit(cache=True)
def _strict(q,lo,hi):
    return q-8.>lo+5. and q+8.<hi-5.


@njit(cache=True)
def _axis_tables(values,axis,controls,start,hold,env):
    trace=np.empty((len(controls),len(values),hold,2))
    certified=np.ones((len(controls),len(values)),np.bool_)
    empty=np.empty((0,9));base=env[start+1]
    cx=(base[0]+base[2])*.5;cy=(base[1]+base[3])*.5
    for a in range(len(controls)):
        own=int(controls[a]) & (19 if axis==0 else 28)
        for i in range(len(values)):
            s=np.array([cx,cy,0.,0.,0.,0.,0.,1.,750.,0.,0.])
            s[axis],s[axis+2]=values[i,0],values[i,1]
            for j in range(hold):
                row=env[start+j+1]
                if not (_strict(s[0],row[0],row[2]) and _strict(s[1],row[1],row[3])):
                    certified[a,i]=False
                delta=s[axis+2]*row[7]
                if not (row[7]>0 and math.sqrt(delta*delta)+.5<2.):certified[a,i]=False
                step_mask_into(s,own,row,empty,s)
                if not (_strict(s[0],row[0],row[2]) and _strict(s[1],row[1],row[3])):
                    certified[a,i]=False
                trace[a,i,j,0]=s[axis];trace[a,i,j,1]=s[axis+2]
    return trace,certified


@njit(cache=True)
def _combine(states,controls,ix,iy,tx,ty,cx,cy,start,hold,env,platforms,white,blue,payload):
    following=np.empty((len(states)*len(controls),11))
    parents=np.empty(len(following),np.int64);masks=np.empty(len(following),np.int64)
    n=0;fast=0;fallback=0
    for i in range(len(states)):
        for a in range(len(controls)):
            mask=controls[a];s=states[i].copy();safe=True
            use_axes=cx[a,ix[i]] and cy[a,iy[i]]
            if use_axes:fast+=1
            else:fallback+=1
            for j in range(hold):
                tick=start+j+1
                if use_axes:
                    s[0],s[2]=tx[a,ix[i],j,0],tx[a,ix[i],j,1]
                    s[1],s[3]=ty[a,iy[i],j,0],ty[a,iy[i],j,1]
                    s[4]=mask;s[6]=env[tick,4];s[7]=env[tick,5]
                    s[8]=env[tick,8];s[9]=env[tick,12];s[10]=0.
                else:step_mask_into(s,mask,env[tick],platforms[tick],s)
                if collision_query(white,blue,tick,s,0.,payload):safe=False;break
            if safe:following[n]=s;parents[n]=i;masks[n]=mask;n+=1
    return following[:n],parents[:n],masks[:n],fast,fallback


def expand_red_axes(wave,states,controls,start,hold,cspace):
    """Return all safe edges in original parent/control order, or None.

    None means the environment is outside the proved domain. Callers must
    then use the complete operator, never interpret it as an empty relation.
    Returned state bytes and parent/mask arrays equal complete expansion.
    """
    if not supported(wave,start,hold,states):return None
    axes=[];inverses=[]
    for cols in ([0,2],[1,3]):
        pairs=np.ascontiguousarray(states[:,cols])
        _,indices,inverse=np.unique(pairs.view('V16').ravel(),return_index=True,return_inverse=True)
        axes.append(pairs[indices]);inverses.append(inverse)
    tx,cx=_axis_tables(axes[0],0,controls,start,hold,wave.env_schedule)
    ty,cy=_axis_tables(axes[1],1,controls,start,hold,wave.env_schedule)
    out,parents,masks,fast,fallback=_combine(states,controls,inverses[0],inverses[1],tx,ty,cx,cy,
        start,hold,wave.env_schedule,wave.platform_table,wave.geometry_white,wave.geometry_blue,cspace.payload)
    stats={'x_axis_states':len(axes[0]),'y_axis_states':len(axes[1]),
           'axis_microsteps':(len(axes[0])+len(axes[1]))*len(controls)*hold,
           'fast_joint_edges':fast,'full_operator_edges':fallback}
    return out,parents,masks,stats


@njit(cache=True)
def _combine_keys(states,controls,ix,iy,tx,ty,cx,cy,xmap,ymap,ny,start,hold,env,platforms,white,blue,payload):
    keys=np.empty(len(states)*len(controls),np.uint64)
    parents=np.empty(len(keys),np.int64);masks=np.empty(len(keys),np.int64)
    n=0
    # Packed output requires certified axes for every edge. Caller checks this;
    # otherwise the unpacked full-operator fallback retains exact endpoints.
    for i in range(len(states)):
        for a in range(len(controls)):
            mask=controls[a];s=states[i].copy();safe=True
            for j in range(hold):
                tick=start+j+1
                s[0],s[2]=tx[a,ix[i],j,0],tx[a,ix[i],j,1]
                s[1],s[3]=ty[a,iy[i],j,0],ty[a,iy[i],j,1]
                s[4]=mask;s[6]=env[tick,4];s[7]=env[tick,5]
                s[8]=env[tick,8];s[9]=env[tick,12];s[10]=0.
                if collision_query(white,blue,tick,s,0.,payload):safe=False;break
            if safe:
                keys[n]=(xmap[a,ix[i]]*ny+ymap[a,iy[i]])*32+mask
                parents[n]=i;masks[n]=mask;n+=1
    return keys[:n],parents[:n],masks[:n]


def compact_red_axis_step(wave,states,controls,start,hold,cspace):
    """Exact unique full exits using integer IDs only for temporary edge storage.

    IDs intern complete binary64 (position,velocity) pairs. The packed key is
    bijective on these pairs and actual masks; it is not a spatial cell index.
    Return (full_states, predecessor_indices, masks, stats), or None outside
    the environment domain. Unsupported individual axes use unpacked fallback.
    """
    if not supported(wave,start,hold,states):return None
    if not len(states):return states.copy(),np.empty(0,np.int64),np.empty(0,np.int64),{}
    # slammed is the only old non-kinematic field surviving this fixed-red
    # transition. Keep even its signed-zero bits exact.
    if np.any(states[:,5].view(np.uint64)!=states[0,5:6].view(np.uint64)[0]):return None
    axes=[];inverses=[];traces=[];certified=[];endpoints=[];endpoint_maps=[]
    for axis,cols in enumerate(([0,2],[1,3])):
        pairs=np.ascontiguousarray(states[:,cols])
        _,indices,inverse=np.unique(pairs.view('V16').ravel(),return_index=True,return_inverse=True)
        values=pairs[indices];axes.append(values);inverses.append(inverse)
        trace,valid=_axis_tables(values,axis,controls,start,hold,wave.env_schedule)
        traces.append(trace);certified.append(valid)
        final=np.ascontiguousarray(trace[:,:,-1,:]).reshape(-1,2)
        _,take,mapping=np.unique(final.view('V16').ravel(),return_index=True,return_inverse=True)
        endpoints.append(final[take]);endpoint_maps.append(mapping.reshape(len(controls),len(values)))
    stats={'x_axis_states':len(axes[0]),'y_axis_states':len(axes[1]),
        'axis_microsteps':sum(map(len,axes))*len(controls)*hold}
    if not all(np.all(v) for v in certified):
        result=expand_red_axes(wave,states,controls,start,hold,cspace)
        out,parents,masks,stats=result
        _,take=np.unique(out.view('V88').ravel(),return_index=True)
        stats['packed']=False
        return out[take],parents[take],masks[take],stats
    # Numba computes the expression from signed int64 table indices before
    # assigning uint64 storage; reject before signed arithmetic can overflow.
    if len(endpoints[0])*len(endpoints[1])*32>=2**63:raise OverflowError('axis key capacity')
    keys,parents,masks=_combine_keys(states,controls,inverses[0],inverses[1],traces[0],traces[1],
        certified[0],certified[1],endpoint_maps[0],endpoint_maps[1],len(endpoints[1]),start,hold,
        wave.env_schedule,wave.platform_table,wave.geometry_white,wave.geometry_blue,cspace.payload)
    unique,take=np.unique(keys,return_index=True);parents=parents[take];masks=masks[take]
    yids=(unique//32)%len(endpoints[1]);xids=(unique//32)//len(endpoints[1])
    out=states[parents].copy();out[:,0]=endpoints[0][xids,0];out[:,2]=endpoints[0][xids,1]
    out[:,1]=endpoints[1][yids,0];out[:,3]=endpoints[1][yids,1]
    env=wave.env_schedule[start+hold]
    out[:,4]=masks;out[:,6]=env[4];out[:,7]=env[5];out[:,8]=env[8];out[:,9]=env[12];out[:,10]=0.
    stats.update(packed=True,safe_edges=len(keys),exact_exits=len(out),
        temporary_edge_key_bytes=len(keys)*8,unpacked_edge_state_bytes=len(keys)*88)
    return out,parents,masks,stats
