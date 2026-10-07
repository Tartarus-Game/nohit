"""Exact dense joint reachability in a certified static horizontal-blue strip.

Independent experiment. All 16 arrows are covered. Unsafe factorization
domains return unsupported; no platform, slam, teleport or wall-touching
entry is silently approximated. Persistent slammed must be zero.
"""
from dataclasses import dataclass
import numpy as np
from numba import njit
from .discrete_operator import step_mask_into,direction_xy
from .cspace import collision_query


@dataclass
class BlueFrontier:
    x: np.ndarray # x, dx, old jump bit
    y: np.ndarray # y, dy
    bits: np.ndarray
    template: np.ndarray
    tick: int

    @classmethod
    def from_states(cls,states,tick):
        states=np.asarray(states,dtype=np.float64)
        if states.ndim!=2 or states.shape[1]!=11 or not len(states):raise ValueError('nonempty full11 states required')
        if not np.isfinite(states).all():raise ValueError('finite states required')
        if not np.all(states[:,5:].view(np.uint64)==states[0,5:].view(np.uint64)):
            raise ValueError('common persistent fields required')
        if states[0,5]!=0 or states[0,6]!=1 or states[0,7] not in (0,2) or states[0,10]!=0:
            raise ValueError('horizontal blue with zero slammed/damage required')
        jump=1 if states[0,7]==0 else 2
        x=states[:,[0,2,4]].copy();x[:,2]=x[:,2].astype(np.int64)&jump
        y=states[:,[1,3]].copy()
        _,take,ix=np.unique(x.view('V24').ravel(),return_index=True,return_inverse=True);x=x[take]
        _,take,iy=np.unique(y.view('V16').ravel(),return_index=True,return_inverse=True);y=y[take]
        ids=ix.astype(np.int64)*len(y)+iy
        bits=_pack(ids,len(x)*len(y))
        unique_ids,origins=np.unique(ids,return_index=True)
        return cls(x,y,bits,states[0].copy(),int(tick)),unique_ids,origins

    def contains(self,ix,iy):
        key=int(ix)*len(self.y)+int(iy)
        return bool((int(self.bits[key//64])>>(key%64))&1)

    def state(self,ix,iy,mask=None):
        s=self.template.copy();s[0],s[2],jump=self.x[ix];s[1],s[3]=self.y[iy]
        s[4]=int(jump)+(4 if s[3]<0 else 8 if s[3]>0 else 0) if mask is None else mask
        return s

    def count(self):return int(_count(self.bits))


@njit(cache=True)
def _pack(ids,capacity):
    bits=np.zeros((capacity+63)//64,np.uint64)
    for key in ids:bits[key//64]|=np.uint64(1)<<np.uint64(key%64)
    return bits


@njit(cache=True)
def _count(bits):
    n=0
    for value in bits:
        while value:
            value&=value-np.uint64(1);n+=1
    return n


def _supported(wave,front,hold):
    rows=wave.env_schedule[front.tick+1:front.tick+hold+1]
    if len(rows)!=hold or rows.shape[1]!=22 or not np.isfinite(rows).all():return False
    if front.template[5]!=0 or front.template[10]!=0:return False
    if np.any(rows[:,4]!=1) or np.any(rows[:,5]!=front.template[7]) or np.any(rows[:,6]!=0) or np.any(rows[:,9]!=0):return False
    if front.template[7] not in (0,2):return False
    bounds=rows[0,:4]
    if not all(np.all(rows[:,j:j+4]==bounds) for j in (0,14,18)):return False
    if np.any(wave.platform_table[front.tick+1:front.tick+hold+1,:,6:8]):return False
    if wave.pending_target is not None and wave.pending_target['tick']<=front.tick+hold:return False
    if any(front.tick<t<=front.tick+hold and cmd=='getheartpos' for t,cmd,_ in wave.source_events):return False
    if wave.termination_reason=='dialogue_boundary' and front.tick+hold>=len(wave.env_schedule)-1:return False
    return True


@njit(cache=True)
def _strict(q,lo,hi):return q-8.>lo+5. and q+8.<hi-5.


@njit(cache=True)
def _traces(x,y,template,start,hold,env):
    # x uses jump/no jump, y uses neutral/up/down. Actual collision remains
    # joint: these traces never mark a marginal position reachable on its own.
    jump=1 if template[7]==0. else 2
    tx=np.empty((2,len(x),hold,3));ty=np.empty((3,len(y),hold,2))
    empty=np.empty((0,9));row=env[start+1];cx=(row[0]+row[2])*.5;cy=(row[1]+row[3])*.5
    gx,gy=direction_xy(template[7])
    for a in range(2):
        for i in range(len(x)):
            s=template.copy();s[0],s[2],s[4]=x[i];s[1]=cy;s[3]=0.
            for micro in range(hold):
                row=env[start+micro+1]
                if not _strict(s[0],row[0],row[2]):return False,tx,ty
                step_mask_into(s,a*jump,row,empty,s)
                if not _strict(s[0],row[0],row[2]) or s[5]!=0. or s[10]!=0.:return False,tx,ty
                tx[a,i,micro,0]=s[0];tx[a,i,micro,1]=s[2];tx[a,i,micro,2]=s[4]
    for a in range(3):
        for i in range(len(y)):
            s=template.copy();s[0]=cx;s[2]=0.;s[4]=0.;s[1],s[3]=y[i]
            for micro in range(hold):
                row=env[start+micro+1]
                if not _strict(s[1],row[1],row[3]):return False,tx,ty
                step_mask_into(s,a*4,row,empty,s)
                if not _strict(s[1],row[1],row[3]) or s[5]!=0. or s[10]!=0.:return False,tx,ty
                # Cardinal trig residuals in support probes must not move y
                # onto a perpendicular border in the actual binary64 domain.
                if not _strict(s[1]+gy,row[1],row[3]) or not _strict(s[1]+gy*.2,row[1],row[3]):return False,tx,ty
                ty[a,i,micro,0]=s[1];ty[a,i,micro,1]=s[3]
    return True,tx,ty


@njit(cache=True)
def _advance(bits,nx,ny,tx,ty,xmap,ymap,newny,capacity,template,start,hold,white,blue,payload):
    out=np.zeros((capacity+63)//64,np.uint64);n=0;checked=0
    jump=1 if template[7]==0. else 2
    for ix in range(nx):
        for iy in range(ny):
            old=ix*ny+iy
            if not (bits[old//64]&(np.uint64(1)<<np.uint64(old%64))):continue
            for ax in range(2):
                for ay in range(3):
                    key=xmap[ax,ix]*newny+ymap[ay,iy];word=key//64;bit=np.uint64(1)<<np.uint64(key%64)
                    if out[word]&bit:continue
                    checked+=1;s=template.copy();safe=True
                    for micro in range(hold):
                        s[0],s[2],s[4]=tx[ax,ix,micro];s[1],s[3]=ty[ay,iy,micro]
                        s[4]=ax*jump+ay*4
                        if collision_query(white,blue,start+micro+1,s,0.,payload):safe=False;break
                    if safe:out[word]|=bit;n+=1
    return out,n,checked


def advance_blue(wave,front,hold,cspace,*,max_product=100_000_000):
    if hold<1 or max_product<1:raise ValueError('positive hold and resource bound required')
    if not _supported(wave,front,hold):return 'unsupported',None,None,{'reason':'outside_horizontal_blue_domain'}
    valid,tx,ty=_traces(front.x,front.y,front.template,front.tick,hold,wave.env_schedule)
    if not valid:return 'unsupported',None,None,{'reason':'strict_axis_certificate_failed'}
    axes=[];maps=[]
    for trace,width in ((tx,3),(ty,2)):
        final=np.ascontiguousarray(trace[:,:,-1,:]).reshape(-1,width)
        _,take,mapping=np.unique(final.view(f'V{width*8}').ravel(),return_index=True,return_inverse=True)
        axes.append(final[take]);maps.append(mapping.reshape(trace.shape[:2]))
    capacity=len(axes[0])*len(axes[1])
    stats=dict(x_states=len(axes[0]),y_states=len(axes[1]),product=capacity,axis_microsteps=(2*len(front.x)+3*len(front.y))*hold)
    if capacity>max_product:return 'resource_limit',None,None,stats
    bits,count,checked=_advance(front.bits,len(front.x),len(front.y),tx,ty,*maps,len(axes[1]),capacity,
                                front.template,front.tick,hold,wave.geometry_white,wave.geometry_blue,cspace.payload)
    template=front.template.copy();template[8]=wave.env_schedule[front.tick+hold,8];template[9]=wave.env_schedule[front.tick+hold,12]
    child=BlueFrontier(*axes,bits,template,front.tick+hold)
    stats.update(states=int(count),joint_edges_checked=int(checked),bitset_bytes=bits.nbytes)
    return 'complete',child,(maps[0],maps[1]),stats


def predecessor(wave,front,child,target,maps,hold,cspace):
    """One safe real predecessor, with collision rechecked at every microtick."""
    tx,ty=target
    if not child.contains(tx,ty):raise ValueError('target is unreachable')
    jump=1 if front.template[7]==0 else 2
    for ax in range(2):
        xs=np.flatnonzero(maps[0][ax]==tx)
        for ay in range(3):
            ys=np.flatnonzero(maps[1][ay]==ty);mask=ax*jump+ay*4
            expected=child.state(tx,ty,mask)
            for ix in xs:
                for iy in ys:
                    if not front.contains(ix,iy):continue
                    s=front.state(ix,iy);safe=True
                    for tick in range(front.tick+1,front.tick+hold+1):
                        step_mask_into(s,mask,wave.env_schedule[tick],wave.platform_table[tick],s)
                        if collision_query(wave.geometry_white,wave.geometry_blue,tick,s,0.,cspace.payload):safe=False;break
                    if safe and s.tobytes()==expected.tobytes():return (int(ix),int(iy)),mask
    raise AssertionError('reachable joint state has no exact safe predecessor')


def full_states(front):
    """Expand all actual terminal arrow aliases after a completed blue edge."""
    jump=1 if front.template[7]==0 else 2
    for ix in range(len(front.x)):
        for iy in range(len(front.y)):
            if not front.contains(ix,iy):continue
            for mask in range(16):
                up=int(bool(mask&4))-int(bool(mask&8))
                if (mask&jump)!=front.x[ix,2] or -up*150.!=front.y[iy,1]:continue
                yield front.state(ix,iy,mask)
