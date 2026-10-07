"""Resident exact axis-ID frontier with a coupled reachable-set bitset.

Independent experiment. Only certified fixed-red windows are supported.
Neither marginal axis set is itself considered reachable; every joint key
must be reached from an actual predecessor and pass all collision queries.
"""
from dataclasses import dataclass
import numpy as np
from numba import njit
from .red_axis_expansion import supported,_axis_tables
from .cspace import collision_query


def control_velocity(mask):
    speed=75. if mask&16 else 150.
    ux=int(bool(mask&2))-int(bool(mask&1));up=int(bool(mask&4))-int(bool(mask&8))
    return np.array([ux*speed,-up*speed],dtype=np.float64)


@dataclass
class AxisFrontier:
    x: np.ndarray
    y: np.ndarray
    joint: np.ndarray
    mask: np.ndarray
    template: np.ndarray
    parents: np.ndarray
    controls: tuple = ()

    @classmethod
    def from_states(cls,states):
        """Retain one real representative per x/dx/y/dy pair for a next red step.

        This is not a claim that input latches can be discarded at arbitrary
        blue/observation boundaries. advance_joint validates its next window.
        """
        states=np.asarray(states,dtype=np.float64)
        if states.ndim!=2 or states.shape[1]!=11 or not len(states):raise ValueError('nonempty full11 frontier required')
        if not np.isfinite(states).all():raise ValueError('finite states required')
        if not np.all(states[:,5:].view(np.uint64)==states[0,5:].view(np.uint64)):
            raise ValueError('common persistent fields required')
        axes=[];inverse=[]
        for cols in ([0,2],[1,3]):
            values=np.ascontiguousarray(states[:,cols])
            _,take,ids=np.unique(values.view('V16').ravel(),return_index=True,return_inverse=True)
            axes.append(values[take]);inverse.append(ids)
        key=inverse[0].astype(np.uint64)*len(axes[1])+inverse[1].astype(np.uint64)
        keys,take=np.unique(key,return_index=True)
        return cls(axes[0],axes[1],keys,states[take,4].astype(np.uint8),states[0].copy(),take)

    def representative_states(self):
        ix=self.joint//len(self.y);iy=self.joint%len(self.y)
        s=np.tile(self.template,(len(self.joint),1))
        s[:,0]=self.x[ix,0];s[:,2]=self.x[ix,1];s[:,1]=self.y[iy,0];s[:,3]=self.y[iy,1];s[:,4]=self.mask
        return s

    def terminal_states(self):
        """Materialize all actual final masks, only when raw exits are needed."""
        if not self.controls:raise ValueError('no completed red edge')
        representative=self.representative_states();parts=[]
        for mask in self.controls:
            velocity=control_velocity(mask)
            matching=np.all(representative[:,2:4].view(np.uint64)==velocity.view(np.uint64),axis=1)
            s=representative[matching].copy();s[:,4]=mask;parts.append(s)
        return np.concatenate(parts) if parts else np.empty((0,11))

    @property
    def resident_bytes(self):
        return sum(v.nbytes for v in (self.x,self.y,self.joint,self.mask,self.template,self.parents))


@njit(cache=True)
def _joint_kernel(joint,old_ny,template,controls,tx,ty,xmap,ymap,new_ny,start,hold,
                  env,white,blue,payload,capacity,max_states):
    visited=np.zeros((capacity+63)//64,np.uint64)
    keys=np.empty(max_states,np.uint64);parents=np.empty(max_states,np.int64);masks=np.empty(max_states,np.uint8)
    n=0;edges=0
    for i in range(len(joint)):
        ix=int(joint[i]//old_ny);iy=int(joint[i]%old_ny);s=template.copy()
        for a in range(len(controls)):
            mask=controls[a];safe=True;edges+=1
            key=int(xmap[a,ix]*new_ny+ymap[a,iy]);word=key//64;bit=np.uint64(1)<<np.uint64(key%64)
            # Boolean reachability union is idempotent. A set bit already has
            # a fully checked safe witness, so another incoming edge cannot
            # add an exit or improve the representative required here.
            if visited[word]&bit:continue
            for micro in range(hold):
                tick=start+micro+1
                s[0],s[2]=tx[a,ix,micro,0],tx[a,ix,micro,1]
                s[1],s[3]=ty[a,iy,micro,0],ty[a,iy,micro,1]
                s[4]=mask;s[6]=env[tick,4];s[7]=env[tick,5]
                s[8]=env[tick,8];s[9]=env[tick,12];s[10]=0.
                if collision_query(white,blue,tick,s,0.,payload):safe=False;break
            if not safe:continue
            if n==max_states:return False,keys[:n],parents[:n],masks[:n],edges
            visited[word]|=bit;keys[n]=key;parents[n]=i;masks[n]=mask;n+=1
    return True,keys[:n],parents[:n],masks[:n],edges


def advance_joint(wave,frontier,controls,start,hold,cspace,*,max_states=2_000_000,max_product_cells=100_000_000):
    """Return (status, new_frontier_or_None, stats); unknown never loses input.

    Internal previous-mask quotient and equal-velocity control aliases are
    exact in this certified red window. Every final actual mask can be expanded
    by terminal_states; its representative parent permits the same final mask
    substitution because all microtick kinematics/safety are identical.
    """
    controls=tuple(int(mask) for mask in controls)
    if not controls or any(mask<0 or mask>=32 for mask in controls) or hold<1:raise ValueError('controls/hold')
    if max_states<1 or max_product_cells<1:raise ValueError('resource budget')
    stop=start+hold
    if not 0<=start<stop<len(wave.env_schedule):raise ValueError('tick_range')
    pending=wave.pending_target
    if pending is not None and pending['tick']<=stop:
        return 'unsupported',None,{'reason':'unresolved_target'}
    if getattr(wave,'termination_reason',None)=='dialogue_boundary' and stop>=len(wave.env_schedule)-1:
        return 'unsupported',None,{'reason':'unresolved_dialogue'}
    if any(start<t<=stop and cmd=='getheartpos' for t,cmd,_ in wave.source_events):
        return 'unsupported',None,{'reason':'target_observation_boundary'}
    if not supported(wave,start,hold,frontier.template.reshape(1,11)):
        return 'unsupported',None,{}
    if not len(frontier.joint):return 'complete',frontier,{'joint_states':0}
    groups={}
    for mask in controls:groups.setdefault(control_velocity(int(mask)).tobytes(),int(mask))
    canonical=np.array(list(groups.values()),dtype=np.int64)
    traces=[];endpoints=[];maps=[]
    for axis,values in enumerate((frontier.x,frontier.y)):
        trace,valid=_axis_tables(values,axis,canonical,start,hold,wave.env_schedule)
        if not np.all(valid):return 'unsupported',None,{'reason':'axis_boundary_or_multistep'}
        traces.append(trace)
        final=np.ascontiguousarray(trace[:,:,-1,:]).reshape(-1,2)
        _,take,mapping=np.unique(final.view('V16').ravel(),return_index=True,return_inverse=True)
        endpoints.append(final[take]);maps.append(mapping.reshape(len(canonical),len(values)))
    capacity=len(endpoints[0])*len(endpoints[1])
    if capacity>max_product_cells or capacity>=2**63:return 'resource_limit',None,{'product_cells':capacity}
    done,keys,parents,masks,edges=_joint_kernel(frontier.joint,len(frontier.y),frontier.template,canonical,
        traces[0],traces[1],maps[0],maps[1],len(endpoints[1]),start,hold,wave.env_schedule,
        wave.geometry_white,wave.geometry_blue,cspace.payload,capacity,max_states)
    stats={'joint_states':len(keys),'product_cells':capacity,'bitset_bytes':((capacity+63)//64)*8,
        'canonical_controls':len(canonical),'joint_edges_checked':edges,'x_axis_states':len(endpoints[0]),'y_axis_states':len(endpoints[1])}
    if not done:return 'resource_limit',None,stats
    template=frontier.template.copy();env=wave.env_schedule[start+hold]
    template[6]=env[4];template[7]=env[5];template[8]=env[8];template[9]=env[12];template[10]=0.
    # Discard unused marginal IDs only after the complete joint union. This
    # does not discard any reachable pair; it keeps tables from accumulating
    # axis states whose every joint continuation already collided.
    used_x,ix=np.unique(keys//len(endpoints[1]),return_inverse=True)
    used_y,iy=np.unique(keys%len(endpoints[1]),return_inverse=True)
    packed=ix.astype(np.uint64)*len(used_y)+iy.astype(np.uint64)
    new=AxisFrontier(endpoints[0][used_x],endpoints[1][used_y],packed,masks.copy(),template,parents.copy(),tuple(controls))
    stats['resident_bytes']=new.resident_bytes
    return 'complete',new,stats
