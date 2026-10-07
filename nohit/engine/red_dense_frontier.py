"""Exact dense joint relation; witnesses are recovered from saved relations.

Axes are exact-bit values. Occupancy, never marginal membership, establishes
reachability. Dropping eager parent storage does not drop a single exit.
"""
from dataclasses import dataclass
import numpy as np
from numba import njit
from .red_joint_frontier import control_velocity
from .red_axis_expansion import supported,_axis_tables
from .cspace import collision_query

@njit(cache=True)
def pack_keys(keys,capacity):
    bits=np.zeros((capacity+63)//64,np.uint64)
    for key in keys:bits[key//64]|=np.uint64(1)<<np.uint64(key%64)
    return bits

@njit(cache=True)
def unpack_keys(bits,capacity):
    count=0
    for key in range(capacity):
        if bits[key//64]&(np.uint64(1)<<np.uint64(key%64)):count+=1
    out=np.empty(count,np.uint64);n=0
    for key in range(capacity):
        if bits[key//64]&(np.uint64(1)<<np.uint64(key%64)):out[n]=key;n+=1
    return out

@dataclass
class DenseFrontier:
    x: np.ndarray
    y: np.ndarray
    bits: np.ndarray
    template: np.ndarray
    count: int

    @classmethod
    def from_axis(cls,front):
        return cls(front.x.copy(),front.y.copy(),pack_keys(front.joint,len(front.x)*len(front.y)),front.template.copy(),len(front.joint))

    def state(self,key):
        ix,iy=divmod(int(key),len(self.y));s=self.template.copy()
        s[0],s[2]=self.x[ix];s[1],s[3]=self.y[iy];s[4]=0.
        return s

    @property
    def resident_bytes(self):return self.x.nbytes+self.y.nbytes+self.bits.nbytes+self.template.nbytes

def prepare(wave,front,controls,start,hold):
    stop=start+hold
    if hold<1 or not 0<=start<stop<len(wave.env_schedule):raise ValueError('tick_range')
    if not controls or any(mask<0 or mask>=32 for mask in controls):raise ValueError('controls')
    if wave.pending_target is not None and wave.pending_target['tick']<=stop:return None,'unresolved_target'
    if getattr(wave,'termination_reason',None)=='dialogue_boundary' and stop>=len(wave.env_schedule)-1:return None,'unresolved_dialogue'
    if any(start<t<=stop and cmd=='getheartpos' for t,cmd,_ in wave.source_events):return None,'target_observation_boundary'
    if not supported(wave,start,hold,front.template.reshape(1,11)):return None,'unsupported_environment'
    groups={}
    for mask in controls:groups.setdefault(control_velocity(mask).tobytes(),mask)
    canonical=np.array(list(groups.values()),np.int64);traces=[];endpoints=[];maps=[]
    for axis,values in enumerate((front.x,front.y)):
        trace,valid=_axis_tables(values,axis,canonical,start,hold,wave.env_schedule)
        if not valid.all():return None,'axis_boundary_or_multistep'
        final=np.ascontiguousarray(trace[:,:,-1,:]).reshape(-1,2)
        _,take,inverse=np.unique(final.view('V16').ravel(),return_index=True,return_inverse=True)
        traces.append(trace);endpoints.append(final[take]);maps.append(inverse.reshape(len(canonical),len(values)))
    return (canonical,traces,endpoints,maps),None

@njit(cache=True)
def _advance(bits,old_nx,old_ny,template,controls,tx,ty,xmap,ymap,nx,ny,start,hold,env,white,blue,payload):
    out=np.zeros((nx*ny+63)//64,np.uint64);usedx=np.zeros(nx,np.bool_);usedy=np.zeros(ny,np.bool_)
    count=0;edges=0;checks=0
    for word in range(len(bits)):
        if bits[word]==0:continue
        for b in range(64):
            oldkey=word*64+b
            if oldkey>=old_nx*old_ny:break
            if not bits[word]&(np.uint64(1)<<np.uint64(b)):continue
            ix=oldkey//old_ny;iy=oldkey%old_ny;s=template.copy()
            for a in range(len(controls)):
                edges+=1;x=xmap[a,ix];y=ymap[a,iy];key=x*ny+y;w=key//64;bit=np.uint64(1)<<np.uint64(key%64)
                if out[w]&bit:continue
                checks+=1;safe=True
                for micro in range(hold):
                    tick=start+micro+1;s[0],s[2]=tx[a,ix,micro,0],tx[a,ix,micro,1]
                    s[1],s[3]=ty[a,iy,micro,0],ty[a,iy,micro,1];s[4]=controls[a]
                    s[6]=env[tick,4];s[7]=env[tick,5];s[8]=env[tick,8];s[9]=env[tick,12];s[10]=0.
                    if collision_query(white,blue,tick,s,0.,payload):safe=False;break
                if safe:out[w]|=bit;usedx[x]=True;usedy[y]=True;count+=1
    return out,usedx,usedy,count,edges,checks

@njit(cache=True)
def _compact(bits,old_ny,xmap,ymap,new_nx,new_ny):
    out=np.zeros((new_nx*new_ny+63)//64,np.uint64)
    for word in range(len(bits)):
        if bits[word]==0:continue
        for b in range(64):
            if bits[word]&(np.uint64(1)<<np.uint64(b)):
                key=word*64+b;x=key//old_ny;y=key%old_ny;target=xmap[x]*new_ny+ymap[y]
                out[target//64]|=np.uint64(1)<<np.uint64(target%64)
    return out

def advance_dense(wave,front,controls,start,hold,cspace,*,max_product_cells=200_000_000):
    if max_product_cells<1:raise ValueError('budget')
    prepared,reason=prepare(wave,front,controls,start,hold)
    if prepared is None:return 'unsupported',None,{'reason':reason}
    if front.count==0:return 'complete',front,{'joint_states':0}
    canonical,traces,endpoints,maps=prepared;nx,ny=map(len,endpoints)
    if nx*ny>max_product_cells:return 'resource_limit',None,{'product_cells':nx*ny}
    bits,ux,uy,count,edges,checks=_advance(front.bits,len(front.x),len(front.y),front.template,canonical,*traces,*maps,nx,ny,start,hold,wave.env_schedule,wave.geometry_white,wave.geometry_blue,cspace.payload)
    stats=dict(joint_states=int(count),product_cells=nx*ny,edges=edges,collision_edges=checks)
    if not (ux.all() and uy.all()):
        bits=_compact(bits,ny,np.cumsum(ux)-1,np.cumsum(uy)-1,int(ux.sum()),int(uy.sum()))
        endpoints=[endpoints[0][ux],endpoints[1][uy]]
    template=front.template.copy();e=wave.env_schedule[start+hold]
    template[6]=e[4];template[7]=e[5];template[8]=e[8];template[9]=e[12];template[10]=0.
    new=DenseFrontier(*endpoints,bits,template,int(count));stats['resident_bytes']=new.resident_bytes
    return 'complete',new,stats

def predecessor(wave,front,target,controls,start,hold,cspace,*,terminal_mask=None):
    """Find a safe predecessor of an internal class (target old mask ignored).

    Supply terminal_mask to require that exact allowed final input alias. All
    other target fields are compared bitwise with the actual replayed state.
    """
    if terminal_mask is not None and terminal_mask not in controls:raise ValueError('terminal_mask')
    prepared,reason=prepare(wave,front,controls,start,hold)
    if prepared is None:raise ValueError(reason)
    canonical,traces,_,_=prepared
    from .discrete_operator import step_mask_into
    target=np.asarray(target,dtype=np.float64)
    for a,mask in enumerate(canonical):
        if terminal_mask is not None:
            if control_velocity(int(mask)).tobytes()!=control_velocity(terminal_mask).tobytes():continue
            mask=terminal_mask
        matches=[]
        for axis in (0,1):
            desired=np.ascontiguousarray(target[[axis,axis+2]])
            matches.append(np.flatnonzero(np.all(traces[axis][a,:,-1,:].view(np.uint64)==desired.view(np.uint64),axis=1)))
        for ix in matches[0]:
            for iy in matches[1]:
                key=int(ix)*len(front.y)+int(iy)
                if not int(front.bits[key//64])&(1<<(key%64)):continue
                s=front.state(key);safe=True
                for tick in range(start+1,start+hold+1):
                    step_mask_into(s,int(mask),wave.env_schedule[tick],wave.platform_table[tick],s)
                    if collision_query(wave.geometry_white,wave.geometry_blue,tick,s,0.,cspace.payload):safe=False;break
                if safe and np.array_equal(s[:4].view(np.uint64),target[:4].view(np.uint64)) and np.array_equal(s[5:].view(np.uint64),target[5:].view(np.uint64)):
                    return key,int(mask)
    raise ValueError('no safe joint predecessor')
