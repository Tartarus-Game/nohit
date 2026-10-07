"""Exact vertical C-space sections over ordered floating-point coordinates.

For fixed x, each rectangle/convex-quad SAT inequality is monotone in y.
Intersect its integer index bounds, using the ORIGINAL floating operations
instead of dividing by an edge slope or rounding geometric intersections.
This batches collision queries without identifying any player states.
"""
import math
import numpy as np
from numba import njit


@njit(cache=True)
def _first_false(ys,low,high,ax,ay,x,radius,bound,lower):
    while low<high:
        mid=(low+high)//2
        projection=ax*x+ay*ys[mid]
        failed=projection+radius<bound if lower else projection-radius>bound
        if failed:low=mid+1
        else:high=mid
    return low


@njit(cache=True)
def _first_true(ys,low,high,ax,ay,x,radius,bound,lower):
    while low<high:
        mid=(low+high)//2
        projection=ax*x+ay*ys[mid]
        failed=projection+radius<bound if lower else projection-radius>bound
        if failed:high=mid
        else:low=mid+1
    return low


@njit(cache=True)
def quad_y_interval(poly,x,ys,rx=2.,ry=2.):
    """[first,last) indices matching quad_intersects_box; ys must be sorted finite."""
    if not math.isfinite(poly[0]):return 0,0
    left=min(poly[0],poly[2],poly[4],poly[6]);right=max(poly[0],poly[2],poly[4],poly[6])
    top=min(poly[1],poly[3],poly[5],poly[7]);bottom=max(poly[1],poly[3],poly[5],poly[7])
    if x+rx<left or x-rx>right:return 0,0
    lo=0;hi=len(ys)
    # Bounding-box operations match the native query, including closed edges.
    while lo<hi:
        m=(lo+hi)//2
        if ys[m]+ry<top:lo=m+1
        else:hi=m
    first=lo;lo=first;hi=len(ys)
    while lo<hi:
        m=(lo+hi)//2
        if ys[m]-ry>bottom:hi=m
        else:lo=m+1
    last=lo
    for j in range(4):
        k=(j+1)%4
        ax=-(poly[k*2+1]-poly[j*2+1]);ay=poly[k*2]-poly[j*2]
        pmin=ax*poly[0]+ay*poly[1];pmax=pmin
        for q in range(1,4):
            dot=ax*poly[q*2]+ay*poly[q*2+1]
            pmin=min(pmin,dot);pmax=max(pmax,dot)
        radius=abs(ax)*rx+abs(ay)*ry
        if ay>0.:
            first=_first_false(ys,first,last,ax,ay,x,radius,pmin,True)
            last=_first_true(ys,first,last,ax,ay,x,radius,pmax,False)
        elif ay<0.:
            first=_first_false(ys,first,last,ax,ay,x,radius,pmax,False)
            last=_first_true(ys,first,last,ax,ay,x,radius,pmin,True)
        else:
            mid=ax*x+ay*(ys[first] if first<last else 0.)
            if mid+radius<pmin or mid-radius>pmax:return 0,0
        if first>=last:return 0,0
    return first,last


@njit(cache=True)
def rect_y_interval(box,x,ys,radius=2.):
    """Exact section of _rect_hit, including even inverted finite boxes."""
    if not (x+radius>=box[0] and x-radius<=box[2]):return 0,0
    if math.isnan(box[1]) or math.isnan(box[3]):return 0,0
    lo=0;hi=len(ys)
    while lo<hi:
        m=(lo+hi)//2
        if ys[m]+radius>=box[1]:hi=m
        else:lo=m+1
    first=lo;hi=len(ys)
    while lo<hi:
        m=(lo+hi)//2
        if ys[m]-radius<=box[3]:lo=m+1
        else:hi=m
    return first,lo


@njit(cache=True)
def _set_interval(bits,first,last):
    """Set [first,last) with word operations; does not touch padding bits."""
    while first<last and first%64:
        bits[first//64]|=np.uint64(1)<<np.uint64(first%64);first+=1
    while first+64<=last:
        bits[first//64]=np.uint64(0xffffffffffffffff);first+=64
    while first<last:
        bits[first//64]|=np.uint64(1)<<np.uint64(first%64);first+=1


@njit(cache=True)
def section_collision_bits(xs,ys,white,blue,polygons):
    """Two bit planes: unconditional hazards, and moving-only blue hazards.

    xs/ys must be finite; ys sorted numerically. State dynamics and slam damage
    are outside this observation operator. Each plane has row-major x/y bits.
    """
    ny=len(ys);bits=np.zeros((2,(len(xs)*ny+63)//64),np.uint64)
    for ix in range(len(xs)):
        x=xs[ix];offset=ix*ny
        for plane in range(2):
            boxes=white if plane==0 else blue
            for box in boxes:
                a,b=rect_y_interval(box,x,ys)
                _set_interval(bits[plane],offset+a,offset+b)
        for poly in polygons:
            a,b=quad_y_interval(poly,x,ys)
            _set_interval(bits[0],offset+a,offset+b)
    return bits
