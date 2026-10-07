"""Pure mathematical transitions for static, axis-aligned jcw attacks.

No engine snapshots are searched. Collision uses floating point rectangles;
there is no coordinate binning. Search scheduling lives in adaptive_dag.
"""
import math
import numpy as np
from numba import njit


@njit(cache=True)
def solid(x, y, dy, env, platforms, offset=0.):
    if x-8 < env[0]+5 or x+8 > env[2]-5 or y+offset-8 < env[1]+5 or y+offset+8 > env[3]-5:
        return True
    for p in platforms:
        if p[6] and x+8>p[0] and x-8<p[0]+p[2] and y+offset+8>p[1] and y+offset-8<p[1]+p[3]:
            if p[1]>y+offset and dy>=p[5] and y+8<=p[1]+2:
                return True
    return False


@njit(cache=True, inline='always')
def step_into(s, ux, up, env, platforms, out):
    x,y,dx,dy,prev=s
    dt=env[7]
    start=x
    count=max(1,int(math.floor(abs(dx*dt)+.5)))
    for i in range(1,count+1):
        candidate=start+dx*dt*(i/count)
        if solid(candidate,y,dy,env,platforms):
            break
        x=candidate
    start=y
    count=max(1,int(math.floor(abs(dy*dt)+.5)))
    for i in range(1,count+1):
        candidate=start+dy*dt*(i/count)
        if solid(x,candidate,dy,env,platforms):
            y=start+dy*dt*((i-1)/count)
            dy=0.
            break
        y=candidate
    if env[4] == 0:
        # Original InputManagement sets both axes independently. Diagonal
        # movement is faster; normalizing it loses valid trajectories.
        out[0],out[1],out[2],out[3],out[4]=x,y,ux*150.,-up*150.,float(up)
        return
    if up and not prev and solid(x,y,dy,env,platforms,1.):
        dy-=180.
    if prev and not up and dy < -30.:
        dy=-30.
    gravity=0.
    if 15<dy<240: gravity=540.
    elif -30<dy<=15: gravity=180.
    elif -120<dy<=-30: gravity=450.
    elif dy<=-120: gravity=180.
    if not solid(x,y,dy,env,platforms,.2):
        dy=min(750.,dy+gravity*dt)
    dx=0.
    for p in platforms:
        if p[6] and x+8>p[0] and x-8<p[0]+p[2] and y+.5+8>p[1] and y+.5-8<p[1]+p[3] and dy>=p[5] and y+8<=p[1]+2:
            dx,dy,y=p[4],p[5],p[1]-8.05
    out[0],out[1],out[2],out[3],out[4]=x,y,dx+ux*150.,dy,float(up)


@njit(cache=True)
def step(s, ux, up, env, platforms):
    out=np.empty(5,np.float64)
    step_into(s,ux,up,env,platforms,out)
    return out


@njit(cache=True)
def collision(white, blue, tick, s, margin):
    for b in white[tick]:
        if s[0]+2+margin>=b[0] and s[0]-2-margin<=b[2] and s[1]+2+margin>=b[1] and s[1]-2-margin<=b[3]:
            return True
    if s[2]!=0 or s[3]!=0:
        for b in blue[tick]:
            if s[0]+2+margin>=b[0] and s[0]-2-margin<=b[2] and s[1]+2+margin>=b[1] and s[1]-2-margin<=b[3]:
                return True
    return False


