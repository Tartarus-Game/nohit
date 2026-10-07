"""Opt-in one-tick player/environment product graph, including real dialogue.

Environment termination is a source boundary, not a game victory certificate.
No production solver is switched to this interface by importing it.
"""
from dataclasses import dataclass
import numpy as np

from .dialogue_operator import split_control
from .discrete_operator import step_mask_into, sample_position
from .resumable_wave import preview_observation_frame, state_environment_key
from .environment_state_key import encode_typed
from .cspace import collision_query


@dataclass(frozen=True)
class JointState:
    player: tuple
    environment: object


@dataclass(frozen=True)
class JointEdge:
    status: str
    state: JointState | None
    reason: str | None = None


def _validate(node):
    player=np.asarray(node.player,dtype=np.float64)
    if player.shape!=(11,) or not np.all(np.isfinite(player)):
        raise ValueError('player must contain eleven finite values')
    if player[4]!=int(player[4]) or not 0<=player[4]<32:
        raise ValueError('invalid player keymask')
    env=node.environment
    if bool(int(player[4])&16)!=bool(env.input_code&16):
        raise ValueError('previous Cancel must agree with player keymask')
    if env.state.dialogue_coupled and env.state.phase=='committed':
        if env.state.dialogue_last_input!=split_control(env.input_code)[1:]:
            raise ValueError('previous dialogue input inconsistent with control')
    return player


def begin_joint(template,binding,player,*,previous_input_code):
    env=template.begin_controlled(binding,previous_input_code=previous_input_code)
    node=JointState(tuple(float(x) for x in player),env)
    _validate(node)
    return node


def joint_key(node):
    """Exact structural future key; no hash-only equality or coordinate rounding.

    Pending bootstrap states retain their full in-flight structural snapshot.
    Completed edges retain clock protocol, resource semantics, dialogue latch,
    player bits and complete source environment. No suspended edge is merged.
    """
    player=_validate(node);env=node.environment;s=env.state
    if s.phase=='committed' and 'last_dt' in s.data:
        world=state_environment_key(s)
    else:
        def structural(value):
            if type(value) is dict:return {k:structural(v) for k,v in value.items()}
            if type(value) is list:return [structural(v) for v in value]
            if type(value) is tuple:return tuple(structural(v) for v in value)
            if isinstance(value,np.ndarray):return ('ndarray',value.dtype.str,value.shape,value.tobytes())
            if type(value) in (str,bytes,float,int,bool) or value is None or isinstance(value,np.generic):return value
            fields=getattr(type(value),'__slots__',None)
            attributes=({k:getattr(value,k) for k in fields} if fields is not None else vars(value))
            return (type(value).__module__,type(value).__name__,structural(attributes))
        world=encode_typed(structural((s.data,s.vm.vars,s.vm.rng.state,s.vm.heart_pos,
            s.supplied_target,s.request,s.dialogue,s.dialogue_coupled,
            s.dialogue_last_input,s.dialogue_current_input,s.dialogue_blocked_callback)))
    return encode_typed((player.tobytes(),s.program.identity,s.program.dt_schedule,
        s.clock_timestamp,s.initial_dt,s.max_ticks,s.vm.termination_policy,
        env.status,env.input_code,s.phase,world))


def frame_collision(frame,player):
    # Empty grid deliberately uses exact rectangle/quad tests, without a
    # whole-wave rebake for an input-dependent single frame.
    payload=(np.empty((1,2,0,0),np.uint8),frame.polygons[None,:,:],0.,0.,1.)
    return bool(collision_query(frame.white[None,:,:],frame.blue[None,:,:],
        0,np.asarray(player,dtype=np.float64),0.,payload))


def step_joint(template,node,control,*,allow_cancel=False):
    player=_validate(node);mask,_,_=split_control(control)
    env=template.step_controlled(node.environment,control,allow_cancel=allow_cancel)
    while env.status=='need_target':
        context=preview_observation_frame(env.state)
        x,y=sample_position(player,context.env,context.platforms)
        env=template.supply_controlled_target(env,float(x),float(y))
    if env.status in ('unknown','need_input'):
        return JointEdge('unknown',None,env.reason or env.status)
    if env.frame is None:
        # Never report a successful physical tick without a committed frame.
        return JointEdge('unknown',None,'missing_committed_frame')
    following=np.empty(11,dtype=np.float64)
    step_mask_into(player,mask,env.frame.env,env.frame.platforms,following)
    if frame_collision(env.frame,following):return JointEdge('collision',None)
    child=JointState(tuple(float(x) for x in following),env)
    _validate(child)
    return JointEdge(env.status,child,env.reason)


def verify_joint_witness(template,start,controls,*,allow_cancel=False):
    """Replay every physical tick, rejecting collision/unknown immediately."""
    node=start
    for control in controls:
        edge=step_joint(template,node,control,allow_cancel=allow_cancel)
        if edge.state is None:return edge
        node=edge.state
    return JointEdge(node.environment.status,node,node.environment.reason)


def joint_reachable(template,start,*,controls=(0,32),max_ticks=100,max_states=10000,
                    allow_cancel=False):
    """Small exact layered DAG returning a safe source-terminal witness.

    All distinct states survive each layer; rewards never prune. Resource or
    unmodeled transitions produce unknown, not an infeasibility certificate.
    """
    if max_ticks<1 or max_states<1:raise ValueError('positive resource limits required')
    controls=tuple(controls)
    if not controls:raise ValueError('nonempty control domain required')
    frontier={joint_key(start):(start,())};unknown=False
    for _ in range(max_ticks):
        following={}
        for node,word in frontier.values():
            for control in controls:
                edge=step_joint(template,node,control,allow_cancel=allow_cancel)
                if edge.status=='unknown':unknown=True;continue
                if edge.state is None:continue
                witness=word+(control,)
                if edge.status=='terminal':return 'terminal',witness,edge.state
                following.setdefault(joint_key(edge.state),(edge.state,witness))
                if len(following)>max_states:return 'unknown',None,None
        if not following:return ('unknown' if unknown else 'exhausted'),None,None
        frontier=following
    return 'unknown',None,None
