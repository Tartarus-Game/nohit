"""Source-derived EOF evidence schemas and adversarial verifier mutations.

These synthetic records test the independent verifier. They are not native
captures and must never be reported as a successful original-game replay.
Existing captured EndAttack fixtures remain in the companion verifier tests.
"""
import copy
import ast
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

import pytest

from tools.verify_csv_native_acceptance import (EOF_ATTACK_TYPES, EOF_CALLBACK_CONTRACT,
    EOF_FAMILIES, EOF_OWNED_KEYS, EOF_RPG_TYPES, EOF_SOURCE_HASHES, verify_record)


@pytest.fixture(scope='module')
def native_export_roundtrip():
    """Parse original export in real JS, then serialize as native evidence does."""
    root = Path(__file__).resolve().parents[2]
    source = root / 'jcw87-c2-sans-fight/data.js'
    assert hashlib.sha256(source.read_bytes()).hexdigest() == EOF_SOURCE_HASHES['data.js']
    node = shutil.which('node')
    if node is None:
        pytest.skip('JavaScript export round-trip regression requires Node.js')
    result = subprocess.run([node, '-e',
        r'const fs=require("fs"); const p=JSON.parse(fs.readFileSync(process.argv[1],"utf8").replace(/^\uFEFF/,"")); process.stdout.write(JSON.stringify(p));',
        str(source)], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)['project']


def test_all_verifier_sid_literals_exist_after_native_javascript_roundtrip(native_export_roundtrip):
    # Python preserves integer source spellings; native JS first rounds them to
    # binary64. Verify every SID literal independently of the schema builder.
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / 'tools/verify_csv_native_acceptance.py').read_text(encoding='utf-8'))
    expected = {n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and type(n.value) is int and n.value > 10**12}
    actual = set()
    def visit(value):
        if type(value) is int:
            actual.add(value)
        elif isinstance(value, list):
            for item in value:visit(item)
        elif isinstance(value, dict):
            for item in value.values():visit(item)
    visit(native_export_roundtrip)
    assert not expected - actual, f'Non-native SID spellings: {sorted(expected - actual)}'


def test_complete_eof_inventories_match_original_export_in_javascript(native_export_roundtrip):
    types, memberships = native_export_roundtrip[3:5]
    sid = lambda index: types[index][11]
    # These original type indices are independent of verifier constants.
    families = {sid(row[0]): {sid(i) for i in row[1:]}
                for row in memberships if row[0] in (69, 70, 71)}
    assert EOF_FAMILIES == families
    assert EOF_ATTACK_TYPES == {sid(i) for i in range(29, 43)}
    rpg = next(row for row in memberships if row[0] == 67)
    assert EOF_RPG_TYPES == {sid(i) for i in rpg[1:]}


def synthetic_eof(*, blue=False):
    source='0,HeartMode,'+('1' if blue else '0')+'\n'
    digest=hashlib.sha256(source.encode()).hexdigest()
    bounds=[33.,251.,608.,391.]
    mode=1 if blue else 0
    state=[320.,378. if blue else 320.,0.,0.,0.,0.,mode,1.,750.,0.,0.]
    env=[*bounds,mode,1.,0.,1/30,750.,0.,0.,0.,0.,0.,*bounds,*bounds]
    arena=dict(target=bounds,size=[575.,140.],speed=480.,callback='')
    step=1000/30+1e-6
    stamps=[1000.]
    for _ in range(2):stamps.append(stamps[-1]+step)
    rows=[]
    native=[]
    physical=[]
    for i in range(3):
        common=dict(tick=100+i,time=10.+sum([1/30]*i),clock_start_ms=stamps[i],dt=1/30,
            HP=92,KR=0,line=2,T=(i+1)/30,running=1)
        rows.append(dict(**common,state=state.copy(),vpad=[0]*14,mask=0,confirm=False))
        native.append(dict(**common,SimulatorMode=2,attack='custom',lineCount=1,keymask=0,confirm=0,
            state=state.copy(),arena=bounds.copy(),arenaTarget=bounds.copy(),resizeSpeed=480.,endResize='',pending=[]))
        physical.append(dict(**common,initial=state.copy(),initial_environment=env.copy(),
            timeline=common['T'],
            arena=copy.deepcopy(arena),vpad=[0]*14,physical_keymask=0,physical_confirm=False,
            initial_confirm=False,previous_confirm=False,SimulatorMode=2,SingleAttack='custom',
            rpgtext=[dict(uid=uid,typeSid=6163397057824361,familyOffset=0,
                vars=[name,'','','',0,0,(i+1)/30,0],fields=[name,'','','',0,0,(i+1)/30,0])
                for uid,name in ((28,'HP'),(6,'PlayerName'),(97,'QuitMessage'))]))
    keys=[dict(code=k,pressed=False) for k in sorted(EOF_OWNED_KEYS)]
    def geometry(sid,uid,x,y,width,height,angle,bbox):
        return dict(typeSid=sid,uid=uid,x=x,y=y,width=width,height=height,angle=angle,
            bbox=bbox,collisions_enabled=True,collision_polygon=None)
    heart=geometry(5960708907117077,10,state[0],state[1],16,16,math.pi/2,
        [state[0]-8,state[1]-8,state[0]+8,state[1]+8])
    heart['collision_polygon']=[-.5,.5,-.5,-.5,.5,-.5,.5,.5]
    l,t,r,b=bounds
    borders=[geometry(6657741784745805,20+i,box[0],box[1],box[2]-box[0],box[3]-box[1],0,box)
        for i,box in enumerate([[l,t,r,t+5],[l,t,l+5,b],[l,b-5,r,b],[r-5,t,r,b]])]
    def facts(i):
        return dict(schema_version=1,tick=100+i,capture_phase='posttick',physical=copy.deepcopy(physical[i]),
            timeline=dict(line=2,width=1,width_field='ra',list_sid=456555951765879),
            attack_types=[dict(sid=sid,count=0) for sid in sorted(EOF_ATTACK_TYPES)],
            attack_families=[dict(sid=sid,members=sorted(members)) for sid,members in EOF_FAMILIES.items()],
            rpgtext_family=dict(sid=8627438680975019,members=sorted(EOF_RPG_TYPES)),
            rpgtext_types=[dict(sid=sid,count=3 if sid==6163397057824361 else 0) for sid in sorted(EOF_RPG_TYPES)],
            rpgtext_policy='original-passive-ui-v1',
            wait_queue=dict(field='Hd.fc',is_array=True,length=0,entries=[]),
            pending_layout=dict(field='ih',present=True,value=None),loading=False,
            layout=dict(sid=8667945925241823,name='BattleScreen'),owned_keys=copy.deepcopy(keys),
            globals=dict(SimulatorMode=2,SingleAttack='custom'),menu_state=dict(sid=5359025861573384,value=0),
            heart_geometry=copy.deepcopy(heart),borders=copy.deepcopy(borders),
            callback_contract=EOF_CALLBACK_CONTRACT,source_sha256=EOF_SOURCE_HASHES.copy())
    final_facts=facts(2)
    final_facts['drain_snapshot']=facts(0)
    final_facts['release_snapshots']=[dict(physical=copy.deepcopy(physical[i]),owned_keys=copy.deepcopy(keys)) for i in (1,2)]
    details=dict(timeline_exhausted=True,pending_callbacks=[],pending_dialogue=None,
        active_bones=0,active_stabs=0,active_blasters=0,active_platforms=0,
        arena_settled=True,end_resize=None,initial_callback_contract='explicit_initial_arena')
    completion=dict(schema_version=1,kind='eof_invariant',tick=2,eof_tick=0,drain_tick=0,
        release_start_tick=1,release_tick_count=2,model_verified=True,native_verified=False,
        certificate=dict(status='proven',proof='static-empty-release-fixed-point-v1',policy_mask=0,
            policy_confirm=False,invariant_state=state.copy(),static_environment=env.copy(),terminal_details=details))
    plan=dict(status='candidate_found',verified=True,control_ticks=1,clock_protocol='explicit_dt_schedule',
        physics_hz=30,control_hz=30,actions=[0,0],confirm_sequence=[False,False],
        trajectory=[state.copy() for _ in range(3)],dt_sequence=[1/30]*3,csv_sha256=digest,
        initial_environment=env.copy(),initial_confirm=False,previous_confirm=False,target_history=[],
        termination_policy='eof_hazards_drained',reached_tick=2,completion=completion)
    boundary=copy.deepcopy(physical[0])
    controller=dict(version=1,status='completed',error=None,nativeEndAttack=False,firstDamage=None,
        csv_sha256=digest,plan=plan,boundary=boundary,rows=rows,actionsApplied=2,
        events=[dict(tick=99,fn='tlplay')],original_replay_passed=False)
    entry=copy.deepcopy(native[0]);entry['tick']=99
    observer=dict(version=1,started=True,status='incomplete_eof',errors=[],firstDamage=None,
        sourceText=source,csv_sha256=digest,csv_bytes=len(source.encode()),entry=entry,
        rows=native,events=[dict(tick=99,fn='tlplay',args=[])],eofObserved=True,
        eofSnapshot=copy.deepcopy(native[0]),eofTerminal=final_facts,
        ticks=[[100+i,92,0,2,0,0,2,(i+1)/30,1,0] for i in range(3)],lifecycles=[])
    return dict(controller=controller,observer=observer,finalSnapshot=copy.deepcopy(native[-1]),
        clock=dict(mode='fixed-30hz-native-clamp',logicalStepMs=step))


def rejected(data,code):
    verdict=verify_record(data)
    assert not verdict['passed'],verdict
    assert code in {e['code'] for e in verdict['errors']},verdict['errors']
    return verdict


@pytest.mark.parametrize('blue',[False,True])
def test_source_derived_closed_eof_schema_passes_without_endattack_or_win(blue):
    result=verify_record(synthetic_eof(blue=blue))
    assert result['passed'],result['errors']
    summary=result['summary']
    assert summary['completion_kind']=='eof_invariant'
    assert summary['safe_forever_under_release'] is True
    assert summary['original_replay_passed'] is True
    assert summary['nativeEndAttack'] is summary['complete_in_original_game'] is False
    assert summary['compared_state_components']==33


def test_only_passive_original_ui_persists_while_its_clock_increases():
    data=synthetic_eof()
    facts=data['observer']['eofTerminal']
    first=facts['drain_snapshot']['physical']['rpgtext']
    last=facts['physical']['rpgtext']
    assert {v['fields'][0] for v in last}=={'HP','PlayerName','QuitMessage'}
    assert all(a['fields'][6]<b['fields'][6] for a,b in zip(first,last))
    verdict=verify_record(data)
    assert verdict['passed'],verdict['errors']


@pytest.mark.parametrize('where',['final','drain'])
@pytest.mark.parametrize('field,value',[(0,'UnexpectedUI'),(1,'Sans'),(2,'x'),(3,'TLResume'),
    (4,1),(5,1),(6,-1),(6,float('inf')),(6,float('nan')),(7,1),(4,False)])
def test_passive_ui_any_active_or_malformed_family_field_is_rejected(where,field,value):
    data=synthetic_eof()
    facts=data['observer']['eofTerminal']
    if where=='drain':facts=facts['drain_snapshot']
    row=facts['physical']['rpgtext'][0]
    row['fields'][field]=value
    row['vars'][field]=value
    rejected(data,'eof_dialogue')


@pytest.mark.parametrize('where',['final','drain'])
@pytest.mark.parametrize('mutation',['missing','extra','duplicate_uid','duplicate_name',
    'wrong_sid','offset','short_vars','unequal_fields','missing_policy','wrong_count','extra_member','malformed'])
def test_passive_ui_exact_inventory_and_original_field_layout_are_required(where,mutation):
    data=synthetic_eof()
    facts=data['observer']['eofTerminal']
    if where=='drain':facts=facts['drain_snapshot']
    rows=facts['physical']['rpgtext']
    if mutation=='missing':rows.pop()
    elif mutation=='extra':rows.append(copy.deepcopy(rows[0]))
    elif mutation=='duplicate_uid':rows[1]['uid']=rows[0]['uid']
    elif mutation=='duplicate_name':rows[1]['fields'][0]=rows[1]['vars'][0]=rows[0]['fields'][0]
    elif mutation=='wrong_sid':rows[0]['typeSid']=1422059525027614
    elif mutation=='offset':rows[0]['familyOffset']=1
    elif mutation=='short_vars':rows[0]['vars'].pop()
    elif mutation=='unequal_fields':rows[0]['vars'][3]='TLResume'
    elif mutation=='missing_policy':facts.pop('rpgtext_policy')
    elif mutation=='wrong_count':next(v for v in facts['rpgtext_types'] if v['sid']==6163397057824361)['count']=0
    elif mutation=='extra_member':next(v for v in facts['rpgtext_types'] if v['sid']==1422059525027614)['count']=1
    elif mutation=='malformed':rows[0]=None
    rejected(data,'eof_dialogue')


def test_replacement_passive_ui_uid_after_drain_is_rejected():
    data=synthetic_eof()
    facts=data['observer']['eofTerminal']
    facts['physical']['rpgtext'][0]['uid']=999
    facts['release_snapshots'][-1]['physical']['rpgtext'][0]['uid']=999
    rejected(data,'eof_dialogue_identity')


@pytest.mark.parametrize('field',list(range(11)))
def test_every_final_component_is_checked_without_menu_exception(field):
    data=synthetic_eof()
    data['controller']['plan']['trajectory'][-1][field]+=1e-9
    rejected(data,'trajectory_mismatch')


@pytest.mark.parametrize('field,code',[
    ('physical','eof_physical'),('timeline','eof_timeline'),('attack_types','eof_attack_types'),
    ('attack_families','eof_attack_families'),('rpgtext_family','eof_dialogue'),
    ('rpgtext_types','eof_dialogue'),('wait_queue','eof_wait_queue'),('pending_layout','eof_layout'),
    ('loading','eof_layout'),('layout','eof_layout'),('globals','eof_layout'),('menu_state','eof_layout'),
    ('owned_keys','eof_inputs'),('heart_geometry','eof_geometry'),('borders','eof_geometry'),
    ('release_snapshots','eof_release_observation'),('source_sha256','eof_source_contract'),
    ('callback_contract','eof_source_contract'),('drain_snapshot','eof_drain_snapshot'),
])
def test_missing_native_obligation_is_not_inferred_from_completed_status(field,code):
    data=synthetic_eof()
    data['observer']['eofTerminal'].pop(field)
    rejected(data,code)


def test_model_proven_and_forged_status_cannot_replace_native_facts():
    data=synthetic_eof()
    data['observer'].pop('eofTerminal')
    data['observer'].update(status='completed',terminalCertified=True,stableTailTicks=10000)
    rejected(data,'eof_native_facts')


@pytest.mark.parametrize('where',['final','drain'])
@pytest.mark.parametrize('kind',['head','platform','wait','dialogue','resize','layout','source'])
def test_pending_source_obligations_fail_at_both_drain_and_terminal(where,kind):
    data=synthetic_eof()
    facts=data['observer']['eofTerminal']
    if where=='drain':facts=facts['drain_snapshot']
    if kind in ('head','platform'):
        sid=9836012384209520 if kind=='head' else 1226268899238104
        next(v for v in facts['attack_types'] if v['sid']==sid)['count']=1
        code='eof_active_entities'
    elif kind=='wait':
        facts['wait_queue'].update(length=1,entries=[dict(ev=123,t=99.)]);code='eof_wait_queue'
    elif kind=='dialogue':
        facts['rpgtext_types'][0]['count']=1;code='eof_dialogue'
    elif kind=='resize':
        facts['physical']['arena']['callback']='TLResume';code='eof_arena'
    elif kind=='layout':
        facts['pending_layout']['value']={'name':'GameOver'};code='eof_layout'
    else:
        facts['source_sha256']['data.js']='0'*64;code='eof_source_contract'
    rejected(data,code)


@pytest.mark.parametrize('where',['final','drain'])
@pytest.mark.parametrize('field,native_sid,source_sid,code',[
    ('attack_families',9784977049754560,9784977049754561,'eof_attack_families'),
    ('attack_types',9836012384209520,9836012384209519,'eof_attack_types'),
])
def test_non_native_source_integer_spelling_is_rejected_without_input_normalization(
        where,field,native_sid,source_sid,code):
    data=synthetic_eof()
    facts=data['observer']['eofTerminal']
    if where=='drain':facts=facts['drain_snapshot']
    next(row for row in facts[field] if row['sid']==native_sid)['sid']=source_sid
    rejected(data,code)


@pytest.mark.parametrize('index',range(14))
def test_all_fourteen_vpad_fields_must_be_zero_at_endpoint(index):
    data=synthetic_eof()
    data['observer']['eofTerminal']['physical']['vpad'][index]=1
    rejected(data,'eof_inputs')


@pytest.mark.parametrize('mutate,code',[
    (lambda d:d['controller']['plan']['completion'].__setitem__('drain_tick',1),'eof_completion_ticks'),
    (lambda d:d['controller']['plan']['completion'].__setitem__('release_tick_count',1),'eof_completion_ticks'),
    (lambda d:d['controller']['plan']['confirm_sequence'].__setitem__(0,True),'eof_release_controls'),
    (lambda d:d['controller']['plan']['actions'].__setitem__(0,2),'eof_release_controls'),
    (lambda d:d['observer']['eofTerminal']['release_snapshots'].pop(),'eof_release_observation'),
    (lambda d:d['observer']['eofTerminal']['release_snapshots'].reverse(),'eof_release_observation'),
    (lambda d:d['observer']['eofTerminal']['owned_keys'][0].__setitem__('pressed',True),'eof_inputs'),
    (lambda d:d['observer']['eofTerminal']['wait_queue'].pop('is_array'),'eof_wait_queue'),
    (lambda d:d['observer']['eofTerminal']['pending_layout'].pop('value'),'eof_layout'),
    (lambda d:d['observer']['eofSnapshot'].__setitem__('tick',101),'eof_observation'),
    (lambda d:d['observer']['eofTerminal']['drain_snapshot'].__setitem__('tick',101),'eof_native_schema'),
    (lambda d:d['controller']['plan']['completion'].__setitem__('schema_version',2),'completion_schema'),
    (lambda d:d['controller']['plan']['completion'].__setitem__('native_verified',True),'completion_schema'),
    (lambda d:d['controller']['plan'].__setitem__('termination_policy','endattack'),'eof_policy'),
])
def test_rejects_release_schedule_and_native_provenance_tampering(mutate,code):
    data=synthetic_eof();mutate(data);rejected(data,code)


@pytest.mark.parametrize('name',['endattack','resetvars','tlstop'])
def test_eof_cannot_hide_native_end_or_reset(name):
    data=synthetic_eof()
    for owner in ('controller','observer'):
        data[owner]['events'].append(dict(tick=101,fn=name,args=[]))
    rejected(data,'eof_unexpected_end')


def test_native_stationary_blue_midair_is_not_a_fixed_point():
    data=synthetic_eof(blue=True)
    # Preserve all cross-record equality while changing the entire synthetic
    # trajectory to stationary midair; only the native analytic proof rejects.
    def change(value):
        if isinstance(value,dict):
            for k,v in value.items():
                if k in ('state','initial','invariant_state') and isinstance(v,list):v[1]=320.
                elif k=='trajectory':
                    for row in v:row[1]=320.
                elif k=='heart_geometry':v['y']=320.;v['bbox']=[312.,312.,328.,328.]
                else:change(v)
        elif isinstance(value,list):
            for v in value:change(v)
    change(data)
    rejected(data,'eof_blue_support')


def test_inactive_teleport_coordinates_and_proof_dt_are_not_active_effects():
    data=synthetic_eof()
    env=data['controller']['plan']['completion']['certificate']['static_environment']
    env[7]=1/240;env[10:12]=[123.,456.]
    assert verify_record(data)['passed']
    env[9]=1
    rejected(data,'eof_environment')


def test_running_one_and_growing_t_are_allowed_by_subsystem_closure():
    data=synthetic_eof()
    assert data['observer']['ticks'][-1][7]>data['observer']['ticks'][0][7]
    assert all(row[8]==1 for row in data['observer']['ticks'])
    assert verify_record(data)['passed']


@pytest.mark.parametrize('mutate,code',[
    (lambda d:d['observer']['eofTerminal']['borders'][2].__setitem__('collisions_enabled',False),'eof_geometry'),
    (lambda d:d['observer']['eofTerminal']['borders'].pop(),'eof_geometry'),
    (lambda d:d['observer']['eofTerminal']['heart_geometry'].__setitem__('collision_polygon',None),'eof_geometry'),
    (lambda d:d['finalSnapshot'].__setitem__('endResize','TLResume'),'eof_arena'),
    (lambda d:d['finalSnapshot'].__setitem__('arenaTarget',[0,0,10,10]),'eof_arena'),
    (lambda d:d['controller']['plan']['completion'].__setitem__('release_start_tick',True),'eof_completion_ticks'),
])
def test_native_geometry_and_terminal_details_cannot_be_replaced(mutate,code):
    data=synthetic_eof(blue=True);mutate(data);rejected(data,code)


@pytest.mark.parametrize('owner,key,value,code',[
    ('physical','arena',None,'eof_arena'),
    ('physical','initial',None,'eof_physical'),
    ('physical','initial_environment',[0]*21,'eof_physical'),
    ('timeline','line','2','eof_timeline'),
    ('timeline','width',True,'eof_observation'),
    ('wait_queue','length',False,'eof_wait_queue'),
])
def test_malformed_nested_native_facts_return_rejection_without_raising(owner,key,value,code):
    data=synthetic_eof()
    data['observer']['eofTerminal'][owner][key]=value
    rejected(data,code)


def test_two_actual_neutral_ticks_clear_prior_confirm_without_assuming_first_latch_zero():
    data=synthetic_eof()
    c,o=data['controller'],data['observer']
    c['boundary']['vpad'][4]=1
    c['boundary']['initial_confirm']=True
    c['plan']['initial_confirm']=True
    c['rows'][0]['vpad'][4]=1
    c['rows'][1]['vpad'][11]=1
    o['rows'][0]['confirm']=1
    o['eofSnapshot']['confirm']=1
    o['ticks'][0][5]=1
    drain=o['eofTerminal']['drain_snapshot']['physical']
    drain['vpad'][4]=1
    drain['initial_confirm']=drain['physical_confirm']=True
    released=o['eofTerminal']['release_snapshots'][0]['physical']
    released['vpad'][11]=1
    released['previous_confirm']=True
    verdict=verify_record(data)
    assert verdict['passed'],verdict['errors']
