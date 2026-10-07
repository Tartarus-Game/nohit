"""Exact continuous C-space queries accelerated by preclassified spatial cells.

A cell is free only when its entire closed square misses all expanded hazards.
A cell is blocked only when one convex expanded hazard contains all its corners.
Mixed cells use the original continuous coordinates and exact rectangle/quad
intersection. Thus cell size affects speed and memory, never route feasibility.
"""
from dataclasses import dataclass
import math
import numpy as np
from numba import njit


@dataclass(slots=True)
class CSpace:
    cells: np.ndarray
    polygons: np.ndarray
    origin: tuple[float, float]
    cell_size: float

    @property
    def payload(self):
        return (self.cells, self.polygons, float(self.origin[0]),
                float(self.origin[1]), float(self.cell_size))


@njit(cache=True, inline='always')
def quad_intersects_box(poly, x, y, rx, ry):
    """Closed convex quad vs axis-aligned box, separating-axis theorem."""
    if not math.isfinite(poly[0]):
        return False
    left=poly[0]; right=left; top=poly[1]; bottom=top
    for j in range(1,4):
        left=min(left,poly[j*2]); right=max(right,poly[j*2])
        top=min(top,poly[j*2+1]); bottom=max(bottom,poly[j*2+1])
    if x+rx<left or x-rx>right or y+ry<top or y-ry>bottom:
        return False
    for j in range(4):
        k=(j+1)%4
        ax=-(poly[k*2+1]-poly[j*2+1])
        ay=poly[k*2]-poly[j*2]
        lo=ax*poly[0]+ay*poly[1]; hi=lo
        for m in range(1,4):
            dot=ax*poly[m*2]+ay*poly[m*2+1]
            lo=min(lo,dot); hi=max(hi,dot)
        mid=ax*x+ay*y; radius=abs(ax)*rx+abs(ay)*ry
        if mid+radius<lo or mid-radius>hi:
            return False
    return True


@njit(cache=True, inline='always')
def _rect_hit(box,x,y,radius):
    return (x+radius>=box[0] and x-radius<=box[2] and
            y+radius>=box[1] and y-radius<=box[3])


@njit(cache=True)
def _bake(white,blue,polygons,ox,oy,cell_size,height,width):
    cells=np.zeros((len(white),2,height,width),np.uint8)
    for tick in range(len(white)):
        for plane in range(2):
            boxes=white[tick] if plane==0 else blue[tick]
            for box in boxes:
                if not math.isfinite(box[0]) or box[2]<box[0] or box[3]<box[1]:
                    continue
                l=box[0]-2.; r=box[2]+2.; t=box[1]-2.; b=box[3]+2.
                x0=max(0,int(math.floor((l-ox)/cell_size)))
                x1=min(width-1,int(math.floor((r-ox)/cell_size)))
                y0=max(0,int(math.floor((t-oy)/cell_size)))
                y1=min(height-1,int(math.floor((b-oy)/cell_size)))
                for yy in range(y0,y1+1):
                    cy=oy+yy*cell_size
                    for xx in range(x0,x1+1):
                        if cells[tick,plane,yy,xx]==1:
                            continue
                        cx=ox+xx*cell_size
                        if cx>=l and cx+cell_size<=r and cy>=t and cy+cell_size<=b:
                            cells[tick,plane,yy,xx]=1
                        else:
                            cells[tick,plane,yy,xx]=2
        for poly in polygons[tick]:
            if not math.isfinite(poly[0]):
                continue
            l=min(poly[0],poly[2],poly[4],poly[6])-2.
            r=max(poly[0],poly[2],poly[4],poly[6])+2.
            t=min(poly[1],poly[3],poly[5],poly[7])-2.
            b=max(poly[1],poly[3],poly[5],poly[7])+2.
            x0=max(0,int(math.floor((l-ox)/cell_size)))
            x1=min(width-1,int(math.floor((r-ox)/cell_size)))
            y0=max(0,int(math.floor((t-oy)/cell_size)))
            y1=min(height-1,int(math.floor((b-oy)/cell_size)))
            for yy in range(y0,y1+1):
                cy=oy+yy*cell_size
                for xx in range(x0,x1+1):
                    if cells[tick,0,yy,xx]==1:
                        continue
                    cx=ox+xx*cell_size
                    # Intersection of the cell with the C-obstacle is equivalent
                    # to intersecting the quad with cell Minkowski player-box.
                    half=cell_size*.5
                    if not quad_intersects_box(poly,cx+half,cy+half,half+2.,half+2.):
                        continue
                    full=True
                    for corner in range(4):
                        if not quad_intersects_box(poly,cx+(corner%2)*cell_size,
                                cy+(corner//2)*cell_size,2.,2.):
                            full=False
                            break
                    cells[tick,0,yy,xx]=1 if full else 2
    return cells


def bake_cspace(wave, cell_size=4.):
    """Bake once per fixed environment; no player states are rounded or merged."""
    if not math.isfinite(cell_size) or cell_size<=0:
        raise ValueError('cell_size must be positive and finite')
    polygons=getattr(wave,'geometry_polygons',None)
    if polygons is None:
        polygons=np.empty((len(wave.env_schedule),0,8),np.float64)
    height=max(1,math.ceil(wave.dimensions[0]/cell_size)+1)
    width=max(1,math.ceil(wave.dimensions[1]/cell_size)+1)
    ox,oy=wave.origin
    cells=_bake(wave.geometry_white,wave.geometry_blue,polygons,
                float(ox),float(oy),float(cell_size),height,width)
    return CSpace(cells,polygons,(float(ox),float(oy)),float(cell_size))


@njit(cache=True)
def collision_query(white,blue,tick,state,margin,collision_data):
    """Production operator contract used by the layered DAG-DP specialization."""
    cells,polygons,ox,oy,cell_size=collision_data
    if len(state)>10 and state[10]!=0.:
        return True
    x=state[0]; y=state[1]; radius=2.+margin
    moving=state[2]!=0. or state[3]!=0.
    xx=int(math.floor((x-ox)/cell_size)); yy=int(math.floor((y-oy)/cell_size))
    in_cells=(0<=xx<cells.shape[3] and 0<=yy<cells.shape[2] and margin==0.)
    for plane in range(2):
        if plane==1 and not moving:
            continue
        if in_cells:
            flag=cells[tick,plane,yy,xx]
            if flag==0:
                continue
            if flag==1:
                return True
        boxes=white[tick] if plane==0 else blue[tick]
        for box in boxes:
            if _rect_hit(box,x,y,radius):
                return True
        if plane==0:
            for poly in polygons[tick]:
                if quad_intersects_box(poly,x,y,radius,radius):
                    return True
    return False


@njit(cache=True)
def _signed_grid_distance(cells):
    """Two-pass Manhattan transform; approximate preference, never safety."""
    nt,np_,h,w=cells.shape
    result=np.empty(cells.shape,np.int16)
    distance=np.empty((h,w),np.int32)
    cap=min(30000,h+w+1)
    for tick in range(nt):
        for plane in range(np_):
            for target in range(2):
                for y in range(h):
                    for x in range(w):
                        blocked=cells[tick,plane,y,x]!=0
                        distance[y,x]=0 if blocked==(target==0) else cap
                for y in range(h):
                    for x in range(w):
                        if x>0: distance[y,x]=min(distance[y,x],distance[y,x-1]+1)
                        if y>0: distance[y,x]=min(distance[y,x],distance[y-1,x]+1)
                for y in range(h-1,-1,-1):
                    for x in range(w-1,-1,-1):
                        if x+1<w: distance[y,x]=min(distance[y,x],distance[y,x+1]+1)
                        if y+1<h: distance[y,x]=min(distance[y,x],distance[y+1,x]+1)
                        if target==0 and cells[tick,plane,y,x]==0:
                            result[tick,plane,y,x]=distance[y,x]
                        elif target==1 and cells[tick,plane,y,x]!=0:
                            result[tick,plane,y,x]=-distance[y,x]
    return result


def bake_guidance(cspace):
    """Optional smooth style cost over the same baked environment, no new search."""
    return _signed_grid_distance(cspace.cells)


@njit(cache=True,inline='always')
def guidance_query(field,tick,x,y,ox,oy,cell_size,moving):
    fx=(x-ox)/cell_size-.5; fy=(y-oy)/cell_size-.5
    fx=max(0.,min(field.shape[3]-1.,fx)); fy=max(0.,min(field.shape[2]-1.,fy))
    x0=int(math.floor(fx)); y0=int(math.floor(fy))
    x1=min(x0+1,field.shape[3]-1); y1=min(y0+1,field.shape[2]-1)
    ax=fx-x0; ay=fy-y0
    value=1.e10
    for plane in range(2 if moving else 1):
        a=float(field[tick,plane,y0,x0])*(1.-ax)+field[tick,plane,y0,x1]*ax
        b=float(field[tick,plane,y1,x0])*(1.-ax)+field[tick,plane,y1,x1]*ax
        value=min(value,a*(1.-ay)+b*ay)
    return value*cell_size


@njit(cache=True)
def _navigation_cost(cells,clearance,env,ox,oy,size,stride):
    """Backward style cost on coarse positions, not a feasibility certificate.

    Its dynamics are deliberately only guidance. Actual acceptance still uses
    the complete state operator and continuous C-space query at every microstep.
    """
    nt,planes,h,w=cells.shape
    layers=(nt-1+stride-1)//stride+1
    values=np.zeros((layers,h,w),np.float32)
    blue_during=np.zeros((h,w),np.uint8)
    for layer in range(layers-1,-1,-1):
        tick=min(layer*stride,nt-1)
        blue_during[:,:]=0
        for t in range(tick+1,min(tick+stride+1,nt)):
            for y in range(h):
                for x in range(w):
                    if cells[t,1,y,x]:blue_during[y,x]=1
        for y in range(h):
            cy=oy+(y+.5)*size
            for x in range(w):
                cx=ox+(x+.5)*size
                penalty=0.
                if cx<env[tick,0]+13. or cx>env[tick,2]-13. or cy<env[tick,1]+13. or cy>env[tick,3]-13.:
                    penalty+=10000.
                # Include hazards during the whole coarse interval. Mixed cells
                # carry finite preference cost only; no candidate is rejected.
                for t in range(max(0,tick-stride+1),tick+1):
                    if cells[t,0,y,x]:penalty+=1000.
                penalty+=1./(1.+max(0.,float(clearance[tick,0,y,x])))
                if layer+1<layers:
                    best=1.e20
                    for dy in range(-1,2):
                        yy=y+dy
                        if yy<0 or yy>=h:continue
                        for dx in range(-1,2):
                            xx=x+dx
                            if xx<0 or xx>=w:continue
                            edge=.01*(abs(dx)+abs(dy))
                            # Blue hazards punish movement only. A wait edge
                            # has no such penalty; exact velocity dependence
                            # remains the responsibility of collision_query.
                            if (dx!=0 or dy!=0) and (blue_during[y,x] or blue_during[yy,xx]):
                                edge+=1000.
                            best=min(best,values[layer+1,yy,xx]+edge)
                    penalty+=best
                values[layer,y,x]=penalty
    return values


def bake_navigation(cspace,env,stride=16,clearance=None):
    if stride<1:raise ValueError('navigation stride must be positive')
    if clearance is None:clearance=bake_guidance(cspace)
    return _navigation_cost(cspace.cells,clearance,env,
                            *cspace.origin,cspace.cell_size,stride)


@njit(cache=True,inline='always')
def navigation_query(values,tick,x,y,ox,oy,size,stride):
    layer=min(values.shape[0]-1,int(tick//stride))
    fx=max(0.,min(values.shape[2]-1.,(x-ox)/size-.5))
    fy=max(0.,min(values.shape[1]-1.,(y-oy)/size-.5))
    x0=int(fx);y0=int(fy);x1=min(x0+1,values.shape[2]-1);y1=min(y0+1,values.shape[1]-1)
    ax=fx-x0;ay=fy-y0
    a=values[layer,y0,x0]*(1.-ax)+values[layer,y0,x1]*ax
    b=values[layer,y1,x0]*(1.-ax)+values[layer,y1,x1]*ax
    return a*(1.-ay)+b*ay
