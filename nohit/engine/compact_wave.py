"""Compile fixed timeline environments from the original jcw event equations.

Rotated hazards retain their convex geometry. GetHeartPos requires an explicit
player history; it cannot be replaced by the initial spawn position. Continuous
C-space baking lives in cspace.py; legacy sampled masks below are slice tools.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import struct
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
from numba import njit

from .compact_types import CompiledWave, GeometryArray
from .native_numbers import (native_int, native_local_number,
    native_parameter_in_range, native_for_count_indices)
from .timeline_csv import read_timeline_rows
from .native_function_dispatch import call_arguments, audited_no_action_function, NO_ACTION_FUNCTION_AUDIT


ROOT = Path(__file__).resolve().parents[2]
CSV_HASH = "2c23db06eccc8f7eda2341abafb4ebfe9162f3e7ed5bfe026f73f4ea19a42cd2"

CANONICAL_ATTACK_NAMES = {
    "sans_bluebone",
    "sans_bonegap1",
    "sans_bonegap1fast",
    "sans_bonegap2",
    "sans_boneslideh",
    "sans_boneslidev",
    "sans_bonestab1",
    "sans_bonestab2",
    "sans_bonestab3",
    "sans_final",
    "sans_intro",
    "sans_multi1",
    "sans_multi2",
    "sans_multi3",
    "sans_platformblaster",
    "sans_platformblasterfast",
    "sans_platforms1",
    "sans_platforms2",
    "sans_platforms3",
    "sans_platforms4",
    "sans_platforms4hard",
    "sans_randomblaster1",
    "sans_randomblaster2",
    "sans_realhell_extreme",
    "sans_spare",
}


class XorShift32:
    """32-bit xorshift RNG matching Construct 2 / attack_seed.js bit-for-bit."""
    def __init__(self, seed: int = 42):
        self.state = (int(seed) & 0xFFFFFFFF) or 0x6D2B79F5

    def random(self) -> float:
        x = self.state
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= (x >> 17) & 0xFFFFFFFF
        x ^= (x << 5) & 0xFFFFFFFF
        self.state = x & 0xFFFFFFFF
        return self.state / 4294967296.0


class _ActiveBone:
    __slots__ = ("x", "y", "w", "h", "vx", "vy", "color", "direction")
    def __init__(self, x: float, y: float, w: float, h: float, vx: float, vy: float, color: int, direction: int | None = None):
        self.x = float(x)
        self.y = float(y)
        self.w = float(w)
        self.h = float(h)
        self.vx = float(vx)
        self.vy = float(vy)
        self.color = float(color)
        self.direction=int(round(math.atan2(vy,vx)*2./math.pi))%4 if direction is None else float(direction)

    def step(self, dt: float) -> None:
        next_x = self.x + self.vx * dt
        next_y = self.y + self.vy * dt
        if self.x != next_x: self.x = next_x
        if self.y != next_y: self.y = next_y


class _ActivePlatform:
    __slots__ = ("x", "y", "w", "h", "vx", "vy", "reverse", "born", "direction", "pre_active", "pre_dy")
    def __init__(self, x: float, y: float, w: float, vx: float, vy: float, reverse: int):
        self.x = float(x)
        self.y = float(y)
        self.w = float(w)
        self.h = 7.0
        self.vx = float(vx)
        self.vy = float(vy)
        self.reverse = int(reverse)
        self.born=True
        self.pre_active=0.
        self.pre_dy=float(vy)
        self.direction=int(round(math.atan2(vy,vx)*2./math.pi))%4

    def step(self, dt: float, cz_left: float, cz_right: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.reverse:
            if self.vx > 0.0 and self.x + self.w >= cz_right:
                self.vx = -abs(self.vx)
            elif self.vx < 0.0 and self.x <= cz_left:
                self.vx = abs(self.vx)


def _bone_from_command(horizontal, args):
    """Battle BoneH/BoneV: six typed System.int calls after load_line."""
    # Timeline supplies nine At() results; missing columns are numeric zero.
    args = tuple(args) + (0.,) * max(0, 6-len(args))
    x, y, extent, direction, speed = (native_int(value) for value in args[:5])
    color = native_int(args[5]) if len(args) > 5 else 0.
    angle = direction * (math.pi / 2.0)
    vx, vy = math.cos(angle) * speed, math.sin(angle) * speed
    # Native creates at +0,+0, then separate SetX/SetY skip equal values.
    x = 0. if x == 0. else x
    y = 0. if y == 0. else y
    return _ActiveBone(x, y, extent if horizontal else 10.,
        10. if horizontal else extent, vx, vy, color, direction)


def _platform_from_command(args):
    """Battle Platform: raw typed fields, and Reverse is int(P5) > 0."""
    args = tuple(args) + (0.,) * max(0, 6-len(args))
    x, y, width, direction, speed = (native_int(value) for value in args[:5])
    reverse = native_int(args[5]) > 0. if len(args) > 5 else False
    angle = direction * (math.pi / 2.0)
    vx, vy = math.cos(angle) * speed, math.sin(angle) * speed
    platform = _ActivePlatform(0. if x == 0. else x, 0. if y == 0. else y,
        width, vx, vy, reverse)
    # Direction is an instance variable, independent of signed/zero speed.
    platform.direction = direction
    return platform


def _repeat_command_children(args):
    """Repeat number locals precede the child's single-object admission."""
    x, y, extent, direction, speed = (native_local_number(value) for value in args[:5])
    count = native_int(args[5])
    spacing = native_int(args[6])
    angle = direction * (math.pi / 2.0)
    for index in native_for_count_indices(count):
        child_x = x - math.cos(angle) * spacing * index
        child_y = y - math.sin(angle) * spacing * index
        # Omitted sixth parameter defaults to zero in the single function.
        yield (child_x, child_y, extent, direction, speed)


def normalize_initial_arena(arena):
    """Copy native pre-Timeline arena state, separate from the env row ABI."""
    if arena is None:return None
    if not isinstance(arena,Mapping):raise ValueError('initial_arena must be an object')
    try:
        target=tuple(float(x) for x in arena['target'])
        size=tuple(float(x) for x in arena['size'])
        speed=float(arena['speed'])
        callback=arena['callback']
    except (KeyError,TypeError,ValueError,OverflowError) as exc:
        raise ValueError('initial_arena requires target, size, speed and callback') from exc
    if len(target)!=4 or len(size)!=2 or not all(math.isfinite(x) for x in (*target,*size,speed)):
        raise ValueError('initial_arena requires 4 finite target bounds, 2 finite sizes and finite speed')
    if not isinstance(callback,str):raise ValueError('initial_arena callback must be a string')
    if callback!='' and callback.lower()!='tlresume' and not audited_no_action_function(callback):
        raise ValueError('unsupported_initial_arena_callback:'+callback)
    return dict(target=target,size=size,speed=speed,callback=callback)


def initial_arena_identity(arena):
    """Exact native scalar bytes; omission preserves the old template key."""
    if arena is None:return b''
    callback=arena['callback'].encode('utf-8')
    return (b'NOHIT-INITIAL-ARENA\x01'+struct.pack('<7dQ',*arena['target'],*arena['size'],
            arena['speed'],len(callback))+callback)


def _initial_arena_state(bounds,arena):
    if arena is None:return [bounds[2]-bounds[0],bounds[3]-bounds[1]],list(bounds),480.,None
    callback=({'source_line':None,'tick':-1,'function':arena['callback']}
              if arena['callback'] else None)
    return list(arena['size']),list(arena['target']),arena['speed'],callback


def _resize_combat_zone(bounds, size, target, speed, dt):
    """Battle CombatZoneTick in original x/y/width/height assignment order."""
    x,y=bounds[0],bounds[1]
    width,height=size
    x1=min(speed*dt,abs(x-target[0]))
    y1=min(speed*dt,abs(y-target[1]))
    x2=min(speed*dt,abs(x+width-target[2]))
    y2=min(speed*dt,abs(y+height-target[3]))
    if x>target[0]:x-=x1;width+=x1
    elif x<target[0]:x+=x1;width-=x1
    if y>target[1]:y-=y1;height+=y1
    elif y<target[1]:y+=y1;height-=y1
    if x+width>target[2]:width-=x2
    elif x+width<target[2]:width+=x2
    if y+height>target[3]:height-=y2
    elif y+height<target[3]:height+=y2
    bounds[:]=[x,y,x+width,y+height]
    size[:]=[width,height]


class _ActiveBoneStab:
    """Battle.xml BoneStab event order; warning and body are separate phases."""
    def __init__(self, direction, height, warn_time, stab_time):
        self.direction=native_int(direction)
        self.height=native_int(height)
        self.warn_time=float(warn_time)
        self.stay=float(stab_time)
        self.spawned=False
        self.reverse=False
        self.x=self.y=self.w=self.h=self.dest_x=self.dest_y=0.

    def step(self, dt, cz, cz_size=None):
        if not self.spawned and self.warn_time==0.:
            self.spawned=True
            if self.direction in (1,3):
                self.x=cz[0]; self.w=cz[2]-cz[0] if cz_size is None else cz_size[0]; self.h=self.height+8.
                self.y=cz[3]-5. if self.direction==1 else cz[1]+5.-self.h
            else:
                self.y=cz[1]; self.h=cz[3]-cz[1] if cz_size is None else cz_size[1]; self.w=self.height+8.
                self.x=cz[2]-5. if self.direction==0 else cz[0]+5.-self.w
            ang=self.direction*math.pi/2.
            self.dest_x=self.x-math.cos(ang)*self.height
            self.dest_y=self.y-math.sin(ang)*self.height
            # Source uses explicit axis expressions, avoiding trig drift in destinations.
            if self.direction in (1,3): self.dest_x=self.x
            else: self.dest_y=self.y
        if not self.spawned:
            self.warn_time-=min(dt,self.warn_time)
            return True
        # Runtime G converts degrees by division; Speed is evaluated before
        # cos/sin * dt * Speed. Keep those binary64 operations source-ordered.
        degrees_per_radian=180./math.pi
        ang=(self.direction*90.)/degrees_per_radian
        speed=self.height*10.
        dx=math.cos(ang)*dt*speed;dy=math.sin(ang)*dt*speed
        x=self.x+dx if self.reverse else self.x-dx
        y=self.y+dy if self.reverse else self.y-dy
        if self.x!=x:self.x=x
        if self.y!=y:self.y=y
        if not self.reverse:
            # Battle.xml IsWithinAngle(Direction*90, .5, angle(...)) uses
            # Ka(atan2) then G, and runtime Ra's clamped acos. A dot half-plane
            # snaps a tick early when the axis arrives with orthogonal drift.
            bearing=degrees_per_radian*math.atan2(self.dest_y-self.y,self.dest_x-self.x)
            target_angle=bearing/degrees_per_radian
            if ang==target_angle:angle_difference=0.
            else:
                cosine=math.sin(ang)*math.sin(target_angle)+math.cos(ang)*math.cos(target_angle)
                angle_difference=0. if cosine>=1. else math.pi if cosine<=-1. else math.acos(cosine)
            if angle_difference<=.5/degrees_per_radian:
                if self.x!=self.dest_x:self.x=self.dest_x
                if self.y!=self.dest_y:self.y=self.dest_y
            if self.x==self.dest_x and self.y==self.dest_y:
                self.stay-=min(dt,self.stay)
                if self.stay==0.: self.reverse=True
        return not (self.x+self.w<0 or self.x>640 or self.y+self.h<0 or self.y>480)

    def bbox(self):
        return (self.x,self.y,self.x+self.w,self.y+self.h) if self.spawned else None


def _blaster_fire_bbox(x,y,ux,uy,scale_x,scale_y):
    """Bounds of the original Fire sprite, including its off-centre hotspot.

    data.js type SID 7974524067202295: all five Fire frames are 57x44,
    hotspot (0.5087719559669495, 0.5). Default has a different hotspot,
    but the outside-layout stop condition only runs during Fire/leave.
    """
    width=57.*scale_x;height=44.*scale_y
    offset=(.5-0.5087719559669495)*width
    cx=x+ux*offset;cy=y+uy*offset
    rx=(abs(ux)*width+abs(uy)*height)*.5
    ry=(abs(uy)*width+abs(ux)*height)*.5
    return cx-rx,cy-ry,cx+rx,cy+ry


class _ActiveGasterBlaster:
    """Source-ordered ENTER/WAIT/FIRE/LEAVE and beam growth, never an AABB beam."""
    def __init__(self,size,start_x,start_y,end_x,end_y,end_ang,timer,blast_time):
        self.size=native_int(size)
        self.x=0.; self.y=0.
        self._set_position(native_int(start_x),native_int(start_y))
        self.end_x=native_int(end_x); self.end_y=native_int(end_y)
        self.end_ang=native_int(end_ang)
        self.angle=self.end_ang if self.x==self.end_x and self.y==self.end_y else 90.
        self.timer=float(timer); self.blast_time=float(blast_time)
        self.state=0; self.leave_speed=0.; self.beam_timer=0.; self.base_size=0.
        self.damage=False; self.opacity=100.
        self.scale_y=2. if self.size==1 else 3. if self.size==2 else 1.
        self.scale_x=3. if self.size==2 else 2.

    def _set_position(self,x,y):
        # Native SetX/SetY skip an assignment if old === new. Unlike the
        # EndX/EndY variables, an existing +0 is not replaced by a supplied -0.
        if self.x!=x:self.x=x
        if self.y!=y:self.y=y

    def step(self,dt):
        if self.timer>0. and self.state in (1,2):
            self.timer-=min(dt,self.timer)
        if self.state==0:
            for key,target in (('x',self.end_x),('y',self.end_y),('angle',self.end_ang)):
                v=getattr(self,key)
                if abs(v-target)>=3.: v+=(target-v)*dt*10.
                if abs(v-target)<3.: v=target
                if key=='angle' or getattr(self,key)!=v:setattr(self,key,v)
            if self.x==self.end_x and self.y==self.end_y and self.angle==self.end_ang:
                self.state=1
        if self.state==1 and self.timer==0.:
            self.state=2; self.timer=.1
        if self.state==2 and self.timer==0.:
            self.state=3; self.damage=True
        if self.state==3:
            self.leave_speed+=30.
            a=math.radians(self.angle); ux=math.cos(a); uy=math.sin(a)
            left,top,right,bottom=_blaster_fire_bbox(self.x,self.y,ux,uy,self.scale_x,self.scale_y)
            if right<0. or left>640. or bottom<0. or top>480.:
                self.leave_speed=0.
            self._set_position(self.x-ux*dt*self.leave_speed,self.y-uy*dt*self.leave_speed)
            self.beam_timer+=dt
            if self.beam_timer<4./30.:
                self.base_size+=math.floor(35.*self.scale_y/4.)*dt*30.
            if 4./30.<=self.beam_timer<4./30.+dt:
                self.base_size=35.*self.scale_y
            if self.beam_timer>5./30.+self.blast_time:
                self.base_size*=.8**(dt*30.)
                self.opacity=100.-((self.beam_timer-self.blast_time)*30.-5.)*10.
                if self.base_size<=2.: return False
            # Construct 2 SetOpacity normalizes/clamps; CompareOpacity rounds to 6 decimals.
            normalized_opacity=min(1.,max(0.,self.opacity/100.))
            compared_opacity=math.floor(1e6*(100.*normalized_opacity)+.5)/1e6
            if compared_opacity<=80.: self.damage=False
        return True

    def polygon(self):
        if not self.damage: return None
        a=math.radians(self.angle); ux,uy=math.cos(a),math.sin(a)
        ax=self.x+ux*70.*self.scale_y/2.
        ay=self.y+uy*70.*self.scale_y/2.
        hw=self.base_size*3./8.
        return (ax-uy*hw,ay+ux*hw,ax+uy*hw,ay-ux*hw,
                ax+1000.*ux+uy*hw,ay+1000.*uy-ux*hw,
                ax+1000.*ux-uy*hw,ay+1000.*uy+ux*hw)


@njit(cache=True)
def _build_geometry_fast_njit(
    flat_w: np.ndarray,
    counts_w: np.ndarray,
    flat_b: np.ndarray,
    counts_b: np.ndarray,
    N_ticks: int,
    max_w: int,
    max_b: int,
    max_all: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    geom_white = np.full((N_ticks, max_w, 4), np.nan, dtype=np.float64)
    geom_blue = np.full((N_ticks, max_b, 4), np.nan, dtype=np.float64)
    geom_all = np.full((N_ticks, max_all, 4), np.nan, dtype=np.float64)
    iw = 0
    ib = 0
    for t in range(N_ticks):
        cw = counts_w[t]
        cb = counts_b[t]
        for i in range(cw):
            for k in range(4):
                val = flat_w[iw, k]
                geom_white[t, i, k] = val
                geom_all[t, i, k] = val
            iw += 1
        for j in range(cb):
            for k in range(4):
                val = flat_b[ib, k]
                geom_blue[t, j, k] = val
                geom_all[t, cw + j, k] = val
            ib += 1
    return geom_white, geom_blue, geom_all


# Warm up JIT so first compile_wave incurs zero compilation overhead
_build_geometry_fast_njit(
    np.empty((0, 4), dtype=np.float64),
    np.zeros(1, dtype=np.int32),
    np.empty((0, 4), dtype=np.float64),
    np.zeros(1, dtype=np.int32),
    1, 0, 0, 0
)


class TimelineVM:
    """Virtual Machine decoding and executing Construct 2 timeline bytecode."""

    def __init__(self, seed: int = 42, initial_environment=None, heart_samples=None, allow_partial=False, dt_schedule=None, termination_policy='endattack', max_ticks=40000,capture_state_keys=False,initial_arena=None):
        if not isinstance(capture_state_keys,bool):raise ValueError('capture_state_keys must be boolean')
        self.capture_state_keys=capture_state_keys
        if termination_policy not in ('endattack','eof_hazards_drained'):
            raise ValueError('invalid termination_policy')
        if isinstance(max_ticks,bool) or not isinstance(max_ticks,int) or max_ticks<1:
            raise ValueError('max_ticks must be a positive integer resource budget')
        if dt_schedule is not None:
            if not len(dt_schedule):raise ValueError('dt_schedule must not be empty')
            # A finite observed clock is another resource limit, never a
            # license to repeat its last dt for unobserved future ticks.
            max_ticks=min(max_ticks,len(dt_schedule))
        self.termination_policy=termination_policy
        self.max_ticks=max_ticks
        self.initial_environment=initial_environment
        self.initial_arena=normalize_initial_arena(initial_arena)
        self.heart_samples=heart_samples
        self.allow_partial=allow_partial
        self.dt_schedule=dt_schedule
        self.rng = XorShift32(seed)
        self.vars: dict[str, Any] = {"pi": math.pi}
        self.heart_pos = [320.0, 304.0]

    def eval_arg(self, token: Any) -> Any:
        """Convert an already loaded value; never resolve variable references."""
        if isinstance(token, (int, float)):
            return token
        s = str(token).strip()
        if not s:
            return 0.0
        try:
            return float(s) if "." in s else int(s)
        except ValueError:
            return s

    @staticmethod
    def variable_key(value):
        """Dictionary property-key coercion for loaded numeric/string names."""
        if isinstance(value,(int,float)):
            value=float(value)
            if value==0.:return '0'
            if math.isnan(value):return 'NaN'
            if math.isinf(value):return 'Infinity' if value>0 else '-Infinity'
            if 1e-6<=abs(value)<1e21:
                return np.format_float_positional(value,unique=True,trim='-')
            return np.format_float_scientific(value,unique=True,trim='-',exp_digits=1)
        return str(value)

    def load_line(self, parsed_row):
        """TLLoadLine substitutes all $ tokens once, including destination keys.

        The immutable result survives the line's delay. Values returned from
        the dictionary are not recursively substituted or interpreted as names.
        """
        d_tok,_,cmd,_,args=parsed_row
        def resolve(token):
            return self.vars.get(token[1:],0.) if token.startswith('$') else token
        loaded_cmd=self.variable_key(resolve(cmd))
        return (float(self.eval_arg(resolve(d_tok))),loaded_cmd.lower(),tuple(resolve(a) for a in args))

    def run(self, rows: list[list[str]], dt_nominal: float = 1.0 / 240.0) -> dict[str, Any]:
        # Pre-scan labels and initial environment state
        labels: dict[str, int] = {}
        has_end_attack = False
        initial_cz = [133.0, 251.0, 508.0, 391.0]
        initial_heart_mode = 1.0
        initial_heart_pos = [320.0, 376.0]
        cz_initialized = False
        heart_pos_initialized = False
        heart_mode_initialized = False

        for i, row in enumerate(rows):
            if len(row) > 1:
                cmd_raw = row[1].strip()
                if cmd_raw.startswith(":"):
                    labels[cmd_raw.lstrip(":").strip()] = i
                cmd_lower = cmd_raw.lower()
                if cmd_lower == "endattack":
                    has_end_attack = True
                elif cmd_lower in ("combatzoneresize", "combatzoneresizeinstant") and not cz_initialized:
                    try:
                        if len(row) >= 6 and row[2].strip() and row[3].strip() and row[4].strip() and row[5].strip():
                            initial_cz = [float(row[2]), float(row[3]), float(row[4]), float(row[5])]
                            cz_initialized = True
                    except ValueError:
                        pass
                elif cmd_lower == "heartteleport" and not heart_pos_initialized:
                    try:
                        if len(row) >= 4 and row[2].strip() and row[3].strip():
                            initial_heart_pos = [float(row[2]), float(row[3])]
                            heart_pos_initialized = True
                    except ValueError:
                        pass
                elif cmd_lower == "heartmode" and not heart_mode_initialized:
                    try:
                        if len(row) >= 3 and row[2].strip():
                            initial_heart_mode = float(row[2])
                            heart_mode_initialized = True
                    except ValueError:
                        pass

        if not has_end_attack and self.termination_policy=='endattack':
            raise ValueError("unsupported_mechanism: CSV reached EOF without EndAttack or contains unaudited mechanism")

        if self.initial_environment is not None:
            initial_cz=list(self.initial_environment[:4])
            initial_heart_mode=float(self.initial_environment[4])
        self.heart_pos = list(initial_heart_pos)

        # Simulation states
        cz = list(initial_cz)
        cz_size,tgt_cz,cz_speed,end_resize=_initial_arena_state(cz,self.initial_arena)
        heart_mode = initial_heart_mode
        gravity_dir = 1.0  # Down
        max_fall_speed=750.
        slam_damage=0.
        if self.initial_environment is not None:
            if len(self.initial_environment)>5: gravity_dir=float(self.initial_environment[5])
            if len(self.initial_environment)>8: max_fall_speed=float(self.initial_environment[8])
            if len(self.initial_environment)>12: slam_damage=float(self.initial_environment[12])
        source_events=[]
        player_dependent=False
        pending_target=None
        target_history=[]
        # env22 has no EndResize payload. An explicit native arena snapshot
        # supplies it; omission retains the prior assumed-none contract.
        unproven_callbacks=[]
        callback_events=[]

        active_bones: list[_ActiveBone] = []
        active_platforms: list[_ActivePlatform] = []
        active_stabs: list[_ActiveBoneStab] = []
        active_blasters: list[_ActiveGasterBlaster] = []
        environment_state_keys=[]
        if self.capture_state_keys:
            from .environment_state_key import encode_environment_state
            def entity_state(entity):
                fields=getattr(type(entity),'__slots__',None)
                # Slot declaration order and entity-list order are retained.
                return (type(entity).__name__,tuple((name,getattr(entity,name)) for name in fields)) if fields is not None else (type(entity).__name__,dict(vars(entity)))

        max_ticks = self.max_ticks
        capacity = 16384
        env_schedule = np.empty((capacity, 22), dtype=np.float64)
        platform_table = np.zeros((capacity, 4, 7), dtype=np.float64)
        num_platforms = np.zeros(capacity, dtype=np.int32)

        flat_white_list: list[float] = []
        flat_blue_list: list[float] = []
        counts_white: list[int] = []
        counts_blue: list[int] = []
        polygon_frames=[]
        platform_frames=[]
        max_w = 0
        max_b = 0
        max_all = 0

        # Pre-parse rows for fast evaluation
        parsed_rows: list[tuple[str, float | None, str, str, list[str]] | None] = []
        for r in rows:
            if not r or not any(c.strip() for c in r):
                parsed_rows.append(None)
                continue
            d_tok = r[0].strip() if len(r) > 0 else ""
            c_tok = r[1].strip() if len(r) > 1 else ""
            a_toks = [a.strip() for a in r[2:]]
            try:
                sd = float(d_tok) if d_tok else 0.0
            except ValueError:
                sd = None
            parsed_rows.append((d_tok, sd, c_tok, c_tok.lower(), a_toks))

        pc = 0
        time_acc = 0.0
        running = True
        ended = False
        termination_reason=None
        eof_tick=None
        pending_dialogue=None
        loaded_line=None
        def finish_resize(phase):
            nonlocal end_resize,running
            if end_resize is None or cz!=tgt_cz:return
            # Function.CallFunction lowercases names (native runtime:374).
            if end_resize['function'].lower()=='tlresume':
                # Timeline.xml TLResume is exactly Running=1. A custom script
                # which is already running therefore has no timer side effect.
                running=True
                callback_events.append(dict(end_resize,executed_tick=tick,phase=phase))
                end_resize=None
            elif audited_no_action_function(end_resize['function']):
                callback_events.append(dict(end_resize,executed_tick=tick,phase=phase,
                    no_action_audit=NO_ACTION_FUNCTION_AUDIT))
                end_resize=None
            # Unknown callbacks retain an unproven-effect record forever;
            # reaching their trigger is not equivalent to executing them.
        tick = 0
        initial_heart_pos_captured: list[float] | None = None

        while not ended and tick < max_ticks and pending_target is None and pending_dialogue is None:
            if self.dt_schedule is not None:
                dt_nominal=float(self.dt_schedule[tick])
            previous_cz=list(cz)
            teleport_pulse=mode_pulse=0.
            run_count = 0
            removed_platforms=[]

            # Execute bytecode instructions scheduled up to current time
            while running and pc < len(parsed_rows) and run_count < 1000:
                if pc < 0:
                    raise ValueError('model_mismatch: negative timeline instruction index')
                p_row = parsed_rows[pc]
                if p_row is None:
                    pc += 1
                    loaded_line=None
                    continue
                if loaded_line is None:
                    loaded_line=self.load_line(p_row)
                delay,cmd_l,loaded_args=loaded_line
                if time_acc < delay:
                    break
                args=call_arguments(loaded_args)
                # A taken self-jump must reload too. In native execution the
                # next TLLoadLine occurs after the command and Line increment.
                loaded_line=None
                time_acc -= delay
                run_count += 1
                source_events.append((tick,cmd_l,args))

                if cmd_l == 'sanstext':
                    # Native SansText pauses Timeline but not world physics.
                    # A later EndAttack cannot bypass its input-driven pause.
                    # The uncoupled compiler must expose this boundary.
                    pending_dialogue={'tick':tick,'line':pc+1,'text':self.variable_key(args[0])}
                    break
                elif cmd_l == "endattack":
                    # Both EndAttack and BlackScreen(1) destroy Attack9Patch
                    # and AttackSprite, including all blaster container parts.
                    # Movement already saw old platforms before Timeline.
                    removed_platforms.extend((p.x+p.vx*dt_nominal,p.y+p.vy*dt_nominal,
                        p.w,p.h,p.vx,p.vy,0.,1.,p.vy) for p in active_platforms if not p.born)
                    active_bones.clear();active_stabs.clear();active_blasters.clear();active_platforms.clear()
                    ended = True
                    termination_reason='endattack'
                    break
                elif cmd_l == "blackscreen" and int(self.eval_arg(args[0]))==1:
                    removed_platforms.extend((p.x+p.vx*dt_nominal,p.y+p.vy*dt_nominal,
                        p.w,p.h,p.vx,p.vy,0.,1.,p.vy) for p in active_platforms if not p.born)
                    active_bones.clear();active_stabs.clear();active_blasters.clear();active_platforms.clear()
                elif cmd_l in ("tlpause", "tlresume"):
                    # A settled arena still resumes only at the later world
                    # callback phase; commands after TLPause wait a real tick.
                    running=cmd_l=='tlresume'
                elif cmd_l == "set":
                    self.vars[self.variable_key(args[0])] = args[1]
                elif cmd_l == "add":
                    self.vars[self.variable_key(args[0])] = float(self.eval_arg(args[1])) + float(self.eval_arg(args[2]))
                elif cmd_l == "sub":
                    self.vars[self.variable_key(args[0])] = float(self.eval_arg(args[1])) - float(self.eval_arg(args[2]))
                elif cmd_l == "mul":
                    self.vars[self.variable_key(args[0])] = float(self.eval_arg(args[1])) * float(self.eval_arg(args[2]))
                elif cmd_l == "div":
                    d = float(self.eval_arg(args[2]))
                    self.vars[self.variable_key(args[0])] = float(self.eval_arg(args[1])) / d if d != 0.0 else 0.0
                elif cmd_l == "mod":
                    d = float(self.eval_arg(args[2]))
                    self.vars[self.variable_key(args[0])] = float(self.eval_arg(args[1])) % d if d != 0.0 else 0.0
                elif cmd_l == "floor":
                    self.vars[self.variable_key(args[0])] = math.floor(float(self.eval_arg(args[1])))
                elif cmd_l == "sin":
                    self.vars[self.variable_key(args[0])] = math.sin(math.radians(float(self.eval_arg(args[1]))))
                elif cmd_l == "cos":
                    self.vars[self.variable_key(args[0])] = math.cos(math.radians(float(self.eval_arg(args[1]))))
                elif cmd_l == "deg":
                    self.vars[self.variable_key(args[0])] = float(self.eval_arg(args[1])) * 180.0 / math.pi
                elif cmd_l == "rad":
                    self.vars[self.variable_key(args[0])] = float(self.eval_arg(args[1])) * math.pi / 180.0
                elif cmd_l == "angle":
                    x1, y1 = float(self.eval_arg(args[1])), float(self.eval_arg(args[2]))
                    x2, y2 = float(self.eval_arg(args[3])), float(self.eval_arg(args[4]))
                    # Native Ka(Pa(...)) preserves signed degrees and multiplies
                    # by 180/pi first; normalizing changes blaster entry timing.
                    self.vars[self.variable_key(args[0])] = (180.0 / math.pi) * math.atan2(y2 - y1, x2 - x1)
                elif cmd_l == "rnd":
                    self.vars[self.variable_key(args[0])] = math.floor(self.rng.random() * float(self.eval_arg(args[1])))
                elif cmd_l == "jmpabs":
                    t = str(self.eval_arg(args[0])).strip()
                    pc = labels[t] if t in labels else int(float(t)) - 1
                    continue
                elif cmd_l == "jmprel":
                    pc += int(float(self.eval_arg(args[0])))
                    continue
                elif cmd_l == "jmpz":
                    if float(self.eval_arg(args[1])) == 0.0:
                        t = str(self.eval_arg(args[0])).strip()
                        pc = labels[t] if t in labels else int(float(t)) - 1
                        continue
                elif cmd_l == "jmpnz":
                    if float(self.eval_arg(args[1])) != 0.0:
                        t = str(self.eval_arg(args[0])).strip()
                        pc = labels[t] if t in labels else int(float(t)) - 1
                        continue
                elif cmd_l == "jmpe":
                    if float(self.eval_arg(args[1])) == float(self.eval_arg(args[2])):
                        t = str(self.eval_arg(args[0])).strip()
                        pc = labels[t] if t in labels else int(float(t)) - 1
                        continue
                elif cmd_l == "jmpne":
                    if float(self.eval_arg(args[1])) != float(self.eval_arg(args[2])):
                        t = str(self.eval_arg(args[0])).strip()
                        pc = labels[t] if t in labels else int(float(t)) - 1
                        continue
                elif cmd_l == "jmpl":
                    if float(self.eval_arg(args[1])) < float(self.eval_arg(args[2])):
                        t = str(self.eval_arg(args[0])).strip()
                        pc = labels[t] if t in labels else int(float(t)) - 1
                        continue
                elif cmd_l == "jmpnl":
                    if float(self.eval_arg(args[1])) >= float(self.eval_arg(args[2])):
                        t = str(self.eval_arg(args[0])).strip()
                        pc = labels[t] if t in labels else int(float(t)) - 1
                        continue
                elif cmd_l == "jmpg":
                    if float(self.eval_arg(args[1])) > float(self.eval_arg(args[2])):
                        t = str(self.eval_arg(args[0])).strip()
                        pc = labels[t] if t in labels else int(float(t)) - 1
                        continue
                elif cmd_l == "jmpng":
                    if float(self.eval_arg(args[1])) <= float(self.eval_arg(args[2])):
                        t = str(self.eval_arg(args[0])).strip()
                        pc = labels[t] if t in labels else int(float(t)) - 1
                        continue
                elif cmd_l == "combatzoneresizeinstant":
                    new_b = [float(self.eval_arg(args[0])), float(self.eval_arg(args[1])),
                             float(self.eval_arg(args[2])), float(self.eval_arg(args[3]))]
                    cz = list(new_b)
                    cz_size=[cz[2]-cz[0],cz[3]-cz[1]]
                    cz[2]=cz[0]+cz_size[0];cz[3]=cz[1]+cz_size[1]
                    tgt_cz = list(new_b)
                    # Native ResizeInstant calls CombatZoneTick inline.
                    finish_resize('inline_combatzonetick')
                elif cmd_l == "combatzoneresize":
                    tgt_cz = [float(self.eval_arg(args[0])), float(self.eval_arg(args[1])),
                              float(self.eval_arg(args[2])), float(self.eval_arg(args[3]))]
                    end_resize=({'source_line':pc+1,'tick':tick,'function':self.variable_key(args[4])}
                        if args[4]!='' else None)
                    if end_resize is not None and end_resize['function'].lower()!='tlresume' and not audited_no_action_function(end_resize['function']):
                        # Settled bounds do not prove that an arbitrary native
                        # callback has executed or that its effects are modeled.
                        unproven_callbacks.append(dict(end_resize,status='execution_unproven'))
                elif cmd_l == "combatzonespeed":
                    cz_speed = native_int(args[0])
                elif cmd_l == "heartmode":
                    requested_mode = native_int(args[0])
                    if requested_mode == 0. or requested_mode == 1.:
                        # Native branches assign the constant RED/BLUE mode.
                        heart_mode = 0. if requested_mode == 0. else 1.
                        gravity_dir=1.
                        mode_pulse=1.
                elif cmd_l == "heartmaxfallspeed":
                    max_fall_speed=native_int(args[0])
                elif cmd_l == "sansslamdamage":
                    slam_damage=float(int(self.eval_arg(args[0]))!=0)
                elif cmd_l == "heartteleport":
                    self.heart_pos = [float(int(self.eval_arg(args[0]))), float(int(self.eval_arg(args[1])))]
                    teleport_pulse=1.
                elif cmd_l == "getheartpos":
                    sample_key=(tick,pc+1)
                    available=self.heart_samples or {}
                    sample=available.get(sample_key,available.get(tick))
                    if sample is None:
                        if not self.allow_partial:
                            raise ValueError(f"player_history_required: GetHeartPos at tick {tick}, row {pc+1}")
                        pending_target={"tick":tick,"line":pc+1,"variables":tuple(args[:2]),
                            "sample_phase":"after_custom_movement_before_remaining_timeline",
                            "preceding_teleport":tuple(self.heart_pos) if teleport_pulse else None,
                            "source_command":"getheartpos"}
                        break
                    self.heart_pos=list(sample)
                    target_history.append((tick,pc+1,*self.heart_pos))
                    player_dependent=True
                    self.vars[self.variable_key(args[0])] = self.heart_pos[0]
                    self.vars[self.variable_key(args[1])] = self.heart_pos[1]
                elif cmd_l == "sansslam":
                    slam_dir = float(math.floor(self.eval_arg(args[0])))
                    gravity_dir = slam_dir
                    heart_mode = 1.0
                    mode_pulse=1.
                    self.vars["_last_slam_tick"] = tick
                elif cmd_l in ("bonev", "boneh"):
                    active_bones.append(_bone_from_command(cmd_l == "boneh", args))
                elif cmd_l in ("bonevrepeat", "bonehrepeat"):
                    for child_args in _repeat_command_children(args):
                        active_bones.append(_bone_from_command(cmd_l == "bonehrepeat", child_args))
                elif cmd_l == "platform":
                    active_platforms.append(_platform_from_command(args))
                elif cmd_l == "platformrepeat":
                    for child_args in _repeat_command_children(args):
                        active_platforms.append(_platform_from_command(child_args))
                elif cmd_l == "bonestab":
                    # Timeline passes TLCurrentLine.At(2..10): absent cells
                    # are numeric zero, while explicit empty strings stay typed.
                    args = tuple(args) + (0.,) * max(0, 4-len(args))
                    # Function.CompareParam tests the original value BEFORE System.int.
                    if native_parameter_in_range(args[0], 0., 3.):
                        w_time = float(self.eval_arg(args[2]))
                        s_time = float(self.eval_arg(args[3]))
                        active_stabs.append(_ActiveBoneStab(args[0], args[1], w_time, s_time))
                elif cmd_l == "sinebones":
                    count = native_int(args[0])
                    spacing = native_int(args[1])
                    speed = native_int(args[2])
                    h_base = native_int(args[3])
                    for i_s in native_for_count_indices(count):
                        if spacing > 0:
                            x_s = cz[2] + spacing * i_s
                            dir_s = 2
                        elif spacing < 0:
                            x_s = cz[0] + spacing * i_s
                            dir_s = 0
                        else:
                            # Neither source Spacing branch runs at zero.
                            x_s = 0.
                            dir_s = 0
                        sine_val = math.floor(math.sin(i_s / 3.0) * 28.0)
                        top_y = cz[1] + 6.0
                        top_h = h_base + sine_val
                        active_bones.append(_bone_from_command(False,
                            (x_s, top_y, top_h, dir_s, speed)))
                        bot_y = cz[1] + 6.0 + top_h + 39.0
                        bot_h = (cz[3] - 5.0) - bot_y
                        active_bones.append(_bone_from_command(False,
                            (x_s, bot_y, bot_h, dir_s, speed)))
                elif cmd_l == "gasterblaster":
                    timer = float(self.eval_arg(args[6]))
                    blast_t = float(self.eval_arg(args[7]))
                    # System.int distinguishes loaded literal/SET strings from
                    # numeric arithmetic results. Do not eval away that type.
                    active_blasters.append(_ActiveGasterBlaster(*args[:6], timer, blast_t))
                pc += 1

            if initial_heart_pos_captured is None:
                initial_heart_pos_captured = list(self.heart_pos)

            middle_cz=list(cz)

            # Advance kinematics (inlined for high performance)
            for b in active_bones:
                next_x = b.x + b.vx * dt_nominal
                next_y = b.y + b.vy * dt_nominal
                if b.x != next_x: b.x = next_x
                if b.y != next_y: b.y = next_y
            active_bones=[b for b in active_bones if not
                ((b.direction==0 and b.x>640.) or (b.direction==1 and b.y>480.) or
                 (b.direction==2 and b.x<-b.w) or (b.direction==3 and b.y<-b.h))]

            cz_l = cz[0]
            cz_r = cz[2]
            for p in active_platforms:
                p.pre_active=0. if p.born else 1.
                p.pre_dy=p.vy
                if p.born:
                    p.born=False
                else:
                    p.x += p.vx * dt_nominal
                    p.y += p.vy * dt_nominal
                if p.reverse:
                    speed=math.hypot(p.vx,p.vy)
                    if p.direction==0 and p.x+p.w>=cz_r:
                        p.vx=-speed; p.vy=math.sin(math.pi)*speed; p.direction=2
                    elif p.direction==2 and p.x<=cz_l:
                        p.vx=speed; p.vy=0.; p.direction=0
                    elif p.direction==1 and p.y+p.h>=cz[3]:
                        p.vx=math.cos(3.*math.pi/2.)*speed; p.vy=-speed; p.direction=3
                    elif p.direction==3 and p.y<=cz[1]:
                        p.vx=math.cos(math.pi/2.)*speed; p.vy=speed; p.direction=1

            active_stabs = [s for s in active_stabs if s.step(dt_nominal,cz,cz_size)]
            active_blasters = [gb for gb in active_blasters if gb.step(dt_nominal)]

            # Expand buffer capacity if needed
            if tick >= capacity:
                capacity *= 2
                new_env = np.empty((capacity, 22), dtype=np.float64)
                new_env[:tick] = env_schedule[:tick]
                env_schedule = new_env

                new_plat = np.zeros((capacity, 4, 7), dtype=np.float64)
                new_plat[:tick] = platform_table[:tick]
                platform_table = new_plat

                new_num = np.zeros(capacity, dtype=np.int32)
                new_num[:tick] = num_platforms[:tick]
                num_platforms = new_num

            # Check slam active flag
            slam_active = 1.0 if self.vars.get("_last_slam_tick") == tick else 0.0
            env_schedule[tick, 0] = cz[0]
            env_schedule[tick, 1] = cz[1]
            env_schedule[tick, 2] = cz[2]
            env_schedule[tick, 3] = cz[3]
            env_schedule[tick, 4] = heart_mode
            env_schedule[tick, 5] = gravity_dir
            env_schedule[tick, 6] = slam_active
            env_schedule[tick, 7] = dt_nominal
            env_schedule[tick, 8:14]=[max_fall_speed,teleport_pulse,*self.heart_pos,slam_damage,mode_pulse]
            env_schedule[tick, 14:18]=previous_cz
            env_schedule[tick, 18:22]=middle_cz

            # Preserve every live platform. A fixed four-object cap loses branches.
            p_count=len(active_platforms)
            num_platforms[tick]=p_count
            platform_frames.append([(p.x,p.y,p.w,p.h,p.vx,p.vy,1.,p.pre_active,p.pre_dy) for p in active_platforms]
                +removed_platforms)

            # Collect hazard boxes for tick
            cw = 0
            cb = 0
            for b in active_bones:
                # C2 accepts signed sprite sizes and normalizes the resulting bbox.
                # Do not clamp height: SineBones uses it again to position the gap.
                box = (min(b.x, b.x + b.w), min(b.y, b.y + b.h),
                       max(b.x, b.x + b.w), max(b.y, b.y + b.h))
                if b.color == 1:
                    flat_blue_list.extend(box)
                    cb += 1
                else:
                    flat_white_list.extend(box)
                    cw += 1

            for stab in active_stabs:
                box=stab.bbox()
                if box is not None:
                    flat_white_list.extend(box)
                    cw+=1
            polygon_frames.append([poly for gb in active_blasters
                                   if (poly:=gb.polygon()) is not None])

            counts_white.append(cw)
            counts_blue.append(cb)
            if cw > max_w:
                max_w = cw
            if cb > max_b:
                max_b = cb
            if cw + cb > max_all:
                max_all = cw + cb

            # The included Timeline sheet increments T before Battle's regular
            # CombatZoneTick. A callback resuming a paused timeline cannot add
            # this dt retroactively (inline ResizeInstant is handled above).
            if running:
                time_acc += dt_nominal

            # Source order stores size separately; independent boundary lerps
            # are mathematically equivalent but not binary64-equivalent.
            _resize_combat_zone(cz,cz_size,tgt_cz,cz_speed,dt_nominal)
            env_schedule[tick,0:4]=cz
            if pending_target is None and pending_dialogue is None:
                finish_resize('post_timeline_combatzonetick')
            tick += 1

            if pc>=len(parsed_rows) and not ended and pending_target is None and pending_dialogue is None:
                if eof_tick is None:eof_tick=tick-1
                # EOF leaves native objects alive. Include ENTER/WAIT blasters
                # and warning stabs, not merely this tick's collision polygons.
                # Platforms are passive supports, not damage-producing objects.
                if (self.termination_policy=='eof_hazards_drained' and
                    not active_bones and not active_stabs and not active_blasters and cz==tgt_cz):
                    ended=True
                    termination_reason='eof_hazards_drained'

            if self.capture_state_keys:
                if pending_target is not None or pending_dialogue is not None:
                    # This compiled row stops during Timeline and has not
                    # committed all native world updates. Never memoize it as
                    # an ordinary completed tick or as a terminal state.
                    environment_state_keys.append(None)
                else:
                    environment_state_keys.append(encode_environment_state({
                        'phase':'post_world_tick','next_tick':tick,'pc':pc,
                        'loaded_line':loaded_line,'time_acc':time_acc,'running':running,
                        'vars':dict(self.vars),'rng_state':self.rng.state,
                        'heart_pos':tuple(self.heart_pos),'cz':tuple(cz),'cz_size':tuple(cz_size),
                        'tgt_cz':tuple(tgt_cz),'cz_speed':cz_speed,'heart_mode':heart_mode,
                        'gravity_dir':gravity_dir,'max_fall_speed':max_fall_speed,'slam_damage':slam_damage,
                        'active_bones':[entity_state(x) for x in active_bones],
                        'active_platforms':[entity_state(x) for x in active_platforms],
                        'active_stabs':[entity_state(x) for x in active_stabs],
                        'active_blasters':[entity_state(x) for x in active_blasters],
                        'ended':ended,'termination_reason':termination_reason,'eof_tick':eof_tick,
                        'dt_nominal':dt_nominal,'unproven_callbacks':unproven_callbacks,
                        'end_resize':end_resize,
                    }))

        if not ended:
            termination_reason=('pending_target' if pending_target is not None else
                'dialogue_boundary' if pending_dialogue is not None else 'tick_budget')
        env_schedule = env_schedule[:tick].copy()
        max_platforms=max(4,max((len(p) for p in platform_frames),default=0))
        platform_table=np.zeros((tick,max_platforms,9),np.float64)
        for t,frame in enumerate(platform_frames):
            if frame: platform_table[t,:len(frame)]=frame
        num_platforms = num_platforms[:tick].copy()

        flat_w_arr = np.asarray(flat_white_list, dtype=np.float64).reshape(-1, 4) if flat_white_list else np.empty((0, 4), dtype=np.float64)
        flat_b_arr = np.asarray(flat_blue_list, dtype=np.float64).reshape(-1, 4) if flat_blue_list else np.empty((0, 4), dtype=np.float64)
        counts_w_arr = np.asarray(counts_white, dtype=np.int32)
        counts_b_arr = np.asarray(counts_blue, dtype=np.int32)

        geom_white, geom_blue, geom_all = _build_geometry_fast_njit(
            flat_w_arr, counts_w_arr, flat_b_arr, counts_b_arr, tick, max_w, max_b, max_all
        )

        if initial_heart_pos_captured is None:
            initial_heart_pos_captured = list(initial_heart_pos)
        initial_state = np.array([initial_heart_pos_captured[0], initial_heart_pos_captured[1], 0.0, 0.0, 0.0], dtype=np.float64)

        max_polygons=max((len(p) for p in polygon_frames),default=0)
        polygons=np.full((tick,max_polygons,8),np.nan,np.float64)
        for t,frame in enumerate(polygon_frames):
            if frame: polygons[t,:len(frame)]=frame
        return {
            "env_schedule": env_schedule,
            "geometry_polygons": polygons,
            "source_events": tuple(source_events),
            "player_dependent": player_dependent,
            "pending_target": pending_target,
            "complete": ended,
            "environment_state_keys":tuple(environment_state_keys),
            "termination_reason": termination_reason,
            "eof_tick": eof_tick,
            "terminal_details": {'active_bones':len(active_bones),'active_stabs':len(active_stabs),
                'active_blasters':len(active_blasters),'active_platforms':len(active_platforms),
                'arena_settled':cz==tgt_cz,'player_invariant_proven':False,'pending_dialogue':pending_dialogue,
                'timeline_exhausted':pc>=len(parsed_rows) and loaded_line is None and pending_target is None and pending_dialogue is None,
                'pending_callbacks':unproven_callbacks+([dict(end_resize,status='awaiting_arena_settle')]
                    if end_resize is not None and (end_resize['function'].lower()=='tlresume' or audited_no_action_function(end_resize['function'])) else []),
                'end_resize':end_resize,'executed_callbacks':callback_events,
                'initial_callback_contract':('explicit_initial_arena' if self.initial_arena is not None
                    else 'assumed_none_not_encoded_in_initial_environment')},
            "target_history": tuple(target_history),
            "platform_table": platform_table,
            "num_platforms": num_platforms,
            "geom_white": geom_white,
            "geom_blue": geom_blue,
            "geom_all": geom_all,
            "initial": initial_state,
            "ticks": tick,
        }


def native_fixed_dt(clock_start_ms, count, initial_dt=None):
    """Original runtime dt for repeated JS timestamp += 1000/240 operations.

    Python float and JS Number use binary64 with the same addition/subtraction
    here. Do not replace this with a constant 1/240: timer==0 boundaries differ.
    Index zero is the already observed starting snapshot, future indices are
    the subsequent calls to the unchanged runtime.
    """
    timestamp=float(clock_start_ms)
    if not math.isfinite(timestamp): raise ValueError('clock_start_ms must be finite')
    step_ms=1000./240.
    dt=np.empty(count,np.float64)
    dt[0]=(timestamp-(timestamp-step_ms))/1000. if initial_dt is None else float(initial_dt)
    for tick in range(1,count):
        next_timestamp=timestamp+step_ms
        elapsed=(next_timestamp-timestamp)/1000.
        dt[tick]=0. if elapsed>.5 else min(elapsed,1./30.)
        timestamp=next_timestamp
    if np.any(dt<=0.) or not np.isfinite(dt).all():
        raise ValueError('clock schedule does not advance')
    return dt


def compile_wave(path: str | Path, clock_path: str | Path | None = None, seed: int = 42, fps: int = 60, initial_environment=None, heart_samples=None, legacy_calibrated=False, allow_partial=False, dt_schedule=None, clock_start_ms=None, termination_policy='endattack', max_ticks=40000,capture_state_keys=False,initial_arena=None) -> CompiledWave:
    """Universal Wave Compiler compiling any canonical attack CSV into a CompiledWave object."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    # Exact backward-compatible execution for Platforms4Hard slice
    if legacy_calibrated and path.name == "sans_platforms4hard.csv" and clock_path is None:
        if initial_arena is not None:raise ValueError('legacy calibrated geometry cannot consume initial_arena')
        if capture_state_keys:raise ValueError('legacy calibrated geometry has no complete VM state keys')
        clock_file = ROOT / "tests/fixtures/platforms4hard-clock.json"
        clock = json.loads(clock_file.read_text())
        dt = np.asarray(clock["dt"], dtype=np.float64)
        if len(dt) != 1753 or not np.all(np.isfinite(dt)) or np.any(dt <= 0):
            raise ValueError("model_mismatch: invalid calibrated clock")
        initial = np.asarray(clock["initial"], dtype=np.float64)
        if initial.shape != (5,) or not np.all(np.isfinite(initial)) or initial[4] not in (0.0, 1.0):
            raise ValueError("model_mismatch: invalid initial state")
        rows = read_timeline_rows(path)
        bones = []
        for row in rows:
            if len(row) > 1 and row[1] == "BoneVRepeat":
                x, y, h, d, speed, count, spacing = map(float, row[2:9])
                angle = d * math.pi / 2.0
                vx, vy = math.cos(angle) * speed, math.sin(angle) * speed
                for i in range(int(count)):
                    bones.append([int(x - math.cos(angle) * spacing * i), int(y - math.sin(angle) * spacing * i), 10, h, vx, vy])
        bones = np.asarray(bones, dtype=np.float64)
        geometry = np.empty((len(dt), len(bones), 4), dtype=np.float64)
        schedule = np.empty((len(dt), 7), dtype=np.float64)
        for tick in range(len(dt)):
            bones[:, 0] += bones[:, 4] * dt[tick]
            bones[:, 1] += bones[:, 5] * dt[tick]
            geometry[tick, :, 0:2] = bones[:, 0:2]
            geometry[tick, :, 2:4] = bones[:, 0:2] + bones[:, 2:4]
            if tick < 976:
                px, pdx, pdy = 151.0 + 0.375 * tick, 90.0, 0.0
            else:
                px, pdx, pdy = 517.0 - 0.375 * (tick - 976), -90.0, math.sin(math.pi) * 90.0
            schedule[tick] = [px, 336.0, 31.0, 7.0, pdx, pdy, dt[tick]]

        env_schedule = np.empty((len(dt), 8), dtype=np.float64)
        env_schedule[:, 0] = 113.0
        env_schedule[:, 1] = 231.0
        env_schedule[:, 2] = 548.0
        env_schedule[:, 3] = 391.0
        env_schedule[:, 4] = 1.0
        env_schedule[:, 5] = 1.0
        env_schedule[:, 6] = 0.0
        env_schedule[:, 7] = dt

        platform_table = np.zeros((len(dt), 4, 7), dtype=np.float64)
        platform_table[:, 0, 0:6] = schedule[:, 0:6]
        platform_table[:, 0, 6] = 1.0
        num_platforms = np.ones((len(dt),), dtype=np.int32)

        geom_obj = GeometryArray(geometry, geometry_white=geometry, geometry_blue=np.empty((len(dt), 0, 4), dtype=np.float64),
                                 origin_x=113, origin_y=231, width=435, height=160)

        return CompiledWave(
            schedule=schedule,
            geometry=geom_obj,
            initial=initial,
            env_schedule=env_schedule,
            platform_table=platform_table,
            num_platforms=num_platforms,
            geometry_white=geometry,
            geometry_blue=np.empty((len(dt), 0, 4), dtype=np.float64),
            origin=(113, 231),
            dimensions=(160, 435),
            attack_name="sans_platforms4hard",
            total_frames=438,
            dt=dt,
        )

    # Universal TimelineVM simulation for all canonical attacks
    rows = read_timeline_rows(path)

    dt_nominal = 1.0 / 240.0
    if clock_start_ms is not None:
        if dt_schedule is not None:
            raise ValueError("supply either clock_start_ms or dt_schedule")
        initial_dt=(initial_environment[7] if initial_environment is not None and len(initial_environment)>7 else None)
        dt_schedule=native_fixed_dt(clock_start_ms,max_ticks,initial_dt)
    vm = TimelineVM(seed=seed,initial_environment=initial_environment,heart_samples=heart_samples,allow_partial=allow_partial,dt_schedule=dt_schedule,termination_policy=termination_policy,max_ticks=max_ticks,capture_state_keys=capture_state_keys,initial_arena=initial_arena)
    sim = vm.run(rows, dt_nominal=dt_nominal)

    env_schedule = sim["env_schedule"]
    platform_table = sim["platform_table"]
    num_platforms = sim["num_platforms"]
    geom_white = sim["geom_white"]
    geom_blue = sim["geom_blue"]
    geom_all = sim["geom_all"]
    initial = sim["initial"]
    N_ticks = len(env_schedule)

    # Wave-enclosing bounding box
    min_x = math.floor(np.min(env_schedule[:, 0]))
    min_y = math.floor(np.min(env_schedule[:, 1]))
    max_x = math.ceil(np.max(env_schedule[:, 2]))
    max_y = math.ceil(np.max(env_schedule[:, 3]))
    origin_x = int(min_x)
    origin_y = int(min_y)
    width = int(max_x - min_x)
    height = int(max_y - min_y)

    schedule = np.empty((N_ticks, 7), dtype=np.float64)
    schedule[:, 0:6] = platform_table[:, 0, 0:6]
    schedule[:, 6] = env_schedule[:, 7]

    geom_obj = GeometryArray(geom_all, geometry_white=geom_white, geometry_blue=geom_blue,
                             origin_x=origin_x, origin_y=origin_y, width=width, height=height)

    return CompiledWave(
        schedule=schedule,
        geometry=geom_obj,
        initial=initial,
        env_schedule=env_schedule,
        platform_table=platform_table,
        num_platforms=num_platforms,
        geometry_white=geom_white,
        geometry_blue=geom_blue,
        origin=(origin_x, origin_y),
        dimensions=(height, width),
        attack_name=path.stem,
        total_frames=math.ceil(N_ticks / 4.0),
        dt=env_schedule[:, 7],
        geometry_polygons=sim["geometry_polygons"],
        source_events=sim["source_events"],
        player_dependent=sim["player_dependent"],
        pending_target=sim["pending_target"],
        complete=sim["complete"],
        target_history=sim["target_history"],
        termination_reason=sim["termination_reason"],
        eof_tick=sim["eof_tick"],
        terminal_details=sim["terminal_details"],
        environment_state_keys=sim["environment_state_keys"],
    )


@njit(cache=True)
def _prepare_collision_plane_njit(
    geometry: np.ndarray,
    origin_x: int,
    origin_y: int,
    H: int,
    W: int,
    words: int,
    margin: float,
    margin_x: float,
    margin_y: float,
    soul_rx: float,
    soul_ry: float,
) -> np.ndarray:
    mask = np.zeros((len(geometry), H, words), dtype=np.uint64)
    for tick in range(len(geometry)):
        for box in geometry[tick]:
            left, top, right, bottom = box[0], box[1], box[2], box[3]
            if not (math.isfinite(left) and math.isfinite(top) and math.isfinite(right) and math.isfinite(bottom)) or right < left or bottom < top:
                continue
            x0 = max(0, math.ceil(left - soul_rx - margin - margin_x - origin_x))
            x1 = min(W - 1, math.floor(right + soul_rx + margin + margin_x - origin_x))
            y0 = max(0, math.ceil(top - soul_ry - margin - margin_y - origin_y))
            y1 = min(H - 1, math.floor(bottom + soul_ry + margin + margin_y - origin_y))
            if x1 < x0 or y1 < y0:
                continue
            for word in range(x0 // 64, x1 // 64 + 1):
                lo = max(x0, word * 64) - word * 64
                hi = min(x1, word * 64 + 63) - word * 64
                length = hi - lo + 1
                if length == 64:
                    bits = np.uint64(0xFFFFFFFFFFFFFFFF)
                else:
                    bits = ((np.uint64(1) << np.uint64(length)) - np.uint64(1)) << np.uint64(lo)
                for y in range(y0, y1 + 1):
                    mask[tick, y, word] |= bits
    return mask


def prepare_collision_dual_native(
    geom_white_or_compiled: Any,
    geom_blue: np.ndarray | None = None,
    margin: float = 0.0,
    margin_x: float = 0.0,
    margin_y: float = 0.0,
    origin_x: int | None = None,
    origin_y: int | None = None,
    width: int | None = None,
    height: int | None = None,
    soul_rx: float = 2.0,
    soul_ry: float = 2.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Bakes dual-plane C-space hazard bitmasks: (mask_white, mask_blue)."""
    if isinstance(geom_white_or_compiled, CompiledWave):
        gw = geom_white_or_compiled.geometry_white
        gb = geom_white_or_compiled.geometry_blue
        ox = origin_x if origin_x is not None else geom_white_or_compiled.origin[0]
        oy = origin_y if origin_y is not None else geom_white_or_compiled.origin[1]
        h = height if height is not None else geom_white_or_compiled.dimensions[0]
        w = width if width is not None else geom_white_or_compiled.dimensions[1]
    elif geom_blue is not None:
        gw = geom_white_or_compiled
        gb = geom_blue
        ox = origin_x if origin_x is not None else getattr(gw, "origin_x", 113)
        oy = origin_y if origin_y is not None else getattr(gw, "origin_y", 231)
        h = height if height is not None else getattr(gw, "height", 160)
        w = width if width is not None else getattr(gw, "width", 435)
    else:
        # Check if geom_white_or_compiled has attached dual planes
        attached_w = getattr(geom_white_or_compiled, "geometry_white", None)
        attached_b = getattr(geom_white_or_compiled, "geometry_blue", None)
        if attached_w is not None and attached_b is not None:
            gw = attached_w
            gb = attached_b
        else:
            gw = geom_white_or_compiled
            gb = np.empty((len(gw), 0, 4), dtype=np.float64)
        ox = origin_x if origin_x is not None else getattr(geom_white_or_compiled, "origin_x", 113)
        oy = origin_y if origin_y is not None else getattr(geom_white_or_compiled, "origin_y", 231)
        h = height if height is not None else getattr(geom_white_or_compiled, "height", 160)
        w = width if width is not None else getattr(geom_white_or_compiled, "width", 435)

    words = (w + 63) // 64
    mask_white = _prepare_collision_plane_njit(gw, ox, oy, h, w, words, margin, margin_x, margin_y, soul_rx, soul_ry)
    mask_blue = _prepare_collision_plane_njit(gb, ox, oy, h, w, words, margin, margin_x, margin_y, soul_rx, soul_ry)
    return mask_white, mask_blue


def prepare_collision(geometry: Any, margin: float = 0.0, margin_x: float = 0.0, margin_y: float = 0.0) -> np.ndarray:
    """Pure-Python conservative bbox C-space operator for reference verification."""
    ox = getattr(geometry, "origin_x", 113)
    oy = getattr(geometry, "origin_y", 231)
    h = getattr(geometry, "height", 160)
    w = getattr(geometry, "width", 435)
    words = (w + 63) // 64
    mask = np.zeros((len(geometry), h, words), dtype=np.uint64)
    for tick, boxes in enumerate(geometry):
        for left, top, right, bottom in boxes:
            if not (math.isfinite(left) and math.isfinite(top) and math.isfinite(right) and math.isfinite(bottom)) or right < left or bottom < top:
                continue
            x0 = max(0, math.ceil(left - 2.0 - margin - margin_x - ox))
            x1 = min(w - 1, math.floor(right + 2.0 + margin + margin_x - ox))
            y0 = max(0, math.ceil(top - 2.0 - margin - margin_y - oy))
            y1 = min(h - 1, math.floor(bottom + 2.0 + margin + margin_y - oy))
            if x1 < x0 or y1 < y0:
                continue
            for word in range(x0 // 64, x1 // 64 + 1):
                lo = max(x0, word * 64) - word * 64
                hi = min(x1, word * 64 + 63) - word * 64
                length = hi - lo + 1
                if length == 64:
                    bits = np.uint64(0xFFFFFFFFFFFFFFFF)
                else:
                    bits = np.uint64(((1 << length) - 1) << lo)
                mask[tick, y0:y1 + 1, word] |= bits
    return mask


@njit(cache=True)
def prepare_collision_native(geometry: Any, margin: float = 0.0, margin_x: float = 0.0, margin_y: float = 0.0) -> np.ndarray:
    """Native word-write collision operator preserving exact Platforms4Hard behavior."""
    return _prepare_collision_plane_njit(geometry, 113, 231, 160, 435, 7, margin, margin_x, margin_y, 2.0, 2.0)


@njit(cache=True, inline="always")
def is_point_blocked(mask: np.ndarray, tick: int, xpos: float, ypos: float, origin_x: int, origin_y: int, W: int, H: int) -> bool:
    """Queries whether world coordinates (xpos, ypos) intersect mask[tick]."""
    xl, xh = int(math.floor(xpos)), int(math.ceil(xpos))
    yl, yh = int(math.floor(ypos)), int(math.ceil(ypos))
    W_words = mask.shape[2]
    for x in (xl, xh):
        xx = x - origin_x
        if xx < 0 or xx >= W:
            return True
        w = xx >> 6
        if w >= W_words:
            return True
        bit = np.uint64(1) << np.uint64(xx & 63)
        for y in (yl, yh):
            yy = y - origin_y
            if yy < 0 or yy >= H:
                return True
            if mask[tick, yy, w] & bit:
                return True
    return False
