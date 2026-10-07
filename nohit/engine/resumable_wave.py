"""Resumable pure source environment operator; no prefix replay or native search.

Equation bodies are kept independent of TimelineVM.run for differential tests.
Only entity classes, argument coercion and arena arithmetic are shared.
"""
from dataclasses import dataclass
from pathlib import Path
import copy,math,struct
import numpy as np
from .compact_wave import (TimelineVM,_ActiveBone,_ActivePlatform,_ActiveBoneStab,
    _ActiveGasterBlaster,_resize_combat_zone,_initial_arena_state,initial_arena_identity,
    _bone_from_command,_platform_from_command,_repeat_command_children)
from .native_numbers import native_int, native_parameter_in_range, native_for_count_indices
from .dialogue_operator import DialogueState,step_dialogue
from .timeline_csv import parse_timeline_rows
from .native_function_dispatch import call_arguments, audited_no_action_function, NO_ACTION_FUNCTION_AUDIT

# Full static bytes, not a digest accepted without a collision check. A branch
# shares its Program object, so this is not copied into each tick's live state.
_SEMANTIC_SOURCE=tuple(Path(__file__).with_name(name).read_bytes() for name in
    ('resumable_wave.py','compact_wave.py','dialogue_operator.py','timeline_csv.py','native_function_dispatch.py'))

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
    if prior.phase!='await_target' or prior.request is None:raise ValueError('state is not awaiting a target')
    if len(position)!=2 or not all(math.isfinite(x) for x in position):raise ValueError('target must have two finite coordinates')
    state=prior.clone()
    state.supplied_target=tuple(state.request['preceding_teleport'] or position)
    state.phase='timeline';state.request=None
    return state

_PERSISTENT = ('tick', 'pc', 'loaded_line', 'time_acc', 'running', 'ended', 'termination_reason', 'eof_tick', 'cz', 'cz_size', 'tgt_cz', 'cz_speed', 'heart_mode', 'gravity_dir', 'max_fall_speed', 'slam_damage', 'active_bones', 'active_platforms', 'active_stabs', 'active_blasters', 'end_resize', 'unproven_callbacks')
_IN_FLIGHT = ('dt_nominal', 'previous_cz', 'teleport_pulse', 'mode_pulse', 'removed_platforms', 'run_count', 'source_events', 'target_history', 'callback_events')
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
    if any(value not in (0,1) for value in (confirm,cancel)):
        raise ValueError('Confirm and Cancel must be zero or one')
    state=prior.clone()
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
                p.w,p.h,p.vx,p.vy,0.,1.,p.vy) for p in active_platforms if not p.born)
            active_bones.clear();active_stabs.clear();active_blasters.clear();active_platforms.clear()
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
            self.heart_pos=list(state.supplied_target)
            state.supplied_target=None
            target_history.append((tick,pc+1,*self.heart_pos))
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
            active_blasters.append(_ActiveGasterBlaster(*args[:6], timer, blast_t))
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


    env=np.array([*cz,heart_mode,gravity_dir,1. if self.vars.get('_last_slam_tick')==tick else 0.,dt_nominal,
        max_fall_speed,teleport_pulse,*self.heart_pos,slam_damage,mode_pulse,*previous_cz,*middle_cz],dtype=float)
    platforms=np.asarray([(p.x,p.y,p.w,p.h,p.vx,p.vy,1.,p.pre_active,p.pre_dy) for p in active_platforms]+removed_platforms,dtype=float).reshape(-1,9)
    white=[];blue=[]
    for b in active_bones:
        box=(min(b.x,b.x+b.w),min(b.y,b.y+b.h),max(b.x,b.x+b.w),max(b.y,b.y+b.h))
        (blue if b.color==1 else white).append(box)
    for stab in active_stabs:
        box=stab.bbox()
        if box is not None:white.append(box)
    polygons=[poly for gb in active_blasters if (poly:=gb.polygon()) is not None]
    if timeline_running:time_acc+=dt_nominal
    _resize_combat_zone(cz,cz_size,tgt_cz,cz_speed,dt_nominal);env[:4]=cz
    if not _preview:finish_resize('post_timeline_combatzonetick')
    frame=Frame(tick,env,platforms,np.asarray(white,dtype=float).reshape(-1,4),
        np.asarray(blue,dtype=float).reshape(-1,4),np.asarray(polygons,dtype=float).reshape(-1,8),
        tuple(source_events),tuple(target_history),tuple(callback_events))
    if state.dialogue_coupled and not _preview:
        frame.dialogue=state.dialogue;frame.dialogue_input=state.dialogue_current_input
        state.dialogue_last_input=state.dialogue_current_input;state.dialogue_current_input=None
    tick+=1;state.stats['ticks_committed']+=1
    if pc>=len(parsed_rows) and not ended:
        if eof_tick is None:eof_tick=tick-1
        if self.termination_policy=='eof_hazards_drained' and not active_bones and not active_stabs and not active_blasters and cz==tgt_cz and not (state.dialogue and state.dialogue.alive) and not state.dialogue_blocked_callback:
            ended=True;termination_reason='eof_hazards_drained'
    _save(state,locals(),'committed')
    return Terminal(state,frame,termination_reason) if ended else TickCommitted(state,frame)
