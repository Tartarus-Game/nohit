import copy
import hashlib
import json
import math
import struct

import pytest

from tools.verify_full_game_acceptance import (EXPECTED_ATTACKS,REQUIRED_SOURCES,TICK_FIELDS,
    CSV_TICK_FIELDS,_implementation_hashes,load_record,verify_record)
from tools.verify_full_game_acceptance import diagnose_completed_csv_rounds


def fixture_record(tmp_path):
    game=tmp_path/'game';original=tmp_path/'original'
    game.mkdir();original.mkdir()
    source_hashes={};script_hashes={}
    for name in REQUIRED_SOURCES:
        content=('verified fixture '+name).encode()
        (game/name).write_bytes(content)
        if name in ('c2runtime.js','data.js'):(original/name).write_bytes(content)
        source_hashes[name]=hashlib.sha256(content).hexdigest()
    for attack in set(EXPECTED_ATTACKS):
        name=attack+'.csv';content=('original fixture '+name).encode()
        (game/name).write_bytes(content);(original/name).write_bytes(content)
        script_hashes[name]=hashlib.sha256(content).hexdigest()
    rounds=[];events=[];plans=[]
    for i,attack in enumerate(EXPECTED_ATTACKS):
        start=1+i*32;end=start+20
        rounds.append(dict(attack=attack,startTick=start,endTick=end))
        events.extend([dict(fn='startattack',tick=start,param=0),dict(fn='runattack',tick=start,param=attack),dict(fn='endattack',tick=end,param='')])
        cap=dict(tick=start+1,HP=92,KR=0,initial=[320.,320.,0.,0.,0.,0.,1.,1.,750.,0.,0.],
                 initial_environment=[0.]*22,clock_start_ms=float(start*1000/240))
        plans.append(dict(wave=attack+'.csv',captured=cap,actions=[0]*5,planner='canonical-dag-dp',
                          status='candidate_found',route_cache_hit=False,clock_start_ms=cap['clock_start_ms'],
                          control_ticks=4,kernel_sha256='a'*64,csv_sha256=script_hashes[attack+'.csv']))
    win_tick=rounds[-1]['endTick']+2
    events.extend([dict(fn='win1',tick=win_tick-1,param=''),dict(fn='win2',tick=win_tick,param='')])
    first,last=2,win_tick+1
    rows=[dict(tick=t,HP=92,KR=0,dt=1/240) for t in sorted({first,last,*range(16,last+1,16)})]
    data=dict(suite='continuous-normal-game',seed=42,clock='original-runtime-realtime-catchup-240hz',
              result=dict(passed=True,status='passed',rounds=24),winObserved=True,firstDamage=None,
              tickGaps=[],clockErrors=[],checkedTicks=last-first+1,rows=rows,events=events,rounds=rounds,
              computedPlans=plans,source_sha256=source_hashes,script_sha256=script_hashes)
    return data,game,original


def check(data,game,original):
    return verify_record(data,game_dir=game,original_dir=original)


def test_complete_record_accepts_failed_paused_retries_but_does_not_invent_fight_count(tmp_path):
    data,game,original=fixture_record(tmp_path)
    failed=copy.deepcopy(data['computedPlans'][3]);failed.update(status='resource_limit',actions=[])
    data['computedPlans'].insert(3,failed)
    verdict=check(data,game,original)
    assert verdict['passed'],verdict['errors']
    assert verdict['summary']['fresh_candidates']==24
    assert verdict['summary']['failed_search_attempts']==1
    assert verdict['summary']['successful_fights'] is None


@pytest.mark.parametrize('mutation,code',[
    (lambda d:d['rounds'].__setitem__(2,copy.deepcopy(d['rounds'][1])),'round_sequence'),
    (lambda d:d['events'].__setitem__(-1,dict(fn='not_win2',tick=d['events'][-1]['tick'])),'win_event_count'),
    (lambda d:d.__setitem__('checkedTicks',d['checkedTicks']-1),'coverage_count'),
    (lambda d:d['rows'].pop(2),'sample_coverage'),
    (lambda d:d.__setitem__('firstDamage',dict(tick=100,HP=91,KR=0)),'first_damage'),
    (lambda d:d['computedPlans'][0].__setitem__('route_cache_hit',True),'cached_route'),
    (lambda d:d['computedPlans'].pop(3),'candidate_count'),
])
def test_rejects_partial_or_falsely_green_evidence(tmp_path,mutation,code):
    data,game,original=fixture_record(tmp_path);mutation(data)
    verdict=check(data,game,original)
    assert not verdict['passed']
    assert code in {e['code'] for e in verdict['errors']}


def test_hash_record_cannot_bless_a_modified_original_engine(tmp_path):
    data,game,original=fixture_record(tmp_path)
    content=b'modified collision runtime';(game/'c2runtime.js').write_bytes(content)
    data['source_sha256']['c2runtime.js']=hashlib.sha256(content).hexdigest()
    verdict=check(data,game,original)
    assert not verdict['passed']
    assert 'original_runtime_hash' in {e['code'] for e in verdict['errors']}


def test_optional_recorded_fight_counter_and_simulator_mode_are_checked(tmp_path):
    data,game,original=fixture_record(tmp_path)
    data['rows'][0]['hitAttempts']=0;data['rows'][-1]['hitAttempts']=23
    assert check(data,game,original)['summary']['successful_fights']==23
    data['rows'][10]['SimulatorMode']=2
    assert not check(data,game,original)['passed']


def raw_record(tmp_path):
    data,game,original=fixture_record(tmp_path)
    first=data['rows'][0]['tick'];last=data['rows'][-1]['tick']
    data.update(evidenceVersion=2,sampleStride=64,tickEvidenceFields=TICK_FIELDS,protocolErrors=[])
    raw=[]
    for tick in range(first,last+1):
        hits=min(23,(tick-1)//32)
        raw.append([tick,92,0,hits,0,0,0])
    data['tickEvidence']=raw
    data['rows']=[dict(zip(TICK_FIELDS,raw[t-first]),dt=1/240) for t in sorted({first,last,*range(64,last+1,64)})]
    for event in data['events']:
        event.update(HP=92,KR=0,SimulatorMode=0,HitAttempts=min(23,(event['tick']-1)//32))
    data['entrySnapshot']=dict(data['events'][0])
    data['win2Snapshot']=dict(data['events'][-1])
    return data,game,original


def test_one_tick_controls_match_each_actual_native_input(tmp_path):
    data,game,original=raw_record(tmp_path)
    plan=data['computedPlans'][0]
    plan.update(control_ticks=1,actions=[2,4,1,0]+[0]*16)
    first=data['tickEvidence'][0][0]
    for index,mask in enumerate(plan['actions']):
        data['tickEvidence'][plan['captured']['tick']+index+1-first][5]=mask
    verdict=check(data,game,original)
    assert verdict['passed'],verdict['errors']
    data['tickEvidence'][plan['captured']['tick']+2-first][5]=2
    verdict=check(data,game,original)
    assert not verdict['passed']
    assert 'candidate_input_mismatch' in {e['code'] for e in verdict['errors']}


def test_raw_evidence_checks_every_hp_mode_counter_and_planned_input(tmp_path):
    data,game,original=raw_record(tmp_path)
    verdict=check(data,game,original)
    assert verdict['passed'],verdict['errors']
    assert verdict['summary']['verified_raw_hp_kr_ticks']==data['checkedTicks']
    assert verdict['summary']['successful_fights']==23
    assert verdict['summary']['matched_planned_input_ticks']>0


@pytest.mark.parametrize('column,value,code',[(1,91,'raw_damage'),(4,2,'raw_mode'),(3,9,'raw_fight_progress'),(5,16,'candidate_input_mismatch')])
def test_raw_evidence_rejects_errors_between_sparse_samples(tmp_path,column,value,code):
    data,game,original=raw_record(tmp_path)
    data['tickEvidence'][3][column]=value
    verdict=check(data,game,original)
    assert not verdict['passed']
    assert code in {e['code'] for e in verdict['errors']}


def csv_record(tmp_path):
    """Synthetic complete campaign for v3 format/corruption tests, not a native run."""
    data,game,original=raw_record(tmp_path)
    content=b'verified fixture csv_round_controller.js'
    (game/'csv_round_controller.js').write_bytes(content)
    data['source_sha256']['csv_round_controller.js']=hashlib.sha256(content).hexdigest()
    data['script_text_sha256']=dict(data['script_sha256'])
    data['solver_source_sha256']=_implementation_hashes()
    data.update(evidenceVersion=3,tickEvidenceFields=CSV_TICK_FIELDS,
                clockProtocol=dict(mode='fixed-240hz-realtime-catchup',physicsHz=240,logicalStepMs=1000/240))
    stamp=1017.25;raw=data['tickEvidence'];first=raw[0][0]
    for row in raw:
        following=stamp+1000/240;dt=(following-stamp)/1000;stamp=following
        row.extend([dt,stamp,0,[320.,320.,0.,0.,0,0,0,1,750.,0.,0.]])
    for rnd in data['rounds']:
        for offset,confirm in enumerate([1,1,0,1]+[0]*16):
            raw[rnd['startTick']+2+offset-first][6]=confirm
    for i,row in enumerate(raw):row[9]=raw[i-1][6] if i else 0

    def snapshot(tick):
        row=raw[tick-first];result=copy.deepcopy(dict(zip(CSV_TICK_FIELDS,row)))
        bounds=[32.,240.,608.,384.]
        result.update(line=2,T=0.,running=0,
                      initial_environment=[*bounds,0,1,0,row[7],750,0,0,0,0,0,*bounds,*bounds],
                      arena=dict(target=bounds,size=[576.,144.],speed=480,callback=''),
                      vpad=[0,0,0,0,row[6],0,0,0,0,0,0,row[9],0,0])
        return result

    data['rows']=[snapshot(t) for t in sorted({first,raw[-1][0],*range(64,raw[-1][0]+1,64)})]
    data['entrySnapshot']=dict(snapshot(first),tick=first-1)
    data['win2Snapshot']=dict(snapshot(raw[-1][0]),tick=raw[-1][0]-1)
    plans=[]
    for ri,rnd in enumerate(data['rounds']):
        boundary=snapshot(rnd['startTick']+1);cap=dict(copy.deepcopy(boundary),
            initial=copy.deepcopy(boundary['state']),timeline=boundary['T'],
            initial_confirm=bool(boundary['confirm']),previous_confirm=bool(boundary['previous_confirm']))
        text=(game/(rnd['attack']+'.csv')).read_text(encoding='utf-8')
        sha=hashlib.sha256(text.encode()).hexdigest()
        pre=dict(copy.deepcopy(boundary),tick=boundary['tick']-1)
        rnd.update(round=ri,source=dict(text=text,sha256=sha,preSnapshot=pre),
                   boundary=boundary,endSnapshot=snapshot(rnd['endTick']+1))
        schedule=[cap['dt']];stamp=cap['clock_start_ms']
        for _ in range(31):
            following=stamp+1000/240;schedule.append((following-stamp)/1000);stamp=following
        request=dict(request_id=f'unique-fixture-request-{ri}',custom_csv=text,initial=cap['initial'],
                     initial_environment=pre['initial_environment'],initial_arena=pre['arena'],
                     initial_target_history=[],initial_confirm=cap['initial_confirm'],
                     previous_confirm=cap['previous_confirm'],dt_schedule=schedule,max_ticks=32,seed=42)
        count=rnd['endTick']+1-cap['tick']
        controls=[raw[cap['tick']+i-first] for i in range(1,count+1)]
        plan=dict(status='candidate_found',planner='bounded-frontier-with-dialogue',verified=True,
                  csv_sha256=sha,seed=42,max_ticks=32,control_ticks=1,clock_protocol='explicit_dt_schedule',
                  clock=dict(protocol='explicit_dt_schedule',decision_ticks=1,schedule_count=32,
                    schedule_sha256=hashlib.sha256(b''.join(struct.pack('<d',v) for v in schedule)).hexdigest()),
                  actions=[r[5] for r in controls],confirm_sequence=[bool(r[6]) for r in controls],
                  trajectory=[copy.deepcopy(raw[cap['tick']+i-first][10]) for i in range(count+1)],
                  dt_sequence=schedule[:count+1],initial=cap['initial'],initial_environment=pre['initial_environment'],
                  visualization=dict(frames=[dict(env=boundary['initial_environment'])]),
                  initial_arena=pre['arena'],initial_confirm=cap['initial_confirm'],previous_confirm=cap['previous_confirm'],
                  initial_target_history=[],target_history=[],
                  provenance=dict(request_id=request['request_id'],fresh_computation=True,route_cache_hit=False,
                                  implementation_sha256=data['solver_source_sha256']))
        plans.append(dict(round=ri,wave=rnd['attack']+'.csv',captured=cap,plan=plan,
                          source_environment=pre['initial_environment'],source_arena=pre['arena'],
                          source_text=text,source_sha256=sha,initial_target_history=[],request=request,
                          request_generation=1,actionsApplied=count))
        plans[-1]['rows']=[dict(snapshot(cap['tick']+i),
            mask=plan['actions'][i-1] if i else None,
            confirm=plan['confirm_sequence'][i-1] if i else None) for i in range(count+1)]
        plans[-1]['events']=[dict(tick=pre['tick'],fn='tlplay'),dict(tick=rnd['endTick'],fn='endattack')]
        for event in data['events']:
            if event['tick'] in (rnd['startTick'],rnd['endTick']):event['round']=ri
        data['events'].append(dict(fn='tlplay',tick=pre['tick'],param=text,round=ri))
    data['events'].sort(key=lambda e:(e['tick'],{'startattack':0,'runattack':1,'tlplay':2}.get(e['fn'],3)))
    data['computedPlans']=plans
    # Avoid aliased Python objects hiding inconsistent mutations; real JSON
    # storage always materializes distinct copies at these boundaries.
    return json.loads(json.dumps(data)),game,original


def test_csv_v3_checks_whole_native_campaign_and_every_confirm_clock_state(tmp_path):
    data,game,original=csv_record(tmp_path)
    verdict=check(data,game,original)
    assert verdict['passed'],verdict['errors']
    summary=verdict['summary']
    assert summary['verified_native_clock_ticks']==data['checkedTicks']
    assert summary['matched_planned_input_ticks']==480
    assert summary['compared_nonterminal_state_components']==5280
    assert summary['successful_fights']==23
    assert summary['max_nonterminal_abs_error']==0
    assert summary['verified_request_schedules']==24


def add_native_final_endattack_pause(data):
    """Native EndAttack -> FinalAttackEnd -> TLPause shares the terminal tick.

    The observer clears active on EndAttack; its nested TLPause therefore has
    round 24, while the round controller still owns the entire physical tick.
    Win1's later TLPause is outside that controller's execution interval.
    """
    end = data['rounds'][-1]['endTick']
    last = next(i for i, event in enumerate(data['events'])
                if event['fn']=='endattack' and event['tick']==end)
    data['events'].insert(last+1, dict(fn='tlpause',tick=end,param=0,round=24,
                                     HP=92,KR=0,SimulatorMode=0,HitAttempts=23))
    data['events'].insert(last+3, dict(fn='tlpause',tick=end+1,param=0,round=24,
                                     HP=92,KR=0,SimulatorMode=0,HitAttempts=23))
    data['computedPlans'][-1]['events'].append(dict(fn='tlpause',tick=end))


def test_final_nested_pause_belongs_to_controller_until_terminal_posttick(tmp_path):
    data,game,original=csv_record(tmp_path)
    add_native_final_endattack_pause(data)
    verdict=check(data,game,original)
    assert verdict['passed'],verdict['errors']


@pytest.mark.parametrize('mutation',[
    lambda d:d['computedPlans'][-1]['events'].pop(),
    lambda d:d['computedPlans'][-1]['events'].append(dict(d['computedPlans'][-1]['events'][-1])),
    lambda d:d['computedPlans'][-1]['events'][-1].__setitem__('tick',d['rounds'][-1]['endTick']+1),
    lambda d:d['computedPlans'][-1]['events'][-1].__setitem__('fn','tlresume'),
])
def test_terminal_event_scope_still_rejects_missing_extra_retimed_or_changed_events(tmp_path,mutation):
    data,game,original=csv_record(tmp_path)
    add_native_final_endattack_pause(data);mutation(data)
    verdict=check(data,game,original)
    assert not verdict['passed']
    assert 'csv_controller_events' in {error['code'] for error in verdict['errors']}


@pytest.mark.parametrize('mutation,code',[
    (lambda d:d['tickEvidence'][3].__setitem__(6,1),'csv_candidate_input_mismatch'),
    (lambda d:d['tickEvidence'][3].__setitem__(7,math.nextafter(d['tickEvidence'][3][7],math.inf)),'csv_native_clock'),
    (lambda d:d['tickEvidence'][3].__setitem__(8,math.nextafter(d['tickEvidence'][3][8],math.inf)),'csv_native_clock'),
    (lambda d:d['tickEvidence'][3][10].__setitem__(0,321),'csv_trajectory_mismatch'),
    (lambda d:d['tickEvidence'][24].__setitem__(1,91),'raw_damage'),
    (lambda d:d['tickEvidence'].pop(4),'raw_tick_gap'),
    (lambda d:d['computedPlans'][0]['request']['dt_schedule'].__setitem__(-1,1/240),'csv_request_clock'),
    (lambda d:d['computedPlans'][0]['plan']['dt_sequence'].__setitem__(2,1/240),'csv_candidate_dt'),
    (lambda d:d['computedPlans'][0]['plan']['confirm_sequence'].__setitem__(1,False),'csv_candidate_input_mismatch'),
    (lambda d:d['computedPlans'][0]['plan']['provenance'].__setitem__('fresh_computation',False),'csv_fresh_provenance'),
    (lambda d:d['computedPlans'][0]['plan']['provenance'].__setitem__('request_id','stale'),'csv_request_identity'),
    (lambda d:d['computedPlans'][0].__setitem__('round',1),'csv_attempt_wave'),
    (lambda d:d['computedPlans'][0].__setitem__('source_text','different CSV'),'csv_round_source'),
    (lambda d:d['computedPlans'][0]['source_environment'].__setitem__(0,80),'csv_source_environment'),
    (lambda d:d['computedPlans'][0]['request']['initial_arena']['target'].__setitem__(0,80),'csv_source_arena'),
    (lambda d:d['computedPlans'][0]['captured'].__setitem__('previous_confirm',True),'csv_boundary_confirm'),
    (lambda d:d['computedPlans'][0]['plan']['actions'].pop(),'csv_terminal_coverage'),
    (lambda d:d['computedPlans'][0].__setitem__('actionsApplied',19),'csv_terminal_coverage'),
    (lambda d:d['rounds'][0]['endSnapshot'].__setitem__('tick',23),'csv_terminal_coverage'),
    (lambda d:d['events'].append(dict(fn='damageplayer',tick=5,param=0,kr=1)),'csv_damage_event'),
    (lambda d:d['source_sha256'].pop('csv_round_controller.js'),'loaded_source_hash'),
])
def test_csv_v3_rejects_source_clock_input_provenance_or_coverage_corruption(tmp_path,mutation,code):
    data,game,original=csv_record(tmp_path);mutation(data)
    verdict=check(data,game,original)
    assert not verdict['passed']
    assert code in {e['code'] for e in verdict['errors']},verdict['errors']


def test_csv_v3_retains_unknown_attempts_without_treating_them_as_rounds(tmp_path):
    data,game,original=csv_record(tmp_path)
    attempt=copy.deepcopy(data['computedPlans'][0])
    attempt['plan'].update(status='unknown',verified=False,actions=[],confirm_sequence=[],trajectory=[])
    attempt['request']['request_id']=attempt['plan']['provenance']['request_id']='unique-failed-attempt'
    data['computedPlans'][0]['request_generation']=2
    data['computedPlans'].insert(0,attempt)
    verdict=check(data,game,original)
    assert verdict['passed'],verdict['errors']
    assert verdict['summary']['fresh_candidates']==24
    assert verdict['summary']['failed_search_attempts']==1
    data['computedPlans'][1]['request_generation']=1
    assert 'csv_request_generation' in {e['code'] for e in check(data,game,original)['errors']}


def test_csv_v3_raw_and_actual_tlplay_text_hashes_are_distinct(tmp_path):
    data,game,original=csv_record(tmp_path)
    name=EXPECTED_ATTACKS[0]+'.csv'
    text='0,HeartMode,0\n1,EndAttack\n'
    raw=b'\xef\xbb\xbf'+text.replace('\n','\r\n').encode()
    (game/name).write_bytes(raw);(original/name).write_bytes(raw)
    raw_sha=hashlib.sha256(raw).hexdigest();text_sha=hashlib.sha256(text.encode()).hexdigest()
    data['script_sha256'][name]=raw_sha;data['script_text_sha256'][name]=text_sha
    source=data['rounds'][0]['source'];source.update(text=text,sha256=text_sha)
    attempt=data['computedPlans'][0];attempt.update(source_text=text,source_sha256=text_sha)
    attempt['request']['custom_csv']=text;attempt['plan']['csv_sha256']=text_sha
    next(e for e in data['events'] if e['fn']=='tlplay')['param']=text
    verdict=check(data,game,original)
    assert verdict['passed'],verdict['errors']
    attempt['plan']['csv_sha256']=raw_sha
    assert not check(data,game,original)['passed']


def test_csv_v3_checks_trigger_phase_target_reads_instead_of_posttick_position(tmp_path):
    data,game,original=csv_record(tmp_path)
    target=dict(fn='getheartpos',tick=1,round=0,param='x',source_line=4,sampled_position=[319.,320.])
    data['events'].append(target);data['events'].sort(key=lambda e:e['tick'])
    attempt=data['computedPlans'][0];initial=[[0,4,319.,320.]]
    attempt['initial_target_history']=copy.deepcopy(initial)
    attempt['request']['initial_target_history']=copy.deepcopy(initial)
    attempt['plan']['initial_target_history']=copy.deepcopy(initial)
    attempt['plan']['target_history']=copy.deepcopy(initial)
    verdict=check(data,game,original)
    assert verdict['passed'],verdict['errors']
    assert verdict['summary']['independently_matched_target_reads']==1
    attempt['plan']['target_history'][0][2]=320.
    assert 'csv_target_history' in {e['code'] for e in check(data,game,original)['errors']}


@pytest.mark.parametrize('mutation,code',[
    (lambda d:d['computedPlans'][0]['plan']['visualization']['frames'][0]['env'].__setitem__(0,80),'csv_committed_environment'),
    (lambda d:d['rounds'][0]['boundary']['vpad'].__setitem__(11,1),'csv_boundary_vpad'),
    (lambda d:d['computedPlans'][0]['plan'].__setitem__('dt_sequence',None),'csv_candidate_dt'),
    (lambda d:d['computedPlans'][0]['rows'].pop(4),'csv_controller_coverage'),
    (lambda d:d['computedPlans'][0]['rows'][-1]['state'].__setitem__(2,999),'csv_controller_state'),
    (lambda d:d['computedPlans'][0]['events'][-1].__setitem__('tick',20),'csv_controller_events'),
])
def test_csv_v3_rejects_wrong_committed_physics_latch_or_missing_dt(tmp_path,mutation,code):
    data,game,original=csv_record(tmp_path);mutation(data)
    verdict=check(data,game,original)
    assert not verdict['passed']
    assert code in {e['code'] for e in verdict['errors']}


def test_csv_v3_cli_loader_reassembles_all_parts_and_binds_server_hashes(tmp_path):
    from nohit.dashboard.acceptance_evidence import store_evidence_part
    import base64
    data,game,original=csv_record(tmp_path)
    fields=('source_sha256','script_sha256','script_text_sha256','solver_source_sha256')
    attestations={k:data.pop(k) for k in fields}
    data['note']='无损 UTF8 证据'
    encoded=json.dumps(data,ensure_ascii=False).encode('utf-8')
    parts=[]
    for start in range(0,len(encoded),997):
        block=encoded[start:start+997]
        part=store_evidence_part(dict(evidenceVersion=3,encoding='base64',
            data=base64.b64encode(block).decode(),sha256=hashlib.sha256(block).hexdigest()),tmp_path)
        parts.append(dict(index=len(parts),**part))
    manifest={k:data.get(k) for k in ('suite','evidenceVersion','seed','clock','criterion','result')}
    manifest.update(storage='json-utf8-parts-v1',total_byte_count=len(encoded),
                    total_sha256=hashlib.sha256(encoded).hexdigest(),evidenceParts=parts,**attestations)
    path=tmp_path/'evidence.json';path.write_text(json.dumps(manifest),encoding='utf-8')
    restored=load_record(path)
    assert restored['note']==data['note']
    assert check(restored,game,original)['passed']
    assert not check(manifest,game,original)['passed']
    (tmp_path/parts[len(parts)//2]['path']).write_bytes(b'changed')
    with pytest.raises(ValueError,match='altered'):
        load_record(path)


def test_partial_csv_diagnostic_checks_finished_rounds_but_never_passes_campaign(tmp_path):
    data,game,original=csv_record(tmp_path)
    current_boundary=copy.deepcopy(data['rounds'][2]['boundary'])
    final_tick=current_boundary['tick']
    data['rounds']=data['rounds'][:2]
    data['computedPlans']=data['computedPlans'][:3]
    data['computedPlans'][-1]['plan'].update(status='unknown',verified=False)
    data['tickEvidence']=[row for row in data['tickEvidence'] if row[0]<=final_tick]
    data['rows']=[row for row in data['rows'] if row['tick']<final_tick]+[current_boundary]
    data['events']=[event for event in data['events'] if event['tick']<final_tick]
    data['checkedTicks']=len(data['tickEvidence'])
    data.update(winObserved=False,result=dict(passed=False,status='unknown',rounds=2))
    diagnostic=diagnose_completed_csv_rounds(data,game_dir=game,original_dir=original)
    assert diagnostic['passed'] is False
    assert diagnostic['completed_rounds_valid'] is True,diagnostic['errors']
    assert diagnostic['summary']['completed_rounds']==2
    assert diagnostic['summary']['unfinished_attempts']==1
    assert diagnostic['summary']['matched_planned_input_ticks']==40
    assert not check(data,game,original)['passed']
    data['computedPlans'][0]['rows'].pop(4)
    diagnostic=diagnose_completed_csv_rounds(data,game_dir=game,original_dir=original)
    assert diagnostic['passed'] is diagnostic['completed_rounds_valid'] is False
    assert 'csv_controller_coverage' in {error['code'] for error in diagnostic['errors']}


def test_partial_csv_diagnostic_does_not_invent_success_before_first_endattack(tmp_path):
    data,game,original=csv_record(tmp_path)
    data['rounds']=[]
    diagnostic=diagnose_completed_csv_rounds(data,game_dir=game,original_dir=original)
    assert diagnostic['passed'] is False
    assert diagnostic['completed_rounds_valid'] is None
    assert diagnostic['summary']['completed_rounds']==0


def test_native_ajax_tlplay_phase_is_uniquely_derived_from_exact_current_tick_clock(tmp_path):
    data,game,original=csv_record(tmp_path)
    # Round 2's native AJAX callback fires between physical ticks. Its pre
    # source snapshot therefore retains the already committed current stamp.
    rnd=data['rounds'][1];pre=rnd['source']['preSnapshot'];attempt=data['computedPlans'][1]
    row=data['tickEvidence'][pre['tick']-data['tickEvidence'][0][0]]
    pre['clock_start_ms'],pre['dt']=row[8],row[7]
    # This fixture sits inside one binary64 clock bin, so only the timestamp
    # changes, not the dt-dependent source environment.
    assert pre['dt']==pre['initial_environment'][7]
    verdict=check(data,game,original)
    assert verdict['passed'],verdict['errors']
    phases=verdict['summary']['source_trigger_phases']
    assert phases[0]['phase']=='in_tick'
    assert phases[1]['phase']=='between_ticks'
    pre['clock_start_ms']=math.nextafter(pre['clock_start_ms'],math.inf)
    verdict=check(data,game,original)
    assert not verdict['passed']
    assert 'csv_source_trigger_phase' in {e['code'] for e in verdict['errors']}
