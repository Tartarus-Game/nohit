import json
import numpy as np
import pytest

from nohit.engine.csv_solver import solve_csv
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.search_preferences import current
from nohit.engine.terminal_invariant import certify_release_invariant,settle_release_to_invariant
from nohit.dashboard.csv_visualization import build_csv_visualization

INITIAL=[320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.]


def test_failure_exports_safe_frontier_and_exact_variable_clock_source_cursor(tmp_path):
    path=tmp_path/'blocked.csv'
    path.write_text('0,CombatZoneResizeInstant,307,291,333,317\n0,HeartMode,0\n0.1,BoneH,0,300,640,0,0,0\n1,EndAttack\n')
    clock=[1/60,1/30,1/60]*100
    settings=dict(dt_schedule=clock,max_ticks=len(clock))
    wave=ParametricEnvironment(path,**settings).bind().wave
    blocked=next(i for i,row in enumerate(wave.geometry_white) if np.isfinite(row).any())
    result=solve_csv(path,INITIAL,width=16,seconds=1,diagnostic_routes=2,**settings)
    assert result['status']=='unknown' and result['actions']==[] and not result['verified']
    diagnostic=result['failure_diagnostics']
    assert diagnostic['last_safe_tick']==blocked-1
    assert diagnostic['failure']['tick']==blocked
    assert diagnostic['failure']['seconds']==sum(clock[1:blocked+1])
    assert diagnostic['failure']['csv']['last_executed']['line']==3
    assert diagnostic['failure']['csv']['line']==4
    assert not diagnostic['exhaustive'] and not diagnostic['deadlock_proven']
    for route in diagnostic['routes']:
        assert route['prefix_verified'] and not route['complete']
        assert len(route['trajectory'])==len(route['actions'])+1==len(route['dt_sequence'])
        assert route['reached_tick']==blocked-1
        assert all(row[10]==0 for row in route['trajectory'])
    json.dumps(result,allow_nan=False)


def test_initial_collision_has_no_safe_tick_or_playable_route(tmp_path):
    path=tmp_path/'initial.csv';path.write_text('0,HeartMode,0\n0,BoneH,0,300,640\n1,EndAttack\n')
    result=solve_csv(path,INITIAL,seconds=1,width=4)
    diagnostic=result['failure_diagnostics']
    assert diagnostic['last_safe_tick'] is None and diagnostic['failure']['tick']==0
    assert not any(row['prefix_verified'] for row in diagnostic['routes'])
    assert result['actions']==[]


def test_fewest_operations_changes_the_selected_control_word_and_resets_per_request(tmp_path):
    path=tmp_path/'easy.csv';path.write_text('0,HeartMode,0\n0.1,EndAttack\n')
    initial=INITIAL.copy();initial[4]=2.
    result=solve_csv(path,initial,dt_schedule=[1/60]*60,max_ticks=60,width=16,
        seconds=2,objective='fewest_operations')
    assert result['verified'] and result['actions'] and set(result['actions'])=={2}
    assert result['input_cost']['churn']==0 and result['input_cost']['reward']==0
    assert not result['optimality_proven'] and current()['objective']=='balanced'
    balanced=solve_csv(path,initial,dt_schedule=[1/60]*60,max_ticks=60,width=16,seconds=2)
    assert balanced['verified'] and balanced['search_objective']['objective']=='balanced'
    assert balanced['input_cost']['churn_weight']==12


@pytest.mark.parametrize('options',[dict(objective='optimal'),dict(operation_weight=-1),
    dict(operation_weight=0,held_weight=0),dict(diagnostic_routes=0),dict(diagnostic_routes=True)])
def test_invalid_preferences_are_rejected_before_search(tmp_path,options):
    path=tmp_path/'a.csv';path.write_text('0,EndAttack\n')
    with pytest.raises(ValueError):solve_csv(path,INITIAL,**options)


def test_static_blue_eof_proves_released_tail_and_keeps_blue_geometry_in_preview(tmp_path):
    path=tmp_path/'blue.csv';path.write_text('0,HeartMode,0\n0,BoneH,300,300,40,0,0,1\n')
    clock=[1/60]*100
    result=solve_csv(path,INITIAL,dt_schedule=clock,max_ticks=100,width=4,
        termination_policy='eof_hazards_drained')
    assert result['verified'] and result['completion']['certificate']['proof']=='static-blue-release-fixed-point-v1'
    assert result['completion']['certificate']['terminal_details']['active_bones']==1
    assert result['actions'][-2:]==[0,0]
    visual=build_csv_visualization(path,result,dt_schedule=clock)
    assert all(frame['blue'] for frame in visual['frames'])


def test_static_blue_release_bridge_must_not_move_into_blue_bone():
    state=np.array(INITIAL);state[2]=150.;state[6]=1.
    bounds=[100.,100.,540.,420.]
    env=np.array(bounds+[1.,1.,0.,1/60,750.,0.,0.,0.,0.,0.]+bounds+bounds)
    details=dict(active_bones=1,static_blue_bones=[[324.,300.,10.,40.,0.,0.,1.,0.]],
        active_stabs=0,active_blasters=0,active_platforms=0,arena_settled=True,
        timeline_exhausted=True,pending_callbacks=[],pending_dialogue=None)
    assert settle_release_to_invariant(state,env,details,[1/60]*4)['status']=='unknown'
    state[2]=0.
    state[6]=env[4]=0.
    assert certify_release_invariant(state,env,details)['status']=='proven'
    for column,value in ((4,1.),(6,0.),(6,2.)):
        changed=dict(details,static_blue_bones=[details['static_blue_bones'][0].copy()])
        changed['static_blue_bones'][0][column]=value
        assert certify_release_invariant(state,env,changed)['status']=='unknown'


def test_script_parked_red_heart_outside_finite_arena_is_a_real_fixed_point(tmp_path):
    path=tmp_path/'offscreen.csv'
    path.write_text('0,HeartMode,0\n0,HeartTeleport,114514,1919\n0,BoneH,300,300,40,0,0,1\n')
    initial=INITIAL.copy();initial[:2]=[114514.,1919.]
    result=solve_csv(path,initial,dt_schedule=[1/60]*100,max_ticks=100,width=4,
        termination_policy='eof_hazards_drained')
    assert result['verified'] and result['trajectory'][-1][:2]==[114514.,1919.]
    assert result['trajectory'][-1][2:5]==[0.,0.,0.]


def test_black_screen_preserves_same_tick_creations_but_destroys_registered_bones(tmp_path):
    # Reduced from the original C2 replay failure in final Real HELL:
    # BoneV/BoneH, then BlackScreen(1), BlackScreen(0), all at delay zero.
    path=tmp_path/'clear.csv'
    path.write_text('0,BoneH,100,100,20\n0.1,BoneH,200,200,30,0,0,1\n0,BlackScreen,1\n0,BlackScreen,0\n0.1,EndAttack\n')
    settings=dict(dt_schedule=[1/60]*100,max_ticks=100)
    from nohit.engine.compact_wave import compile_wave
    from nohit.engine import resumable_wave as world
    compiled=compile_wave(path,**settings)
    bound=ParametricEnvironment(path,**settings).bind().wave
    tick=next(i for i,cmd,args in compiled.source_events if cmd=='blackscreen')
    for wave in (compiled,bound):
        assert not np.isfinite(wave.geometry_white[tick]).any()
        assert [200.,200.,230.,210.] in wave.geometry_blue[tick].tolist()
    # A player read in the middle of the tick must preserve the pending-create
    # boundary too, including through the reference suspension bridge.
    path.write_text('0,BoneH,100,100,20\n0.1,BoneH,200,200,30,0,0,1\n0,GetHeartPos,x,y\n0,BlackScreen,1\n0.1,EndAttack\n')
    template=ParametricEnvironment(path,**settings)
    first=template.bind();assert first.pending_target is not None
    full=template.extend(first,320.,304.)
    assert [200.,200.,230.,210.] in full.wave.geometry_blue[tick].tolist()
