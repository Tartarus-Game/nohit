"""Source-derived discrete player operator for the original jcw event sheet.

The environment is an explicit time-indexed input, never an engine checkpoint.
State (float64, 11): x,y,dx,dy,keymask,slammed,mode,direction,max_fall,
slam_damage,damage_this_tick.  Direction is right/down/left/up = 0/1/2/3.
The key mask preserves all edge-triggered inputs: L=1,R=2,U=4,D=8,Cancel=16.

Environment (22): L,T,R,B,mode,direction,slam_pulse,dt,max_fall,
teleport_pulse,teleport_x,teleport_y,slam_damage,mode_pulse,old_L,old_T,old_R,
old_B,mid_L,mid_T,mid_R,mid_B. Old bounds belong to behavior movement;
mid bounds follow timeline instant resizing; current bounds follow the late
CombatZoneTick. Platforms are current behavior-phase
positions [left,top,width,height,dx,dy,active,pre_timeline_active,pre_movement_dy].
The optional last fields exclude newborn platforms from preceding movement and
preserve their pre-bounce vertical speed for its one-way contact predicate.

Tick order is CustomMovement (horizontal then vertical), timeline resets,
PlayerMovement input/gravity/contact, and late CombatZoneTick clamping.
InstantResize explicitly invokes an additional CombatZoneTick in Timeline.
Damage from a damaging slam is returned as state[10], for the safety oracle.

This is the active-battle player operator. Simulator/menu transitions belong to
the outer controller: in original MODE_SINGLE, a rising Cancel input exits the
layout, so that context must exclude such edges or use a fuller global state.
X and Shift are equivalent Cancel keys; remapping does not avoid that rule.

Source: .capx_extract/Event sheets/Battle.xml, PlayerMovement group
6451037740410459, and the Cc CustomMovement behavior in c2runtime.js.
Do not use the older c2step/c2spec modules as authoritative transcriptions.
"""
import math
import numpy as np
from numba import njit

STATE_WIDTH = 11
ENV_WIDTH = 22
LEFT, RIGHT, UP, DOWN, CANCEL = 1, 2, 4, 8, 16


def initial_state(initial, env, *, keymask=None, slammed=False, mode=None,
                  direction=None, max_fall=None, slam_damage=None):
    """Lift an observed legacy state without inventing prior input edges.

Callers with native observations should supply the optional persistent fields.
An already complete state is copied verbatim.
"""
    initial = np.asarray(initial, dtype=np.float64)
    if initial.shape == (STATE_WIDTH,):
        return initial.copy()
    if initial.shape != (5,):
        raise ValueError("player state must contain 5 legacy or 11 complete values")
    s = np.zeros(STATE_WIDTH, dtype=np.float64)
    s[:4] = initial[:4]
    s[4] = (UP if initial[4] > 0 else DOWN if initial[4] < 0 else 0) if keymask is None else keymask
    s[5] = float(slammed)
    s[6] = env[4] if mode is None else mode
    s[7] = env[5] if direction is None else direction
    s[8] = (env[8] if len(env) > 8 else 750.) if max_fall is None else max_fall
    s[9] = (env[12] if len(env) > 12 else 0.) if slam_damage is None else slam_damage
    return s


@njit(cache=True, inline='always')
def direction_xy(direction):
    # JS uses Math.cos/Math.sin even for cardinal angles. Keeping the residual
    # matters when velocity, rather than displacement, controls blue damage.
    angle = direction * (math.pi / 2.)
    return math.cos(angle), math.sin(angle)


@njit(cache=True, inline='always')
def overlaps(x, y, l, t, r, b):
    # Native rect/quad/poly tests include touching edges. Read-only native
    # HeartCheckSolid at L+13+eps confirmed [-1e-9,0,+1e-9] -> [1,1,0].
    return x+8. >= l and x-8. <= r and y+8. >= t and y-8. <= b


@njit(cache=True, inline='always')
def heart_solid(x, y, dy, direction, bounds, platforms, ox=0., oy=0., old=False):
    j = 14 if old and len(bounds) >= 18 else 18 if not old and len(bounds) >= 22 else 0
    l,t,r,b = bounds[j],bounds[j+1],bounds[j+2],bounds[j+3]
    qx,qy = x+ox,y+oy
    # Four finite native border objects, not infinite outside half-planes.
    if (overlaps(qx,qy,l,t,r,t+5.) or overlaps(qx,qy,l,t,l+5.,b)
            or overlaps(qx,qy,l,b-5.,r,b) or overlaps(qx,qy,r-5.,t,r,b)):
        return True
    # Three rotated platform contact variants are disabled in the source.
    if direction == 1:
        for p in platforms:
            active=p[7] if old and len(p)>7 else p[6]
            platform_dy=p[8] if old and len(p)>8 else p[5]
            if (active and overlaps(qx,qy,p[0],p[1],p[0]+p[2],p[1]+p[3])
                    and p[1] > y and dy >= platform_dy and y+8. <= p[1]+2.):
                return True
    return False


@njit(cache=True, inline='always')
def clamp_to_arena(x,y,env,j):
    if overlaps(x,y,env[j],env[j+1],env[j+2],env[j+3]):
        if env[j]+5.>x-8.: x=env[j]+5.+8.
        if env[j+1]+5.>y-8.: y=env[j+1]+5.+8.
        if env[j+2]-5.<x+8.: x=env[j+2]-5.-8.
        if env[j+3]-5.<y+8.: y=env[j+3]-5.-8.
    return x,y


@njit(cache=True, inline='always')
def movement_phase(s, env, platforms):
    """CustomMovement before Timeline, shared with player-target observation."""
    x,y,dx,dy = s[0],s[1],s[2],s[3]
    slammed,direction,slam_damage = s[5],s[7],s[9]
    dt=env[7]
    damage=0.
    # CustomMovement captures BOTH displacements before either step trigger.
    mx,my=dx*dt,dy*dt
    if mx != 0.:
        start=x
        count=max(1,int(math.floor(math.sqrt(mx*mx)+.5)))
        for i in range(1,count+1):
            candidate=start+mx*(i/count)
            if heart_solid(candidate,y,dy,direction,env,platforms,old=True):
                if slammed:
                    slammed=0.
                    if abs(dx)>=330. and slam_damage: damage=1.
                if dx != 0.:
                    dx=0.
                    x=start+mx*((i-1)/count)
                    break
            x=candidate
    if my != 0.:
        start=y
        count=max(1,int(math.floor(math.sqrt(my*my)+.5)))
        for i in range(1,count+1):
            candidate=start+my*(i/count)
            if heart_solid(x,candidate,dy,direction,env,platforms,old=True):
                if slammed:
                    slammed=0.
                    if abs(dy)>=330. and slam_damage: damage=1.
                if dy != 0.:
                    dy=0.
                    y=start+my*((i-1)/count)
                    break
            y=candidate
    return x,y,dx,dy,slammed,damage


@njit(cache=True)
def sample_position(s, env, platforms):
    """Position read by GetHeartPos after physics and before timeline resets."""
    moved=movement_phase(s,env,platforms)
    return moved[0],moved[1]


@njit(cache=True, inline='always')
def step_mask_into(s, mask, env, platforms, out):
    """One logical tick, with all physical arrow/Cancel key states explicit.

The caller checks hazards after this operator and rejects out[10] != 0.
"""
    x,y,dx,dy,slammed,damage=movement_phase(s,env,platforms)
    previous=int(s[4])
    mode,direction,max_fall,slam_damage=s[6],s[7],s[8],s[9]
    dt=env[7]

    # The baked schedule supplies event-sheet state AFTER timeline dispatch.
    mode=env[4]
    direction=env[5]
    if len(env)>8: max_fall=env[8]
    if len(env)>12: slam_damage=env[12]
    if len(env)>=22 and (env[18]!=env[14] or env[19]!=env[15] or env[20]!=env[16] or env[21]!=env[17]):
        # In every original CSV, a same-tick teleport follows InstantResize.
        # The native instant resize performs this clamp before that teleport.
        x,y=clamp_to_arena(x,y,env,18)
    if len(env)>9 and env[9]:
        x,y=env[10],env[11]
    if env[6]:
        mode=1.
        gx,gy=direction_xy(direction)
        dx,dy=gx*max_fall,gy*max_fall
        slammed=1.

    speed=75. if mask&CANCEL else 150.
    ux=(1 if mask&RIGHT else 0)-(1 if mask&LEFT else 0)
    up=(1 if mask&UP else 0)-(1 if mask&DOWN else 0)
    if mode == 0.:
        dx,dy=ux*speed,-up*speed
    else:
        gx,gy=direction_xy(direction)
        jumpkey=LEFT if direction==0 else UP if direction==1 else RIGHT if direction==2 else DOWN
        if mask&jumpkey and not previous&jumpkey:
            if heart_solid(x,y,dy,direction,env,platforms,gx,gy):
                dx=dx-gx*180.
                dy=dy-gy*180.
        if previous&jumpkey and not mask&jumpkey:
            if direction==0. and dx < -30.: dx=-30.
            elif direction==1. and dy < -30.: dy=-30.
            elif direction==2. and dx > 30.: dx=30.
            elif direction==3. and dy > 30.: dy=30.
        down_speed=dx if direction==0. else dy if direction==1. else -dx if direction==2. else -dy
        gravity=0.
        if 15.<down_speed<240.: gravity=540.
        elif -30.<down_speed<=15.: gravity=180.
        elif -120.<down_speed<=-30.: gravity=450.
        elif down_speed<=-120.: gravity=180.
        if not heart_solid(x,y,dy,direction,env,platforms,gx*.2,gy*.2):
            dx=dx+gx*gravity*dt
            dy=dy+gy*gravity*dt
            if direction==0. and dx>max_fall: dx=max_fall
            elif direction==1. and dy>max_fall: dy=max_fall
            elif direction==2. and dx < -max_fall: dx=-max_fall
            elif direction==3. and dy < -max_fall: dy=-max_fall
        if direction==0. or direction==2.:
            dy=-up*speed
        else:
            dx=0.
            if direction==1.:
                for p in platforms:
                    if (p[6] and overlaps(x+gx*.5,y+gy*.5,p[0],p[1],p[0]+p[2],p[1]+p[3])
                            and dy>=p[5] and y+8.<=p[1]+2.):
                        dx,dy,y=p[4],p[5],p[1]-8.05
            dx=dx+ux*speed
    # The top-level CombatZone group runs AFTER PlayerMovement in Battle.xml.
    x,y=clamp_to_arena(x,y,env,0)
    out[0],out[1],out[2],out[3]=x,y,dx,dy
    out[4],out[5],out[6],out[7]=float(mask),slammed,mode,direction
    out[8],out[9],out[10]=max_fall,slam_damage,damage


@njit(cache=True, inline='always')
def step_into(s, ux, up, env, platforms, out):
    mask=(LEFT if ux<0 else RIGHT if ux>0 else 0)|(UP if up>0 else DOWN if up<0 else 0)
    step_mask_into(s,mask,env,platforms,out)


@njit(cache=True, inline='always')
def step_action_into(s, mask, unused, env, platforms, out):
    """Search adapter for up to 32 inputs, filtered by the outer mode contract."""
    step_mask_into(s,int(mask),env,platforms,out)


@njit(cache=True)
def step(s, ux, up, env, platforms):
    out=np.empty(STATE_WIDTH,np.float64)
    step_into(s,ux,up,env,platforms,out)
    return out
