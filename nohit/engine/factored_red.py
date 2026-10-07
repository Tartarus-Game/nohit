"""Exact fixed-red kinematic factorization with a coupled Boolean reachability set.

Experimental standalone operator, not a production solver switch. Coordinates
are float64 bit patterns; no rounded cells or representative exits are used.
"""
from dataclasses import dataclass
import numpy as np
from .discrete_operator import step_mask_into,heart_solid
from .cspace import bake_cspace,collision_query


def admissibility(wave,start_tick,stop_tick,initial):
    """Sufficient separability conditions, deliberately narrower than red mode."""
    s=np.asarray(initial,dtype=np.float64)
    if s.shape!=(11,) or not np.isfinite(s).all():return 'initial_state'
    if not 0<=start_tick<stop_tick<len(wave.env_schedule):return 'tick_range'
    if (stop_tick-start_tick)%4:return 'partial_control_hold'
    if s[5]!=0 or s[10]!=0:return 'pending_slam_or_damage'
    env=wave.env_schedule[start_tick+1:stop_tick+1]
    if env.shape[1]!=22:return 'environment_width'
    if not np.isfinite(env).all() or np.any(env[:,7]<=0):return 'invalid_environment'
    if np.any(env[:,4]!=0) or np.any(env[:,6]!=0):return 'not_fixed_red'
    if np.any(env[:,9]!=0):return 'teleport_not_yet_certified'
    bounds=env[0,:4]
    if not (np.all(env[:,:4]==bounds) and np.all(env[:,14:18]==bounds) and np.all(env[:,18:22]==bounds)):
        return 'moving_arena'
    if np.any(wave.platform_table[start_tick+1:stop_tick+1,:,6:8]):return 'platform_contact'
    if not (bounds[0]+13<s[0]<bounds[2]-13 and bounds[1]+13<s[1]<bounds[3]-13):
        return 'not_strict_interior'
    if heart_solid(s[0],s[1],s[3],s[7],env[0],np.empty((0,9))):return 'rounded_border_contact'
    if wave.pending_target is not None and wave.pending_target['tick']<=stop_tick:return 'unresolved_target'
    if any(start_tick<t<=stop_tick and cmd=='getheartpos' for t,cmd,_ in wave.source_events):
        return 'target_observation_boundary'
    return None


@dataclass
class ProductLayer:
    tick: int
    x: np.ndarray  # Nx2: exact x, previous dx
    y: np.ndarray  # Ny2: exact y, previous dy
    reachable: int  # bit (ix*Ny+iy); compressed Boolean matrix
    parents: dict  # one witness per retained joint state; edges remain implicit

    @property
    def count(self):return self.reachable.bit_count()


@dataclass
class FactoredResult:
    layers: list
    exits: dict  # (joint-index, actual final mask) -> preceding joint-index
    initial: np.ndarray
    final_environment: np.ndarray
    stats: dict

    def exit_states(self):
        last=self.layers[-1];ny=len(last.y)
        for node,mask in self.exits:
            ix,iy=divmod(node,ny)
            s=self.initial.copy()
            s[0],s[2]=last.x[ix];s[1],s[3]=last.y[iy]
            s[4]=mask;s[6]=self.final_environment[4];s[7]=self.final_environment[5]
            s[8]=self.final_environment[8];s[9]=self.final_environment[12];s[10]=0.
            yield s

    def witness(self,node,mask):
        previous=self.exits[(node,mask)];word=[mask]
        for layer in reversed(self.layers[1:-1]):
            previous,control=layer.parents[previous];word.append(control)
        return list(reversed(word))


def _indices(bits):
    while bits:
        low=bits&-bits;yield low.bit_length()-1;bits^=low


def solve_fixed_red(wave,start_tick,stop_tick,initial,*,controls=tuple(range(16)),cspace=None,max_joint_cells=5_000_000):
    """Retain every safe joint exit and final input latch in a declared slice.

    Resource overflow raises a distinct exception and is not a false verdict.
    A segment with no exits is exhausted only within this declared fixed slice.
    """
    issue=admissibility(wave,start_tick,stop_tick,initial)
    if issue:raise ValueError('factorization_not_certified: '+issue)
    if not controls or any(type(m) is not int or not 0<=m<32 for m in controls):raise ValueError('invalid controls')
    controls=tuple(dict.fromkeys(controls))
    s0=np.asarray(initial,dtype=np.float64).copy();space=bake_cspace(wave) if cspace is None else cspace
    layers=[ProductLayer(start_tick,s0[[0,2]].reshape(1,2),s0[[1,3]].reshape(1,2),1,{})]
    stats={'axis_micro_transitions':0,'joint_action_edges':0,'collision_queries':0}
    if collision_query(wave.geometry_white,wave.geometry_blue,start_tick,s0,0.,space.payload):
        layers[0].reachable=0
        return FactoredResult(layers,{},s0,wave.env_schedule[start_tick],stats)
    exits={};empty=np.empty((0,9),dtype=float)
    for tick in range(start_tick,stop_tick,4):
        previous=layers[-1];axis_values=[];maps=[];trajectories=[]
        for axis,values in enumerate((previous.x,previous.y)):
            intern={};following=[];mapping=np.empty((len(controls),len(values)),np.int64)
            trace=np.empty((len(controls),len(values),4,2))
            for a,mask in enumerate(controls):
                for i,pair in enumerate(values):
                    s=s0.copy();s[axis],s[axis+2]=pair
                    for micro in range(4):
                        out=np.empty(11)
                        step_mask_into(s,mask,wave.env_schedule[tick+micro+1],empty,out)
                        s=out;trace[a,i,micro]=s[[axis,axis+2]];stats['axis_micro_transitions']+=1
                        bounds=wave.env_schedule[tick+micro+1,:4]
                        if (not (bounds[0]+13<s[0]<bounds[2]-13 and bounds[1]+13<s[1]<bounds[3]-13)
                            or heart_solid(s[0],s[1],s[3],s[7],wave.env_schedule[tick+micro+1],empty)):
                            # Border contacts are closed. A y touching the top
                            # can block x too, so no factorization is claimed
                            # once any reachable axis touches either border.
                            raise ValueError('factorization_not_certified: reachable_boundary_coupling')
                    pair=s[[axis,axis+2]];key=pair.tobytes()
                    if key not in intern:intern[key]=len(following);following.append(pair)
                    mapping[a,i]=intern[key]
            axis_values.append(np.asarray(following));maps.append(mapping);trajectories.append(trace)
        nx,ny=map(len,axis_values)
        if nx*ny>max_joint_cells:raise RuntimeError('resource_limit: joint product cell budget')
        reachable=0;parents={};exits={}
        for node in _indices(previous.reachable):
            ix,iy=divmod(node,len(previous.y))
            for a,mask in enumerate(controls):
                stats['joint_action_edges']+=1;safe=True
                for micro in range(4):
                    s=s0.copy()
                    s[0],s[2]=trajectories[0][a,ix,micro]
                    s[1],s[3]=trajectories[1][a,iy,micro]
                    # Safety uses position, post-input velocity and damage.
                    s[4]=mask;s[10]=0.;stats['collision_queries']+=1
                    if collision_query(wave.geometry_white,wave.geometry_blue,tick+micro+1,s,0.,space.payload):
                        safe=False;break
                if not safe:continue
                target=int(maps[0][a,ix])*ny+int(maps[1][a,iy])
                reachable|=1<<target
                parents.setdefault(target,(node,mask))
                exits.setdefault((target,mask),node)
        layers.append(ProductLayer(tick+4,axis_values[0],axis_values[1],reachable,parents))
        if not reachable:break
    return FactoredResult(layers,exits,s0,wave.env_schedule[layers[-1].tick],stats)
