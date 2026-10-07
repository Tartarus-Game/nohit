"""An EOF witness includes real neutral inputs and an independently rebuilt tail."""
import copy
import json

import numpy as np
import pytest

from nohit.engine.csv_solver import solve_csv
from nohit.dashboard.csv_visualization import build_csv_visualization


INITIAL=[320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.]
SCHEDULE=(1/30,1/60,1/45)*100


def solve(tmp_path,text,**kwargs):
    path=tmp_path/'eof.csv';path.write_text(text,encoding='utf-8')
    settings=dict(dt_schedule=SCHEDULE,max_ticks=len(SCHEDULE),width=4,
                  termination_policy='eof_hazards_drained')
    settings.update(kwargs)
    return path,solve_csv(path,settings.pop('initial',INITIAL),**settings)


def check(path,result,schedule=SCHEDULE):
    assert result['status']=='candidate_found' and result['verified']
    completion=result['completion'];n=len(result['actions']);d=completion['drain_tick']
    assert completion['kind']=='eof_invariant' and completion['tick']==n==result['reached_tick']
    assert n-d>=2 and completion['release_start_tick']==d+1
    assert result['actions'][d:]==[0]*(n-d)
    assert result['confirm_sequence'][d:]==[False]*(n-d)
    assert len(result['trajectory'])==len(result['dt_sequence'])==n+1
    assert result['dt_sequence']==list(schedule[:n+1])
    assert np.asarray(completion['certificate']['invariant_state']).tobytes()==np.asarray(result['trajectory'][-1]).tobytes()
    assert result['trajectory'][-1][4]==0.
    assert completion['native_verified'] is False and not result['original_replay_passed']
    visual=build_csv_visualization(path,result,dt_schedule=schedule)
    assert visual['end_reason']=='eof_invariant' and visual['frame_count']==n+1
    assert [f['player'] for f in visual['frames']]==result['trajectory']
    assert [f['dt'] for f in visual['frames']]==result['dt_sequence']
    assert all(not f['white'] and not f['blue'] and not f['platforms'] and not f['polygons']
               for f in visual['frames'][d+1:])
    json.dumps(result,allow_nan=False)


def test_zero_tick_eof_physically_releases_existing_motion_and_input(tmp_path):
    initial=INITIAL.copy();initial[2]=150.;initial[4]=2.
    path,result=solve(tmp_path,'0,HeartMode,0\n',initial=initial)
    check(path,result)
    assert result['completion']['drain_tick']==0
    assert result['trajectory'][0]==initial
    assert result['trajectory'][1][0]==320.+150.*SCHEDULE[1]
    assert result['trajectory'][1][2]==0. and result['trajectory'][1][4]==0.
    assert result['trajectory'][1]==result['trajectory'][2]


def test_blue_eof_settles_under_the_exact_clock_before_certifying(tmp_path):
    bounds=[100.,100.,540.,420.]
    environment=bounds+[1.,1.,0.,SCHEDULE[0],750.,0.,0.,0.,0.,0.]+bounds+bounds
    initial=INITIAL.copy();initial[1]=400.;initial[6]=1.
    path,result=solve(tmp_path,'0,Sound,x\n',initial=initial,initial_environment=environment)
    assert result['status']=='candidate_found'
    completion=result['completion']
    assert completion['release_tick_count']>2
    assert result['trajectory'][-1][3]==0. and result['trajectory'][-1][1]>400.
    visual=build_csv_visualization(path,result,initial_environment=environment,dt_schedule=SCHEDULE)
    assert [frame['player'] for frame in visual['frames']]==result['trajectory']
    assert result['dt_sequence']==list(SCHEDULE[:len(result['actions'])+1])


@pytest.mark.parametrize('prefix',['','0,HeartMode,0\n0.1,Sound,x\n'])
def test_dialogue_eof_keeps_real_confirm_and_absolute_tail_clock(tmp_path,prefix):
    path,result=solve(tmp_path,prefix+'0,SansText,a,\n')
    check(path,result)
    assert any(result['confirm_sequence'])
    assert result['completion']['drain_tick']>=result['dialogue_start_tick']


def test_audited_absent_functions_keep_their_delays(tmp_path):
    path,result=solve(tmp_path,'0,HeartMode,0\n0.1,Score,Flash\n0.1,mus_zz_megalovania,20\n')
    check(path,result)
    _,reference=solve(tmp_path,'0,HeartMode,0\n0.1,Sound,Flash\n0.1,Sound,20\n')
    assert result['completion']['drain_tick']==reference['completion']['drain_tick']>0
    assert result['dt_sequence']==reference['dt_sequence']
    assert result['trajectory']==reference['trajectory']


@pytest.mark.parametrize('text',[
    '0,Platform,100,350,40,0,0\n',
    '0,SansText,a,\n0,GetHeartPos,x,y\n',
    '0,AnUnauditedFunction,x\n',
    '0,SansText,a,UnprovenCallback\n',
    '0,GasterBlaster,0,0,0,50,50,17,10,0.1\n',
])
def test_unproved_worlds_never_publish_an_eof_candidate(tmp_path,text):
    _,result=solve(tmp_path,text)
    assert result['status']=='unknown' and not result['verified']
    assert result['actions']==[] and 'completion' not in result
    assert not result['deadlock_proven']


def test_insufficient_clock_does_not_fake_neutral_latches(tmp_path):
    _,result=solve(tmp_path,'0,HeartMode,0\n',dt_schedule=(1/30,)*2,max_ticks=2)
    assert result['status']=='unknown' and not result['verified']
    assert result.get('terminal_reasons')==['neutral_release_clock_exhausted']


def test_default_policy_still_requires_endattack(tmp_path):
    path=tmp_path/'default.csv';path.write_text('0,HeartMode,0\n')
    result=solve_csv(path,INITIAL,dt_schedule=SCHEDULE,max_ticks=len(SCHEDULE),width=1)
    assert result['status']=='unknown' and {'reason':'missing_endattack'} in result['issues']


def test_explicit_eof_policy_keeps_an_actual_endattack(tmp_path):
    path,result=solve(tmp_path,'0,HeartMode,0\n0.1,EndAttack\n')
    assert result['completion']['kind']=='endattack'
    assert 'certificate' not in result['completion']
    visual=build_csv_visualization(path,result,dt_schedule=SCHEDULE)
    assert visual['end_reason']=='endattack'


@pytest.mark.parametrize('change',[
    lambda r:r['completion'].__setitem__('native_verified',True),
    lambda r:r['completion'].__setitem__('drain_tick',1),
    lambda r:r['completion']['certificate'].__setitem__('policy_confirm',True),
    lambda r:r['completion']['certificate']['terminal_details'].__setitem__('active_platforms',1),
    lambda r:r['actions'].__setitem__(-1,2),
    lambda r:r['confirm_sequence'].__setitem__(-1,True),
    lambda r:r['dt_sequence'].__setitem__(-1,1/240),
])
def test_eof_visualization_rejects_forged_tail_evidence(tmp_path,change):
    path,result=solve(tmp_path,'0,HeartMode,0\n')
    changed=copy.deepcopy(result);change(changed)
    with pytest.raises(ValueError):build_csv_visualization(path,changed,dt_schedule=SCHEDULE)


@pytest.mark.parametrize('delta',[-1,1])
def test_self_consistent_tail_length_tampering_is_still_rejected(tmp_path,delta):
    path,result=solve(tmp_path,'0,HeartMode,0\n')
    changed=copy.deepcopy(result)
    for key in ('actions','confirm_sequence','unified_controls','trajectory','dt_sequence'):
        if delta<0:changed[key].pop()
        else:changed[key].append(copy.deepcopy(changed[key][-1]))
    n=len(changed['actions'])
    changed['reached_tick']=n;changed['completion']['tick']=n
    changed['completion']['release_tick_count']=n
    changed['dt_sequence']=list(SCHEDULE[:n+1])
    with pytest.raises(ValueError):build_csv_visualization(path,changed,dt_schedule=SCHEDULE)
