"""Resumable pure source environment operator; no prefix replay or native search.

Equation bodies are kept independent of TimelineVM.run for differential tests.
Only entity classes, argument coercion and arena arithmetic are shared.
"""
from dataclasses import dataclass
from pathlib import Path
import copy,math,struct
import numpy as np
from .compact_wave import (TimelineVM,_ActiveBone,_ActivePlatform,_ActiveBoneStab,
    _ActiveGasterBlaster,_StreamingGasterBlaster,_resize_combat_zone,_initial_arena_state,initial_arena_identity,
    _bone_from_command,_platform_from_command,_repeat_command_children,_bounded_bone_rows,
    _reference_numeric,_no_collision_bounds,_discard_registered_prefix)
from .native_math import native_atan2
from .native_numbers import native_int, native_parameter_number, native_parameter_in_range, native_for_count_indices
from .dialogue_operator import DialogueState,step_dialogue
from .timeline_csv import parse_timeline_rows
from .static_blue_tail import stationary_blue_rows
from .native_function_dispatch import call_arguments, audited_no_action_function, NO_ACTION_FUNCTION_AUDIT

# Full static bytes, not a digest accepted without a collision check. A branch
# shares its Program object, so this is not copied into each tick's live state.
_SEMANTIC_SOURCE=tuple(Path(__file__).with_name(name).read_bytes() for name in
    ('resumable_wave.py','compact_wave.py','dialogue_operator.py','timeline_csv.py','native_function_dispatch.py'))

class _BoneArrays:
    """Private owned continuation storage; scalar iteration preserves public keys."""
    def __init__(self,items=(),native=False):
        self.native=native;self.proposal=False;self.clip_bounds=None;self.count=0;self.rows=np.empty((max(16,len(items)),8),np.float64,order="C" if native else "F")
        for item in items:self.append(item)
    def __len__(self):return self.count
    def __iter__(self):
        for row in self.rows[:self.count]:
            item=_ActiveBone.__new__(_ActiveBone)
            for key,value in zip(_ActiveBone.__slots__,row):setattr(item,key,float(value))
            yield item
    def append(self,item):
        if self.count==len(self.rows):
            expanded=np.empty((max(16,self.count*2),8),np.float64,order="C" if self.native else "F")
            expanded[:self.count]=self.rows[:self.count];self.rows=expanded
        self.rows[self.count]=tuple(getattr(item,key) for key in _ActiveBone.__slots__);self.count+=1
    def clear(self):self.count=0
    def advance(self,dt):
        if not self.count:return
        if not self.native and _reference_numeric is not None:
            self.count=_reference_numeric.advance_bones(self.rows,self.count,dt)
            return
        if self.native:
            from .native_backend import _bones_advance,load_backend
            # Once search has loaded the kernel, small batches also avoid
            # several NumPy temporaries. Keep the compiler-free small-wave
            # path until then; do not compile merely to move a single bone.
            if self.count>=64 or load_backend.cache_info().currsize:
                self.count=_bones_advance(self.rows,self.count,dt);return
        rows=self.rows[:self.count];old=rows[:,:2]
        following=old+rows[:,4:6]*dt
        np.copyto(old,following,where=old!=following)
        direction=rows[:,7]
        keep=~(((direction==0)&(rows[:,0]>640.))|((direction==1)&(rows[:,1]>480.))|
            ((direction==2)&(rows[:,0]<-rows[:,2]))|((direction==3)&(rows[:,1]<-rows[:,3])))
        if not keep.all():
            kept=rows[keep];self.count=len(kept);self.rows[:self.count]=kept
    def geometry(self,bounds=None):
        if not self.count:return np.empty((0,4),np.float64),np.empty((0,4),np.float64)
        if bounds is None:bounds=self.clip_bounds
        if not self.native and _reference_numeric is not None:
            white=np.empty((self.count,4),np.float64);blue=np.empty_like(white)
            clip=_no_collision_bounds if bounds is None else np.asarray(bounds,np.float64)
            nw,nb=_reference_numeric.bone_geometry(self.rows,self.count,clip,white,blue)
            return white[:nw],blue[:nb]
        if self.native:
            from .native_backend import _bones_geometry,load_backend
            if self.count>=64 or load_backend.cache_info().currsize:
                return _bones_geometry(self.rows,self.count,bounds)
        rows=_bounded_bone_rows(self.rows[:self.count],bounds);first=rows[:,:2];second=first+rows[:,2:4]
        boxes=np.concatenate((np.where(second<first,second,first),np.where(second>first,second,first)),axis=1)
        blue=rows[:,6]==1.
        return boxes[~blue],boxes[blue]


class _BlasterArrays:
    fields=('size','x','y','end_x','end_y','end_ang','angle','timer','blast_time',
        'state','leave_speed','beam_timer','base_size','damage','opacity','scale_y','scale_x')
    def __init__(self,items=()):
        self.count=0;self.rows=np.empty((max(16,len(items)),17),np.float64)
        self.boxes=np.empty((0,8),np.float64)
        for item in items:self.append(item)
    def __len__(self):return self.count
    def __iter__(self):
        for row in self.rows[:self.count]:
            item=_ActiveGasterBlaster.__new__(_ActiveGasterBlaster)
            for key,value in zip(self.fields,row):
                setattr(item,key,bool(value) if key=='damage' else int(value) if key=='state' else float(value))
            yield item
    def append(self,item):
        if self.count==len(self.rows):
            rows=np.empty((self.count*2,17),np.float64);rows[:self.count]=self.rows;self.rows=rows
        self.rows[self.count]=tuple(getattr(item,key) for key in self.fields);self.count+=1
    def clear(self):self.count=0;self.boxes=np.empty((0,8),np.float64)
    def advance(self,dt):
        if not self.count:self.boxes=np.empty((0,8),np.float64);return
        from .native_backend import _blasters_advance
        self.count,self.boxes=_blasters_advance(self.rows,self.count,dt)
    def polygons(self):return self.boxes


class _PlatformArrays:
    """Owned linear platforms; published frames and public keys remain values."""
    def __init__(self,items=()):
        self.count=0;self.has_reverse=False;self.integer_directions=[]
        self.rows=np.empty((max(16,len(items)),11),np.float64,order='F')
        for item in items:self.append(item)
    def __len__(self):return self.count
    def __iter__(self):
        for number,row in enumerate(self.rows[:self.count]):
            item=_ActivePlatform.__new__(_ActivePlatform)
            for index,(key,value) in enumerate(zip(_ActivePlatform.__slots__,row)):
                setattr(item,key,bool(value) if index==7 else int(value) if index==6 or index==8 and self.integer_directions[number] else float(value))
            yield item
    def append(self,item):
        if self.count==len(self.rows):
            rows=np.empty((self.count*2,11),np.float64,order='F');rows[:self.count]=self.rows;self.rows=rows
        self.rows[self.count]=tuple(getattr(item,key) for key in _ActivePlatform.__slots__)
        self.integer_directions.append(type(item.direction) is int)
        self.count+=1;self.has_reverse|=bool(item.reverse)
    def clear(self):self.count=0;self.has_reverse=False;self.integer_directions.clear()
    def advance(self,dt):
        if not self.count:return
        rows=self.rows[:self.count];born=rows[:,7]!=0.
        rows[:,9]=np.where(born,0.,1.);rows[:,10]=rows[:,5]
        if born.any():
            np.copyto(rows[:,0],rows[:,0]+rows[:,4]*dt,where=~born)
            np.copyto(rows[:,1],rows[:,1]+rows[:,5]*dt,where=~born)
        else:
            rows[:,0]+=rows[:,4]*dt;rows[:,1]+=rows[:,5]*dt
        rows[:,7]=0.
    def geometry(self,removed):
        rows=self.rows[:self.count];out=np.empty((self.count+len(removed),9),np.float64)
        out[:self.count,:6]=rows[:,:6];out[:self.count,6]=1.;out[:self.count,7:]=rows[:,9:11]
        if removed:out[self.count:]=removed
        return out


def _enable_bone_arrays(state,*,native=False,proposal=False,clip_bounds=None):
    if not isinstance(state.data['active_bones'],_BoneArrays):
        state.data['active_bones']=_BoneArrays(state.data['active_bones'],native=native)
    bones=state.data['active_bones']
    if native and not bones.rows.flags.c_contiguous:bones.rows=np.ascontiguousarray(bones.rows)
    bones.native=native
    bones.proposal=proposal;bones.clip_bounds=clip_bounds
    if native and not isinstance(state.data['active_blasters'],_BlasterArrays):
        state.data['active_blasters']=_BlasterArrays(state.data['active_blasters'])
    return state


@dataclass(frozen=True)
class Program:
    rows: tuple
    parsed: tuple
    labels: dict
    identity: bytes
    dt_schedule: tuple | None

@dataclass
class EnvState:
    program: Program
    vm: TimelineVM
    data: dict
    max_ticks: int
    phase: str='committed'
    supplied_target: tuple | None=None
    request: dict | None=None
    clock_timestamp: float | None=None
    initial_dt: float | None=None
    stats: dict=None
    dialogue: DialogueState | None=None
    dialogue_coupled: bool=False
    dialogue_last_input: tuple=(False,False)
    dialogue_current_input: tuple | None=None
    dialogue_blocked_callback: str | None=None
    def clone(self):
        return EnvState(self.program,copy.deepcopy(self.vm),copy.deepcopy(self.data),self.max_ticks,
            self.phase,self.supplied_target,copy.deepcopy(self.request),self.clock_timestamp,
            self.initial_dt,dict(self.stats),self.dialogue,self.dialogue_coupled,
            self.dialogue_last_input,self.dialogue_current_input,self.dialogue_blocked_callback)
    def __deepcopy__(self,memo):
        result=self.clone();memo[id(self)]=result
        return result

@dataclass
class Frame:
    tick: int
    env: np.ndarray
    platforms: np.ndarray
    white: np.ndarray
    blue: np.ndarray
    polygons: np.ndarray
    events: tuple
    target_history: tuple
    callback_events: tuple=()
    committed: bool=True
    dialogue: DialogueState | None=None
    dialogue_input: tuple | None=None

@dataclass
class TickCommitted:
    state: EnvState
    frame: Frame
@dataclass
class Terminal:
    state: EnvState
    frame: Frame | None
    reason: str
@dataclass
class NeedTarget:
    state: EnvState
    request: dict
@dataclass
class NeedDialogue:
    state: EnvState
    request: dict
@dataclass
class ResourceLimit:
    state: EnvState
    reason: str

def initialize(path_or_rows,seed=42,initial_environment=None,termination_policy='endattack',
               dt_schedule=None,clock_start_ms=None,max_ticks=40000,initial_arena=None):
    if isinstance(path_or_rows,(str,Path)):
        raw=Path(path_or_rows).read_bytes()
        rows=parse_timeline_rows(raw.decode('utf-8-sig'))
    else:
        rows=[list(r) for r in path_or_rows]
        raw=repr(rows).encode()
    if dt_schedule is not None and clock_start_ms is not None:raise ValueError('supply one clock protocol')
    if dt_schedule is not None and (not len(dt_schedule) or any(not math.isfinite(x) or x<=0 for x in dt_schedule)):
        raise ValueError('invalid dt schedule')
    vm=TimelineVM(seed=seed,initial_environment=initial_environment,termination_policy=termination_policy,max_ticks=max_ticks,initial_arena=initial_arena)
    labels={};parsed=[];cz=[133.,251.,508.,391.];mode=1.;heart=[320.,376.]
    got_cz=got_mode=got_heart=False
    for i,row in enumerate(rows):
        if not row or not any(str(x).strip() for x in row):parsed.append(None);continue
        row=[str(x).strip() for x in row];cmd=row[1] if len(row)>1 else ''
        if cmd.startswith(':'):labels[cmd.lstrip(':').strip()]=i
        low=cmd.lower();args=row[2:]
        try:
            if low in ('combatzoneresize','combatzoneresizeinstant') and not got_cz and len(args)>=4 and all(args[:4]):
                cz=list(map(float,args[:4]));got_cz=True
            elif low=='heartmode' and not got_mode and args and args[0]:mode=float(args[0]);got_mode=True
            elif low=='heartteleport' and not got_heart and len(args)>=2 and all(args[:2]):heart=list(map(float,args[:2]));got_heart=True
        except ValueError:pass
        parsed.append((row[0],None,cmd,low,tuple(args)))
    if termination_policy=='endattack' and not any(p and p[3]=='endattack' for p in parsed):
        raise ValueError('unsupported_mechanism: CSV reached EOF without EndAttack')
    gravity=1.;maxfall=750.;slam=0.
    if initial_environment is not None:
        cz=list(initial_environment[:4]);mode=float(initial_environment[4])
        if len(initial_environment)>5:gravity=float(initial_environment[5])
        if len(initial_environment)>8:maxfall=float(initial_environment[8])
        if len(initial_environment)>12:slam=float(initial_environment[12])
    vm.heart_pos=list(heart)
    cz_size,tgt_cz,cz_speed,end_resize=_initial_arena_state(cz,vm.initial_arena)
    data=dict(tick=0,pc=0,loaded_line=None,time_acc=0.,running=True,ended=False,
        termination_reason=None,eof_tick=None,cz=cz,cz_size=cz_size,
        tgt_cz=tgt_cz,cz_speed=cz_speed,heart_mode=mode,gravity_dir=gravity,
        max_fall_speed=maxfall,slam_damage=slam,active_bones=[],active_platforms=[],
        active_stabs=[],active_blasters=[],end_resize=end_resize,unproven_callbacks=[])
    schedule=None if dt_schedule is None else tuple(float(x) for x in dt_schedule)
    identity=b'NOHIT-RESUMABLE-PROGRAM\x01'+b''.join(struct.pack('<Q',len(part))+part for part in (raw,*_SEMANTIC_SOURCE))
    identity+=initial_arena_identity(vm.initial_arena)
    program=Program(tuple(tuple(r) for r in rows),tuple(parsed),labels,identity,schedule)
    initial_dt=initial_environment[7] if initial_environment is not None and len(initial_environment)>7 else None
    if clock_start_ms is not None and not math.isfinite(clock_start_ms):raise ValueError('clock_start_ms must be finite')
    return EnvState(program,vm,data,max_ticks,clock_timestamp=clock_start_ms,initial_dt=initial_dt,
        stats={'commands_executed':0,'ticks_committed':0})

def supply_target(suspension,position):
    prior=suspension.state if isinstance(suspension,NeedTarget) else suspension
    return _supply_target_owned(prior.clone(),position)

def _supply_target_owned(state,position):
    """Consume an exclusively owned suspension, without cloning its world."""
    prior=state
    if prior.phase!='await_target' or prior.request is None:raise ValueError('state is not awaiting a target')
    if len(position)!=2 or not all(math.isfinite(x) for x in position):raise ValueError('target must have two finite coordinates')
    state.supplied_target=tuple(state.request['preceding_teleport'] or position)
    state.phase='timeline';state.request=None
    return state

def _observation_sampling_arrays(suspension):
    """Read only the pre-timeline movement fields needed by sample_position.

    This is not a committed frame. No hazard, callback, RNG or entity is
    advanced. The public full preview remains the independent oracle.
    """
    state=suspension.state if isinstance(suspension,(NeedTarget,NeedDialogue)) else suspension
    if state.phase not in ('await_target','await_dialogue'):
        raise ValueError('sampling requires an unresolved observation or dialogue')
    data=state.data;dt=data['dt_nominal']
    env=np.zeros(22,dtype=np.float64);env[7]=dt;env[14:18]=data['previous_cz']
    rows=[(p.x if p.born else p.x+p.vx*dt,
           p.y if p.born else p.y+p.vy*dt,
           p.w,p.h,p.vx,p.vy,1.,0. if p.born else 1.,p.vy)
          for p in data['active_platforms']]
    rows.extend(data['removed_platforms'])
    return env,np.asarray(rows,dtype=np.float64).reshape(-1,9)

_PERSISTENT = ('tick', 'pc', 'loaded_line', 'time_acc', 'running', 'ended', 'termination_reason', 'eof_tick', 'cz', 'cz_size', 'tgt_cz', 'cz_speed', 'heart_mode', 'gravity_dir', 'max_fall_speed', 'slam_damage', 'active_bones', 'active_platforms', 'active_stabs', 'active_blasters', 'end_resize', 'unproven_callbacks')
_IN_FLIGHT = ('dt_nominal', 'previous_cz', 'teleport_pulse', 'mode_pulse', 'removed_platforms', 'run_count', 'source_events', 'target_history', 'callback_events', 'registered_counts')
def _save(state,scope,phase):
    state.data={name:scope[name] for name in _PERSISTENT}
    if 'dt_nominal' in scope:state.data['last_dt']=scope['dt_nominal']
    if phase!='committed':state.data.update({name:scope[name] for name in _IN_FLIGHT})
    state.phase=phase
    return state

def preview_observation_frame(suspension):
    """Read-only pre-observation context from the suspended transaction.

    Only the uncommitted world's remaining entity/frame phases are evaluated
    on a clone. No source command or target guess is executed. The returned
    frame is explicitly not a committed transition or a valid memo-key tick.
    """
    state=suspension.state if isinstance(suspension,(NeedTarget,NeedDialogue)) else suspension
    if state.phase not in ('await_target','await_dialogue'):raise ValueError('preview requires an unresolved observation or dialogue')
    result=advance_one_tick(state,_preview=True)
    result.frame.committed=False
    return result.frame

sample_context=preview_observation_frame

def state_environment_key(state):
    """Exact template-relative bytes matching the reference committed key.

    The consumer must separately retain program/clock identity. Suspension
    previews and the pre-tick initial state are not committed frame keys.
    """
    if state.phase!='committed' or 'last_dt' not in state.data:
        raise ValueError('environment key requires a committed world tick')
    from .environment_state_key import encode_environment_state
    d=state.data
    def entity_state(entity):
        fields=getattr(type(entity),'__slots__',None)
        return ((type(entity).__name__,tuple((name,getattr(entity,name)) for name in fields))
            if fields is not None else (type(entity).__name__,dict(vars(entity))))
    snapshot={key:d[key] for key in (
        'pc','loaded_line','time_acc','running','cz_speed','heart_mode','gravity_dir',
        'max_fall_speed','slam_damage','ended','termination_reason','eof_tick',
        'unproven_callbacks','end_resize')}
    snapshot.update(phase='post_world_tick',next_tick=d['tick'],vars=dict(state.vm.vars),
        rng_state=state.vm.rng.state,heart_pos=tuple(state.vm.heart_pos),dt_nominal=d['last_dt'])
    for key in ('cz','cz_size','tgt_cz'):snapshot[key]=tuple(d[key])
    for key in ('active_bones','active_platforms','active_stabs','active_blasters'):
        snapshot[key]=[entity_state(entity) for entity in d[key]]
    if state.dialogue_coupled:
        snapshot['dialogue_coupled']=True
        snapshot['dialogue']=None if state.dialogue is None else dict(vars(state.dialogue))
        snapshot['dialogue_last_input']=state.dialogue_last_input
        snapshot['dialogue_blocked_callback']=state.dialogue_blocked_callback
    return encode_environment_state(snapshot)


def advance_with_dialogue_input(prior,*,confirm,cancel,previous_confirm=None,previous_cancel=None):
    """Pure full-world tick with explicit VPad Confirm/Cancel input.

    First coupling requires both previous VPad values: an already-held Confirm
    must not become a false rising edge. Later ticks inherit the prior input.
    LRUD/Cancel player movement must still use this frame's dt/environment via
    the discrete player operator; Cancel legality remains the caller's concern.
    No waiting tick or live hazard is skipped. A suspended GetHeartPos retains
    this tick's inputs, which cannot be changed when that transaction resumes.
    """
    return _advance_with_dialogue_input_owned(prior.clone(),confirm=confirm,cancel=cancel,
        previous_confirm=previous_confirm,previous_cancel=previous_cancel)


def _advance_with_dialogue_input_owned(state,*,confirm,cancel,previous_confirm=None,previous_cancel=None):
    """Private collector: owns its entire state and retains committed Frames only."""
    if any(value not in (0,1) for value in (confirm,cancel)):
        raise ValueError('Confirm and Cancel must be zero or one')
    if not state.dialogue_coupled:
        if any(value not in (0,1) for value in (previous_confirm,previous_cancel)):
            raise ValueError('first dialogue coupling requires previous Confirm and Cancel')
        state.dialogue_coupled=True
        state.dialogue_last_input=(bool(previous_confirm),bool(previous_cancel))
    elif previous_confirm is not None or previous_cancel is not None:
        raise ValueError('previous input is already part of the coupled state')
    current=(bool(confirm),bool(cancel))
    if state.dialogue_current_input is not None and state.dialogue_current_input!=current:
        raise ValueError('cannot change input during a suspended tick')
    state.dialogue_current_input=current
    if state.phase=='await_dialogue':
        state.phase='timeline';state.request=None
    return _advance_owned_tick(state)

def advance_one_tick(prior,*,_preview=False):
    """Pure value operator: the caller retains its independent prior state."""
    return _advance_owned_tick(prior.clone(),_preview=_preview)


def _advance_idle_world_owned(state,limit):
    """Batch an event-free interval; never cross a source command boundary.

    Private alternating-Confirm collector only. Frames retain all geometry;
    the independent certificate still executes the original scalar source.
    """
    d=state.data;tick=d['tick'];bones=d['active_bones'];schedule=state.program.dt_schedule
    blasters=d['active_blasters'];platforms=d['active_platforms']
    if (limit<2 or tick<1 or state.phase!='committed' or not state.dialogue_coupled
            or state.dialogue_current_input is not None or state.dialogue_blocked_callback
            or state.dialogue and state.dialogue.alive or d['ended'] or not d['running']
            or schedule is None or d['loaded_line'] is None or d['end_resize'] is not None
            or d['pc']>=len(state.program.parsed) or not isinstance(bones,_BoneArrays)
            or not bones.native or d['active_stabs'] or not isinstance(blasters,_BlasterArrays)):return []
    cz=d['cz'];size=d['cz_size']
    last_slam=state.vm.vars.get('_last_slam_tick',-1)
    if (cz!=d['tgt_cz'] or
            struct.pack('<dd',cz[0]+size[0],cz[1]+size[1])!=struct.pack('<dd',cz[2],cz[3])
            or not isinstance(last_slam,(int,float)) or last_slam>=tick
            or (platforms.has_reverse if isinstance(platforms,_PlatformArrays) else any(p.reverse for p in platforms))):return []
    limit=min(limit,64,len(schedule)-tick,state.max_ticks-tick)
    # Do not turn a large single-frame inventory into an unbounded tensor.
    bytes_per_tick=bones.count*32+blasters.count*64+len(platforms)*72+192
    limit=min(limit,(8*1024*1024)//bytes_per_tick)
    delay=d['loaded_line'][0]
    if limit<2 or not d['time_acc']<delay:return []
    from .native_backend import _idle_world,load_backend
    # Small observed waves may finish without loading any native kernel.
    # Batching must not turn those compiler-free requests into native builds.
    if not load_backend.cache_info().currsize:return []
    if not isinstance(platforms,_PlatformArrays):
        platforms=_PlatformArrays(platforms);d['active_platforms']=platforms
    ticks,elapsed,boxes,polygons,platform_frames,counts=_idle_world(bones,blasters,platforms,
        schedule[tick:tick+limit],delay,d['time_acc'])
    if not ticks:return []
    base=[*cz,d['heart_mode'],d['gravity_dir'],0.,0.,d['max_fall_speed'],0.,
        *state.vm.heart_pos,d['slam_damage'],0.,*cz,*cz]
    envs=np.tile(np.asarray(base,np.float64),(ticks,1));envs[:,7]=schedule[tick:tick+ticks]
    frames=[]
    from .search_preferences import current
    sparse_confirm=current()['objective']=='human_friendly'
    for offset in range(ticks):
        count,white,alive,polygon_count=map(int,counts[offset]);now=tick+offset
        frame=Frame(now,envs[offset],platform_frames[offset],boxes[offset,:white],
            boxes[offset,white:count],polygons[offset,:polygon_count],(),())
        frame.dialogue=state.dialogue;frame.dialogue_input=(False if sparse_confirm else now%2==0,False)
        frames.append(frame)
    bones.count=int(counts[-1,0])
    blasters.count=int(counts[-1,2]);blasters.boxes=frames[-1].polygons
    d.update(tick=tick+ticks,time_acc=elapsed,last_dt=schedule[tick+ticks-1])
    state.stats['ticks_committed']+=ticks
    state.dialogue_last_input=frames[-1].dialogue_input
    return frames


def _advance_owned_tick(state,*,_preview=False):
    """Consume an exclusively owned continuation, preserving exact tick order.

    Private collector fast path. Its caller must own every mutable object in
    state and must not retain intermediate states: successive results alias
    this continuation. Published branch checkpoints enter through clone (or
    supply_target); previews always use the public pure operator. Frame arrays
    and event tuples are newly materialized and can be retained independently.
    """
    if state.phase=='await_target' and not _preview:return NeedTarget(state,dict(state.request))
    if state.phase=='await_dialogue' and not _preview:return NeedDialogue(state,dict(state.request))
    if state.data['ended']:return Terminal(state,None,state.data['termination_reason'])
    if state.phase=='committed' and state.data['tick']>=state.max_ticks:return ResourceLimit(state,'tick_budget')
    if state.dialogue_blocked_callback and not _preview:
        return ResourceLimit(state,'unsupported_dialogue_callback:'+state.dialogue_blocked_callback)
    if state.dialogue_coupled and state.dialogue_current_input is None and not _preview:
        return NeedDialogue(state,{'tick':state.data['tick'],'kind':'input_required',
            'phase':state.phase,'dialogue':None if state.dialogue is None else dict(vars(state.dialogue))})
    self=state.vm
    parsed_rows=state.program.parsed;labels=state.program.labels
    tick=state.data['tick']
    pc=state.data['pc']
    loaded_line=state.data['loaded_line']
    time_acc=state.data['time_acc']
    running=state.data['running']
    ended=state.data['ended']
    termination_reason=state.data['termination_reason']
    eof_tick=state.data['eof_tick']
    cz=state.data['cz']
    cz_size=state.data['cz_size']
    tgt_cz=state.data['tgt_cz']
    cz_speed=state.data['cz_speed']
    heart_mode=state.data['heart_mode']
    gravity_dir=state.data['gravity_dir']
    max_fall_speed=state.data['max_fall_speed']
    slam_damage=state.data['slam_damage']
    active_bones=state.data['active_bones']
    active_platforms=state.data['active_platforms']
    active_stabs=state.data['active_stabs']
    active_blasters=state.data['active_blasters']
    end_resize=state.data['end_resize']
    unproven_callbacks=state.data['unproven_callbacks']
    if state.phase=='committed':
        schedule=state.program.dt_schedule
        if schedule is not None:
            if tick>=len(schedule):return ResourceLimit(state,'clock_budget')
            dt_nominal=schedule[tick]
        elif state.clock_timestamp is not None:
            stamp=float(state.clock_timestamp);step=1000./240.
            if tick==0:dt_nominal=(stamp-(stamp-step))/1000. if state.initial_dt is None else float(state.initial_dt)
            else:
                nxt=stamp+step;elapsed=(nxt-stamp)/1000.
                dt_nominal=0. if elapsed>.5 else min(elapsed,1/30);state.clock_timestamp=nxt
            if dt_nominal<=0:raise ValueError('clock schedule does not advance')
        else:dt_nominal=1/240
        previous_cz=list(cz);teleport_pulse=mode_pulse=0.;removed_platforms=[];run_count=0
        source_events=[];target_history=[];callback_events=[]
        registered_counts=[len(active_bones),len(active_stabs),len(active_blasters),len(active_platforms)]
    else:
        dt_nominal=state.data['dt_nominal']
        previous_cz=state.data['previous_cz']
        teleport_pulse=state.data['teleport_pulse']
        mode_pulse=state.data['mode_pulse']
        removed_platforms=state.data['removed_platforms']
        run_count=state.data['run_count']
        source_events=state.data['source_events']
        target_history=state.data['target_history']
        callback_events=state.data['callback_events']
        registered_counts=state.data['registered_counts']
    def finish_resize(phase):
        nonlocal end_resize,running
        if end_resize is None or cz!=tgt_cz:return
        if end_resize['function'].lower()=='tlresume':
            running=True;callback_events.append(dict(end_resize,executed_tick=tick,phase=phase));end_resize=None
        elif audited_no_action_function(end_resize['function']):
            callback_events.append(dict(end_resize,executed_tick=tick,phase=phase,
                no_action_audit=NO_ACTION_FUNCTION_AUDIT));end_resize=None
    while running and pc<len(parsed_rows) and run_count<1000 and not _preview:
        if pc<0:raise ValueError('model_mismatch: negative timeline instruction index')
        p_row=parsed_rows[pc]
        if p_row is None:pc+=1;loaded_line=None;continue
        if loaded_line is None:loaded_line=self.load_line(p_row)
        delay,cmd_l,loaded_args=loaded_line
        if time_acc<delay:break
        args=call_arguments(loaded_args)
        if cmd_l=='getheartpos' and state.supplied_target is None:
            request={'tick':tick,'line':pc+1,'variables':tuple(args[:2]),
                'sample_phase':'after_custom_movement_before_remaining_timeline',
                'preceding_teleport':tuple(self.heart_pos) if teleport_pulse else None,
                'source_command':'getheartpos','instruction_accounted':False}
            state.request=request
            return NeedTarget(_save(state,locals(),'await_target'),request)
        # Dialogue pauses Timeline under every termination policy, including
        # when a later EndAttack would clear the still-active hazards.
        if cmd_l=='sanstext' and not state.dialogue_coupled:
            request={'tick':tick,'line':pc+1,'text':self.variable_key(args[0]), 'instruction_accounted':False}
            state.request=request
            return NeedDialogue(_save(state,locals(),'await_dialogue'),request)
        loaded_line=None;time_acc-=delay;run_count+=1;state.stats['commands_executed']+=1
        source_events.append((tick,cmd_l,args))
        observer=getattr(state,'source_observer',None)
        if observer is not None:observer(tick,pc+1,cmd_l)
        if cmd_l=='sanstext' and state.dialogue_coupled:
            if state.dialogue is not None and state.dialogue.alive:
                raise ValueError('unsupported_mechanism: overlapping SansText instances')
            text=self.variable_key(args[0])
            # Timeline passes Array.At(2..10) to every Function call. A
            # missing callback cell is numeric 0, not the explicit empty
            # string that SansText recognizes as its default EndSansText.
            callback_value=args[1]
            callback='EndSansText' if callback_value=='' else self.variable_key(callback_value)
            state.dialogue=DialogueState(text,end_func=callback)
            running=False
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
                p.w,p.h,p.vx,p.vy,0.,1.,p.vy) for p in list(active_platforms)[:registered_counts[3]] if not p.born)
            for entities,count in zip((active_bones,active_stabs,active_blasters,active_platforms),registered_counts):
                _discard_registered_prefix(entities,count)
            registered_counts=[0,0,0,0]
        elif cmd_l in ("tlpause", "tlresume"):
            # Source Timeline control applies whether or not text is coupled.
            # A later resize callback cannot rerun this tick's Timeline phase.
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
            self.vars[self.variable_key(args[0])] = math.sin(float(self.eval_arg(args[1])) / (180.0 / math.pi))
        elif cmd_l == "cos":
            self.vars[self.variable_key(args[0])] = math.cos(float(self.eval_arg(args[1])) / (180.0 / math.pi))
        elif cmd_l == "deg":
            self.vars[self.variable_key(args[0])] = float(self.eval_arg(args[1])) * (180.0 / math.pi)
        elif cmd_l == "rad":
            self.vars[self.variable_key(args[0])] = float(self.eval_arg(args[1])) / (180.0 / math.pi)
        elif cmd_l == "angle":
            x1, y1 = float(self.eval_arg(args[1])), float(self.eval_arg(args[2]))
            x2, y2 = float(self.eval_arg(args[3])), float(self.eval_arg(args[4]))
            # Native Ka(Pa(...)) preserves signed degrees and multiplies
            # by 180/pi first; normalizing changes blaster entry timing.
            self.vars[self.variable_key(args[0])] = (180.0 / math.pi) * native_atan2(y2 - y1, x2 - x1)
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
            self.heart_pos=list(state.supplied_target)
            state.supplied_target=None
            target_history.append((tick,pc+1,*self.heart_pos))
            self.vars[self.variable_key(args[0])] = self.heart_pos[0]
            self.vars[self.variable_key(args[1])] = self.heart_pos[1]
        elif cmd_l == "sansslam":
            if native_parameter_in_range(args[0], 0., 3.):
                gravity_dir = native_int(native_parameter_number(args[0]))
                heart_mode = 1.0
                mode_pulse=1.
                self.vars["_last_slam_tick"] = tick
                self.vars["_last_slam_speed"] = max_fall_speed
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
            # Timeline passes TLCurrentLine.At(2..10): absent cells are
            # numeric zero; do not replace present empty strings or raw types.
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
            # Preserve loaded string/number types for native System.int.
            blaster_type=(_StreamingGasterBlaster if isinstance(active_bones,_BoneArrays) and not active_bones.native
                else _ActiveGasterBlaster)
            active_blasters.append(blaster_type(*args[:6], timer, blast_t))
        pc += 1
    # Timeline's trailing T += dt precedes the RPGText include. A callback
    # restoring Running here cannot retroactively advance T or execute CSV.
    timeline_running=running
    if state.dialogue_coupled and not _preview:
        confirm,cancel=state.dialogue_current_input
        if state.dialogue is not None and state.dialogue.alive:
            dialogue_step=step_dialogue(state.dialogue,dt_nominal,confirm=confirm,cancel=cancel,
                previous_confirm=state.dialogue_last_input[0],previous_cancel=state.dialogue_last_input[1])
            state.dialogue=dialogue_step.state
            if dialogue_step.callback:
                if dialogue_step.callback.lower() in ('endsanstext','tlresume'):
                    callback_events.append({'tick':tick,'executed_tick':tick,'phase':'rpgtext',
                        'function':dialogue_step.callback,'kind':'dialogue_destroyed'})
                    running=True
                elif audited_no_action_function(dialogue_step.callback):
                    callback_events.append({'tick':tick,'executed_tick':tick,'phase':'rpgtext',
                        'function':dialogue_step.callback,'kind':'dialogue_destroyed',
                        'no_action_audit':NO_ACTION_FUNCTION_AUDIT})
                else:
                    state.dialogue_blocked_callback=dialogue_step.callback
                    unproven_callbacks.append({'tick':tick,'function':dialogue_step.callback,
                        'phase':'rpgtext','status':'execution_unproven'})
                    # Its effects may change this same tick's later physics.
                    # Do not publish a committed frame assuming no effects.
                    return ResourceLimit(_save(state,locals(),'await_dialogue_callback'),
                        'unsupported_dialogue_callback:'+dialogue_step.callback)
    middle_cz=list(cz)

    if isinstance(active_bones,_BoneArrays):
        active_bones.advance(dt_nominal)
    else:
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
    if (isinstance(active_bones,_BoneArrays) and active_bones.native and
            not isinstance(active_platforms,_PlatformArrays) and len(active_platforms)>=64
            and not any(p.reverse for p in active_platforms)):
        active_platforms=_PlatformArrays(active_platforms)
    if isinstance(active_platforms,_PlatformArrays) and active_platforms.has_reverse:
        active_platforms=list(active_platforms)
    if isinstance(active_platforms,_PlatformArrays):active_platforms.advance(dt_nominal)
    else:
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
    if isinstance(active_blasters,_BlasterArrays):active_blasters.advance(dt_nominal)
    else:active_blasters = [gb for gb in active_blasters if gb.step(dt_nominal)]


    env=np.array([*cz,heart_mode,gravity_dir,1. if self.vars.get('_last_slam_tick')==tick else 0.,dt_nominal,
        max_fall_speed,teleport_pulse,*self.heart_pos,slam_damage,mode_pulse,*previous_cz,*middle_cz],dtype=float)
    if self.vars.get("_last_slam_tick")==tick and self.vars["_last_slam_speed"] != max_fall_speed:
        env[6]=self.vars["_last_slam_speed"]
        env[13]=mode_pulse+2.
    platforms=(active_platforms.geometry(removed_platforms) if isinstance(active_platforms,_PlatformArrays) else
        np.asarray([(p.x,p.y,p.w,p.h,p.vx,p.vy,1.,p.pre_active,p.pre_dy) for p in active_platforms]+removed_platforms,dtype=float).reshape(-1,9))
    if timeline_running:time_acc+=dt_nominal
    _resize_combat_zone(cz,cz_size,tgt_cz,cz_speed,dt_nominal);env[:4]=cz
    if not _preview:finish_resize('post_timeline_combatzonetick')
    if isinstance(active_bones,_BoneArrays):
        clip=None
        if (active_bones.proposal and len(active_bones)>=256 and
                min(env[0],env[14],env[18])>=-48. and max(env[2],env[16],env[20])<=688. and
                min(env[1],env[15],env[19])>=-48. and max(env[3],env[17],env[21])<=528.):
            clip=(-66.,-66.,706.,546.)
        white,blue=active_bones.geometry(clip)
        if clip is not None and len(white)+len(blue)<len(active_bones):
            white=np.concatenate((white,np.array([[-np.inf,-np.inf,-64.,np.inf],
                [704.,-np.inf,np.inf,np.inf],[-np.inf,-np.inf,np.inf,-64.],[-np.inf,544.,np.inf,np.inf]])))
        stabs=[box for stab in active_stabs if (box:=stab.bbox()) is not None]
        if stabs:white=np.concatenate((white,np.asarray(stabs,dtype=float)),axis=0)
    elif len(active_bones)>=64:
        # Pack dense geometry in arrays. Strict comparisons keep the original
        # first operand on ties, including signed zero and NaN semantics.
        raw=np.asarray([(b.x,b.y,b.w,b.h) for b in active_bones],dtype=float)
        first=raw[:,:2];second=first+raw[:,2:]
        boxes=np.concatenate((np.where(second<first,second,first),
            np.where(second>first,second,first)),axis=1)
        colors=np.fromiter((b.color==1 for b in active_bones),dtype=bool,count=len(active_bones))
        white=boxes[~colors];blue=boxes[colors]
        stabs=[box for stab in active_stabs if (box:=stab.bbox()) is not None]
        if stabs:white=np.concatenate((white,np.asarray(stabs,dtype=float)),axis=0)
    else:
        white=[];blue=[]
        for b in active_bones:
            box=(min(b.x,b.x+b.w),min(b.y,b.y+b.h),max(b.x,b.x+b.w),max(b.y,b.y+b.h))
            (blue if b.color==1 else white).append(box)
        for stab in active_stabs:
            box=stab.bbox()
            if box is not None:white.append(box)
    polygons=(active_blasters.polygons() if isinstance(active_blasters,_BlasterArrays) else
        [poly for gb in active_blasters if (poly:=gb.polygon()) is not None])
    frame=Frame(tick,env,platforms,np.asarray(white,dtype=float).reshape(-1,4),
        np.asarray(blue,dtype=float).reshape(-1,4),np.asarray(polygons,dtype=float).reshape(-1,8),
        tuple(source_events),tuple(target_history),tuple(callback_events))
    if state.dialogue_coupled and not _preview:
        frame.dialogue=state.dialogue;frame.dialogue_input=state.dialogue_current_input
        state.dialogue_last_input=state.dialogue_current_input;state.dialogue_current_input=None
    tick+=1;state.stats['ticks_committed']+=1
    if pc>=len(parsed_rows) and not ended:
        if eof_tick is None:eof_tick=tick-1
        if self.termination_policy=='eof_hazards_drained' and (not active_bones or (not active_platforms and stationary_blue_rows(active_bones) is not None)) and not active_stabs and not active_blasters and cz==tgt_cz and not (state.dialogue and state.dialogue.alive) and not state.dialogue_blocked_callback:
            ended=True;termination_reason='eof_hazards_drained'
    # A committed tick needs only these persistent fields. locals() also
    # synchronizes every temporary command/geometry variable in this large
    # interpreter; do not rebuild that unrelated dictionary for every frame.
    state.data=dict(tick=tick,pc=pc,loaded_line=loaded_line,time_acc=time_acc,
        running=running,ended=ended,termination_reason=termination_reason,eof_tick=eof_tick,
        cz=cz,cz_size=cz_size,tgt_cz=tgt_cz,cz_speed=cz_speed,heart_mode=heart_mode,
        gravity_dir=gravity_dir,max_fall_speed=max_fall_speed,slam_damage=slam_damage,
        active_bones=active_bones,active_platforms=active_platforms,active_stabs=active_stabs,
        active_blasters=active_blasters,end_resize=end_resize,unproven_callbacks=unproven_callbacks,
        last_dt=dt_nominal)
    state.phase='committed'
    return Terminal(state,frame,termination_reason) if ended else TickCommitted(state,frame)
