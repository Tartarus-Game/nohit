"""Corrupt a real saved native trace to exercise independent rejection paths.

Fixture: automatic CSV smoke captured on 2026-10-07, five inputs including a
real Confirm edge, observer postticks 4..9 and native EndAttack trigger tick 8.
The original capture is scratch/automatic-csv-native-20261007/smoke.json.
"""
import copy
import json
import math
from pathlib import Path

import pytest

from tools.verify_csv_native_acceptance import EOF_SOURCE_HASHES, derive_menu_velocity, verify_record

FIXTURE = Path(__file__).parents[1] / 'fixtures/native_csv_automatic_smoke.json'
BLUE_FIXTURE = Path(__file__).parents[1] / 'fixtures/native_csv_bonestab3_60.json'


@pytest.fixture
def evidence():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


@pytest.fixture
def blue_evidence():
    return json.loads(BLUE_FIXTURE.read_text(encoding='utf-8'))


def rejected(data, code):
    verdict = verify_record(data)
    assert not verdict['passed'], verdict
    assert code in {e['code'] for e in verdict['errors']}, verdict['errors']


def test_real_native_smoke_accepts_independent_trace_not_observers_eof_label(evidence):
    assert evidence['observer']['status'] == 'incomplete_eof'
    assert evidence['controller']['original_replay_passed'] is False
    verdict = verify_record(evidence)
    assert verdict['passed'], verdict['errors']
    assert verdict['summary']['independent_hp_kr_ticks'] == 6
    assert verdict['summary']['matched_planned_input_ticks'] == 5
    assert verdict['summary']['compared_nonterminal_state_components'] == 55
    assert verdict['summary']['max_nonterminal_abs_error'] == 0
    assert [d['field'] for d in verdict['summary']['terminal_model_differences']] == ['x', 'y']


def expose_resetvars_observation(data):
    """Schema regression for the newly instrumented original call.

    The exact additional shape was captured in the real welcome replay
    tools/real-game/bonesgap1-20261007-115817-087944.json. Augmenting older
    fixtures here tests recorder compatibility, not a new native replay.
    """
    tick=data['finalSnapshot']['tick']-1
    events=data['observer']['events']
    events.insert(len(events)-1,dict(tick=tick,fn='resetvars',args=[0]*9))
    data['controller']['events'].append(dict(tick=tick,fn='resetvars'))


@pytest.mark.parametrize('fixture_name',['evidence','blue_evidence'])
def test_complete_observed_resetvars_chain_retains_original_terminal_velocity(fixture_name,request):
    data=request.getfixturevalue(fixture_name)
    expected=verify_record(data)['summary']['terminal_velocity_derivation']
    expose_resetvars_observation(data)
    verdict=verify_record(data)
    assert verdict['passed'],verdict['errors']
    assert verdict['summary']['terminal_velocity_derivation']==expected


@pytest.mark.parametrize('mutation',['wrong_order','duplicate','extra_command','missing_controller',
    'controller_wrong_tick','controller_duplicate','nonzero_arg','short_args','boolean_arg',
    'null_args','changed_mode'])
def test_new_resetvars_observation_does_not_allow_arbitrary_terminal_commands(evidence,mutation):
    expose_resetvars_observation(evidence)
    events=evidence['observer']['events']
    reset=events[-2]
    if mutation=='wrong_order':events[-1],events[-2]=events[-2],events[-1]
    elif mutation=='duplicate':events.insert(-2,copy.deepcopy(reset))
    elif mutation=='extra_command':events.insert(-1,dict(tick=reset['tick'],fn='sansslam',args=[3]))
    elif mutation=='missing_controller':evidence['controller']['events'].pop()
    elif mutation=='controller_wrong_tick':evidence['controller']['events'][-1]['tick']-=1
    elif mutation=='controller_duplicate':evidence['controller']['events'].append(copy.deepcopy(evidence['controller']['events'][-1]))
    elif mutation=='nonzero_arg':reset['args'][0]=1
    elif mutation=='short_args':reset['args'].pop()
    elif mutation=='boolean_arg':reset['args'][0]=False
    elif mutation=='null_args':reset['args']=None
    elif mutation=='changed_mode':events[-1]['args'][0]=1
    rejected(evidence,'terminal_velocity_scope')


def add_source_derived_endattack_snapshots(data):
    """Synthetic native-snapshot schema, not an original-game capture.

    Older real fixtures have no trigger snapshots. This builder explicitly
    adds a hypothetical observed platform and before/after phase observations
    to isolate the new verification contract without relabeling the fixture.
    """
    expose_resetvars_observation(data)
    final=data['controller']['rows'][-1]
    prior=data['controller']['rows'][-2]
    event=next(e for e in data['observer']['events'] if e['fn']=='endattack')
    source=data['observer']['sourceText'].split('\n')
    source_line=max(i+1 for i,row in enumerate(source) if row.strip())
    loaded=source[source_line-1].split(',')
    bounds=[241.,226.,406.,391.]
    pre=prior['state'].copy();pre[4]=final['mask']
    post=pre.copy();post[7:10]=[1,750,0]
    def geometry(sid,uid,x,y,w,h,angle=0,polygon=None):
        return dict(typeSid=sid,uid=uid,x=x,y=y,width=w,height=h,angle=angle,
            bbox=[x,y,x+w,y+h],collisions_enabled=True,collision_polygon=polygon)
    l,t,r,b=bounds
    borders=[geometry(6657741784745805,20+i,box[0],box[1],box[2]-box[0],box[3]-box[1])
        for i,box in enumerate([[l,t,r,t+5],[l,t,l+5,b],[l,b-5,r,b],[r-5,t,r,b]])]
    platform=geometry(1226268899238104,900,260.,250.,50.,7.)
    platform['vars']=[0,0,0,0,0,0]
    def phase(state,after):
        env=[*bounds,state[6],state[7],0,final['dt'],state[8],0,0,0,state[9],0,*bounds,*bounds]
        physical=dict(initial=state.copy(),initial_environment=env,tick=event['tick'],
            time=final['time'],dt=final['dt'],clock_start_ms=final['clock_start_ms'],
            vpad=final['vpad'].copy(),HP=92,KR=0,SimulatorMode=2,SingleAttack='custom',
            physical_keymask=final['mask'],physical_confirm=final['confirm'],
            initial_confirm=final['confirm'],previous_confirm=bool(final['vpad'][11]),
            line=source_line,timeline=.1,running=1,
            arena=dict(target=[33,251,608,391] if after else bounds.copy(),size=[r-l,b-t],
                speed=480,callback='MenuBattle' if after else ''))
        heart=geometry(5960708907117077,10,state[0],state[1],16,16,state[7]*(math.pi/2),
                       [-.5,.5,-.5,-.5,.5,-.5,.5,.5])
        heart['bbox']=[state[0]-8,state[1]-8,state[0]+8,state[1]+8]
        return dict(capture_phase='after_native_endattack' if after else 'before_native_endattack',
            physical=physical,platforms=[] if after else [copy.deepcopy(platform)],
            heart_geometry=heart,borders=copy.deepcopy(borders))
    event['snapshots']=dict(schema_version=1,source='timeline',source_line=source_line,
        source_sha256=EOF_SOURCE_HASHES.copy(),before=phase(pre,False),after=phase(post,True),
        caller=dict(event_sid=441595194418922,action_sid=9188948149072352,action_index=0,sheet='Timeline',
            action_parameters=['EndAttack',event['args'].copy()],source_line=source_line,loaded_line=loaded,
            loaded_line_sid=3081225054711249,raw_source_line=source[source_line-1]))
    snapshots=event['snapshots']
    # Real C2 destruction is deferred; preserve after-call residual inventory.
    snapshots['after']['platforms']=copy.deepcopy(snapshots['before']['platforms'])
    ready=copy.deepcopy(snapshots['after'])
    ready.update(capture_phase='before_native_player_movement',event_sid=6451037740410459,
                 sheet='Battle',group_name='playermovement',platforms=[])
    ready['physical']['initial'][:2]=final['state'][:2]
    ready['physical']['line']=final['line'];ready['physical']['timeline']=final['T']
    x,y=final['state'][:2]
    ready['heart_geometry'].update(x=x,y=y,bbox=[x-8,y-8,x+8,y+8])
    snapshots['before_movement']=ready
    data['observer']['lifecycles'].append(dict(tick=prior['tick']-1,kind='created',object=copy.deepcopy(platform)))
    return event['snapshots']


@pytest.mark.parametrize('fixture_name',['evidence','blue_evidence'])
def test_native_trigger_snapshot_schema_allows_prior_platform_history(fixture_name,request):
    data=request.getfixturevalue(fixture_name)
    add_source_derived_endattack_snapshots(data)
    verdict=verify_record(data)
    assert verdict['passed'],verdict['errors']
    mode='blue' if data['finalSnapshot']['state'][6] else 'red'
    assert verdict['summary']['terminal_velocity_derivation']['rule']==f'original_{mode}_menu_input_from_native_trigger'


def test_native_behavior_endpoint_drives_velocity_without_using_model_endpoint_or_previous_tick(blue_evidence):
    snapshots=add_source_derived_endattack_snapshots(blue_evidence)
    # A hypothetical observed final behavior contact stopped vertical motion.
    # Previous-tick native dy=150 and model final dy=-150 both remain unchanged.
    snapshots['before']['physical']['initial'][3]=0
    snapshots['after']['physical']['initial'][3]=0
    snapshots['before_movement']['physical']['initial'][3]=0
    final_tick=blue_evidence['finalSnapshot']['tick']
    expected=180*blue_evidence['finalSnapshot']['dt']
    blue_evidence['controller']['rows'][-1]['state'][3]=expected
    for row in [blue_evidence['finalSnapshot'],*blue_evidence['observer']['rows'],blue_evidence['observer']['eofSnapshot']]:
        if row['tick']==final_tick:row['state'][3]=expected
    verdict=verify_record(blue_evidence)
    assert verdict['passed'],verdict['errors']
    rule=verdict['summary']['terminal_velocity_derivation']
    assert rule['incoming_dy']==0 and rule['expected']==[0,expected]


@pytest.mark.parametrize('mutation',['missing_before','missing_after','missing_movement','null_snapshots','snapshot_error','other_caller',
    'wrong_action','wrong_source_line','wrong_raw_line','wrong_loaded_line','wrong_parameters','wrong_source_hash',
    'wrong_phase','wrong_tick','wrong_time','wrong_dt','wrong_timestamp','wrong_vpad','wrong_hp',
    'post_velocity_change','post_position_change','post_mode_change','post_reset_change','movement_platform_survives',
    'missing_platform_inventory','duplicate_platform_uid','missing_platform_vars','changed_border','wrong_heart_shape',
    'wrong_movement_group','wrong_movement_sheet','wrong_menu_position','changed_movement_velocity','new_residual_platform'])
def test_endattack_snapshots_fail_closed_on_missing_or_changed_native_obligations(blue_evidence,mutation):
    s=add_source_derived_endattack_snapshots(blue_evidence)
    if mutation=='missing_before':s.pop('before')
    elif mutation=='missing_after':s.pop('after')
    elif mutation=='missing_movement':s.pop('before_movement')
    elif mutation=='null_snapshots':next(e for e in blue_evidence['observer']['events'] if e['fn']=='endattack')['snapshots']=None
    elif mutation=='snapshot_error':s['error']='capture_failed'
    elif mutation=='other_caller':s['source']='other'
    elif mutation=='wrong_action':s['caller']['action_sid']+=2
    elif mutation=='wrong_source_line':s['source_line']-=1
    elif mutation=='wrong_raw_line':s['caller']['raw_source_line']='0,Sound,Flash'
    elif mutation=='wrong_loaded_line':s['caller']['loaded_line'][1]='Other'
    elif mutation=='wrong_parameters':s['caller']['action_parameters'][0]='Other'
    elif mutation=='wrong_source_hash':s['source_sha256']['data.js']='0'*64
    elif mutation=='wrong_phase':s['before']['capture_phase']='posttick'
    elif mutation=='wrong_tick':s['before']['physical']['tick']+=1
    elif mutation=='wrong_time':s['before']['physical']['time']+=1
    elif mutation=='wrong_dt':s['before']['physical']['dt']=1/30
    elif mutation=='wrong_timestamp':s['before']['physical']['clock_start_ms']+=1
    elif mutation=='wrong_vpad':s['before']['physical']['vpad'][7]=1
    elif mutation=='wrong_hp':s['before']['physical']['HP']=91
    elif mutation=='post_velocity_change':s['after']['physical']['initial'][3]+=1
    elif mutation=='post_position_change':s['after']['physical']['initial'][0]+=1
    elif mutation=='post_mode_change':s['after']['physical']['initial'][6]=0
    elif mutation=='post_reset_change':s['after']['physical']['initial'][8]=330
    elif mutation=='movement_platform_survives':s['before_movement']['platforms']=copy.deepcopy(s['before']['platforms'])
    elif mutation=='missing_platform_inventory':s['after'].pop('platforms')
    elif mutation=='duplicate_platform_uid':s['before']['platforms'].append(copy.deepcopy(s['before']['platforms'][0]))
    elif mutation=='missing_platform_vars':s['before']['platforms'][0].pop('vars')
    elif mutation=='changed_border':s['after']['borders'][2]['bbox'][3]+=1
    elif mutation=='wrong_heart_shape':s['before']['heart_geometry']['width']=4
    elif mutation=='wrong_movement_group':s['before_movement']['event_sid']+=1
    elif mutation=='wrong_movement_sheet':s['before_movement']['sheet']='Timeline'
    elif mutation=='wrong_menu_position':s['before_movement']['physical']['initial'][1]=320
    elif mutation=='changed_movement_velocity':s['before_movement']['physical']['initial'][3]+=1
    elif mutation=='new_residual_platform':s['after']['platforms'][0]['uid']=9999
    rejected(blue_evidence,'terminal_native_snapshots')


def test_platform_history_still_requires_actual_new_snapshots(blue_evidence):
    add_source_derived_endattack_snapshots(blue_evidence)
    next(e for e in blue_evidence['observer']['events'] if e['fn']=='endattack').pop('snapshots')
    rejected(blue_evidence,'terminal_velocity_scope')


@pytest.mark.parametrize('mutate,code', [
    (lambda d: d['observer']['events'].pop(6), 'native_endattack'),
    (lambda d: d['observer']['ticks'].pop(), 'observer_coverage'),
    (lambda d: d['observer']['ticks'][2].__setitem__(0, 7), 'observer_tick_gap'),
    (lambda d: d['observer']['ticks'][1].__setitem__(1, 91), 'observer_damage_mode'),
    (lambda d: d['observer']['ticks'][1].__setitem__(2, 1), 'observer_damage_mode'),
    (lambda d: d['observer']['ticks'][4].__setitem__(5, 0), 'observer_input_mismatch'),
    (lambda d: d['controller']['rows'][4].__setitem__('confirm', False), 'controller_input_mismatch'),
    (lambda d: d['controller']['rows'][2]['vpad'].__setitem__(11, 1), 'confirm_latch'),
    (lambda d: d['controller']['plan']['confirm_sequence'].pop(), 'confirm_sequence'),
    (lambda d: d['controller']['plan']['trajectory'][2].__setitem__(0, 320.125), 'trajectory_mismatch'),
    (lambda d: d['controller']['plan']['trajectory'][2].__setitem__(5, 1e-9), 'trajectory_mismatch'),
    (lambda d: d['controller']['rows'][2].__setitem__('dt', 1/60), 'controller_damage_clock'),
    (lambda d: d['controller']['rows'].pop(2), 'controller_coverage'),
    (lambda d: d['observer'].__setitem__('sourceText', d['observer']['sourceText'] + '0,EndAttack\n'), 'source_hash'),
    (lambda d: d['controller'].__setitem__('csv_sha256', '0'*64), 'source_hash'),
    (lambda d: d['observer']['errors'].append({'reason': 'tick_gap'}), 'observer_errors'),
    (lambda d: d['finalSnapshot'].__setitem__('tick', 10), 'terminal_tick'),
    (lambda d: d['finalSnapshot']['state'].__setitem__(0, 320), 'menu_heart_position'),
    (lambda d: d['finalSnapshot']['state'].__setitem__(7, 3), 'menu_reset_heart'),
    (lambda d: d['finalSnapshot']['state'].__setitem__(3, 999), 'terminal_unexplained_state'),
    (lambda d: d['finalSnapshot'].__setitem__('pending', [{'uid': 88}]), 'terminal_pending'),
    (lambda d: d['finalSnapshot'].__setitem__('arenaTarget', [32, 240, 608, 384]), 'menu_reset_arena'),
])
def test_rejects_incomplete_damaged_or_mismatched_evidence_even_when_controller_completed(evidence, mutate, code):
    mutate(evidence)
    assert evidence['controller']['status'] == 'completed'
    rejected(evidence, code)


def test_damage_callback_is_rejected_even_if_hp_was_restored_and_first_damage_cleared(evidence):
    evidence['controller']['events'].insert(1, {'tick': 5, 'fn': 'damageplayer'})
    evidence['observer']['events'].insert(4, {'tick': 5, 'fn': 'damageplayer', 'args': [1, 6]})
    rejected(evidence, 'damage_event')


def test_early_endattack_cannot_be_repaired_by_completed_status(evidence):
    for owner in ('controller', 'observer'):
        next(e for e in evidence[owner]['events'] if e['fn'] == 'endattack')['tick'] = 7
    rejected(evidence, 'native_endattack')


def test_unmodified_independent_snapshot_catches_fabricated_controller_state(evidence):
    evidence['controller']['rows'][0]['state'][0] = 319
    evidence['controller']['plan']['trajectory'][0][0] = 319
    evidence['controller']['boundary']['initial'][0] = 319
    rejected(evidence, 'independent_state_mismatch')


def test_supported_float_roundoff_is_reported_with_exact_values(evidence):
    evidence['controller']['plan']['trajectory'][2][0] += 5e-8
    verdict = verify_record(evidence)
    assert verdict['passed'], verdict['errors']
    difference = verdict['summary']['nonterminal_differences'][0]
    assert difference == dict(frame=2, tick=6, component=0, field='x', actual=320,
                              expected=320 + 5e-8, abs_error=abs(320-(320+5e-8)))


def test_pre_source_environment_is_distinct_from_rebuilt_frame_zero(evidence):
    original = copy.deepcopy(evidence['controller']['boundary']['initial_environment'])
    original[0] = original[14] = original[18] = 80
    evidence['controller']['source_environment'] = original
    evidence['controller']['plan']['initial_environment'] = original
    assert verify_record(evidence)['passed']
    evidence['controller']['plan']['visualization']['frames'][0]['env'][0] = 80
    rejected(evidence, 'boundary_environment')


def test_rejects_source_environment_replaced_by_post_source_environment(evidence):
    evidence['controller']['source_environment'] = copy.deepcopy(evidence['controller']['boundary']['initial_environment'])
    evidence['controller']['source_environment'][0] = 80
    rejected(evidence, 'source_environment')


def test_pre_source_arena_recipe_cannot_disappear_or_change_in_candidate(evidence):
    arena = dict(target=[33,251,608,391],size=[576,144],speed=480,callback='')
    evidence['controller']['source_arena'] = arena
    evidence['controller']['plan']['initial_arena'] = copy.deepcopy(arena)
    assert verify_record(evidence)['passed']
    evidence['controller']['plan']['initial_arena']['target'][0] = 32
    rejected(evidence, 'source_arena')


def add_target_evidence(data):
    """Augment the schema fixture to isolate source-event/tick correlation."""
    initial = dict(tick=3,fn='getheartpos',source_line=4,sampled_position=[319.,320.],args=['x','y'])
    later = dict(tick=5,fn='getheartpos',source_line=5,sampled_position=[320.,320.],args=['x','y'])
    data['observer']['events'].extend([initial,later])
    data['observer']['events'].sort(key=lambda e:e['tick'])
    data['controller']['initial_target_history'] = [[0,4,319.,320.]]
    data['controller']['plan']['initial_target_history'] = [[0,4,319.,320.]]
    data['controller']['plan']['target_history'] = [[0,4,319.,320.],[2,5,320.,320.]]


def test_target_reads_use_trigger_tick_and_not_posttick_position(evidence):
    add_target_evidence(evidence)
    verdict = verify_record(evidence)
    assert verdict['passed'], verdict['errors']
    assert verdict['summary']['independently_matched_target_reads'] == 2
    # Frame zero's captured x is 320; the already observed target was 319.
    evidence['controller']['plan']['target_history'][0][2] = 320.
    rejected(evidence, 'target_history_mismatch')


def test_missing_target_sample_or_future_history_mismatch_is_not_accepted(evidence):
    add_target_evidence(evidence)
    later = next(e for e in evidence['observer']['events'] if e['fn']=='getheartpos' and e['tick']==5)
    later.pop('sampled_position')
    rejected(evidence, 'target_observation')
    later['sampled_position'] = [320.0000000001,320.]
    rejected(evidence, 'target_history_mismatch')


def retime_clock_fixture(data, hz):
    """Exercise exact clock validation independently of the smoke's score."""
    step = 1000 / hz
    b = data['controller']['boundary']
    p = data['controller']['plan']
    count = len(p['actions']) + 1
    stamp = 1024 - 2.2 * step
    timestamps = [stamp]
    dts = [min((stamp - (stamp-step)) / 1000, 1/30)]
    for _ in range(1,count):
        following = stamp + step
        dts.append(min((following-stamp)/1000,1/30))
        timestamps.append(following)
        stamp = following
    assert len(set(dts)) > 1
    data['clock'] = dict(mode='fixed-native-timestamps',physicsHz=hz,logicalStepMs=step)
    b['clock_start_ms'] = timestamps[0]
    b['dt'] = dts[0]
    b['initial_environment'][7] = dts[0]
    p['initial_environment'][7] = dts[0]
    p['dt_sequence'] = dts
    # The source model correctly reports nonuniform physical deltas without
    # pretending their reciprocals are the nominal driver frequency.
    p['physics_hz'] = p['control_hz'] = None
    for i,row in enumerate(data['controller']['rows']):
        row['clock_start_ms'],row['dt'] = timestamps[i],dts[i]
        row['time'] = b['time'] + sum(dts[1:i+1])
    for row in [*data['observer']['rows'],data['finalSnapshot'],data['observer']['eofSnapshot']]:
        i = row['tick'] - b['tick']
        row['clock_start_ms'],row['dt'] = timestamps[i],dts[i]
        row['time'] = b['time'] + sum(dts[1:i+1])
    data['observer']['entry']['clock_start_ms'] = timestamps[0]
    data['observer']['entry']['dt'] = dts[0]


@pytest.mark.parametrize('hz',[60,120,240])
def test_native_clock_uses_timestamp_subtraction_instead_of_nominal_hz(evidence,hz):
    retime_clock_fixture(evidence,hz)
    verdict = verify_record(evidence)
    assert verdict['passed'],verdict['errors']
    assert verdict['summary']['verified_timestamp_ticks'] == 6
    assert verdict['summary']['nominal_physics_hz'] == hz
    assert verdict['summary']['distinct_native_dt_values'] > 1


@pytest.mark.parametrize('mutate,code',[
    (lambda d:d['controller']['boundary'].__setitem__('clock_start_ms',1000.),'controller_timestamp'),
    (lambda d:d['controller']['rows'][2].__setitem__('clock_start_ms',1000.),'controller_timestamp'),
    (lambda d:d['controller']['rows'][2].__setitem__('dt',1/60),'controller_damage_clock'),
    (lambda d:d['controller']['plan']['dt_sequence'].__setitem__(2,1/60),'dt_sequence'),
    (lambda d:d['observer']['rows'][0].__setitem__('clock_start_ms',1000.),'sample_timestamp'),
    (lambda d:d['finalSnapshot'].__setitem__('dt',1/60),'sample_context'),
    (lambda d:d['clock'].__setitem__('logicalStepMs',1000/60+1e-6),'clock_step'),
    (lambda d:d['clock'].__setitem__('physicsHz',120),'clock_step'),
])
def test_rejects_changed_timestamp_phase_and_nominalized_intermediate_dt(evidence,mutate,code):
    retime_clock_fixture(evidence,60)
    mutate(evidence)
    rejected(evidence,code)


def test_even_one_ulp_of_native_timestamp_or_dt_difference_is_rejected(evidence):
    retime_clock_fixture(evidence,60)
    row = evidence['controller']['rows'][2]
    original = row['clock_start_ms']
    row['clock_start_ms'] = math.nextafter(original,math.inf)
    rejected(evidence,'controller_timestamp')
    row['clock_start_ms'] = original
    row['dt'] = math.nextafter(row['dt'],math.inf)
    rejected(evidence,'controller_damage_clock')


def test_old_30hz_records_keep_exact_clamp_and_timestamp_checks(evidence):
    assert 'physicsHz' not in evidence['clock']
    assert verify_record(evidence)['passed']
    evidence['controller']['rows'][2]['clock_start_ms'] += 1e-10
    rejected(evidence,'controller_timestamp')


def test_real_bonestab3_60hz_derives_menu_velocity_from_native_previous_state(blue_evidence):
    verdict = verify_record(blue_evidence)
    assert verdict['passed'], verdict['errors']
    summary = verdict['summary']
    assert summary['compared_nonterminal_state_components'] == 4455
    assert summary['max_nonterminal_abs_error'] == 0
    assert summary['verified_timestamp_ticks'] == summary['independent_hp_kr_ticks'] == 406
    assert summary['matched_planned_input_ticks'] == 405
    rule = summary['terminal_velocity_derivation']
    assert rule == dict(rule='original_blue_menu_clear_sweep', expected=[0, 159.00000000000017],
                       actual=[0, 159.00000000000017], incoming_dy=150, released_up=False,
                       gravity=540, dt=0.01666666666666697, reset_direction=1,
                       arena=[241, 226, 406, 391])
    # The original mode reset happens before the same tick's input phase.
    # Battle.xml: ResetVars 485, menu position 2686, blue angle 3107,
    # Up/jump 3882-3931, gravity 4054-4159, sideways movement 4328-4477.
    assert blue_evidence['controller']['plan']['trajectory'][-1][2:4] == [149.99999999999943, -150]
    assert [d['field'] for d in summary['terminal_model_differences']] == ['x', 'y', 'dx', 'dy', 'direction']


@pytest.mark.parametrize('component', [2, 3])
def test_even_one_ulp_of_terminal_velocity_is_rejected_after_all_snapshots_agree(blue_evidence, component):
    data = blue_evidence
    final = data['finalSnapshot']
    wrong = math.nextafter(final['state'][component], math.inf)
    # Change every independent/controller endpoint copy so rejection cannot
    # rely merely on different observers disagreeing with each other.
    data['controller']['rows'][-1]['state'][component] = wrong
    for row in [final, *data['observer']['rows'], data['observer']['eofSnapshot']]:
        if row['tick'] == final['tick']:
            row['state'][component] = wrong
    rejected(data, 'terminal_unexplained_state')


def test_blue_menu_rule_never_exempts_a_preterminal_state_difference(blue_evidence):
    blue_evidence['controller']['rows'][-2]['state'][3] += 1
    rejected(blue_evidence, 'trajectory_mismatch')


@pytest.mark.parametrize('mutate', [
    lambda d: d['observer']['lifecycles'].append(dict(tick=300, kind='created',
                                                    object=dict(uid=999, typeSid=1226268899238104))),
    lambda d: d['observer']['lifecycles'].append(dict(tick=301, kind='destroyed',
                                                    uid=999, typeSid=6981383464931416)),
    lambda d: d['observer']['rows'][-2]['pending'].append(dict(uid=999, typeSid=1226268899238104)),
    lambda d: d['observer']['rows'][-2]['arenaTarget'].__setitem__(0, 240),
    lambda d: d['observer']['events'].insert(-3, dict(tick=405, fn='combatzoneresize',
                                                    args=[241, 226, 406, 391])),
    lambda d: d['observer']['events'][-1]['args'].__setitem__(0, 0),
    lambda d: d['observer']['events'].insert(-3, dict(tick=411, fn='sansslam', args=[3])),
])
def test_blue_menu_velocity_requires_its_source_proof_scope(blue_evidence, mutate):
    mutate(blue_evidence)
    rejected(blue_evidence, 'terminal_velocity_scope')


def test_menu_up_edge_does_not_jump_but_releasing_up_applies_original_cutoff():
    arena = [241, 226, 406, 391]
    prior = [320., 320., 0., -180., 4, 0, 1, 2, 750, 0, 0]
    held = derive_menu_velocity(prior, 4, 1/60, 1, arena)
    released = derive_menu_velocity(prior, 0, 1/60, 1, arena)
    assert held['expected'] == [0, -177]
    assert released['released_up'] is True
    assert released['expected'] == [0, -22.5]
    prior[3:5] = [150., 0]
    pressed = derive_menu_velocity(prior, 7, 0.01666666666666697, 1, arena)
    assert pressed['expected'] == [0, 159.00000000000017]


@pytest.mark.parametrize('position,arena', [
    ([254., 320.], [241, 226, 406, 391]),  # Exact left border contact.
    ([320., 320.], [241, 226, 406, 445]),  # Menu solid probes not clear.
])
def test_menu_velocity_rejects_unproven_contact_cases(position, arena):
    prior = [*position, 0., 0., 0, 0, 1, 2, 750, 0, 0]
    with pytest.raises(ValueError, match='contact'):
        derive_menu_velocity(prior, 7, 1/60, 1, arena)


@pytest.mark.parametrize('value', [None, {}, {'controller': 'completed'}, {'controller': {}, 'observer': []}])
def test_missing_records_fail_closed(value):
    assert not verify_record(value)['passed']
