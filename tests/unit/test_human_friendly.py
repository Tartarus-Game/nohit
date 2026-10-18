import ctypes as C
import json
import time
from types import SimpleNamespace
import numpy as np
import pytest
from nohit.engine.native_backend import load_backend,_ptr,frame_clearance
from nohit.engine.source_oracle import scalar_module
from nohit.engine.csv_solver import solve_csv
from nohit.engine.search_preferences import current
from nohit.engine.human_difficulty import analyze_route

INITIAL=[320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.]


@pytest.mark.parametrize('margin',[0.,.125,3.,6.,12.])
def test_padded_collision_matches_original_scalar_with_larger_box(margin):
    rng=np.random.default_rng(71);states=np.tile(INITIAL,(100,1));states[:,:2]=rng.uniform(-30,670,(100,2))
    states[:,2:4]=rng.choice([0.,150.],(100,2))
    white=np.array([[300,200,310,400],[0,0,20,20],[np.nan]*4],np.float64)
    blue=np.array([[315,290,325,330]],np.float64)
    quads=[]
    for angle in np.linspace(0,6,13):
        a=np.array([np.cos(angle),np.sin(angle)])*150;b=np.array([-np.sin(angle),np.cos(angle)])*4;c=np.array([320.,240.])
        quads.append(np.array([c+a+b,c-a+b,c-a-b,c+a-b]).ravel())
    quads=np.array(quads,np.float64);out=np.empty(len(states),np.uint8);lib,_=load_backend()
    lib.nohit_collision_margin(_ptr(states),len(states),_ptr(white),len(white),_ptr(blue),len(blue),_ptr(quads),len(quads),_ptr(out),margin)
    source=scalar_module('cspace');r=2+margin
    for i,s in enumerate(states):
        expected=any(source._rect_hit(b,*s[:2],r) for b in white)
        if s[2]!=0 or s[3]!=0:expected|=any(source._rect_hit(b,*s[:2],r) for b in blue)
        expected|=any(source.quad_intersects_box(q,*s[:2],r,r) for q in quads)
        assert bool(out[i])==expected,(margin,i)


def test_clearance_is_per_side_and_stationary_blue_is_a_motion_lock():
    empty=np.empty((0,4));frame=SimpleNamespace(white=np.array([[325,290,340,330.]]),blue=empty,polygons=np.empty((0,8)))
    assert frame_clearance(frame,INITIAL)[0]==3.
    frame.white=empty;frame.blue=np.array([[310,290,330,330.]])
    metric=frame_clearance(frame,INITIAL);assert np.isinf(metric[0]) and metric[3]==1
    moving=INITIAL.copy();moving[2]=150.
    metric=frame_clearance(frame,moving);assert metric[0]==0 and metric[1]==1 and metric[3]==0


def test_human_search_uses_margin_tiers_and_keeps_request_preferences_local(tmp_path):
    path=tmp_path/'wide.csv';path.write_text('0,HeartMode,0\n0,BoneV,300,200,200,0,0,0\n0.1,EndAttack\n')
    r=solve_csv(path,INITIAL,dt_schedule=[1/60]*100,max_ticks=100,width=16,workers=1,
        seconds=2,objective='human_friendly',analyze_difficulty=False)
    assert r['verified'] and set(r['actions'])=={0}
    meta=r['search_stats']['native_code']
    assert meta['search_margin_px']==6.
    assert meta['human_margin_trials'][0]['margin_px']==12 and not meta['human_margin_trials'][0]['found']
    assert r['search_objective']['objective']=='human_friendly'
    assert current()['objective']=='balanced'


def test_human_confirm_only_presses_after_dialogue_completion_and_is_certified(tmp_path):
    path=tmp_path/'dialogue.csv';path.write_text('0,HeartMode,0\n0.1,SansText,Hello.,\n0.2,EndAttack\n')
    r=solve_csv(path,INITIAL,dt_schedule=[1/60]*200,max_ticks=200,width=16,workers=1,seconds=3,objective='human_friendly')
    assert r['verified'] and sum(r['confirm_sequence'])==1
    assert r['difficulty']['operations']['confirm_presses']==1
    assert not r['difficulty']['human_feasibility']['actual_human_clear_verified']
    json.dumps(r,allow_nan=False)


def test_human_search_prefers_wider_route_over_zero_operation_narrow_route(tmp_path):
    path=tmp_path/'choice.csv';path.write_text('0,HeartMode,0\n0.1,BoneV,330,280,50,0,0,0\n0.2,EndAttack\n')
    settings=dict(dt_schedule=[1/60]*100,max_ticks=100,width=32,workers=1,seconds=3)
    fewest=solve_csv(path,INITIAL,objective='fewest_operations',**settings)
    human=solve_csv(path,INITIAL,objective='human_friendly',**settings)
    assert fewest['verified'] and fewest['input_cost']['churn']==0
    assert human['verified'] and human['input_cost']['churn']>0
    assert human['search_stats']['native_code']['search_margin_px']==12.
    assert human['difficulty']['minimum_clearance_px']>12.


def test_human_mode_releases_initial_opposed_keys_and_never_searches_opposed_chords(tmp_path):
    path=tmp_path/'chords.csv';path.write_text('0,HeartMode,0\n0.3,EndAttack\n')
    initial=INITIAL.copy();initial[4]=3.
    r=solve_csv(path,initial,dt_schedule=[1/60]*100,max_ticks=100,width=16,workers=1,seconds=2,objective='human_friendly')
    assert r['verified'] and set(r['actions'])<={0,1,2,4,5,6,8,9,10}
    assert r['difficulty']['operations']['max_simultaneous_arrows']<=2
    assert r['difficulty']['operations']['opposed_direction_frames']==0


def test_difficulty_detects_three_pixel_space_and_reports_csv_cursor(tmp_path):
    path=tmp_path/'tight.csv';path.write_text('0,HeartMode,0\n0,BoneV,325,280,50,0,0,0\n0.2,EndAttack\n')
    r=solve_csv(path,INITIAL,dt_schedule=[1/60]*100,max_ticks=100,width=16,seconds=2,analyze_difficulty=True)
    d=r['difficulty'];assert r['verified'] and d['minimum_clearance_px']==3.
    assert d['hard_points'][0]['tick']==0 and d['hard_points'][0]['seconds']==0
    assert d['hard_points'][0]['csv']['last_executed']['line']==2
    assert d['scope']=='this_verified_route_only' and not d['human_feasibility']['impossibility_proven']


def test_timing_probe_detects_frame_exact_changes_and_resamples_own_targets(tmp_path,monkeypatch):
    from nohit.engine.native_dynamic import _world,_certify
    from nohit.engine import resumable_wave as world
    path=tmp_path/'frame.csv'
    path.write_text('0,HeartMode,0\n0.05,GetHeartPos,x,y\n0.016666666666666666,BoneV,311,200,200,0,0,0\n0,BoneV,329,200,200,0,0,0\n0.2,EndAttack\n')
    settings=dict(dt_schedule=[1/60]*100,max_ticks=100)
    built=_world(path,INITIAL,settings,[0,2,2,0],False,False,None,time.perf_counter()+5)
    assert built and built[4]
    _,_,trace,_,_,actions=built
    confirms=[False]*len(actions)
    assert _certify(path,INITIAL,settings,actions,trace,confirms,False,False,None,False)
    result=dict(verified=True,actions=actions,confirm_sequence=confirms,trajectory=trace.tolist(),
        dt_sequence=[1/60]*len(trace),initial_confirm=False,previous_confirm=False,initial_target_history=None)
    observed=[];original=world._supply_target_owned
    def supply(state,xy):observed.append(tuple(xy));return original(state,xy)
    monkeypatch.setattr(world,'_supply_target_owned',supply)
    d=analyze_route(path,INITIAL,settings,result)
    assert any(e['frame_exact_locally'] for e in d['timing_events'])
    assert len(set(observed))>1
    assert d['score']>=90 and d['human_feasibility']['estimate']=='manual_play_extremely_demanding'
    assert not d['timing_coverage']['full_suffix_verified']
    assert not d['human_feasibility']['impossibility_proven']


def test_unknown_does_not_receive_an_impossibility_score(tmp_path):
    path=tmp_path/'hit.csv';path.write_text('0,BoneH,0,300,640\n1,EndAttack\n')
    r=solve_csv(path,INITIAL,width=4,seconds=1,analyze_difficulty=True)
    assert not r['verified'] and r['difficulty']['status']=='unavailable'
    assert 'score' not in r['difficulty']
