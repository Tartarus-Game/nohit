"""Immutable, exact-history bindings for player-targeted timeline environments.

This is the environment operator, not a route-search fallback. A binding may
end at an unresolved GetHeartPos boundary. A search must keep that environment
identity in its state key and resume each retained branch after supplying the
position at the specified native sampling phase. A prefix is never a win.
"""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import math
import struct
import numpy as np
from .compact_wave import compile_wave,native_fixed_dt,normalize_initial_arena,initial_arena_identity
from .compact_types import CompiledWave,GeometryArray
from .native_function_dispatch import call_arguments, audited_no_action_function, executable_resize_callback


@dataclass(frozen=True,slots=True)
class EnvironmentBinding:
    identity: bytes
    history: tuple  # ((tick, source_line, exact_x, exact_y), ...)
    wave: CompiledWave
    resume_state: object = None
    committed_frames: tuple = ()
    committed_state_keys: tuple = ()

    @property
    def pending_target(self):
        return self.wave.pending_target

    @property
    def complete(self):
        return self.wave.complete

    @property
    def resolved_through_tick(self):
        """No post-target transition at the boundary is validated yet."""
        if self.pending_target is not None:
            return self.pending_target['tick']-1
        return len(self.wave.env_schedule)-1


@dataclass(frozen=True,slots=True)
class ControlledEnvironmentBinding:
    """One opt-in input-dependent continuation; retains no regenerated prefix."""
    identity: bytes
    state: object
    parent: object
    frame: object = None
    status: str = 'ready'
    request: object = None
    input_code: int = 0
    reason: str | None = None


class ParametricEnvironment:
    def __init__(self,path,seed=42,initial_environment=None,clock_start_ms=None,termination_policy='endattack',max_ticks=40000,capture_state_keys=False,backend='resumable',dt_schedule=None,initial_arena=None):
        """Bind one source and clock protocol to exact target histories.

        An explicit dt schedule is copied into an immutable tuple and scopes
        all binding identities, including its unused future suffix. Exhausting
        this finite clock leaves an incomplete resource boundary; neither
        backend invents later ticks. Omitting it preserves the existing clock.
        """
        if termination_policy not in ('endattack','eof_hazards_drained'):
            raise ValueError('invalid termination_policy')
        if isinstance(max_ticks,bool) or not isinstance(max_ticks,int) or max_ticks<1:
            raise ValueError('max_ticks must be a positive integer resource budget')
        self.path=Path(path)
        self.seed=int(seed)&0xffffffff
        self.initial_environment=None if initial_environment is None else tuple(initial_environment)
        self.initial_arena=normalize_initial_arena(initial_arena)
        self.clock_start_ms=clock_start_ms
        self.termination_policy=termination_policy
        self.max_ticks=max_ticks
        self.capture_state_keys=bool(capture_state_keys)
        if backend not in ('reference','resumable'):raise ValueError('invalid environment backend')
        self.backend=backend
        self.stats={'executed_ticks':0,'committed_ticks':0,'preview_ticks':0,'commands_executed':0,'bindings_compiled':0}
        if dt_schedule is not None and clock_start_ms is not None:
            raise ValueError('supply either clock_start_ms or dt_schedule')
        if dt_schedule is not None:
            try:
                schedule=np.asarray(dt_schedule,dtype=np.float64)
            except (TypeError,ValueError,OverflowError) as exc:
                raise ValueError('dt_schedule must be a nonempty sequence of finite positive numbers') from exc
            if schedule.ndim!=1 or not len(schedule) or not np.isfinite(schedule).all() or np.any(schedule<=0.):
                raise ValueError('dt_schedule must be a nonempty sequence of finite positive numbers')
            self._dt_schedule=tuple(float(value) for value in schedule)
            # Hash every IEEE-754 word, not just the executed prefix. Keep the
            # clock in the base identity so history remains a 32-byte suffix
            # per observation, as required by bind() and history quotients.
            packed=np.asarray(self._dt_schedule,dtype='<f8').tobytes()
            self._clock_identity=b'S'+struct.pack('<Q',len(self._dt_schedule))+hashlib.sha256(packed).digest()
        else:
            self._dt_schedule=None if clock_start_ms is None else tuple(native_fixed_dt(clock_start_ms,max_ticks,
                initial_environment[7] if initial_environment is not None and len(initial_environment)>7 else None))
            self._clock_identity=b'N' if clock_start_ms is None else b'C'+struct.pack('<d',clock_start_ms)
        self.source_digest=hashlib.sha256(self.path.read_bytes()).digest()
        self._bindings={}
        self._controlled_bindings={}

    @property
    def dt_schedule(self):
        """The frozen clock used by all branches of this environment template."""
        return self._dt_schedule

    def begin_controlled(self,binding,*,previous_input_code):
        """Opt into full-world per-tick controls at a published source boundary.

        This does not alter bind()/extend() or the default search. The caller
        must supply the actual prior LRUD/Cancel/Confirm code; its Cancel bit
        must agree with the player's retained keymask. Each later step returns
        only its local Frame, whose physics/collision still need verification.
        """
        from .dialogue_operator import split_control
        split_control(previous_input_code)
        if self.backend!='resumable':raise ValueError('controlled continuation requires resumable backend')
        if self._bindings.get(binding.identity) is not binding:
            raise ValueError('binding belongs to another environment template')
        key=b'NOHIT-CONTROLLED\x01'+struct.pack('<Q',len(binding.identity))+binding.identity+struct.pack('<B',previous_input_code)
        if key in self._controlled_bindings:return self._controlled_bindings[key]
        result=ControlledEnvironmentBinding(key,binding.resume_state.clone(),binding,input_code=previous_input_code)
        self._controlled_bindings[key]=result
        return result

    def _store_controlled_result(self,key,parent,input_code,result):
        from .resumable_wave import TickCommitted,Terminal,NeedTarget,NeedDialogue,ResourceLimit
        if isinstance(result,Terminal):status='terminal';reason=result.reason
        elif isinstance(result,TickCommitted):status='ready';reason=None
        elif isinstance(result,NeedTarget):status='need_target';reason=None
        elif isinstance(result,NeedDialogue):status='need_input';reason=None
        elif isinstance(result,ResourceLimit):status='unknown';reason=result.reason
        else:raise RuntimeError('unexpected controlled environment result')
        binding=ControlledEnvironmentBinding(key,result.state,parent,getattr(result,'frame',None),
            status,getattr(result,'request',None),input_code,reason)
        self._controlled_bindings[key]=binding
        return binding

    def step_controlled(self,binding,input_code,*,allow_cancel=False):
        """Consume one complete tick, or suspend at its exact GetHeartPos phase.

        Confirm uses bit 5. Pass only input_code & 31 to the player operator.
        Cancel defaults illegal because MODE_SINGLE treats it as exit.
        The opt-in caller enumerates inputs; this method never chooses one.
        """
        from .dialogue_operator import split_control
        from .resumable_wave import advance_with_dialogue_input
        if self._controlled_bindings.get(binding.identity) is not binding:
            raise ValueError('controlled binding belongs to another environment template')
        _,confirm,cancel=split_control(input_code)
        if cancel and not allow_cancel:raise ValueError('Cancel is not legal in this input domain')
        if binding.status=='need_target':raise ValueError('supply pending target without changing this tick input')
        if binding.status in ('terminal','unknown'):raise ValueError('controlled continuation cannot advance '+binding.status)
        key=binding.identity+b'I'+struct.pack('<B',input_code)
        if key in self._controlled_bindings:return self._controlled_bindings[key]
        options={}
        if not binding.state.dialogue_coupled:
            _,old_confirm,old_cancel=split_control(binding.input_code)
            options=dict(previous_confirm=old_confirm,previous_cancel=old_cancel)
        result=advance_with_dialogue_input(binding.state,confirm=confirm,cancel=cancel,**options)
        return self._store_controlled_result(key,binding,input_code,result)

    def supply_controlled_target(self,binding,x,y):
        """Resume a target suspension with its already chosen current input."""
        from .dialogue_operator import split_control
        from .resumable_wave import supply_target,advance_with_dialogue_input
        if self._controlled_bindings.get(binding.identity) is not binding:
            raise ValueError('controlled binding belongs to another environment template')
        if binding.status!='need_target':raise ValueError('controlled continuation has no pending target')
        state=supply_target(binding.state,(x,y))
        x,y=state.supplied_target
        key=binding.identity+b'T'+struct.pack('<dd',x,y)
        if key in self._controlled_bindings:return self._controlled_bindings[key]
        _,confirm,cancel=split_control(binding.input_code)
        result=advance_with_dialogue_input(state,confirm=confirm,cancel=cancel)
        return self._store_controlled_result(key,binding,binding.input_code,result)

    def bind(self,history=()):
        history=tuple(tuple(row) for row in history)
        # Full bit-pattern identity: no spatial bins, no approximate equality,
        # and no folding different target histories into the same player state.
        key=self.source_digest+struct.pack('<I',self.seed)
        key+=self.termination_policy.encode('ascii')+struct.pack('<Q',self.max_ticks)
        key+=self._clock_identity
        environment=() if self.initial_environment is None else tuple(self.initial_environment)
        key+=struct.pack('<I',len(environment))
        for value in environment:
            key+=struct.pack('<d',float(value))
        key+=initial_arena_identity(self.initial_arena)
        for tick,line,x,y in history:
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError('target coordinates must be finite')
            key+=struct.pack('<qqdd',int(tick),int(line),float(x),float(y))
        if key in self._bindings:
            return self._bindings[key]
        if hashlib.sha256(self.path.read_bytes()).digest()!=self.source_digest:
            raise ValueError('source timeline changed while binding an environment')
        samples={(int(t),int(line)):(float(x),float(y)) for t,line,x,y in history}
        if len(samples)!=len(history):
            raise ValueError('target history repeats a source observation')
        if self.backend=='resumable':
            if history and key[:-32] not in self._bindings:
                # An explicit full history may arrive before any of its
                # parents. Materialize missing ancestors iteratively rather
                # than recursing once per observation in a long score.
                self.bind()
                base_size=len(key)-32*len(history)
                for count in range(1,len(history)):
                    if key[:base_size+32*count] not in self._bindings:
                        self.bind(history[:count])
            binding=self._bind_resumable(history,key)
            self._bindings[key]=binding
            return binding
        wave=compile_wave(self.path,seed=self.seed,initial_environment=self.initial_environment,
                          heart_samples=samples,allow_partial=True,dt_schedule=self.dt_schedule,
                          termination_policy=self.termination_policy,max_ticks=self.max_ticks,
                          capture_state_keys=self.capture_state_keys,initial_arena=self.initial_arena)
        if tuple(wave.target_history)!=history:
            raise ValueError('history does not match the source program')
        binding=EnvironmentBinding(key,history,wave)
        self.stats['executed_ticks']+=len(wave.env_schedule)
        preview_count=int(wave.termination_reason in ('pending_target','dialogue_boundary'))
        self.stats['preview_ticks']+=preview_count
        self.stats['committed_ticks']+=len(wave.env_schedule)-preview_count
        self.stats['commands_executed']+=len(wave.source_events)
        self.stats['bindings_compiled']+=1
        self._bindings[key]=binding
        return binding

    def _bind_resumable(self,history,key):
        from .resumable_wave import (initialize,_advance_owned_tick,supply_target,
            preview_observation_frame,
            TickCommitted,Terminal,NeedTarget,NeedDialogue,ResourceLimit)
        if self.capture_state_keys:
            from .resumable_wave import state_environment_key
        if history:
            parent=self.bind(history[:-1]);request=parent.pending_target
            if request is None or (request['tick'],request['line'])!=tuple(history[-1][:2]):
                raise ValueError('history does not match the source program')
            state=supply_target(parent.resume_state,history[-1][2:])
            if struct.pack('<dd',*state.supplied_target)!=struct.pack('<dd',*history[-1][2:]):
                raise ValueError('history contradicts preceding source teleport')
            frames=list(parent.committed_frames);keys=list(parent.committed_state_keys)
        else:
            state=initialize(self.path,seed=self.seed,initial_environment=self.initial_environment,
                termination_policy=self.termination_policy,dt_schedule=self.dt_schedule,max_ticks=self.max_ticks,
                initial_arena=self.initial_arena)
            frames=[];keys=[]
        started_commands=state.stats['commands_executed']
        # initialize returns a fresh state; supply_target clones a published
        # parent. Only this loop owns the continuation until the binding is
        # published below, so tick-to-tick deepcopy is unnecessary.
        while True:
            result=_advance_owned_tick(state);state=result.state
            if isinstance(result,(TickCommitted,Terminal)):
                if result.frame is not None:
                    frames.append(result.frame)
                    self.stats['committed_ticks']+=1;self.stats['executed_ticks']+=1
                    if self.capture_state_keys:keys.append(state_environment_key(state))
                if isinstance(result,Terminal):break
                continue
            if isinstance(result,(NeedTarget,NeedDialogue,ResourceLimit)):break
            raise RuntimeError('unexpected environment continuation')
        self.stats['commands_executed']+=state.stats['commands_executed']-started_commands
        self.stats['bindings_compiled']+=1
        committed=tuple(frames);committed_keys=tuple(keys)
        pending=None;dialogue=None
        if isinstance(result,(NeedTarget,NeedDialogue)):
            preview=preview_observation_frame(result.state)
            frames.append(preview)
            self.stats['preview_ticks']+=1;self.stats['executed_ticks']+=1
            if self.capture_state_keys:keys.append(None)
            if isinstance(result,NeedTarget):
                pending={k:v for k,v in result.request.items() if k!='instruction_accounted'}
                reason='pending_target'
            else:dialogue=result.request;reason='dialogue_boundary'
        else:reason=result.reason if isinstance(result,Terminal) else 'tick_budget'
        wave=self._materialize(frames,state,history,pending,dialogue,reason,tuple(keys),isinstance(result,Terminal))
        return EnvironmentBinding(key,history,wave,state,committed,committed_keys)

    def _materialize(self,frames,state,history,pending,dialogue,reason,keys,complete):
        """Compatibility collector; reuses executed frames, never reexecutes a prefix."""
        n=len(frames)
        if not n:raise RuntimeError('environment boundary has no initial frame')
        env=np.asarray([frame.env for frame in frames],dtype=np.float64)
        platform=np.zeros((n,max(4,max(len(f.platforms) for f in frames)),9),np.float64)
        white=np.full((n,max(len(f.white) for f in frames),4),np.nan,np.float64)
        blue=np.full((n,max(len(f.blue) for f in frames),4),np.nan,np.float64)
        geometry=np.full((n,max(len(f.white)+len(f.blue) for f in frames),4),np.nan,np.float64)
        polygons=np.full((n,max(len(f.polygons) for f in frames),8),np.nan,np.float64)
        counts=np.zeros(n,np.int32)
        for t,f in enumerate(frames):
            platform[t,:len(f.platforms)]=f.platforms
            counts[t]=int(np.count_nonzero(f.platforms[:,6]))
            white[t,:len(f.white)]=f.white;blue[t,:len(f.blue)]=f.blue
            geometry[t,:len(f.white)]=f.white
            geometry[t,len(f.white):len(f.white)+len(f.blue)]=f.blue
            polygons[t,:len(f.polygons)]=f.polygons
        events=[event for f in frames for event in f.events]
        if pending is not None or dialogue is not None:
            _,cmd,args=state.data['loaded_line']
            events.append((state.data['tick'],cmd,call_arguments(args)))
        left,top=math.floor(float(env[:,0].min())),math.floor(float(env[:,1].min()))
        right,bottom=math.ceil(float(env[:,2].max())),math.ceil(float(env[:,3].max()))
        wrapped=GeometryArray(geometry,geometry_white=white,geometry_blue=blue,
                              origin_x=left,origin_y=top,width=right-left,height=bottom-top)
        schedule=np.empty((n,7),np.float64);schedule[:,:6]=platform[:,0,:6];schedule[:,6]=env[:,7]
        d=state.data;end_resize=d['end_resize']
        callbacks=d['unproven_callbacks']+([dict(end_resize,status='awaiting_arena_settle')]
            if end_resize is not None and executable_resize_callback(end_resize['function']) else [])
        details={name:len(d[name]) for name in ('active_bones','active_platforms','active_stabs','active_blasters')}
        details.update(arena_settled=d['cz']==d['tgt_cz'],player_invariant_proven=False,
            pending_dialogue=dialogue,timeline_exhausted=d['pc']>=len(state.program.parsed) and
                d['loaded_line'] is None and pending is None and dialogue is None,
            pending_callbacks=callbacks,end_resize=end_resize,
            executed_callbacks=[event for f in frames for event in f.callback_events],
            initial_callback_contract=('explicit_initial_arena' if self.initial_arena is not None
                else 'assumed_none_not_encoded_in_initial_environment'))
        return CompiledWave(schedule,wrapped,np.array([*env[0,10:12],0.,0.,0.]),env,platform,counts,
            white,blue,(left,top),(bottom-top,right-left),self.path.stem,math.ceil(n/4),env[:,7],
            geometry_polygons=polygons,source_events=tuple(events),player_dependent=bool(history),
            pending_target=pending,complete=complete,target_history=history,termination_reason=reason,
            eof_tick=d['eof_tick'],terminal_details=details,environment_state_keys=keys)

    def extend(self,binding,x,y):
        if self._bindings.get(binding.identity) is not binding:
            raise ValueError('binding belongs to another environment template')
        request=binding.pending_target
        if request is None:
            raise ValueError('environment has no pending target: '+str(binding.wave.termination_reason))
        if request['preceding_teleport'] is not None:
            # GetHeartPos sees earlier timeline teleports before caller-supplied
            # custom-movement coordinates. Preserve the source event ordering.
            x,y=request['preceding_teleport']
        return self.bind(binding.history+((request['tick'],request['line'],float(x),float(y)),))
