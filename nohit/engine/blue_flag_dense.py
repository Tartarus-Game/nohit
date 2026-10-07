"""Horizontal blue product with exact coupled slammed bitplanes.

Only zero slam-damage environments are supported: the flag then cannot feed
back into kinematics. Collisions clear it and Timeline slams reset it. Both
possible flag values remain in the joint relation, never just one axis.
"""
from dataclasses import dataclass
import numpy as np
from numba import njit
from .blue_dense import _strict,_count
from .discrete_operator import step_mask_into,direction_xy
from .cspace import collision_query


@dataclass
class FlagFrontier:
    x: np.ndarray # x, dx, full previous horizontal L/R bits
    y: np.ndarray # y, dy
    bits: np.ndarray # [slammed=0/1, packed joint IDs]
    template: np.ndarray
    tick: int

    def contains(self,ix,iy,flag):
        key=int(ix)*len(self.y)+int(iy)
        return bool((int(self.bits[int(flag),key//64])>>(key%64))&1)

    def state(self,ix,iy,flag,mask=None):
        s=self.template.copy();s[0],s[2],lr=self.x[ix];s[1],s[3]=self.y[iy];s[5]=flag
        s[4]=int(lr)+(4 if s[3]<0 else 8 if s[3]>0 else 0) if mask is None else mask
        return s

    def count(self):return int(_count(self.bits[0])+_count(self.bits[1]))


@njit(cache=True)
def _lift(bits,nx,ny,mapping,newnx,flag):
    out=np.zeros((2,(newnx*ny+63)//64),np.uint64)
    for ix in range(nx):
        for iy in range(ny):
            key=ix*ny+iy
            if not bits[key//64]&(np.uint64(1)<<np.uint64(key%64)):continue
            for alias in range(2):
                new=mapping[alias,ix]*ny+iy
                out[flag,new//64]|=np.uint64(1)<<np.uint64(new%64)
    return out


def lift_completed_blue(front):
    """Restore all actual horizontal aliases from a completed restricted edge.

    Do not apply to arbitrary initial observations: the prior completed edge
    must have enumerated all 16 arrows modulo its proved control congruence.
    """
    jump=1 if front.template[7]==0 else 2;other=3^jump
    variants=np.tile(front.x,(2,1));variants[len(front.x):,2]+=other
    _,take,mapping=np.unique(variants.view('V24').ravel(),return_index=True,return_inverse=True)
    x=variants[take];mapping=mapping.reshape(2,len(front.x))
    bits=_lift(front.bits,len(front.x),len(front.y),mapping,len(x),int(front.template[5]))
    result,xmap,ymap=compact_flag(FlagFrontier(x,front.y.copy(),bits,front.template.copy(),front.tick))
    # Conversion preserves an explicit map for BOTH axes. Dead marginal IDs
    # map to -1; they had no joint predecessor and are never reachable origins.
    return result,(xmap[mapping],ymap)


@njit(cache=True)
def _active(bits,nx,ny):
    xs=np.zeros(nx,np.bool_);ys=np.zeros(ny,np.bool_)
    for ix in range(nx):
        for iy in range(ny):
            key=ix*ny+iy;bit=np.uint64(1)<<np.uint64(key%64)
            if (bits[0,key//64]|bits[1,key//64])&bit:xs[ix]=True;ys[iy]=True
    return xs,ys


@njit(cache=True)
def _remap(bits,oldny,xs,ys):
    ny=len(ys);out=np.zeros((2,(len(xs)*ny+63)//64),np.uint64)
    for ix in range(len(xs)):
        for iy in range(ny):
            old=xs[ix]*oldny+ys[iy];oldbit=np.uint64(1)<<np.uint64(old%64)
            key=ix*ny+iy;bit=np.uint64(1)<<np.uint64(key%64)
            for flag in range(2):
                if bits[flag,old//64]&oldbit:out[flag,key//64]|=bit
    return out


def compact_flag(front):
    """Delete only empty marginal rows/columns of the exact joint relation."""
    ax,ay=_active(front.bits,len(front.x),len(front.y));xs=np.flatnonzero(ax);ys=np.flatnonzero(ay)
    mx=np.full(len(front.x),-1,np.int64);my=np.full(len(front.y),-1,np.int64)
    mx[xs]=np.arange(len(xs));my[ys]=np.arange(len(ys))
    if len(xs)==len(front.x) and len(ys)==len(front.y):return front,mx,my
    return FlagFrontier(front.x[xs],front.y[ys],_remap(front.bits,len(front.y),xs,ys),front.template.copy(),front.tick),mx,my


def supported(wave,front,hold):
    rows=wave.env_schedule[front.tick+1:front.tick+hold+1]
    if len(rows)!=hold or rows.shape[1]!=22 or not np.isfinite(rows).all():return False
    if front.template[6]!=1 or front.template[7] not in (0,2) or front.template[9]!=0 or front.template[10]!=0:return False
    if np.any(rows[:,4]!=1) or np.any((rows[:,5]!=0)&(rows[:,5]!=2)) or np.any(rows[:,9]!=0) or np.any(rows[:,12]!=0):return False
    bounds=rows[0,:4]
    if not all(np.all(rows[:,j:j+4]==bounds) for j in (0,14,18)):return False
    if np.any(wave.platform_table[front.tick+1:front.tick+hold+1,:,6:8]):return False
    if wave.pending_target is not None and wave.pending_target['tick']<=front.tick+hold:return False
    if any(front.tick<t<=front.tick+hold and cmd=='getheartpos' for t,cmd,_ in wave.source_events):return False
    if wave.termination_reason=='dialogue_boundary' and front.tick+hold>=len(wave.env_schedule)-1:return False
    return True


@njit(cache=True)
def _traces(x,y,template,start,hold,env):
    tx=np.empty((4,len(x),hold,3));ty=np.empty((3,len(y),hold,2))
    keepx=np.ones((4,len(x)),np.bool_);keepy=np.ones((3,len(y)),np.bool_)
    empty=np.empty((0,9));first=env[start+1];cx=(first[0]+first[2])*.5;cy=(first[1]+first[3])*.5
    last_slam=-1
    for j in range(hold):
        if env[start+j+1,6]:last_slam=j
    for a in range(4):
        for i in range(len(x)):
            s=template.copy();s[0],s[2],s[4]=x[i]
            for j in range(hold):
                row=env[start+j+1];s[1]=cy;s[3]=0.;s[5]=1.;s[10]=0.
                if not _strict(s[0],row[0],row[2]):return False,tx,ty,keepx,keepy,last_slam
                step_mask_into(s,a,row,empty,s)
                if not _strict(s[0],row[0],row[2]) or s[10]!=0:return False,tx,ty,keepx,keepy,last_slam
                if j>last_slam and s[5]==0:keepx[a,i]=False
                tx[a,i,j,0]=s[0];tx[a,i,j,1]=s[2];tx[a,i,j,2]=s[4]
    for a in range(3):
        for i in range(len(y)):
            s=template.copy();s[1],s[3]=y[i];s[4]=0.
            for j in range(hold):
                row=env[start+j+1];s[0]=cx;s[2]=0.;s[5]=1.;s[10]=0.
                if not _strict(s[1],row[1],row[3]):return False,tx,ty,keepx,keepy,last_slam
                step_mask_into(s,a*4,row,empty,s);gx,gy=direction_xy(row[5])
                if not _strict(s[1],row[1],row[3]) or not _strict(s[1]+gy,row[1],row[3]) or not _strict(s[1]+gy*.2,row[1],row[3]) or s[10]!=0:
                    return False,tx,ty,keepx,keepy,last_slam
                if j>last_slam and s[5]==0:keepy[a,i]=False
                ty[a,i,j,0]=s[1];ty[a,i,j,1]=s[3]
    return True,tx,ty,keepx,keepy,last_slam


@njit(cache=True)
def _advance(bits,nx,ny,tx,ty,keepx,keepy,last_slam,xmap,ymap,newny,capacity,template,start,hold,white,blue,payload):
    out=np.zeros((2,(capacity+63)//64),np.uint64);checked=0
    for ix in range(nx):
        for iy in range(ny):
            old=ix*ny+iy;oldbit=np.uint64(1)<<np.uint64(old%64)
            has0=bool(bits[0,old//64]&oldbit);has1=bool(bits[1,old//64]&oldbit)
            if not has0 and not has1:continue
            for ax in range(4):
                for ay in range(3):
                    survives=keepx[ax,ix] and keepy[ay,iy]
                    flag0=(not survives) or (last_slam<0 and has0)
                    flag1=survives and (last_slam>=0 or has1)
                    key=xmap[ax,ix]*newny+ymap[ay,iy];word=key//64;bit=np.uint64(1)<<np.uint64(key%64)
                    need0=flag0 and not bool(out[0,word]&bit);need1=flag1 and not bool(out[1,word]&bit)
                    if not need0 and not need1:continue
                    checked+=1;s=template.copy();s[5]=0.;s[10]=0.;safe=True
                    for j in range(hold):
                        s[0],s[2],s[4]=tx[ax,ix,j];s[1],s[3]=ty[ay,iy,j];s[4]=ax+ay*4
                        if collision_query(white,blue,start+j+1,s,0.,payload):safe=False;break
                    if safe:
                        if flag0:out[0,word]|=bit
                        if flag1:out[1,word]|=bit
    return out,checked


def advance_flag_blue(wave,front,hold,cspace,*,max_product=100_000_000):
    if hold<1 or max_product<1:raise ValueError('positive hold and budget required')
    if not supported(wave,front,hold):return 'unsupported',None,None,{'reason':'outside_zero_damage_horizontal_blue_domain'}
    valid,tx,ty,kx,ky,last_slam=_traces(front.x,front.y,front.template,front.tick,hold,wave.env_schedule)
    if not valid:return 'unsupported',None,None,{'reason':'strict_axis_certificate_failed'}
    axes=[];maps=[]
    for trace,width in ((tx,3),(ty,2)):
        final=np.ascontiguousarray(trace[:,:,-1,:]).reshape(-1,width)
        _,take,mapping=np.unique(final.view(f'V{width*8}').ravel(),return_index=True,return_inverse=True)
        axes.append(final[take]);maps.append(mapping.reshape(trace.shape[:2]))
    capacity=len(axes[0])*len(axes[1]);stats=dict(x_states=len(axes[0]),y_states=len(axes[1]),product=capacity)
    if capacity>max_product:return 'resource_limit',None,None,stats
    bits,checked=_advance(front.bits,len(front.x),len(front.y),tx,ty,kx,ky,last_slam,*maps,len(axes[1]),capacity,
                          front.template,front.tick,hold,wave.geometry_white,wave.geometry_blue,cspace.payload)
    template=front.template.copy();row=wave.env_schedule[front.tick+hold];template[5]=0.;template[6]=row[4];template[7]=row[5];template[8]=row[8];template[9]=row[12]
    child,mx,my=compact_flag(FlagFrontier(*axes,bits,template,front.tick+hold))
    stats.update(states=child.count(),flag0=int(_count(child.bits[0])),flag1=int(_count(child.bits[1])),joint_edges_checked=int(checked),
                 bitset_bytes=child.bits.nbytes,live_x_states=len(child.x),live_y_states=len(child.y),live_product=len(child.x)*len(child.y))
    return 'complete',child,(mx[maps[0]],my[maps[1]]),stats


def full_flag_states(front):
    for ix in range(len(front.x)):
        for iy in range(len(front.y)):
            for flag in (0,1):
                if not front.contains(ix,iy,flag):continue
                for vertical in (0,4,8,12):
                    up=int(bool(vertical&4))-int(bool(vertical&8))
                    if -up*150.!=front.y[iy,1]:continue
                    yield front.state(ix,iy,flag,int(front.x[ix,2])+vertical)


def flag_predecessor(wave,front,child,target,maps,hold,cspace):
    tx,ty,target_flag=target
    if not child.contains(tx,ty,target_flag):raise ValueError('unreachable target')
    for ax in range(4):
        xs=np.flatnonzero(maps[0][ax]==tx)
        for ay in range(3):
            ys=np.flatnonzero(maps[1][ay]==ty);mask=ax+ay*4;expected=child.state(tx,ty,target_flag,mask)
            for ix in xs:
                for iy in ys:
                    for flag in (0,1):
                        if not front.contains(ix,iy,flag):continue
                        s=front.state(ix,iy,flag);safe=True
                        for tick in range(front.tick+1,front.tick+hold+1):
                            step_mask_into(s,mask,wave.env_schedule[tick],wave.platform_table[tick],s)
                            if collision_query(wave.geometry_white,wave.geometry_blue,tick,s,0.,cspace.payload):safe=False;break
                        if safe and s.tobytes()==expected.tobytes():return (int(ix),int(iy),flag),mask
    raise AssertionError('missing exact predecessor')
