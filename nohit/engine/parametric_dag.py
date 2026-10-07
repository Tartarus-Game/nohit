"""Resumable demand-driven DAG reachability across player-observation events.

Each node contains the exact player state AND the bound environment history.
At GetHeartPos the ordinary source-derived movement phase supplies the target;
the environment operator then resumes the original timeline. Failed branches
remain available in their parent's action cursor. Only completely exhausted
states are memoized dead. This extends the same Bellman reachability recurrence
to a larger Markov state; it does not substitute a fixed guessed target route.
"""
from dataclasses import dataclass
from types import SimpleNamespace
import time
import hashlib
import numpy as np
from .parametric_environment import ParametricEnvironment
from .discrete_operator import initial_state,step_mask_into,step_action_into,sample_position
from .cspace import bake_cspace,bake_guidance,collision_query,guidance_query,bake_navigation,navigation_query
from .adaptive_dag import equivalent_controls,create_coast_hint,create_support_coast_hint,support_center_target
from .dp_pruning import make_vertical_cache,forced_vertical_collision,preferred_axis_jump
from .history_quotient import FutureHistoryKey
from .terminal_completion import complete_eof_tail
from .red_reachability_bounds import red_box_deadline
from .parametric_kernels import hold_kernel,option_scores,coast_counts,coast_survival,support_coast_survival


_coast_survival=coast_survival
_support_coast_survival=support_coast_survival
_EMPTY_GUIDE=np.empty((0,0,0,0),np.int16)
_EMPTY_NAVIGATION=np.empty((0,0,0),np.float32)


@dataclass(frozen=True,slots=True)
class _Path:
    mask: int
    parent: object


@dataclass(slots=True)
class _Node:
    tick: int
    state: np.ndarray
    binding: object
    mask: int
    options: list | None = None
    cursor: int = 0
    path: _Path | None = None
    has_solution: bool = False


class ParametricRouteIterator:
    """An iterator of complete route candidates with explicit budget status.

Continuing iteration after a candidate resumes sibling exploration. A caller
must not treat a partial binding, failed replay, or resource limit as UNSAT.
"""
    def __init__(self,path,initial,seed=42,initial_environment=None,clock_start_ms=None,
                 max_nodes=100000,max_expansions=100000,weights=None,allow_cancel=True,
                 lookahead_policy='navigation',lookahead=60,max_ticks=40000,termination_policy='endattack',
                 history_quotient=False,environment_state_quotient=False,environment_backend='resumable',
                 decision_ticks=4,red_box_pruning=True,closure_window=0,
                 closure_trigger=256,closure_max_states=50000,dt_schedule=None):
        if type(decision_ticks) is not int or decision_ticks not in (1,4):
            raise ValueError('decision_ticks must be 1 or 4')
        self.decision_ticks=decision_ticks
        if not isinstance(red_box_pruning,bool):raise ValueError('red_box_pruning must be boolean')
        self.red_box_pruning=red_box_pruning
        self.red_box_pruned=0
        if any(type(v) is not int or v<0 for v in (closure_window,closure_trigger,closure_max_states)):
            raise ValueError('closure limits must be nonnegative integers')
        self.closure_window=closure_window
        self.closure_trigger=max(1,closure_trigger)
        self.closure_max_states=closure_max_states
        self.closure_attempts=set()
        self.closure_stats={'attempts':0,'exhausted':0,'complete':0,'resource_limit':0,'unsupported':0,'expanded_states':0,'memoized_states':0}
        self._closure_last_progress=0
        self._closure_last_attempt=0
        if lookahead_policy not in ('navigation','coast','coast_support'):
            raise ValueError('invalid lookahead policy')
        if not 0<=lookahead<=240:
            raise ValueError('invalid lookahead')
        self.lookahead_policy=lookahead_policy
        self.lookahead_ticks=int(lookahead)*4
        self.started=time.perf_counter()
        self.template=ParametricEnvironment(path,seed,initial_environment,clock_start_ms,
                                            max_ticks=max_ticks,termination_policy=termination_policy,
                                            capture_state_keys=environment_state_quotient,backend=environment_backend,dt_schedule=dt_schedule)
        self.explicit_clock=dt_schedule is not None
        self.environment_state_quotient=bool(environment_state_quotient)
        self.future_history_key=FutureHistoryKey(self.template) if history_quotient else None
        binding=self.template.bind()
        self.environment_base_identity=binding.identity
        state=initial_state(initial,binding.wave.env_schedule[0])
        while binding.pending_target is not None and binding.pending_target['tick']==0:
            binding=self.template.extend(binding,state[0],state[1])
        self.stack=[_Node(0,state,binding,int(state[4]))]
        self.dead=set();self.bindings={};self.baked={}
        self.navigation={}
        # The four-tick control quotient depends only on the environment binding
        # and the control frame, never on the player state. Caching it per
        # (binding identity, frame) therefore preserves the exact representative
        # set and action order while removing a per-node Python rescan.
        self.representative_cache={}
        self.forecast_cache={}
        self._all_masks=np.arange(32,dtype=np.int64)
        self.axis_certificates={}
        self.max_nodes=int(max_nodes);self.max_expansions=int(max_expansions)
        self.nodes=1;self.expansions=0;self.furthest_tick=0
        self._best_path=None;self.best_state=state.copy()
        self.status='searching'
        self.model_termination_reason=None
        self.terminal_tail=None
        self.weights=np.array([1.,1.,1.,0.] if weights is None else weights,dtype=float)
        self._yielded=False
        self._initial_checked=False
        self.mask_count=32 if allow_cancel else 16

    def _clock_fields(self):
        if not self.explicit_clock:
            return dict(physics_hz=240,control_hz=240/self.decision_ticks,
                        clock_protocol='native_fixed_240' if self.template.clock_start_ms is not None else 'nominal_240')
        schedule=self.template.dt_schedule
        hz=1./schedule[0] if all(dt==schedule[0] for dt in schedule) else None
        packed=np.asarray(schedule,dtype='<f8').tobytes()
        return dict(physics_hz=hz,control_hz=None if hz is None else hz/self.decision_ticks,
                    clock_protocol='explicit_dt_schedule',dt_schedule_count=len(schedule),
                    dt_schedule_sha256=hashlib.sha256(packed).hexdigest(),
                    dt_sequence=list(schedule[:self.furthest_tick+1]))

    @property
    def best_prefix(self):
        # Keep only shared mask links during search. Copying the whole stack
        # at every new depth makes a successful L-frame route cost O(L**2).
        # The saved chain also survives backtracking from the deepest node.
        masks=[];path=self._best_path
        while path is not None:
            masks.append(path.mask);path=path.parent
        masks.reverse()
        return masks

    def _require_resolvable(self,binding):
        if not binding.complete and binding.pending_target is None:
            reason=binding.wave.termination_reason
            self.model_termination_reason=reason
            self.status='resource_limit' if reason in ('tick_budget','dt_schedule_exhausted') else 'model_incomplete'
            raise StopIteration

    def _environment(self,binding):
        key=binding.identity
        if key not in self.baked:
            # Only bake the interval this binding contributes. Prefix histories
            # are part of identity but are never resimulated by route expansion.
            first=int(binding.history[-1][0]) if binding.history else 0
            wave=binding.wave
            view=SimpleNamespace(env_schedule=wave.env_schedule[first:],
                geometry_white=wave.geometry_white[first:],geometry_blue=wave.geometry_blue[first:],
                geometry_polygons=wave.geometry_polygons[first:],origin=wave.origin,dimensions=wave.dimensions)
            baked=bake_cspace(view,cell_size=8.)
            self.baked[key]=(first,view,baked,
                bake_guidance(baked) if self.weights[0] or self.weights[1] else None)
        return self.baked[key]

    def _key(self,node):
        identity=node.binding.identity
        if identity not in self.bindings:self.bindings[identity]=len(self.bindings)
        future_identity=self.bindings[identity]
        if self.environment_state_quotient:
            keys=node.binding.wave.environment_state_keys
            history_size=32*len(node.binding.history)
            binding_base=identity[:-history_size] if history_size else identity
            # The underlying binding can contain prebound future observations
            # in nonproduction callers. Such a suffix is not determined by its
            # present VM state; retain its exact evidence identity instead.
            if (binding_base==self.environment_base_identity and
                    0<=node.tick<len(keys) and keys[node.tick] is not None and
                    all(row[0]<=node.tick for row in node.binding.history)):
                future_identity=('exact_environment_state',self.environment_base_identity,keys[node.tick])
        elif self.future_history_key is not None:
            history_size=32*len(node.binding.history)
            binding_base=identity[:-history_size] if history_size else identity
            if binding_base==self.environment_base_identity:
                future_identity=self.future_history_key(node.binding,node.tick)
        key_state=node.state.copy()
        request=node.binding.pending_target
        # The old input mask is read only for the first next-tick jump edge.
        # After that tick the selected mask replaces it. Preserve the full old
        # mask when an unresolved observation may alter that first event sheet.
        if request is None or request['tick']>node.tick+1:
            env=node.binding.wave.env_schedule
            t=min(node.tick+1,len(env)-1)
            latch=0 if env[t,4]==0. and env[t,6]==0. else (1,4,2,8)[int(env[t,5])]
            key_state[4]=int(key_state[4])&latch
        return node.tick,future_identity,key_state.tobytes()

    def _equivalent_controls(self,binding,frame):
        """The exact four-tick hold representatives for one (binding, frame).

        equivalent_controls reads only the environment rows the hold covers, so
        the result is independent of the player state. The returned list keeps the
        ascending-mask order the per-node scan produced.
        """
        key=(binding.identity,frame,self.mask_count)
        cached=self.representative_cache.get(key)
        if cached is not None:return cached
        env=binding.wave.env_schedule
        representatives=[]
        for mask in range(self.mask_count):
            if any(equivalent_controls(mask,other,env,frame) for other in representatives):
                continue
            representatives.append(mask)
        result=np.asarray(representatives,dtype=np.int64)
        self.representative_cache[key]=result
        return result

    def _options(self,node):
        start,view,baked,guide=self._environment(node.binding)
        env=node.binding.wave.env_schedule;state=node.state
        key=node.binding.identity
        if self.weights[1] and self.lookahead_ticks and key not in self.navigation:
            # _environment already baked this binding's clearance field. Handing it
            # to bake_navigation skips a second full distance-field sweep. The
            # argument is the identical array the default path would have rebuilt.
            self.navigation[key]=bake_navigation(baked,view.env_schedule,clearance=guide)
        navigation=self.navigation.get(key)
        axis_preference=-1
        if self.decision_ticks==4 and state[6]==1. and self.weights[1] and self.lookahead_ticks:
            wave=node.binding.wave
            if key not in self.axis_certificates:
                self.axis_certificates[key]=make_vertical_cache(wave.geometry_white,env,wave.platform_table)
            axis_preference=preferred_axis_jump(wave.geometry_white,env,wave.platform_table,
                node.tick//4,state,self.axis_certificates[key])
        jump_bit=(1,4,2,8)[int(state[7])]
        options=[]
        request=node.binding.pending_target
        # The existing control quotient explicitly proves a four-tick hold.
        # Microtick search enumerates every legal mask until separately proved.
        # Microtick search still enumerates the raw mask range in that case; only
        # the proven-quotient branch substitutes the cached representative set.
        known_controls=self.decision_ticks==4 and (request is None or request['tick']>node.tick+5)
        masks=(self._equivalent_controls(node.binding,node.tick//4) if known_controls
               else self._all_masks[:self.mask_count])
        if not np.any(self.weights):
            return sorted((int(mask) for mask in masks),
                key=lambda mask: 0 if mask==node.mask else 1 if mask==0 else mask+2)
        forecast_key=(key,node.tick,self.lookahead_ticks)
        forecasts=self.forecast_cache.get(forecast_key)
        if forecasts is None:
            ticks=[];durations=[]
            for ahead in (24,60,120,200):
                if ahead<=self.lookahead_ticks:
                    tick=min(node.tick+ahead,len(env)-1)
                    ticks.append(tick)
                    durations.append(float(np.sum(env[node.tick+1:tick+1,7])))
            forecasts=(np.asarray(ticks,dtype=np.int64),np.asarray(durations,dtype=np.float64))
            self.forecast_cache[forecast_key]=forecasts
        support=self.lookahead_policy=='coast_support'
        stop=node.tick
        survived=np.zeros(len(masks),np.int64)
        if self.weights[1] and self.lookahead_ticks and self.lookahead_policy in ('coast','coast_support'):
            stop=min(node.tick+self.lookahead_ticks,len(env)-1)
            if request is not None:stop=min(stop,request['tick']-1)
            if stop>node.tick:
                platforms=node.binding.wave.platform_table
                if (_coast_survival is coast_survival and _support_coast_survival is support_coast_survival):
                    survived=coast_counts(state,masks,node.tick-start,stop-start,
                        env[start:],platforms[start:],view.geometry_white,view.geometry_blue,
                        baked.payload,support and self.decision_ticks==4,self.mask_count)
                else:
                    # Preserve instrumentation hooks, including observation-boundary tests.
                    for i,mask in enumerate(masks):
                        survived[i]=_coast_survival(state,int(mask),node.tick-start,stop-start,
                            env[start:],platforms[start:],view.geometry_white,view.geometry_blue,baked.payload)
                        if support and self.decision_ticks==4:
                            survived[i]=max(survived[i],_support_coast_survival(state,int(mask),
                                node.tick-start,stop-start,env[start:stop+1],platforms[start:stop+1],
                                view.geometry_white,view.geometry_blue,baked.payload,self.mask_count))
        scores=option_scores(state,node.mask,masks,node.tick,self.decision_ticks,start,
            env,node.binding.wave.platform_table,guide if guide is not None else _EMPTY_GUIDE,
            navigation if navigation is not None else _EMPTY_NAVIGATION,*baked.origin,baked.cell_size,
            self.weights,self.lookahead_ticks,*forecasts,support,stop,survived,axis_preference,jump_bit)
        options=[(-float(score),0 if mask==node.mask else 1 if mask==0 else int(mask)+2,int(mask))
                 for score,mask in zip(scores,masks)]
        options.sort()
        return [item[2] for item in options]

    def _advance(self,node,mask):
        binding=node.binding;tick=node.tick
        ticks=self.decision_ticks
        request=binding.pending_target
        if (request is None or request['tick']>tick+ticks) and (binding.complete or tick+ticks<len(binding.wave.env_schedule)):
            start,view,baked,_=self._environment(binding)
            stop=min(tick+ticks,len(binding.wave.env_schedule)-1)
            collided,state=hold_kernel(view.geometry_white,view.geometry_blue,
                binding.wave.env_schedule,binding.wave.platform_table,node.state,mask,
                tick,stop,start,baked.payload)
            if collided:return None
            return _Node(stop,state,binding,mask)
        state=node.state.copy()
        for _ in range(ticks):
            if binding.complete and tick>=len(binding.wave.env_schedule)-1:break
            tick+=1
            request=binding.pending_target
            if request is not None and tick==request['tick']:
                wave=binding.wave
                x,y=sample_position(state,wave.env_schedule[tick],wave.platform_table[tick])
                binding=self.template.extend(binding,x,y)
                # Several observations may occur in one source tick.
                while binding.pending_target is not None and binding.pending_target['tick']==tick:
                    binding=self.template.extend(binding,x,y)
                self._require_resolvable(binding)
            wave=binding.wave
            if tick>=len(wave.env_schedule):
                raise RuntimeError('unresolved environment boundary was crossed')
            step_mask_into(state,mask,wave.env_schedule[tick],wave.platform_table[tick],state)
            start,view,baked,_=self._environment(binding)
            if collision_query(view.geometry_white,view.geometry_blue,tick-start,state,0.,baked.payload):
                return None
        return _Node(tick,state,binding,mask)

    def __iter__(self):return self

    def _try_local_closure(self):
        """Prove a finite suffix dead, reusing scoped Bellman false facts."""
        from .closure_search import try_known_dead_closure
        return try_known_dead_closure(self)

    def __next__(self):
        if self.stack:self._require_resolvable(self.stack[-1].binding)
        if not self._initial_checked:
            self._initial_checked=True
            node=self.stack[0];start,view,baked,_=self._environment(node.binding)
            if collision_query(view.geometry_white,view.geometry_blue,0,node.state,0.,baked.payload):
                self.stack.clear();self.status='exhausted_in_declared_model';raise StopIteration
        if self._yielded:
            # A returned witness proves this state is viable. Exhausting this
            # prefix's enumeration must never turn it into a Bellman dead end.
            self.stack.pop()
            self._yielded=False
        while self.stack:
            node=self.stack[-1]
            if node.tick>self.furthest_tick:
                self.furthest_tick=node.tick
                self._best_path=node.path
                self.best_state=node.state.copy()
                self._closure_last_progress=self.expansions
            if node.binding.complete and node.tick>=len(node.binding.wave.env_schedule)-1:
                self.terminal_tail=complete_eof_tail(node.binding.wave,node.state,
                    clock_start_ms=self.template.clock_start_ms,max_ticks=self.template.max_ticks,
                    last_mask=node.mask,decision_ticks=self.decision_ticks,
                    dt_schedule=self.template.dt_schedule if self.explicit_clock else None)
                if self.terminal_tail is not None and self.terminal_tail['status']!='proven':
                    # Failure of this sufficient certificate is unknown. Keep
                    # this leaf and every alternative; never memoize it false.
                    self.status='model_incomplete'
                    self.model_termination_reason='terminal_invariant_unproven'
                    raise StopIteration
                for ancestor in self.stack:
                    ancestor.has_solution=True
                self._yielded=True;self.status='candidate_found'
                return {'status':'candidate_found','planner':'parametric-demand-dag-dp',
                    'actions':[n.mask for n in self.stack[1:]],
                    'trajectory':[n.state.tolist() for n in self.stack],
                    'initial':self.stack[0].state.tolist(),'initial11':self.stack[0].state.tolist(),
                    'target_history':[list(row) for row in node.binding.history],
                    'terminal_tail':self.terminal_tail,
                    'expansions':self.expansions,'retained_states':self.nodes,
                    'environment_bindings':len(self.bindings),'frame':len(self.stack)-1,
                    'decision_ticks':self.decision_ticks,'control_ticks':self.decision_ticks,
                    **self._clock_fields(),
                    'four_tick_pruning_enabled':self.decision_ticks==4,
                    'red_box_pruning':self.red_box_pruning,'red_box_pruned':self.red_box_pruned,
                    'local_closure':dict(self.closure_stats),
                    'environment_backend':self.template.backend,'environment_work':dict(self.template.stats),
                    'lookahead_policy':self.lookahead_policy,'lookahead_microticks':self.lookahead_ticks,
                    'action_format':'keymask-lrud-cancel','weights_affect_safety':False,'no_beam_pruning':True,
                    'original_replay_passed':False,'complete_in_original_game':False,
                    'deadlock_proven':False,'optimality_proven':False,
                    'timing_ms':{'first_route_wall':(time.perf_counter()-self.started)*1000}}
            if self.expansions>=self.max_expansions or self.nodes>=self.max_nodes:
                self.status='resource_limit';raise StopIteration
            if self._try_local_closure():continue
            if node.options is None:
                if self.red_box_pruning and node.state[6]==0.:
                    wave=node.binding.wave
                    stop=min(node.tick+64,len(wave.env_schedule)-1)
                    request=node.binding.pending_target
                    if request is not None:stop=min(stop,request['tick']-1)
                    # The box contains every one-tick continuation, including
                    # every four-tick hold. Only hazard coverage proves death.
                    if red_box_deadline(wave.geometry_white,wave.env_schedule,
                            wave.platform_table,node.tick,node.state,stop):
                        self.dead.add(self._key(node));self.stack.pop()
                        self.red_box_pruned+=1
                        continue
                # This dead-end certificate searches only the four-tick
                # vertical control lattice; it cannot reject microtick paths.
                if self.decision_ticks==4 and node.state[6]==1.:
                    key=node.binding.identity;wave=node.binding.wave
                    if key not in self.axis_certificates:
                        self.axis_certificates[key]=make_vertical_cache(wave.geometry_white,wave.env_schedule,wave.platform_table)
                    if forced_vertical_collision(wave.geometry_white,wave.env_schedule,
                            wave.platform_table,node.tick//4,node.state,self.axis_certificates[key]):
                        self.dead.add(self._key(node));self.stack.pop();continue
                node.options=self._options(node);self.expansions+=1
            if node.cursor==len(node.options):
                if not node.has_solution:self.dead.add(self._key(node))
                self.stack.pop();continue
            mask=node.options[node.cursor];node.cursor+=1
            try:child=self._advance(node,mask)
            except StopIteration:
                # A compilation boundary is unknown, not a failed action.
                node.cursor-=1
                raise
            if child is None or self._key(child) in self.dead:continue
            child.path=_Path(mask,node.path)
            self.nodes+=1;self.stack.append(child)
        self.status='exhausted_in_declared_model'
        raise StopIteration


def solve_parametric(path,initial,**kwargs):
    search=ParametricRouteIterator(path,initial,**kwargs)
    try:return next(search)
    except StopIteration:
        return {'status':search.status,'planner':'parametric-demand-dag-dp','actions':[],
            'decision_ticks':search.decision_ticks,'control_ticks':search.decision_ticks,
            **search._clock_fields(),
            'four_tick_pruning_enabled':search.decision_ticks==4,
            'red_box_pruning':search.red_box_pruning,'red_box_pruned':search.red_box_pruned,
            'local_closure':dict(search.closure_stats),
            'environment_backend':search.template.backend,'environment_work':dict(search.template.stats),
            'lookahead_policy':search.lookahead_policy,'lookahead_microticks':search.lookahead_ticks,
            'expansions':search.expansions,'retained_states':search.nodes,
            'furthest_tick':search.furthest_tick,'deadlock_proven':False,
            'model_termination_reason':search.model_termination_reason,
            'terminal_tail':search.terminal_tail,
            'diagnostic_prefix_masks':search.best_prefix,'diagnostic_state':search.best_state.tolist(),
            'complete_in_original_game':False,
            'timing_ms':{'first_route_wall':(time.perf_counter()-search.started)*1000}}
