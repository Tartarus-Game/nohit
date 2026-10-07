"""Exact unions of Cartesian relations in a certified white-strip C-space.

Flags remain separate relations. Rectangles here are sets of exact axis IDs,
not geometric bounding boxes, rounded coordinates, or an independent-marginal
approximation. Every union/product identity is Boolean relational algebra.
"""
from dataclasses import dataclass
import numpy as np
from numba import njit
from .blue_flag_dense import supported,_traces
from .blue_dense import _count
from .discrete_operator import step_mask_into
from .cspace import collision_query


@dataclass
class ProductFrontier:
    x: np.ndarray
    y: np.ndarray
    rectangles: list # (flag, sorted x IDs, sorted y IDs)
    template: np.ndarray
    tick: int

    def contains(self,ix,iy,flag):
        for f,xs,ys in self.rectangles:
            if f!=flag:continue
            a=np.searchsorted(xs,ix);b=np.searchsorted(ys,iy)
            if a<len(xs) and xs[a]==ix and b<len(ys) and ys[b]==iy:return True
        return False

    def state(self,ix,iy,flag,mask=None):
        s=self.template.copy();s[0],s[2],lr=self.x[ix];s[1],s[3]=self.y[iy];s[5]=flag
        s[4]=int(lr)+(4 if s[3]<0 else 8 if s[3]>0 else 0) if mask is None else mask
        return s

    def counts(self,*,include_vertical_aliases=False):
        counts=[]
        for flag in (0,1):
            rects=[r for r in self.rectangles if r[0]==flag];groups={}
            for iy in range(len(self.y)):
                membership=[]
                for i,(_,xs,ys) in enumerate(rects):
                    pos=np.searchsorted(ys,iy)
                    if pos<len(ys) and ys[pos]==iy:membership.append(i)
                key=tuple(membership)
                if key:groups[key]=groups.get(key,0)+(2 if include_vertical_aliases and self.y[iy,1]==0. else 1)
            count=0
            for group,n in groups.items():
                xs=np.unique(np.concatenate([rects[i][1] for i in group]));count+=len(xs)*n
            counts.append(count)
        return tuple(counts)


def from_full_flag_plane(front,flag=0):
    capacity=len(front.x)*len(front.y)
    if int(_count(front.bits[flag]))!=capacity or int(_count(front.bits[1-flag]))!=0:
        raise ValueError('requires verified full Cartesian product in one flag plane')
    return ProductFrontier(front.x.copy(),front.y.copy(),[(flag,np.arange(len(front.x)),np.arange(len(front.y)))],front.template.copy(),front.tick)


def strip_geometry(wave,start,hold):
    """Exact proof that each white box depends on just one feasible axis.

    Colored moving-only boxes and quads are deliberately unsupported. Bounds
    use the same closed x +/- 2 arithmetic as collision_query.
    """
    x=[];y=[]
    for tick in range(start+1,start+hold+1):
        if np.any(np.isfinite(wave.geometry_blue[tick])):return None
        if wave.geometry_polygons is not None and np.any(np.isfinite(wave.geometry_polygons[tick])):return None
        row=wave.env_schedule[tick];left,top,right,bottom=row[:4]
        xb=[];yb=[]
        for box in wave.geometry_white[tick]:
            if np.isnan(box).all():continue
            if not np.isfinite(box).all():return None
            if top+13.+2.>=box[1] and bottom-13.-2.<=box[3]:xb.append((box[0],box[2]))
            elif left+13.+2.>=box[0] and right-13.-2.<=box[2]:yb.append((box[1],box[3]))
            else:return None
        x.append(xb);y.append(yb)
    def pack(rows):
        result=np.full((hold,max(map(len,rows),default=0),2),np.nan)
        for i,row in enumerate(rows):
            if row:result[i,:len(row)]=row
        return result
    return pack(x),pack(y)


@njit(cache=True)
def _axis_safe(trace,boxes):
    valid=np.ones(trace.shape[:2],np.bool_)
    for a in range(trace.shape[0]):
        for i in range(trace.shape[1]):
            for tick in range(trace.shape[2]):
                p=trace[a,i,tick,0]
                for j in range(boxes.shape[1]):
                    if p+2.>=boxes[tick,j,0] and p-2.<=boxes[tick,j,1]:valid[a,i]=False
    return valid


def _merge(rectangles):
    rectangles=[(f,np.unique(xs),np.unique(ys)) for f,xs,ys in rectangles if len(xs) and len(ys)]
    changed=True
    while changed:
        changed=False
        for i in range(len(rectangles)):
            if changed:break
            f,x,y=rectangles[i]
            for j in range(i+1,len(rectangles)):
                g,u,v=rectangles[j]
                if f!=g:continue
                if np.array_equal(x,u):rectangles[i]=(f,x,np.union1d(y,v))
                elif np.array_equal(y,v):rectangles[i]=(f,np.union1d(x,u),y)
                else:continue
                rectangles.pop(j);changed=True;break
    return rectangles


def advance_product(wave,front,hold,cspace,*,max_axis_states=2_000_000,max_rectangles=256):
    if not supported(wave,front,hold):return 'unsupported',None,None,{'reason':'outside_zero_damage_horizontal_blue_domain'}
    geometry=strip_geometry(wave,front.tick,hold)
    if geometry is None:return 'unsupported',None,None,{'reason':'cspace_not_certified_axis_strips'}
    valid,tx,ty,kx,ky,last_slam=_traces(front.x,front.y,front.template,front.tick,hold,wave.env_schedule)
    if not valid:return 'unsupported',None,None,{'reason':'strict_axis_certificate_failed'}
    vx=_axis_safe(tx,geometry[0]);vy=_axis_safe(ty,geometry[1]);axes=[];maps=[]
    for trace,width in ((tx,3),(ty,2)):
        final=np.ascontiguousarray(trace[:,:,-1,:]).reshape(-1,width)
        _,take,mapping=np.unique(final.view(f'V{width*8}').ravel(),return_index=True,return_inverse=True)
        if len(take)>max_axis_states:return 'resource_limit',None,None,{'reason':'axis_states','count':len(take)}
        axes.append(final[take]);maps.append(mapping.reshape(trace.shape[:2]))
    rectangles=[]
    for flag,xs,ys in front.rectangles:
        groups=[]
        for ids,mapping,safe,kept in ((xs,maps[0],vx,kx),(ys,maps[1],vy,ky)):
            dest=mapping[:,ids];ok=safe[:,ids];survive=kept[:,ids]
            groups.append((np.unique(dest[ok]),np.unique(dest[ok&survive]),np.unique(dest[ok&~survive])))
        (xa,xk,xc),(ya,yk,yc)=groups
        if flag==0 and last_slam<0:rectangles.append((0,xa,ya))
        else:
            rectangles.extend(((1,xk,yk),(0,xc,ya),(0,xa,yc)))
    rectangles=_merge(rectangles)
    if len(rectangles)>max_rectangles:return 'resource_limit',None,None,{'reason':'rectangle_count','count':len(rectangles)}
    active_x=np.unique(np.concatenate([r[1] for r in rectangles])) if rectangles else np.empty(0,np.int64)
    active_y=np.unique(np.concatenate([r[2] for r in rectangles])) if rectangles else np.empty(0,np.int64)
    mx=np.full(len(axes[0]),-1,np.int64);my=np.full(len(axes[1]),-1,np.int64)
    mx[active_x]=np.arange(len(active_x));my[active_y]=np.arange(len(active_y))
    rectangles=[(f,mx[xs],my[ys]) for f,xs,ys in rectangles]
    template=front.template.copy();row=wave.env_schedule[front.tick+hold];template[5]=0.;template[6]=row[4];template[7]=row[5];template[8]=row[8];template[9]=row[12]
    child=ProductFrontier(axes[0][active_x],axes[1][active_y],rectangles,template,front.tick+hold)
    c0,c1=child.counts()
    full0,full1=child.counts(include_vertical_aliases=True)
    stats=dict(x_states=len(child.x),y_states=len(child.y),rectangles=len(rectangles),flag0=c0,flag1=c1,
               states=c0+c1,full11_states=full0+full1,implicit_product=len(child.x)*len(child.y),
               stored_bytes=child.x.nbytes+child.y.nbytes+sum(xs.nbytes+ys.nbytes for _,xs,ys in rectangles),
               axis_microsteps=(4*len(front.x)+3*len(front.y))*hold)
    return 'complete',child,(mx[maps[0]],my[maps[1]]),stats


def product_predecessor(wave,front,child,target,maps,hold,cspace):
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
