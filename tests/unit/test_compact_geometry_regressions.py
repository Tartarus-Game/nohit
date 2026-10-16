"""Regression cases checked against the current jcw87 runtime, not the old export."""
import numpy as np
import pytest

from nohit.engine.compact_wave import TimelineVM


def test_signed_bone_height_matches_jcw_bbox_without_moving_the_gap():
    # Native BoneV(100,232,-2,0,0) reports {left:100,top:230,right:110,bottom:232}.
    sim = TimelineVM().run([['0','BoneV','100','232','-2','0','0'], ['0.02','EndAttack']])
    np.testing.assert_array_equal(sim['geom_white'][0,0], [100,230,110,232])


@pytest.mark.parametrize('command,args', [('BlackScreen',['1']),('EndAttack',[])])
def test_native_attack_family_cleanup_removes_hazards_and_keeps_pre_timeline_platform(command,args):
    # BlackScreen is not purely visual: Battle.xml destroys AttackSprite and
    # Attack9Patch here. Old platforms still existed during CustomMovement.
    rows=[['0','BoneV','200','270','50','0','0'],
          ['0','BoneStab','1','30','0','2'],
          ['0','Platform','200','330','40','0','120','0'],
          ['0.1',command,*args]]
    if command!='EndAttack':rows.append(['0.05','EndAttack'])
    result=TimelineVM().run(rows)
    cleared=next(t for t,c,_ in result['source_events'] if c==command.lower())
    assert np.isfinite(result['geom_white'][cleared-1]).any()
    assert not np.isfinite(result['geom_white'][cleared]).any()
    platform=result['platform_table'][cleared,0]
    assert platform[6]==0 and platform[7]==1
    assert platform[0]==result['platform_table'][cleared-1,0,0]+0.5


def test_platform_repeat_truncates_each_computed_position_like_native_platform_call():
    # sin(pi)'s residual gives the third Y=345.99999999999994. Platform's
    # int(Function.Param(1)) makes that 345: missing it invents a landing.
    result=TimelineVM().run([['0','PlatformRepeat','552','346','51','2','120','3','140'],
                             ['0.05','EndAttack']])
    np.testing.assert_array_equal(result['platform_table'][0,:3,1],[346.,346.,345.])
    np.testing.assert_array_equal(result['platform_table'][0,:3,0],[552.,692.,832.])


def test_platform_parameters_are_truncated_toward_zero():
    result=TimelineVM().run([['0','Platform','-12.9','330.9','40.9','0.9','120.9','0'],
                             ['0.05','EndAttack']])
    np.testing.assert_array_equal(result['platform_table'][0,0,:6],[-12.,330.,40.,7.,120.,0.])


def test_bone_motion_parameters_are_truncated_in_each_native_call():
    result=TimelineVM().run([['0','BoneV','200','300','40','0.9','120.9'],
                             ['0','BoneVRepeat','200','340','40','0','120.9','2','15.9','1'],
                             ['0.05','EndAttack']])
    np.testing.assert_array_equal(result['geom_white'][0,:3],
        [[200.5,300.,210.5,340.],[200.5,340.,210.5,380.],[185.5,340.,195.5,380.]])
    assert not np.isfinite(result['geom_blue'][0]).any()
