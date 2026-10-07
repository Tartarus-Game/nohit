"""Exact scenes require a verified route with matching source, clock and history."""
import copy
import json
import numpy as np
import pytest

from nohit.dashboard.csv_visualization import build_csv_visualization
from nohit.engine.csv_solver import solve_csv
from nohit.engine.joint_transition import JointState, step_joint
from nohit.engine.parametric_environment import ParametricEnvironment


INITIAL=[320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.]
SCHEDULE=(1/30,)*100


def solve(tmp_path,text):
    path=tmp_path/'scene.csv';path.write_text(text)
    result=solve_csv(path,INITIAL,dt_schedule=SCHEDULE,max_ticks=100,width=20)
    assert result['verified'] and result['status']=='candidate_found'
    return path,result


def test_static_scene_keeps_exact_rectangles_polygons_platforms_and_ticks(tmp_path):
    path,result=solve(tmp_path,'0,HeartMode,0\n0,Platform,100.125,350,50,0,30,1\n'
        '0,BoneV,100.125,100.5,20,0,0\n0,BoneV,140.25,100.5,20,0,0,1\n'
        '0,GasterBlaster,0,0,0,50,50,17,0.01,0.1\n1,EndAttack\n')
    visual=build_csv_visualization(path,result,dt_schedule=SCHEDULE)
    wave=ParametricEnvironment(path,dt_schedule=SCHEDULE,max_ticks=100).bind().wave
    assert visual['frame_count']==len(result['actions'])+1
    assert visual['original_replay_passed'] is False
    assert visual['scope']=='verified_source_model' and visual['end_reason']=='endattack'
    for tick,frame in enumerate(visual['frames']):
        assert frame['tick']==tick and frame['player']==result['trajectory'][tick]
        assert frame['env']==wave.env_schedule[tick].tolist()
        for name,field in [('white','geometry_white'),('blue','geometry_blue'),('polygons','geometry_polygons')]:
            rows=getattr(wave,field)[tick];rows=rows[np.isfinite(rows).all(axis=1)]
            assert frame[name]==rows.tolist()
        active=wave.platform_table[tick];active=active[active[:,6]!=0.]
        assert frame['platforms']==active.tolist()
    assert any(frame['polygons'] for frame in visual['frames'])
    assert any(value!=int(value) for frame in visual['frames'] for polygon in frame['polygons'] for value in polygon)
    json.dumps(visual,allow_nan=False)


def test_observed_history_and_two_real_dialogue_sequences_rebuild_exactly(tmp_path):
    path,result=solve(tmp_path,'0,HeartMode,0\n0,BoneV,100,100,20,0,30\n'
        '0.1,GetHeartPos,x,y\n0,BoneV,$x,100,12,0,0\n'
        '0.1,SansText,abc,\n0,SansText,def,\n0,EndAttack\n')
    visual=build_csv_visualization(path,result,dt_schedule=SCHEDULE)
    first=result['dialogue_start_tick']+1
    assert any(result['confirm_sequence']) and first<len(result['actions'])
    assert len(visual['frames'])==len(result['trajectory'])
    for tick,frame in enumerate(visual['frames']):
        assert frame['player']==result['trajectory'][tick]
    # The first bone keeps moving during the text; rendering cannot freeze or
    # erase hazards just because the timeline is paused.
    assert visual['frames'][first]['white'][0]!=visual['frames'][first+1]['white'][0]
    assert visual['frames'][-1]['white']==[]
    assert visual['environment_binding_identity']==result['environment_binding_identity']


@pytest.mark.parametrize('prefix',[
    '0,HeartMode,0\n0.033333,SansText,a,\n',
    '0,HeartMode,0\n0.033333,GetHeartPos,bx,by\n0,SansText,a,\n',
])
def test_dialogue_target_continuation_rebuilds_selected_world(tmp_path,prefix):
    path,result=solve(tmp_path,prefix+'0,GetHeartPos,x,y\n0,BoneV,$x,100,12,0,0\n'
        '0.1,GetHeartPos,x,y\n0,EndAttack\n')
    visual=build_csv_visualization(path,result,dt_schedule=SCHEDULE)
    base=result['environment_provenance']['base_target_history']
    assert len(result['target_history'])==len(base)+2
    assert [frame['player'] for frame in visual['frames']]==result['trajectory']
    assert any(frame['white'] for frame in visual['frames'])
    for mutate in [
        lambda r:r['target_history'][-1].__setitem__(2,r['target_history'][-1][2]+1),
        lambda r:r.update(controlled_environment_binding_identity='bad'),
        lambda r:r['environment_provenance'].update(base_target_history=r['target_history']),
        lambda r:r['environment_provenance'].update(final_binding_identity='bad'),
        lambda r:r['source_terminal']['details'].update(active_bones=1),
        lambda r:r['source_terminal'].update(tick=r['source_terminal']['tick']+1),
    ]:
        corrupt=copy.deepcopy(result);mutate(corrupt)
        with pytest.raises(ValueError):build_csv_visualization(path,corrupt,dt_schedule=SCHEDULE)


@pytest.mark.parametrize('target_reads',[1,2])
def test_target_reads_on_first_dialogue_tick_use_the_unmoved_prefix_state(tmp_path,target_reads):
    source='0,HeartMode,0\n0.1,GetHeartPos,x,y\n'
    source+='0,GetHeartPos,x,y\n'*(target_reads-1)
    path,result=solve(tmp_path,source+'0,BoneV,$x,100,12,0,0\n0,SansText,a,\n0,EndAttack\n')
    first=result['dialogue_start_tick']+1
    assert len(result['target_history'])==target_reads
    assert all(row[0]==first for row in result['target_history'])
    visual=build_csv_visualization(path,result,dt_schedule=SCHEDULE)
    assert visual['environment_binding_identity']==result['environment_binding_identity']
    assert visual['frame_count']==len(result['actions'])+1
    assert [frame['player'] for frame in visual['frames']]==result['trajectory']
    assert [frame['dt'] for frame in visual['frames']]==result['dt_sequence']
    assert visual['frames'][-1]['white']==[]


@pytest.mark.parametrize('change',[
    lambda r:r.update(verified=False),
    lambda r:r.update(status='unknown'),
    lambda r:r.update(csv_sha256='bad'),
    lambda r:r.update(environment_binding_identity='bad'),
    lambda r:r.update(confirm_sequence=[]),
    lambda r:r.update(reached_tick=r['reached_tick']+1),
    lambda r:r['trajectory'][-1].__setitem__(0,r['trajectory'][-1][0]+1),
    lambda r:r['dt_sequence'].__setitem__(1,r['dt_sequence'][1]*2),
])
def test_corrupted_or_unverified_candidates_are_rejected(tmp_path,change):
    path,result=solve(tmp_path,'0,HeartMode,0\n0.1,EndAttack\n')
    changed=copy.deepcopy(result);change(changed)
    with pytest.raises(ValueError):build_csv_visualization(path,changed,dt_schedule=SCHEDULE)


@pytest.mark.parametrize('kwargs',[
    {'dt_schedule':(1/60,)*100}, {'dt_schedule':SCHEDULE[:-1]},
    {'dt_schedule':SCHEDULE,'seed':43}, {'dt_schedule':SCHEDULE,'max_ticks':99},
    {'dt_schedule':SCHEDULE,'initial_environment':[0,0,640,480,0,1,0,1/30,750,0,320,304]},
    {},
])
def test_foreign_clock_or_environment_identity_is_rejected(tmp_path,kwargs):
    path,result=solve(tmp_path,'0,HeartMode,0\n0.1,EndAttack\n')
    with pytest.raises(ValueError):build_csv_visualization(path,result,**kwargs)


def test_removing_confirm_cannot_erase_the_real_dialogue_tail(tmp_path):
    path,result=solve(tmp_path,'0,HeartMode,0\n0.1,SansText,a,\n0,EndAttack\n')
    result['confirm_sequence']=[False]*len(result['actions'])
    result['unified_controls']=result['actions'].copy()
    with pytest.raises(ValueError,match='EndAttack'):
        build_csv_visualization(path,result,dt_schedule=SCHEDULE)


def test_native_timestamp_clock_rebuilds_all_frame_dt_values(tmp_path):
    path=tmp_path/'clock.csv';path.write_text('0,HeartMode,0\n0.04,EndAttack\n')
    result=solve_csv(path,INITIAL,clock_start_ms=971260.6666634805,max_ticks=100,width=1)
    visual=build_csv_visualization(path,result)
    assert [frame['dt'] for frame in visual['frames']]==result['dt_sequence']


def primed_fixture(tmp_path,text='a',tail='0,EndAttack\n',initial=None,**kwargs):
    path=tmp_path/'primed-scene.csv'
    path.write_text('0,SansText,'+text+',\n'+tail,encoding='utf-8')
    initial=INITIAL if initial is None else initial
    bounds=[100.,100.,540.,420.]
    env=bounds+[0.,1.,0.,1/30,750.,0.,0.,0.,0.,0.]+bounds+bounds
    result=solve_csv(path,initial,initial_environment=env,dt_schedule=SCHEDULE,
        max_ticks=100,width=20,**kwargs)
    assert result['verified'] and result['primed_initial_frame']
    return path,result,env


def test_primed_scene_does_not_repeat_observed_player_motion(tmp_path):
    observed=INITIAL.copy();observed[2]=150.;observed[4]=2.
    path,result,env=primed_fixture(tmp_path,initial=observed)
    visual=build_csv_visualization(path,result,initial_environment=env,dt_schedule=SCHEDULE)
    assert np.asarray(visual['frames'][0]['player']).tobytes()==np.asarray(observed).tobytes()
    assert visual['frames'][0]['time_seconds']==0.
    assert visual['frames'][1]['player'][0]==325.
    assert visual['frames'][1]['time_seconds']==1/30
    assert visual['frame_count']==len(result['actions'])+1
    assert [frame['player'] for frame in visual['frames']]==result['trajectory']


@pytest.mark.parametrize('initial_confirm,previous_confirm,expected_end',[
    (False,False,3),(True,False,1),(True,True,3),
])
def test_primed_scene_replays_actual_initial_confirm_edge(tmp_path,initial_confirm,previous_confirm,expected_end):
    path,result,env=primed_fixture(tmp_path,initial_confirm=initial_confirm,previous_confirm=previous_confirm)
    visual=build_csv_visualization(path,result,initial_environment=env,dt_schedule=SCHEDULE)
    assert result['reached_tick']==expected_end
    assert visual['frames'][0]['confirm'] is initial_confirm
    assert [row['confirm'] for row in visual['frames'][1:]]==result['confirm_sequence']
    assert visual['frames'][-1]['tick']==expected_end
    assert visual['original_replay_passed'] is False


def test_primed_scene_geometry_matches_independent_joint_replay(tmp_path):
    path,result,env=primed_fixture(tmp_path,text='abcdef',tail=
        '0,BoneV,100.125,100.5,20,0,30\n0,BoneV,140.25,100.5,20,0,0,1\n'
        '0,Platform,100,350,50,0,30,1\n'
        '0,GasterBlaster,0,0,0,50,50,17,0.01,0.1\n0.5,EndAttack\n')
    visual=build_csv_visualization(path,result,initial_environment=env,dt_schedule=SCHEDULE)
    template=ParametricEnvironment(path,initial_environment=env,dt_schedule=SCHEDULE,max_ticks=100)
    binding=template.bind()
    world=template.begin_controlled(binding,previous_input_code=0)
    world=template.step_controlled(world,result['initial_frame_control'])
    node=JointState(tuple(result['trajectory'][0]),world)
    frames=[world.frame]
    for control in result['unified_controls']:
        edge=step_joint(template,node,control);assert edge.state is not None
        node=edge.state;frames.append(node.environment.frame)
    assert edge.status=='terminal' and edge.reason=='endattack'
    for tick,(scene,frame) in enumerate(zip(visual['frames'],frames)):
        assert scene['tick']==frame.tick==tick
        assert scene['env']==frame.env.tolist()
        for name in ('white','blue','polygons'):
            expected=getattr(frame,name);expected=expected[np.isfinite(expected).all(axis=1)]
            assert scene[name]==expected.tolist()
        platforms=frame.platforms[frame.platforms[:,6]!=0.]
        assert scene['platforms']==platforms.tolist()
    assert any(scene['white'] for scene in visual['frames'])
    assert any(scene['blue'] for scene in visual['frames'])
    assert any(scene['polygons'] for scene in visual['frames'])
    assert any(scene['platforms'] for scene in visual['frames'])
    assert visual['frames'][-1]['white']==[]
    json.dumps(visual,allow_nan=False)


def test_primed_scene_rejects_changed_initial_confirm_history(tmp_path):
    path,result,env=primed_fixture(tmp_path,initial_confirm=True,previous_confirm=False)
    # Current Confirm remains consistent with initial_frame_control, so the
    # replay must catch the changed prior edge through the actual world.
    changed=copy.deepcopy(result);changed['previous_confirm']=True
    with pytest.raises(ValueError,match='EndAttack'):
        build_csv_visualization(path,changed,initial_environment=env,dt_schedule=SCHEDULE)
    changed=copy.deepcopy(result);changed['initial_confirm']=False
    with pytest.raises(ValueError,match='initial control'):
        build_csv_visualization(path,changed,initial_environment=env,dt_schedule=SCHEDULE)
