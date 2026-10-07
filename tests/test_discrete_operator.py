"""Discrete operator contracts, including independently observed legacy motion."""
import math
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from nohit.engine import canonical_lattice
from nohit.engine.discrete_operator import (
    CANCEL, LEFT, UP, DOWN, RIGHT, initial_state, step, step_mask_into,
)


def environment(direction=1, mode=1, bounds=(0.,0.,200.,200.)):
    return np.array([*bounds,mode,direction,0.,1/240,750.,0.,0.,0.,0.,0.,*bounds])


EMPTY=np.zeros((0,7))


def state(x=100.,y=100.,dx=0.,dy=0.,direction=1,mode=1):
    return initial_state(np.array([x,y,dx,dy,0.]),environment(direction,mode))


def test_down_operator_preserves_differentially_verified_motion():
    env=environment(bounds=(133.,251.,508.,391.))
    old=np.array([320.,377.81875,0.,0.,0.])
    new=initial_state(old,env)
    rng=np.random.default_rng(1006)
    for i in range(2000):
        ux=int(rng.integers(-1,2)); up=int(rng.integers(0,2))
        old=canonical_lattice.step(old,ux,up,env[:8],EMPTY)
        new=step(new,ux,up,env,EMPTY)
        np.testing.assert_array_equal(new[:4],old[:4],err_msg=f"microtick {i}")
        assert bool(int(new[4])&UP)==bool(old[4])


def test_recorded_original_variable_dt_motion_matches_bit_for_bit():
    fixture=json.loads((Path(__file__).parent/'fixtures/native_bonegap1_motion.json').read_text())
    env=environment(bounds=fixture['bounds'])
    s=initial_state(np.array(fixture['initial']),env)
    out=np.empty(11)
    for i,(dt,mask,x,y,dx,dy) in enumerate(fixture['samples']):
        env[7]=dt
        step_mask_into(s,mask,env,EMPTY,out)
        np.testing.assert_array_equal(out[:4],[x,y,dx,dy],err_msg=f"native sample {i+1}")
        s,out=out,s


def test_original_intro_slam_teleport_mode_and_arena_transitions_are_exact():
    fixture=json.loads((Path(__file__).parent/'fixtures/native_intro_motion.json').read_text())
    s=np.array(fixture['initial']); out=np.empty(11)
    for tick,mask,env,expected in fixture['samples']:
        step_mask_into(s,mask,np.array(env,dtype=float),EMPTY,out)
        np.testing.assert_array_equal(out,expected,err_msg=f"original Intro tick {tick}")
        s,out=out,s


def test_original_moving_platform_motion_matches_all_native_state_bits():
    fixture=json.loads((Path(__file__).parent/'fixtures/native_platforms4hard_motion.json').read_text())
    s=np.array(fixture['initial']);out=np.empty(11)
    for tick,mask,env,platforms,expected in fixture['samples']:
        ps=np.asarray(platforms,dtype=float).reshape((-1,7))
        step_mask_into(s,mask,np.array(env,dtype=float),ps,out)
        np.testing.assert_array_equal(out,expected,err_msg=f"original platform tick {tick}")
        s,out=out,s


def test_original_four_gravity_directions_match_all_native_state_bits():
    fixture=json.loads((Path(__file__).parent/'fixtures/native_bonestab3_motion.json').read_text())
    s=np.array(fixture['initial']);out=np.empty(11);directions=set()
    for tick,mask,env,platforms,expected in fixture['samples']:
        ps=np.asarray(platforms,dtype=float).reshape((-1,7))
        step_mask_into(s,mask,np.array(env,dtype=float),ps,out)
        np.testing.assert_array_equal(out,expected,err_msg=f"original four-direction tick {tick}")
        directions.add(int(out[7]));s,out=out,s
    assert directions=={0,1,2,3}


def test_original_final_resizing_signed_caps_and_targeted_teleport_are_exact():
    fixture=json.loads((Path(__file__).parent/'fixtures/native_final_motion.json').read_text())
    s=np.array(fixture['initial']);out=np.empty(11);environments=[]
    for tick,mask,env,platforms,expected in fixture['samples']:
        ps=np.asarray(platforms,dtype=float).reshape((-1,fixture['platform_width']))
        step_mask_into(s,mask,np.array(env,dtype=float),ps,out)
        np.testing.assert_array_equal(out,expected,err_msg=f"original Final tick {tick}")
        environments.append(env);s,out=out,s
    assert len(environments)==2268
    assert len({tuple(env[:4]) for env in environments})==427
    assert {int(env[5]) for env in environments}=={0,1,2,3}
    assert {env[8] for env in environments}=={-300.,0.,450.,750.}
    assert any(env[14:18]!=env[18:22] for env in environments)  # Early instant resize.
    assert any(env[:4]!=env[18:22] for env in environments)  # Late routine resize.
    assert [(env[10],env[11]) for env in environments if env[9]]==[(40.,265.)]


def test_target_sample_is_after_movement_before_timeline_teleport():
    from nohit.engine.discrete_operator import sample_position
    env=environment();env[9:12]=[1.,40.,50.]
    s=state(dx=150.,dy=-60.)
    assert sample_position(s,env,EMPTY)==(100.625,99.75)
    assert tuple(step(s,0,0,env,EMPTY)[:2])==(40.,50.)


@pytest.mark.parametrize('direction,key,dx,dy',[
    (0,LEFT,-180.,0.),(1,UP,0.,-180.),
    (2,RIGHT,180.,0.),(3,DOWN,0.,180.),
])
def test_four_gravity_directions_jump_on_corresponding_edge(direction,key,dx,dy):
    env=environment(direction)
    x,y=[(187.,100.),(100.,187.),(13.,100.),(100.,13.)][direction]
    s=state(x,y,direction=direction)
    out=np.empty(11)
    step_mask_into(s,key,env,EMPTY,out)
    assert out[2]==pytest.approx(dx,abs=1e-13)
    assert out[3]==pytest.approx(dy,abs=1e-13)
    # Pressing again while airborne is not a second jump.
    after=np.empty(11)
    step_mask_into(out,key,env,EMPTY,after)
    assert abs(after[2])+abs(after[3]) < 180.
    # Release clamps ascent in the direction of gravity.
    step_mask_into(after,0,env,EMPTY,out)
    assert abs(out[2])+abs(out[3])==pytest.approx(28.125)


def test_slam_changes_velocity_after_movement_and_does_not_teleport():
    env=environment(); env[6]=1.
    s=state(100.,100.,150.,-60.)
    out=step(s,0,0,env,EMPTY)
    assert tuple(out[:2])==(100.625,99.75)
    assert out[3]==750.
    assert out[5]==1.
    env[6]=0.
    after=step(out,0,0,env,EMPTY)
    assert after[1]==102.875


def test_slam_contact_is_exposed_as_damage_only_when_enabled():
    env=environment()
    s=state(y=186.,dy=750.); s[5]=1.
    good=step(s,0,0,env,EMPTY)
    assert good[5]==0. and good[10]==0.
    s[9]=1.; env[12]=1.
    bad=step(s,0,0,env,EMPTY)
    assert bad[5]==0. and bad[10]==1.
    # The damage bit is a transition output, not cumulative damage storage.
    after=step(bad,0,0,env,EMPTY)
    assert after[10]==0.


def test_low_speed_tangent_contact_clears_slam_before_fast_normal_impact():
    env=environment(); env[12]=1.
    s=state(x=186.9,y=186.,dx=150.,dy=750.)
    s[5]=s[9]=1.
    # Horizontal behavior runs first. Its 150px/s contact clears Slammed;
    # the subsequent 750px/s vertical contact therefore causes no slam HP loss.
    out=step(s,0,0,env,EMPTY)
    assert out[5]==0. and out[10]==0.
    assert out[1]==186.
    assert out[3]==.75  # Gravity restarts after the blocked behavior substep.


def test_teleport_preserves_velocity_and_changes_position_in_event_phase():
    env=environment(); env[9:12]=[1.,50.,70.]
    out=step(state(dx=150.,dy=-120.),0,0,env,EMPTY)
    assert tuple(out[:2])==(50.,70.)
    assert out[3]==-119.25


def test_arena_push_is_after_old_boundary_movement_and_retains_velocity():
    env=environment(); env[0]=106.
    out=step(state(100.,100.,150.,0.),1,0,env,EMPTY)
    assert out[0]==119.
    assert out[2]==150.
    # A heart wholly outside does not overlap the combat rectangle: no push.
    outside=step(state(-100.,100.),0,0,env,EMPTY)
    assert outside[0]==-100.


def test_three_arena_phases_distinguish_late_resize_from_instant_resize():
    env=np.concatenate([environment(),[0.,0.,200.,200.]])
    env[3]=112.
    late=step(state(),0,0,env,EMPTY)
    assert late[1]==99.
    assert late[3]==.75  # Old floor was distant during PlayerMovement.
    env[21]=112.
    early=step(state(),0,0,env,EMPTY)
    assert early[1]==99.
    assert early[3]==0.  # InstantResize had clamped before PlayerMovement.


def test_native_solid_positive_touch_is_inclusive():
    from nohit.engine.discrete_operator import heart_solid
    env=environment()
    assert heart_solid(13.-1e-9,100.,0.,1.,env,EMPTY)
    assert heart_solid(13.,100.,0.,1.,env,EMPTY)
    assert not heart_solid(13.+1e-9,100.,0.,1.,env,EMPTY)


def test_platform_down_landing_has_fractional_snap_and_inherits_velocity():
    env=environment()
    platform=np.array([[75.,150.,50.,8.,60.,0.,1.]])
    out=step(state(y=141.9),1,0,env,platform)
    assert out[1]==141.95
    assert out[2]==210.
    assert out[3]==0.
    env[5]=3.
    up=step(state(y=141.9,direction=3),1,0,env,platform)
    assert up[1]==141.9
    assert up[2]==150.


def test_newborn_platform_does_not_collide_in_pre_timeline_movement():
    from nohit.engine.discrete_operator import sample_position
    env=environment()
    old=np.array([[75.,150.,50.,8.,0.,0.,1.,1.]])
    newborn=old.copy();newborn[0,7]=0.
    s=state(y=141.9,dy=120.)
    assert sample_position(s,env,old)[1]==141.9
    assert sample_position(s,env,newborn)[1]==142.4


def test_platform_bounce_does_not_retroactively_change_movement_contact():
    from nohit.engine.discrete_operator import heart_solid, sample_position
    env=environment()
    # A right-to-left bounce gives even a horizontal native platform a tiny
    # positive sin(pi) vertical speed, after the heart's behavior already ran.
    platform=np.array([[75.,150.,50.,8.,-90.,math.sin(math.pi)*90.,1.,1.,0.]])
    s=state(y=142.,dx=75.)
    assert heart_solid(s[0],s[1],0.,1.,env,platform,old=True)
    assert not heart_solid(s[0],s[1],0.,1.,env,platform)
    assert sample_position(s,env,platform)==(100.,142.)


def test_timeline_destroyed_platform_only_supports_earlier_behavior_movement():
    env=environment()
    ghost=np.array([[75.,150.,50.,8.,0.,0.,0.,1.,0.]])
    s=state(y=141.9,dy=120.)
    after=step(s,0,0,env,ghost)
    assert after[1]==141.9  # Its behavior-phase fall still hit the platform.
    assert after[3]==.75   # Timeline then removed support before gravity.


def test_cancel_and_opposite_buttons_are_physical_inputs_not_score_changes():
    env=environment(mode=0)
    s=state(mode=0); out=np.empty(11)
    step_mask_into(s,UP|RIGHT|CANCEL,env,EMPTY,out)
    assert tuple(out[2:4])==(75.,-75.)
    step_mask_into(s,UP|DOWN|LEFT|RIGHT,env,EMPTY,out)
    assert tuple(out[2:4])==(0.,0.)


def test_fall_cap_applies_to_gravity_component():
    env=environment(2); env[8]=100.
    out=step(state(dx=-239.,direction=2),0,0,env,EMPTY)
    assert out[2]==-100.


def test_final_signed_fall_cap_reverses_horizontal_motion_and_zero_holds_x():
    env=environment(0);env[8]=-300.
    q=step(state(dx=450.,direction=0),0,0,env,EMPTY)
    assert q[0]==101.875  # Prior velocity is moved before the new cap.
    assert q[2]==-300.
    env[8]=0.;env[6]=1.
    q=step(q,0,1,env,EMPTY)
    assert q[2]==0.
    assert q[3]==-150.


def test_cspace_outside_baked_extent_uses_exact_geometry_without_world_clipping():
    from types import SimpleNamespace
    from nohit.engine.cspace import bake_cspace,collision_query
    white=np.array([[[100.,100.,110.,110.]]]);blue=np.empty((1,0,4))
    wave=SimpleNamespace(env_schedule=environment().reshape(1,-1),geometry_white=white,
                         geometry_blue=blue,geometry_polygons=np.empty((1,0,8)),
                         origin=(0,0),dimensions=(20,20))
    baked=bake_cspace(wave)
    assert collision_query(white,blue,0,state(105.,105.),0.,baked.payload)
    assert not collision_query(white,blue,0,state(-50.,-50.),0.,baked.payload)


def test_source_contract_slam_is_speed_assignment_not_position_reset():
    root=Path(__file__).resolve().parents[1]
    xml=ET.parse(root/'.capx_extract/Event sheets/Battle.xml').getroot()
    block=next(e for e in xml.iter('event-block') if e.get('sid')=='440749620573975')
    actions=block.find('actions').findall('action')
    names=[a.get('name') for a in actions]
    assert names==['Call function','Set boolean','Set angle','Set speed','Set speed']
    assert [a.findall('param')[-1].text for a in actions[-2:]]==[
        'cos(PlayerHeart.Angle)*MaxFallSpeed','sin(PlayerHeart.Angle)*MaxFallSpeed']
    # One-way platforms are implemented only for downward gravity in source.
    solid=next(e for e in xml.iter('event-block') if e.get('sid')=='8364383427250982')
    active=[]
    def collect(e):
        if e.get('disabled')=='1': return
        if e.tag=='condition' and e.get('name')=='Is within angle':
            active.append(e.findall('param')[1].text)
        for child in e: collect(child)
    collect(solid)
    assert active==['90']


def test_original_single_mode_cancel_exits_for_both_x_and_shift_keys():
    root=Path(__file__).resolve().parents[1]
    inputs=ET.parse(root/'.capx_extract/Event sheets/InputManagement.xml').getroot()
    block=next(e for e in inputs.iter('event-block') if e.get('sid')=='4623232669904996')
    assert [p.text for p in block.findall('conditions/condition/param')]==['88','16']
    battle=ET.parse(root/'.capx_extract/Event sheets/Battle.xml').getroot()
    exit_block=next(e for e in battle.iter('event-block') if e.get('sid')=='9206346910846115')
    assert [p.text for p in exit_block.findall('conditions/condition/param')]==[
        'SimulatorMode','0','MODE_SINGLE','Cancel','4','VPad.LastCancel']
    assert exit_block.findall('actions/action')[-1].get('name')=='Go to layout'
