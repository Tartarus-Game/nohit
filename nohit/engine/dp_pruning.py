"""Sound Bellman false certificates from a gravity-axis reachability relaxation.

In a static blue-heart arena without platforms/events, a heart strictly clear
of both tangential side walls remains clear: native CustomMovement rejects any
candidate touching the inclusive solid band, and its <=1.5px substeps cannot
skip that band. The late clamp does not move an interior accepted point.

Under that invariant, tangential inputs cannot change gravity-axis dynamics.
The relaxation keeps exact position, velocity and the appropriate jump latch,
uses the same four-microtick control clock, and checks only white rectangles
spanning the tangential interior. Any mode/arena/reset/platform change or finite
lookahead boundary is optimistic success. Initial side contact is NEVER folded.
Only an empty relaxed reachable set can reject a full state.
"""
import numpy as np
from numba import njit,types
from numba.typed import Dict
from .discrete_operator import step_action_into

KEY_TYPE=types.UniTuple(types.uint64,6)


@njit(cache=True)
def make_vertical_cache(white,env,platforms):
    prefix=np.zeros((2,len(env)+1),np.int32)
    for normal in range(2):
        tangent=1-normal
        for tick in range(len(env)):
            spanning=False
            for bone in white[tick]:
                if bone[tangent]-2.<=env[tick,tangent]+13. and bone[tangent+2]+2.>=env[tick,tangent+2]-13.:
                    spanning=True;break
            prefix[normal,tick+1]=prefix[normal,tick]+int(spanning)
    # -1 is a proved dead relaxed state; otherwise retain its first viable
    # input. This also supplies a soft timing witness without a second model.
    return Dict.empty(key_type=KEY_TYPE,value_type=types.int8),prefix


@njit(cache=True,inline='always')
def _unaffected(env,platforms,tick,arena,direction):
    e=env[tick]
    if e[4]!=1. or e[5]!=direction or e[6] or e[9] or e[13]:return False
    for axis in range(4):
        if e[axis]!=arena[axis]:return False
        if len(e)>=22 and (e[14+axis]!=arena[axis] or e[18+axis]!=arena[axis]):return False
    for p in platforms[tick]:
        if p[6]:return False
    return True


@njit(cache=True,inline='always')
def _spanning_hit(white,tick,position,arena,normal):
    tangent=1-normal
    for bone in white[tick]:
        if (bone[tangent]-2.<=arena[tangent]+13. and bone[tangent+2]+2.>=arena[tangent+2]-13.
                and position+2.>=bone[normal] and position-2.<=bone[normal+2]):
            return True
    return False


@njit(cache=True)
def _normal_policy(white,env,platforms,frame,state,arena,horizon,dead_cache,normal,direction,jump):
    tick=frame*4
    if tick>=horizon:return 0
    bits=state.view(np.uint64)
    key=(np.uint64(frame),bits[normal],bits[normal+2],np.uint64(int(state[4])&jump),np.uint64(horizon),np.uint64(direction))
    if key in dead_cache:return int(dead_cache[key])
    for mask in (0,jump):
        q=state.copy()
        safe=True
        for micro in range(1,5):
            t=tick+micro
            if t>=len(env) or t>=horizon:
                dead_cache[key]=np.int8(mask)
                return mask
            if not _unaffected(env,platforms,t,arena,direction):
                dead_cache[key]=np.int8(mask)
                return mask
            step_action_into(q,mask,0,env[t],platforms[t],q)
            if _spanning_hit(white,t,q[normal],arena,normal):
                safe=False
                break
        if safe and _normal_policy(white,env,platforms,frame+1,q,arena,horizon,dead_cache,normal,direction,jump)>=0:
            dead_cache[key]=np.int8(mask)
            return mask
    dead_cache[key]=np.int8(-1)
    return -1


@njit(cache=True)
def _axis_action(white,env,platforms,frame,state,dead_cache=None):
    """Return -2 unsupported, -1 relaxed dead, or the first viable input."""
    tick=frame*4
    if tick>=len(env)-1 or state[6]!=1. or state[5]:return -2
    direction=int(state[7])
    if direction<0 or direction>3:return -2
    for p in platforms[tick]:
        if p[6]:return -2
    arena=env[tick]
    normal=0 if direction==0 or direction==2 else 1
    tangent=1-normal
    # Use the same floating-point arithmetic as native touching checks, not
    # just ideal real-number inequalities for the derived center coordinates.
    if not (state[tangent]-8.>arena[tangent]+5. and state[tangent]+8.<arena[tangent+2]-5.):return -2
    if not (state[normal]-8.>=arena[normal]+5. and state[normal]+8.<=arena[normal+2]-5.):return -2
    jump=1 if direction==0 else 4 if direction==1 else 2 if direction==2 else 8
    horizon=min(len(env),tick+481)
    q=state.copy();q[tangent]=(arena[tangent]+arena[tangent+2])*.5;q[tangent+2]=0.;q[4]=int(q[4])&jump
    if dead_cache is None:
        local_cache=make_vertical_cache(white,env,platforms)
        if local_cache[1][normal,horizon]==local_cache[1][normal,tick+1]:return -2
        return _normal_policy(white,env,platforms,frame,q,arena,horizon,local_cache[0],normal,direction,jump)
    if dead_cache[1][normal,horizon]==dead_cache[1][normal,tick+1]:return -2
    return _normal_policy(white,env,platforms,frame,q,arena,horizon,dead_cache[0],normal,direction,jump)


@njit(cache=True)
def forced_vertical_collision(white,env,platforms,frame,state,dead_cache=None):
    """Compatibility name; supports each of the four gravity directions."""
    return _axis_action(white,env,platforms,frame,state,dead_cache)==-1


@njit(cache=True)
def preferred_axis_jump(white,env,platforms,frame,state,dead_cache=None):
    """Soft first viable relaxed input (wait first), or -1 for no witness.

    A witness is not proof of full-state reachability: tangential obstacles
    were relaxed away. It may rank controls but must never remove controls.
    """
    action=_axis_action(white,env,platforms,frame,state,dead_cache)
    return action if action>=0 else -1
