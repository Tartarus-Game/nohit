"""Independent streaming verification retains source equations and boundaries."""
import time
import numpy as np
import pytest

from nohit.engine.compact_wave import compile_wave
from nohit.engine.native_dynamic import _certify, _world
from nohit.engine import native_dynamic, resumable_wave
from nohit.engine.source_verification import _last_active


@pytest.mark.parametrize('ending', ['0.2,EndAttack\n', '0.1,SansText,Hello.,\n0.2,EndAttack\n'])
def test_streamed_source_frames_equal_materialized_source(ending, tmp_path):
    path=tmp_path/'source.csv'
    path.write_text('0,HeartMode,0\n0,CombatZoneResizeInstant,80,80,550,420\n'
        '0,BoneVRepeat,10,20,30,0,70,9,80,1\n'
        '0,BoneHRepeat,25,400,-20,2,90,-8,80,0\n'
        '0,Platform,200,350,60,0,80,1\n'
        '0,GasterBlaster,1,100,100,100,100,45,0,0.1\n'+ending)
    settings=dict(dt_schedule=[1/60]*100,max_ticks=100)
    expected=compile_wave(path,**settings)
    seen=[]
    def observe(tick,env,platforms,white,blue,polygons,committed):
        for actual,tensor in ((env,expected.env_schedule),):
            assert actual.tobytes()==tensor[tick].tobytes()
        for actual,tensor in ((white,expected.geometry_white),(blue,expected.geometry_blue),
                              (polygons,expected.geometry_polygons)):
            assert actual.tobytes()==tensor[tick,:len(actual)].tobytes()
            assert np.isnan(tensor[tick,len(actual):]).all()
        assert platforms.tobytes()==expected.platform_table[tick,:len(platforms)].tobytes()
        seen.append((tick,committed))
    actual=compile_wave(path,**settings,include_combined_geometry=False,_frame_observer=observe)
    assert len(seen)==len(expected.env_schedule)
    assert seen[-1][1]==expected.complete
    assert actual.target_history==expected.target_history
    assert actual.source_events==expected.source_events
    assert actual.terminal_details==expected.terminal_details
    assert actual.env_schedule.tobytes()==expected.env_schedule.tobytes()
    assert actual.geometry_white.nbytes==actual.geometry_blue.nbytes==actual.geometry.nbytes==0


def test_streamed_certificate_rejects_real_collision_and_modified_states(tmp_path):
    path=tmp_path/'collision.csv'
    path.write_text('0,HeartMode,0\n0,BoneV,315,300,20,0,0\n0.2,SansText,Hi.,\n0.1,EndAttack\n')
    initial=np.array([320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.])
    settings=dict(dt_schedule=[1/60]*200,max_ticks=200)
    built=_world(path,initial,settings,[],False,False,None,time.perf_counter()+5)
    _,_,trace,confirms,safe,word=built
    assert not safe
    assert _certify(path,initial,settings,word,trace,confirms,False,False,None,True) is None


def test_first_search_window_does_not_generate_unseen_long_tail(tmp_path,monkeypatch):
    path=tmp_path/'long.csv';path.write_text('0,HeartMode,0\n10,EndAttack\n')
    calls=0;advance=resumable_wave._advance_owned_tick
    def counted(*args,**kwargs):
        nonlocal calls
        calls+=1
        return advance(*args,**kwargs)
    class FirstSearch(Exception):pass
    def search(*args,**kwargs):raise FirstSearch
    monkeypatch.setattr(resumable_wave,'_advance_owned_tick',counted)
    monkeypatch.setattr(native_dynamic,'find_native_candidate',search)
    with pytest.raises(FirstSearch):
        native_dynamic._segmented_coupled(path,[320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.],
            dict(dt_schedule=[1/60]*1000,max_ticks=1000),128,1,8,42,False,False,None,
            time.perf_counter()+5,_chunk_ticks=8)
    assert calls<=11  # initial frame + its resource probe + 9 window frames


def test_chunked_active_counts_preserve_infinity_holes_and_padding():
    rng=np.random.default_rng(42);rows=rng.normal(size=(601,37,4));rows[rng.random((601,37))<.4]=np.nan
    rows[257,36,0]=np.inf
    for polygons in (False,True):
        present=np.isfinite(rows[:,:,0]) if polygons else ~np.isnan(rows[:,:,0])
        expected=np.where(present,np.arange(37)+1,0).max(axis=1)
        assert np.array_equal(_last_active(rows,polygons),expected)


@pytest.mark.parametrize('ending',['0.1,EndAttack\n','0.1,SansText,Hello.,\n0.1,EndAttack\n','0,SansText,Hello.,\n0.1,EndAttack\n'])
def test_continuation_receipt_matches_full_binding_without_historical_tensors(tmp_path,ending):
    from nohit.engine.parametric_environment import ParametricEnvironment,EnvironmentContinuation
    from nohit.engine.resumable_wave import state_environment_key
    path=tmp_path/'receipt.csv'
    path.write_text('0,CombatZoneResizeInstant,80,80,550,420,TLResume\n'
        '0,BoneVRepeat,10,20,30,0,70,9,80,1\n'+ending)
    settings=dict(dt_schedule=[1/60]*100,max_ticks=100)
    template=ParametricEnvironment(path,**settings)
    full=template.bind_history_once()
    receipt=template.bind_history_once(_continuation_only=True)
    assert isinstance(receipt,EnvironmentContinuation) and not hasattr(receipt,'wave')
    assert receipt.identity==full.identity and receipt.history==full.history
    assert receipt.first_environment.tobytes()==full.wave.env_schedule[0].tobytes()
    assert receipt.reason==full.wave.termination_reason and receipt.complete==full.complete
    if receipt.resume_state.phase=='committed':
        assert state_environment_key(receipt.resume_state)==state_environment_key(full.resume_state)
    else:
        import pickle
        assert pickle.dumps(receipt.resume_state)==pickle.dumps(full.resume_state)
    assert template._bindings[full.identity] is full
    assert list(receipt.callback_events)==full.wave.terminal_details['executed_callbacks']


@pytest.mark.parametrize('fixed_ticks',[0,12])
def test_segment_failure_rolls_back_source_observations_and_keeps_fixed_prefix(tmp_path,monkeypatch,fixed_ticks):
    import hashlib
    # This exercises a frontier retry, whose setup includes a native kernel.
    # Keep one-time compilation outside the bounded search deadline.
    from nohit.engine.native_backend import load_backend
    load_backend()
    initial=np.array([320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.])
    path=tmp_path/'rollback.csv'
    path.write_text('0,HeartMode,0\n'+''.join('0.1,GetHeartPos,x,y\n0,BoneV,$x,80,20,1,10\n' for _ in range(12))+'0.2,EndAttack\n')
    settings=dict(dt_schedule=[1/60]*500,max_ticks=500)
    options=dict(_chunk_ticks=6,_preview_ticks=6)
    baseline=native_dynamic._segmented_coupled(path,initial,settings,32,1,8,42,False,False,None,
        time.perf_counter()+10,**options)
    assert baseline is not None and baseline.verified
    if fixed_ticks:
        options['_fixed_prefix']=dict(csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            actions=baseline.actions[:fixed_ticks],trajectory=baseline.trajectory[:fixed_ticks+1].tolist(),
            confirm_sequence=baseline.confirm_sequence[:fixed_ticks])
    original=native_dynamic.find_native_candidate;calls=0
    def limited_once(*args,**kwargs):
        nonlocal calls
        calls+=1
        result=original(*args,**kwargs)
        if calls==7:
            result.status='unknown';result.reason='native_search_limited'
        return result
    monkeypatch.setattr(native_dynamic,'find_native_candidate',limited_once)
    failure={}
    result=native_dynamic._segmented_coupled(path,initial,settings,32,1,8,42,False,False,None,
        time.perf_counter()+10,_failure=failure,**options)
    assert result is not None and result.verified and result.stats['observation_backtracks']==1
    assert result.stats['fixed_prefix_ticks']==fixed_ticks
    assert result.actions[:fixed_ticks]==baseline.actions[:fixed_ticks]
    assert result.trajectory[:fixed_ticks+1].tobytes()==baseline.trajectory[:fixed_ticks+1].tobytes()
    actual=_world(path,initial,settings,result.actions,False,False,None,time.perf_counter()+10)
    assert actual[4] and actual[1].history==result.target_history and len(result.target_history)==12
    assert actual[2].tobytes()==result.trajectory.tobytes()
    assert actual[3]==result.confirm_sequence
    # A later successful branch must not erase the safe receipt from the
    # abandoned branch. It remains available if another retry later fails.
    abandoned=[row for row in failure['routes'] if row['actions']]
    assert abandoned
    for receipt in abandoned:
        replay=_world(path,initial,settings,receipt['actions'],False,False,None,time.perf_counter()+10)
        n=len(receipt['actions'])
        assert replay is not None
        assert receipt['actions']==replay[5][:n]
        assert receipt['confirm_sequence']==replay[3][:n]


@pytest.mark.parametrize('max_ticks,reason',[(100,'clock_budget'),(24,'tick_budget')])
def test_resource_limit_retains_last_committed_diagnostic_word(tmp_path,max_ticks,reason):
    path=tmp_path/'finite.csv'
    path.write_text('0,HeartMode,0\n'+''.join('0.1,GetHeartPos,x,y\n' for _ in range(12))+'1,EndAttack\n')
    failure={}
    result=native_dynamic._segmented_coupled(path,
        [320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.],
        dict(dt_schedule=[1/60]*30,max_ticks=max_ticks),32,1,8,42,False,False,None,
        time.perf_counter()+5,_chunk_ticks=6,_preview_ticks=0,_failure=failure)
    assert result is None and failure['reason']==reason
    assert any(len(row['actions'])>=12 for row in failure['routes'])
    assert all(len(row['actions'])==len(row['confirm_sequence']) for row in failure['routes'])
