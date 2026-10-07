"""Differential and compositional tests against the unchanged monolithic VM.

All observations here are explicit test inputs. No native checkpoints or
runtime damage feedback are used to generate routes or target histories.
"""
import copy
import csv
from pathlib import Path

import numpy as np
import pytest

from nohit.engine.compact_wave import compile_wave
from nohit.engine.resumable_wave import (
    initialize,advance_one_tick,supply_target,preview_observation_frame,
    TickCommitted,Terminal,NeedTarget,NeedDialogue,ResourceLimit,
)


INITIAL_ENV=[133.,251.,508.,391.,0.,1.,0.,1/240,750.,0.,320.,304.,0.]


def source(tmp_path,text,name='source.csv'):
    path=tmp_path/name;path.write_text(text)
    return path


def bits_equal(actual,expected):
    actual=np.asarray(actual,dtype=np.float64)
    expected=np.asarray(expected,dtype=np.float64)
    assert actual.shape==expected.shape
    assert actual.tobytes()==expected.tobytes()


def frame_matches(frame,wave,tick):
    bits_equal(frame.env,wave.env_schedule[tick])
    platforms=wave.platform_table[tick]
    bits_equal(frame.platforms,platforms[(platforms[:,6]!=0)|(platforms[:,7]!=0)])
    for name,attribute in (('white','geometry_white'),('blue','geometry_blue'),('polygons','geometry_polygons')):
        values=getattr(wave,attribute)[tick]
        values=values[np.isfinite(values).all(axis=1)]
        bits_equal(getattr(frame,name),values)
    assert tuple(frame.events)==tuple(event for event in wave.source_events if event[0]==tick)
    assert tuple(frame.target_history)==tuple(event for event in wave.target_history if event[0]==tick)


def default_observation(request):
    return (110.+request['line']%11,220.+request['tick']%7)


def drive(state,observations=None):
    frames=[];samples={};checkpoints=[state]
    for _ in range(5000):
        before=copy.deepcopy(state.stats)
        result=advance_one_tick(state)
        assert state.stats==before  # advancing may not mutate a shared parent
        if isinstance(result,NeedTarget):
            request=result.request;key=(request['tick'],request['line'])
            sample=observations[key] if observations is not None else default_observation(request)
            if request['preceding_teleport'] is not None:sample=request['preceding_teleport']
            samples[key]=tuple(sample)
            state=supply_target(result,tuple(sample))
            continue
        if isinstance(result,(TickCommitted,Terminal)):
            if result.frame is not None:
                frames.append(result.frame);checkpoints.append(result.state)
            state=result.state
            if isinstance(result,Terminal):return frames,state,samples,checkpoints,result
            continue
        assert isinstance(result,(NeedDialogue,ResourceLimit))
        return frames,result.state,samples,checkpoints,result
    raise AssertionError('resumable source failed to reach a bounded result')


CASES=[
    ('entities',
     '0,CombatZoneResizeInstant,100,100,500,400\n'
     '0,Platform,110,350,50,0,120,1\n0,Platform,250,320,40,1,80,1\n'
     '0,BoneV,480,100,120,2,100,1\n0,BoneH,120,220,50,0,30\n'
     '0,BoneStab,1,30,0.0125,0.04\n'
     '0,GasterBlaster,0,0,240,250,250,35,0.0125,0.01\n'
     '0.020833,CombatZoneResize,140,120,480,390\n'
     '0.008333,HeartTeleport,320,304\n0.008333,SansSlam,3\n'
     '0.008333,BlackScreen,1\n0.025,EndAttack\n',{}),
    ('multiple_targets',
     '0,HeartMode,0\n0,Set,HeartY,17\n'
     '0.008333,GetHeartPos,HeartY,$HeartY\n0,BoneV,$17,$HeartY,10,0,0\n'
     '0,HeartTeleport,250,300\n0,GetHeartPos,x,y\n0,Add,x,$x,5\n'
     '0,GetHeartPos,x,y\n0,GasterBlaster,0,0,240,$x,$y,0,0.01,0.02\n'
     '0.05,EndAttack\n',{}),
    ('rng_reload_loop',
     '0,Set,n,3\n0,Rnd,x,100\n0,BoneV,$x,100,12,0,100\n'
     '0,Sub,n,$n,1\n0,JmpNZ,2,$n\n0.05,EndAttack\n',{'seed':123}),
    ('loaded_delay',
     '0,Set,delay,0.0125\n0,Set,value,17\n'
     '$delay,BoneV,$value,100,12,0,100\n0.025,EndAttack\n',{}),
    ('callback',
     '0,CombatZoneResize,241,226,406,391,TLResume\n0.5,EndAttack\n',
     {'initial_environment':INITIAL_ENV,'clock_start_ms':93108.33333335018}),
    ('eof_beam','0,GasterBlaster,1,320,240,320,240,0,0.2,0.1\n',
     {'termination_policy':'eof_hazards_drained','max_ticks':1000}),
    ('eof_platform','0,Platform,200,300,60,0,0\n',
     {'termination_policy':'eof_hazards_drained'}),
    ('budget','0,GasterBlaster,1,320,240,320,240,0,1,0.1\n',
     {'termination_policy':'eof_hazards_drained','max_ticks':8}),
]


@pytest.mark.parametrize('name,text,options',CASES)
def test_full_committed_output_matches_old_compiler_bit_for_bit(tmp_path,name,text,options):
    path=source(tmp_path,text,name+'.csv')
    options=dict({'max_ticks':1000},**options)
    frames,state,samples,_,result=drive(initialize(path,**options))
    old=compile_wave(path,heart_samples=samples,**options)
    assert len(frames)==len(old.env_schedule)
    for tick,frame in enumerate(frames):frame_matches(frame,old,tick)
    assert state.stats['ticks_committed']==len(frames)
    assert isinstance(result,Terminal)==old.complete
    assert result.reason==old.termination_reason


def test_every_committed_tick_can_be_cloned_and_resumed_without_prefix_work(tmp_path):
    path=source(tmp_path,
        '0,Platform,200,350,60,0,80,1\n0.0125,GetHeartPos,x,y\n'
        '0,BoneV,$x,100,15,0,70\n0.025,BlackScreen,1\n0.0125,EndAttack\n')
    frames,final,samples,checkpoints,_=drive(initialize(path,max_ticks=100))
    old=compile_wave(path,heart_samples=samples,max_ticks=100)
    for cut,checkpoint in enumerate(checkpoints):
        counts=dict(checkpoint.stats)
        resumed,branch,_,_,_=drive(checkpoint.clone(),samples)
        assert len(resumed)==len(frames)-cut
        for offset,frame in enumerate(resumed):frame_matches(frame,old,cut+offset)
        assert checkpoint.stats==counts
        assert branch.stats['ticks_committed']-counts['ticks_committed']==len(resumed)
        assert branch.stats['commands_executed']==final.stats['commands_executed']


def test_observation_boundary_forks_reuse_prefix_and_match_two_full_oracles(tmp_path):
    path=source(tmp_path,
        '0,HeartMode,0\n0,Rnd,color,2\n0.025,GetHeartPos,x,y\n'
        '0,BoneV,$x,$y,20,0,80,$color\n0.025,EndAttack\n')
    state=initialize(path,max_ticks=100);prefix=[]
    while True:
        result=advance_one_tick(state)
        if isinstance(result,NeedTarget):break
        assert isinstance(result,TickCommitted)
        prefix.append(result.frame);state=result.state
    fork=result;before=copy.deepcopy(fork.state.stats);totals=[];suffixes=[]
    for sample in ((100.,200.),(200.,250.)):
        branch=supply_target(fork.state.clone(),sample)
        suffix,finished,_,_,terminal=drive(branch)
        assert isinstance(terminal,Terminal)
        observations={(fork.request['tick'],fork.request['line']):sample}
        old=compile_wave(path,heart_samples=observations,max_ticks=100)
        for tick,frame in enumerate(prefix+suffix):frame_matches(frame,old,tick)
        assert len(prefix)+len(suffix)==len(old.env_schedule)
        totals.append(finished.stats['ticks_committed']);suffixes.append(suffix)
    assert fork.state.stats==before
    prefix_work=before['ticks_committed']
    assert prefix_work==len(prefix)>0
    actual_work=prefix_work+sum(total-prefix_work for total in totals)
    monolithic_work=sum(totals)
    assert actual_work==monolithic_work-prefix_work<monolithic_work
    assert suffixes[0][0].white.tobytes()!=suffixes[1][0].white.tobytes()


def test_dialogue_is_an_uncommitted_boundary_not_a_fake_terminal(tmp_path):
    path=source(tmp_path,'0.0125,SansText,hello\n0,GasterBlaster,1,320,240,320,240,0,0,0\n')
    options=dict(termination_policy='eof_hazards_drained',max_ticks=100)
    frames,_,_,_,result=drive(initialize(path,**options))
    assert isinstance(result,NeedDialogue)
    old=compile_wave(path,**options)
    assert not old.complete and old.termination_reason=='dialogue_boundary'
    # The legacy compiler emits a pseudo-row after stopping dispatch. Only
    # genuinely committed prior ticks are eligible for continuation/equality.
    assert len(frames)==len(old.env_schedule)-1
    for tick,frame in enumerate(frames):frame_matches(frame,old,tick)


def test_await_target_is_idempotent_and_keeps_loaded_destination_snapshot(tmp_path):
    path=source(tmp_path,'0,Set,HeartY,17\n0,GetHeartPos,HeartY,$HeartY\n0,EndAttack\n')
    request=advance_one_tick(initialize(path,max_ticks=100))
    assert isinstance(request,NeedTarget)
    before=copy.deepcopy(request.state.stats)
    for _ in range(3):
        repeated=advance_one_tick(request.state)
        assert isinstance(repeated,NeedTarget) and repeated.request==request.request
        assert repeated.state.stats==before
    branch=request.state.clone()
    # Deliberate environment mutation checks that the suspended loaded row is
    # a value snapshot. Resume must not load "$HeartY" a second time.
    branch.vm.vars['HeartY']=999.
    frames,finished,_,_,terminal=drive(supply_target(branch,(123.,456.)))
    assert isinstance(terminal,Terminal)
    assert finished.vm.vars['HeartY']==123.
    assert finished.vm.vars['17']==456.
    assert '999' not in finished.vm.vars and '$HeartY' not in finished.vm.vars
    assert request.state.stats==before
    assert len(frames)==1


@pytest.mark.parametrize('line',[844,862,880,898,916,934])
def test_original_realhell_dynamic_destination_rows_match_old_oracle(tmp_path,line):
    root=Path(__file__).resolve().parents[2]
    rows=list(csv.reader(next(root.glob('Real HELL*.csv')).read_text(encoding='utf-8-sig').splitlines()))
    text='0,Set,HeartY,297.5\n'+','.join(rows[line-1])+'\n0,BoneV,$HeartX,$297.5,10,0,0\n0.01,EndAttack\n'
    path=source(tmp_path,text)
    frames,finished,samples,_,_=drive(initialize(path,max_ticks=100))
    old=compile_wave(path,max_ticks=100,heart_samples=samples)
    for tick,frame in enumerate(frames):frame_matches(frame,old,tick)
    assert finished.vm.vars['HeartY']=='297.5'
    assert '297.5' in finished.vm.vars and '$HeartY' not in finished.vm.vars


def test_new_operator_does_not_call_monolithic_run(tmp_path,monkeypatch):
    from nohit.engine.compact_wave import TimelineVM
    def forbidden(*args,**kwargs):
        raise AssertionError('resumable operator re-entered monolithic prefix compiler')
    monkeypatch.setattr(TimelineVM,'run',forbidden)
    path=source(tmp_path,'0.0125,GetHeartPos,x,y\n0,BoneV,$x,$y,10,0,100\n0.025,EndAttack\n')
    frames,finished,_,_,terminal=drive(initialize(path,max_ticks=100))
    assert isinstance(terminal,Terminal) and len(frames)>1
    assert finished.stats['ticks_committed']==len(frames)


def test_finite_observed_clock_is_not_extended_by_repeating_last_dt(tmp_path):
    path=source(tmp_path,'1,EndAttack\n')
    schedule=np.array([1/240,0.004,0.005,0.003],dtype=float)
    frames,finished,_,_,result=drive(initialize(path,max_ticks=100,dt_schedule=schedule))
    old=compile_wave(path,max_ticks=100,dt_schedule=schedule)
    assert isinstance(result,ResourceLimit)
    assert result.reason=='clock_budget'
    assert len(frames)==4 and finished.stats['ticks_committed']==4
    for tick,frame in enumerate(frames):frame_matches(frame,old,tick)


def test_observation_preview_matches_old_sample_context_without_committing(tmp_path):
    path=source(tmp_path,'0,Platform,200,350,60,0,80,1\n'
                '0.0125,BlackScreen,1\n0,GetHeartPos,x,y\n'
                '0,BoneV,$x,$y,10,0,0\n0.025,EndAttack\n')
    state=initialize(path,max_ticks=100)
    while True:
        event=advance_one_tick(state)
        if isinstance(event,NeedTarget):break
        assert isinstance(event,TickCommitted);state=event.state
    before=copy.deepcopy(event.state.stats)
    preview=preview_observation_frame(event)
    assert preview.committed is False and event.state.stats==before
    old=compile_wave(path,max_ticks=100,allow_partial=True)
    tick=event.request['tick']
    bits_equal(preview.env,old.env_schedule[tick])
    platforms=old.platform_table[tick]
    bits_equal(preview.platforms,platforms[(platforms[:,6]!=0)|(platforms[:,7]!=0)])
    for name,attr in (('white','geometry_white'),('blue','geometry_blue'),('polygons','geometry_polygons')):
        values=getattr(old,attr)[tick]
        bits_equal(getattr(preview,name),values[np.isfinite(values).all(axis=1)])
    # The suspended command has not executed; its report is added only by the
    # explicit legacy collector, not by the source transaction itself.
    assert tuple(preview.events)==tuple(e for e in old.source_events if e[0]==tick)[:-1]
