"""Fresh candidate generation with explicit, checked model scope."""
import hashlib
import math
import time
from pathlib import Path
import numpy as np
from .compact_wave import compile_wave
from .csv_completion import AUDITED_NO_ACTION_COMMANDS, AUDITED_VITALITY_COMMANDS
from .discrete_operator import step_action_into, initial_state
from .cspace import bake_cspace, collision_query, bake_guidance, guidance_query,bake_navigation,navigation_query
from .adaptive_dag import create_demand_kernel
from .dp_pruning import forced_vertical_collision,make_vertical_cache
from .parametric_dag import solve_parametric
from .terminal_completion import complete_eof_tail
from .timeline_csv import read_timeline_rows

search = create_demand_kernel(step_action_into, collision_query, control_masks=True, project_input_latch=True, guidance_query=guidance_query, dead_end_query=forced_vertical_collision,dead_cache_factory=make_vertical_cache,navigation_query=navigation_query)

STATIC_COMMANDS={'combatzoneresize','heartteleport','heartmode','tlpause','endattack','bonev','boneh','bonevrepeat','bonehrepeat'}
PURE_COMMANDS={'set','add','sub','mul','rnd','jmpe','jmpne','jmpnl','jmprel','jmpabs'}
STATIC_COMMANDS |= {'combatzoneresizeinstant','combatzonespeed','heartmaxfallspeed',
    'sansslamdamage','sansslam','platform','platformrepeat','bonestab','sinebones','gasterblaster','tlresume','blackscreen'}
PURE_COMMANDS |= {'div','mod','floor','sin','cos','deg','rad','angle','jmpz','jmpnz','jmpl','jmpg','jmpng'}
COSMETIC_COMMANDS={'sansanimation','sanshead','sansbody','sanstext','sound','music','sanslegs','sansface','wait'}
COSMETIC_COMMANDS |= {'sanssweat','sansrepeat','sansendrepeat','sanstorso','sansx'}
ARITY={'combatzoneresize':4,'heartteleport':2,'heartmode':1,'bonev':5,'boneh':5,
       'bonevrepeat':7,'bonehrepeat':7,'set':2,'add':3,'sub':3,'mul':3,'rnd':2,
       'jmpe':3,'jmpne':3,'jmpnl':3,'jmprel':1,'jmpabs':1}
ARITY.update(combatzoneresizeinstant=4,combatzonespeed=1,heartmaxfallspeed=1,
    sansslamdamage=1,sansslam=1,platform=5,platformrepeat=7,bonestab=4,sinebones=4,gasterblaster=8,blackscreen=1)
REQUIRED_TEXT_ARGUMENTS={command:(0,) for command in (
    'set','add','sub','mul','div','mod','floor','sin','cos','deg','rad','angle','rnd')}
# GetHeartPos destinations may be absent (native numeric 0 -> key "0") or
# explicit empty strings (key ""). The shared nine-slot dispatcher preserves
# that distinction; target-history admission below remains independently gated.
DEFAULT_WEIGHTS={'clearance':1.,'lookahead':1.,'center':1.,'switches':0.}


def ranking_weights(weights=None):
    """Validate style preferences independently of the safety predicate."""
    if weights is None:
        return dict(DEFAULT_WEIGHTS)
    if not isinstance(weights,dict) or weights.keys()-DEFAULT_WEIGHTS.keys():
        raise ValueError('weights must map clearance, lookahead, center, switches to numbers')
    out=dict(DEFAULT_WEIGHTS)
    for key,value in weights.items():
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=1000:
            raise ValueError('weights must be finite numbers between 0 and 1000')
        out[key]=float(value)
    return out


def warm_kernel():
    """Load/JIT code before serving gameplay. Contains no level or route data."""
    started=time.perf_counter()
    env=np.tile(np.array([0.,0.,100.,100.,1.,1.,0.,1/240,750.,0.,0.,0.,0.,0.,0.,0.,100.,100.,0.,0.,100.,100.]),(2,1))
    geometry=np.empty((2,0,4),np.float64)
    platforms=np.empty((2,0,7),np.float64)
    initial=initial_state(np.array([50.,50.,0.,0.,0.]),env[0])
    payload=(np.zeros((2,2,26,26),np.uint8),np.empty((2,0,8),np.float64),0.,0.,4.)
    search(geometry,geometry,env,platforms,initial,2,1,0.,0,4096,np.array(list(DEFAULT_WEIGHTS.values())),payload,np.zeros((2,2,26,26),np.int16),np.zeros((1,2),np.int8),(np.zeros((2,26,26),np.float32),8),32,0,0.,False,-1)
    # Reconstruction calls the public dispatchers outside the inlined search
    # kernel. Warm those signatures too so the first route does not incur a
    # separate several-second transition compilation after search finishes.
    step_action_into(initial,np.int8(0),0,env[0],platforms[0],initial.copy())
    collision_query(geometry,geometry,0,initial,0.,payload)
    return (time.perf_counter()-started)*1000


def model_issues(path, allow_player_history=False,termination_policy='endattack'):
    if termination_policy not in ('endattack','eof_hazards_drained'):
        raise ValueError('invalid termination policy')
    rows=read_timeline_rows(path)
    issues=[]
    elapsed=0.
    preparation_finished=False
    has_end=False
    for number,row in enumerate(rows,1):
        if len(row)<2: continue
        cmd=row[1].strip().lower()
        if not cmd: continue
        if cmd not in STATIC_COMMANDS|PURE_COMMANDS|COSMETIC_COMMANDS and not cmd.startswith(':') and not (cmd=='getheartpos' and allow_player_history):
            issues.append({'line':number,'command':row[1],'reason':
                'environment_depends_on_player_history' if cmd=='getheartpos' else 'mechanism_not_validated'})
        try:
            delay=float(row[0] or 0)
            if not math.isfinite(delay) or delay<0: raise ValueError()
            elapsed+=delay
        except ValueError:
            if not row[0].strip().startswith('$'):
                issues.append({'line':number,'reason':'invalid_or_dynamic_timeline'})
        args=[x.strip() for x in row[2:]]
        # Construct's CSV/function numeric conversion maps absent/empty cells
        # to zero. Keep the current arithmetic-destination admission restriction;
        # GetHeartPos accepts native default/empty keys through shared dispatch.
        if any(index>=len(args) or not args[index] for index in REQUIRED_TEXT_ARGUMENTS.get(cmd,())):
            issues.append({'line':number,'reason':'missing_arguments'})
        for arg in args:
            try:
                if not math.isfinite(float(arg)):
                    issues.append({'line':number,'reason':'nonfinite_argument'})
            except ValueError: pass # variable references and labels are interpreted by TimelineVM
        if cmd=='heartmode':
            try:
                mode=int(float(args[0] or '0')) if args else 0
                if mode not in (0,1):raise ValueError()
            except (ValueError,OverflowError):
                issues.append({'line':number,'reason':'unvalidated_heart_mode'})
        if cmd=='tlpause':
            if preparation_finished: issues.append({'line':number,'reason':'mid_attack_pause'})
            preparation_finished=True
        has_end |= cmd=='endattack'
    if not has_end and termination_policy=='endattack': issues.append({'reason':'missing_endattack'})
    return issues


def solve_attack(path, initial=None, seed=42, max_nodes=500000, max_expansions=5000000, margin=4., lookahead=60, weights=None, initial_environment=None, heart_samples=None, clock_start_ms=None,allow_cancel=True,lookahead_policy='navigation',max_ticks=40000,termination_policy='endattack',environment_state_quotient=False,decision_ticks=4,dt_schedule=None):
    started=time.perf_counter()
    path=Path(path)
    weights=ranking_weights(weights)
    if isinstance(decision_ticks,bool) or not isinstance(decision_ticks,int) or decision_ticks not in (1,4):
        raise ValueError('decision_ticks must be 1 or 4')
    if not isinstance(allow_cancel,bool):raise ValueError('allow_cancel must be boolean')
    if not isinstance(environment_state_quotient,bool):raise ValueError('environment_state_quotient must be boolean')
    if lookahead_policy not in ('navigation','coast','coast_support'):raise ValueError('invalid lookahead policy')
    result={'wave':path.name,'seed':seed,'planner':'canonical-dag-dp',
        'original_replay_passed':False,'realtime_passed_three':False,'deadlock_proven':False,
        'route_cache_hit':False,'environment_cache_hit':False,'actions':[],
        'complete_in_original_game':False,'route_optimality':None,
        'objective':'no_hit_with_style_preferences',
        'ranking_weights':weights,'weights_affect_safety':False,
        'execution_stability_proven':False,'execution_probability':None,
        'kernel_sha256':hashlib.sha256(b''.join(Path(__file__).with_name(f).read_bytes()
            for f in ('discrete_operator.py','adaptive_dag.py','cspace.py','compact_wave.py','resumable_wave.py','dp_pruning.py','parametric_dag.py','parametric_environment.py','history_quotient.py','environment_state_key.py','terminal_invariant.py','terminal_completion.py','red_reachability_bounds.py','local_relation.py','parametric_kernels.py','dead_window.py','closure_search.py','parallel_expansion.py','exact_state_dedup.py','control_quotient.py','execution_schedule.py','timeline_csv.py'))).hexdigest(),
        'csv_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    result['termination_policy']=termination_policy
    audits=AUDITED_NO_ACTION_COMMANDS|AUDITED_VITALITY_COMMANDS
    issues=[issue for issue in model_issues(path, allow_player_history=True,termination_policy=termination_policy)
            if not (issue.get('reason')=='mechanism_not_validated' and
                    issue.get('command','').strip().lower() in audits)]
    if issues:
        return dict(result,status='unsupported_mechanism',issues=issues)
    if initial is None:
        return dict(result,status='initial_state_required',issues=[{'reason':'capture_actual_attack_start_after_preparation'}])
    initial=np.asarray(initial,dtype=np.float64)
    if initial.shape not in ((5,),(11,)) or not np.isfinite(initial).all():
        raise ValueError('initial must contain 5 legacy or 11 full finite state values')
    if initial.shape==(5,) and initial[4] not in (-1,0,1):
        raise ValueError('legacy previous vertical input must be -1, 0, or 1')
    if max_nodes<1 or max_expansions<1 or not 0<=lookahead<=240 or margin<0 or not np.isfinite(margin):
        raise ValueError('invalid search limits or collision margin')
    margin=float(margin)
    player_targeted=any(len(row)>1 and row[1].strip().lower()=='getheartpos'
        for row in read_timeline_rows(path))
    if player_targeted or decision_ticks==1 or dt_schedule is not None:
        dynamic=solve_parametric(path,initial,seed=seed,initial_environment=initial_environment,
            clock_start_ms=clock_start_ms,max_nodes=max_nodes,max_expansions=max_expansions,
            weights=np.array(list(weights.values()),dtype=np.float64),allow_cancel=allow_cancel,
            lookahead_policy=lookahead_policy,lookahead=lookahead,max_ticks=max_ticks,
            termination_policy=termination_policy,environment_state_quotient=environment_state_quotient,
            decision_ticks=decision_ticks,dt_schedule=dt_schedule)
        result.update(dynamic)
        result.update(planner='canonical-dag-dp',environment_solver=dynamic.get('planner'),
            search_order='demand_driven_boolean_bellman_with_environment_history',
            environment_state_quotient=environment_state_quotient,
            dp_evaluation='top_down_short_circuit',control_ticks=decision_ticks,
            control_hz=dynamic.get('control_hz',240//decision_ticks),physics_hz=dynamic.get('physics_hz',240),
            complete_original_input_timing=False,clock_start_ms=clock_start_ms,
            lookahead_policy=lookahead_policy,lookahead=lookahead,
            control_alphabet_size=32 if allow_cancel else 16,allow_cancel=allow_cancel,model_scope='full player state plus exact player-dependent environment history',
            search_limited=result['status']=='resource_limit')
        return result
    try:
        compile_options=dict(seed=seed,initial_environment=initial_environment,heart_samples=heart_samples,
                             max_ticks=max_ticks,termination_policy=termination_policy)
        if clock_start_ms is not None:compile_options['clock_start_ms']=clock_start_ms
        wave=compile_wave(path,**compile_options)
    except (ValueError,IndexError,OverflowError) as error:
        return dict(result,status='model_compile_failed',issues=[{'reason':str(error)}])
    if not wave.complete:
        reason=wave.termination_reason
        return dict(result,status='resource_limit' if reason=='tick_budget' else 'model_incomplete',
                    model_termination_reason=reason,search_limited=reason=='tick_budget',
                    issues=[{'reason':reason}])
    env=wave.env_schedule
    initial=initial_state(initial,env[0])
    csv_compiled=time.perf_counter()
    space=bake_cspace(wave)
    needs_navigation=weights['lookahead']>0. and lookahead>0 and lookahead_policy=='navigation'
    guidance=bake_guidance(space) if weights['clearance']>0. or needs_navigation else np.zeros((1,2,1,1),np.int16)
    navigation=(bake_navigation(space,env,stride=8,clearance=guidance),8) if needs_navigation else (np.zeros((1,1,1),np.float32),8)
    compiled=time.perf_counter()
    signature_count=len(search.signatures)
    progress=np.zeros(((len(env)-1+3)//4,2),np.int8)
    status,frame,expansions,visits,actions=search(wave.geometry_white,wave.geometry_blue,env,wave.platform_table,
        initial,max_nodes,max_expansions,margin,lookahead,4096,np.array(list(weights.values()),dtype=np.float64),space.payload,guidance,progress,navigation,32 if allow_cancel else 16,lookahead*4 if lookahead_policy in ('coast','coast_support') else 0,0.,lookahead_policy=='coast_support',-1)
    searched=time.perf_counter()
    already_loaded=len(search.signatures)==signature_count
    trace=[initial.tolist()]
    state=initial.copy()
    preferred_margin_satisfied=not collision_query(wave.geometry_white,wave.geometry_blue,0,state,margin,space.payload)
    for f,(mask,unused) in enumerate(actions):
        for micro in range(1,5):
            tick=f*4+micro
            if tick<len(env):
                step_action_into(state,mask,0,env[tick],wave.platform_table[tick],state)
                preferred_margin_satisfied &= not collision_query(wave.geometry_white,wave.geometry_blue,tick,state,margin,space.payload)
        trace.append(state.tolist())
    # Margin ranks paths only; even narrow safe states remain in the graph.
    result.update(status=['candidate_found','exhausted_in_declared_model','resource_limit'][status],
        actions=actions[:,0].tolist(),action_format='keymask-lrud-cancel',trajectory=trace,initial=initial.tolist(),frame=int(frame),
        expansions=int(expansions),peak_states=int(visits.max()),retained_states=int(visits.sum()),margin=margin,
        max_nodes=max_nodes,lookahead=lookahead,exact_state_folding=True,complete_search_configuration=True,
        state_quotient='bit_exact_physics_plus_next_jump_latch_bisimulation',
        no_beam_pruning=True,deferred_states_discarded=0,optimality_proven=False,
        margin_is_pruning=False,preferred_margin_satisfied=bool(preferred_margin_satisfied) if status==0 else None,
        search_order='demand_driven_boolean_bellman_recurrence',dp_evaluation='top_down_short_circuit',kernel_already_loaded=already_loaded,
        cspace='continuous_exact_with_tristate_cell_acceleration',control_alphabet_size=32 if allow_cancel else 16,allow_cancel=allow_cancel,
        control_ticks=4,control_hz=60,physics_hz=240,complete_original_input_timing=False,
        clock_start_ms=clock_start_ms,
        lookahead_policy=lookahead_policy,
        model_scope='source-derived full player state; baked scripted geometry/events; context-legal physical key masks; four microsteps per control',
        search_limited=status==2,
        timing_ms={'csv_compile':(csv_compiled-started)*1000,'cspace_bake':(compiled-csv_compiled)*1000,'search_including_load':(searched-compiled)*1000,
                   'hot_search':(searched-compiled)*1000 if already_loaded else None,
                   'reconstruction':(time.perf_counter()-searched)*1000,
                   'first_route_wall':(time.perf_counter()-started)*1000})
    if status==2:
        result['diagnostic_prefix_masks']=progress[:frame,0].tolist()
    if status==0:
        tail=complete_eof_tail(wave,state,clock_start_ms=clock_start_ms,max_ticks=max_ticks,
                               last_mask=int(actions[-1,0]) if len(actions) else int(initial[4]))
        result['terminal_tail']=tail
        if tail is not None and tail['status']!='proven':
            result.update(status='model_incomplete',model_termination_reason='terminal_invariant_unproven',
                          diagnostic_prefix_masks=result['actions'],actions=[])
        result['timing_ms']['first_route_wall']=(time.perf_counter()-started)*1000
    return result
