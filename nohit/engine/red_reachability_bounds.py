"""Sufficient dead-state certificates for a restricted red-heart window.

This is interval reachability through the source operator, not a route rollout.
Each CustomMovement axis has one substep in the supported window. A solid test
can retain the old coordinate or accept its displaced coordinate; even though
the vertical solid predicate depends on the new x, both outcomes lie in their
axis interval. The first displacement uses the incoming velocity. Subsequent
red inputs have velocities in [-150,150], including Cancel and opposing keys.

Every multiply/add bound is rounded outward with nextafter. We keep zero in
the displacement hull because a wall can stop motion. Rather than assuming
that native conditional clamps equal mathematical clipping, this initial
certificate stops before any interval could trigger a clamp. It also stops
before resize, teleport, slam, blue mode, or an active platform. These are
unknown results, never dead-state proofs. The caller truncates before unresolved
target observations and supplies only committed environment rows.

A white rectangle covering the entire propagated box proves every surviving
control word collides by that tick. The rectangle comparisons use the original
player +/-2 arithmetic, including closed boundaries, rather than algebraically
rearranging them. No finite search budget, uncovered box, or unsupported event
is interpreted as feasibility or infeasibility.
"""
import math
from numba import njit


@njit(cache=True)
def red_box_deadline_details(white,env,platforms,tick,state,stop_tick):
    """Return (dead, death_tick, checked_through, xlo, ylo, xhi, yhi)."""
    xlo=xhi=state[0];ylo=yhi=state[1]
    checked=tick
    if (len(state)<11 or len(env)==0 or env.shape[1]<22 or tick<0
            or tick>=len(env) or state[6]!=0. or state[5]!=0. or state[10]!=0.):
        return False,-1,checked,xlo,ylo,xhi,yhi
    for value in state:
        if not math.isfinite(value):return False,-1,checked,xlo,ylo,xhi,yhi
    l,t,r,b=env[tick,0],env[tick,1],env[tick,2],env[tick,3]
    if not (math.isfinite(l) and math.isfinite(t) and math.isfinite(r) and math.isfinite(b)):
        return False,-1,checked,xlo,ylo,xhi,yhi
    if r-l<=26. or b-t<=26.:return False,-1,checked,xlo,ylo,xhi,yhi
    last=min(stop_tick,len(env)-1,len(white)-1,len(platforms)-1)
    for future in range(tick+1,last+1):
        row=env[future]
        if row[4]!=0. or row[6]!=0. or row[9]!=0.:
            return False,-1,checked,xlo,ylo,xhi,yhi
        for offset in (0,14,18):
            if row[offset]!=l or row[offset+1]!=t or row[offset+2]!=r or row[offset+3]!=b:
                return False,-1,checked,xlo,ylo,xhi,yhi
        for platform in platforms[future]:
            if platform[6]!=0. or (len(platform)>7 and platform[7]!=0.):
                return False,-1,checked,xlo,ylo,xhi,yhi
        dt=row[7]
        maximum_delta=150.*dt
        if (not math.isfinite(dt) or dt<=0. or not math.isfinite(maximum_delta)
                or math.sqrt(maximum_delta*maximum_delta)+.5>=2.):
            return False,-1,checked,xlo,ylo,xhi,yhi
        if future==tick+1:
            dx=state[2]*dt;dy=state[3]*dt
            if not (math.isfinite(dx) and math.isfinite(dy)
                    and math.sqrt(dx*dx)+.5<2. and math.sqrt(dy*dy)+.5<2.):
                return False,-1,checked,xlo,ylo,xhi,yhi
            dxlo=math.nextafter(dx,-math.inf);dxhi=math.nextafter(dx,math.inf)
            dylo=math.nextafter(dy,-math.inf);dyhi=math.nextafter(dy,math.inf)
        else:
            dxlo=dylo=math.nextafter(-150.*dt,-math.inf)
            dxhi=dyhi=math.nextafter(150.*dt,math.inf)
        # count=1: solid contact chooses start, otherwise fl(start+delta).
        nxlo=math.nextafter(xlo+min(0.,dxlo),-math.inf)
        nxhi=math.nextafter(xhi+max(0.,dxhi),math.inf)
        nylo=math.nextafter(ylo+min(0.,dylo),-math.inf)
        nyhi=math.nextafter(yhi+max(0.,dyhi),math.inf)
        if not (math.isfinite(nxlo) and math.isfinite(nxhi) and math.isfinite(nylo) and math.isfinite(nyhi)):
            return False,-1,checked,xlo,ylo,xhi,yhi
        # Monotonic IEEE arithmetic makes endpoint comparisons sufficient for
        # every point in the box to skip all four native clamp assignments.
        if l+5.>nxlo-8. or t+5.>nylo-8. or r-5.<nxhi+8. or b-5.<nyhi+8.:
            return False,-1,checked,xlo,ylo,xhi,yhi
        if (future==tick+1 and nxlo-8.>l+5. and nylo-8.>t+5.
                and nxhi+8.<r-5. and nyhi+8.<b-5.):
            # The whole old-to-proposed box misses every border object.
            # With no platforms, neither solid test can stop the known first
            # displacement, regardless of their horizontal/vertical ordering.
            nxlo=math.nextafter(xlo+dxlo,-math.inf)
            nxhi=math.nextafter(xhi+dxhi,math.inf)
            nylo=math.nextafter(ylo+dylo,-math.inf)
            nyhi=math.nextafter(yhi+dyhi,math.inf)
        xlo,xhi,ylo,yhi=nxlo,nxhi,nylo,nyhi;checked=future
        for box in white[future]:
            if (math.isfinite(box[0]) and math.isfinite(box[1]) and math.isfinite(box[2])
                    and math.isfinite(box[3]) and box[0]<=box[2] and box[1]<=box[3]
                    and xlo+2.>=box[0] and xhi-2.<=box[2]
                    and ylo+2.>=box[1] and yhi-2.<=box[3]):
                return True,future,checked,xlo,ylo,xhi,yhi
    return False,-1,checked,xlo,ylo,xhi,yhi


@njit(cache=True)
def red_box_deadline(white,env,platforms,tick,state,stop_tick):
    """True alone certifies death; False means unknown, including truncation."""
    return red_box_deadline_details(white,env,platforms,tick,state,stop_tick)[0]
