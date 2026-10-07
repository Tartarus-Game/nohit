"""Source-derived one-frame typed-command regressions for both backends.

These model microcases do not substitute for whole-game native acceptance.
"""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import numpy as np
import pytest

from nohit.engine.parametric_environment import ParametricEnvironment


def wave(tmp_path,backend,text,**kwargs):
    path=tmp_path/'one-variable.csv';path.write_text(text+'\n1,EndAttack\n')
    return ParametricEnvironment(path,backend=backend,dt_schedule=[1/240],max_ticks=1,**kwargs).bind().wave


def supplied(source,name,value):
    if source=='literal':return '',value
    if source=='set':return f'0,SET,{name},{value}\n',f'${name}'
    return f'0,MUL,{name},{value},1\n',f'${name}'


@pytest.mark.parametrize('backend',['reference','resumable'])
@pytest.mark.parametrize('source,expected',[('literal',-12.),('set',-12.),('mul',-13.)])
def test_bonev_only_height_type_changes(tmp_path,backend,source,expected):
    prefix,height=supplied(source,'height','-12.9')
    result=wave(tmp_path,backend,prefix+f'0,BoneV,200,300,{height},0,0,0')
    active=result.geometry_white[0]
    active=active[np.isfinite(active).all(axis=1)]
    np.testing.assert_array_equal(active,[[200.,300.+float(expected),210.,300.]])


@pytest.mark.parametrize('backend',['reference','resumable'])
@pytest.mark.parametrize('source,expected',[('literal',-12.),('set',-12.),('mul',-13.)])
def test_platform_only_x_type_changes(tmp_path,backend,source,expected):
    prefix,x=supplied(source,'x','-12.9')
    result=wave(tmp_path,backend,prefix+f'0,Platform,{x},330,40,0,0')
    assert result.num_platforms[0]==1
    assert result.platform_table[0,0,0]==expected


@pytest.mark.parametrize('backend',['reference','resumable'])
def test_repeat_local_number_and_generated_x_differ_from_direct_literal(tmp_path,backend):
    direct=wave(tmp_path,backend,'0,Platform,-12.9,330,40,0,0')
    repeat=wave(tmp_path,backend,'0,PlatformRepeat,-12.9,330,40,0,0,1,140')
    assert direct.platform_table[0,0,0]==-12.
    # Repeat local StartX is numeric and its subtraction result is numeric,
    # even for child zero; the nested Platform int therefore floors to -13.
    assert repeat.platform_table[0,0,0]==-13.


@pytest.mark.parametrize('backend',['reference','resumable'])
def test_repeat_forwarded_width_is_a_numeric_local_not_the_literal_string(tmp_path,backend):
    direct=wave(tmp_path,backend,'0,Platform,200,330,1e1,0,0')
    repeat=wave(tmp_path,backend,'0,PlatformRepeat,200,330,1e1,0,0,1,140')
    # System local-number SetValue parseFloats the width before forwarding.
    # Direct int('1e1') is 1; Repeat's nested int(10.0) is 10.
    assert direct.platform_table[0,0,2]==1.
    assert repeat.platform_table[0,0,2]==10.


@pytest.mark.parametrize('backend',['reference','resumable'])
def test_repeat_count_converts_before_entering_numeric_local(tmp_path,backend):
    result=wave(tmp_path,backend,'0,PlatformRepeat,200,330,40,0,0,1e1,140')
    # Count has explicit int(P5) before local assignment: it remains 1.
    assert result.num_platforms[0]==1


@pytest.mark.parametrize('backend',['reference','resumable'])
@pytest.mark.parametrize('source,expected_second_x',[('literal',212.),('set',212.),('mul',213.)])
def test_repeat_only_spacing_type_changes(tmp_path,backend,source,expected_second_x):
    prefix,spacing=supplied(source,'spacing','-12.9')
    result=wave(tmp_path,backend,prefix+f'0,PlatformRepeat,200,330,40,0,0,2,{spacing}')
    assert result.num_platforms[0]==2
    assert result.platform_table[0,0,0]==200.
    assert result.platform_table[0,1,0]==expected_second_x


@pytest.mark.parametrize('backend',['reference','resumable'])
@pytest.mark.parametrize('source,expected',[('literal',-12.),('set',-12.),('mul',-13.)])
def test_heart_max_fall_speed_only_value_type_changes(tmp_path,backend,source,expected):
    prefix,value=supplied(source,'speed','-12.9')
    result=wave(tmp_path,backend,prefix+f'0,HeartMaxFallSpeed,{value}')
    assert result.env_schedule[0,8]==expected


@pytest.mark.parametrize('backend',['reference','resumable'])
def test_combat_zone_speed_literal_is_integer_before_world_resize(tmp_path,backend):
    initial=[0.,0.,100.,100.,0.,1.,0.,1/240,750.,0.,0.,0.,0.,0.,0.,0.,100.,100.,0.,0.,100.,100.]
    arena=dict(target=[0.,0.,100.,100.],size=[100.,100.],speed=480.,callback='')
    result=wave(tmp_path,backend,'0,CombatZoneSpeed,1.9\n0,CombatZoneResize,1,0,101,100,',
        initial_environment=initial,initial_arena=arena)
    assert result.env_schedule[0,0]==1./240.


@pytest.mark.parametrize('backend',['reference','resumable'])
def test_invalid_heart_mode_does_not_change_slam_direction(tmp_path,backend):
    result=wave(tmp_path,backend,'0,SansSlam,2\n0,HeartMode,3')
    assert result.env_schedule[0,4]==1.
    assert result.env_schedule[0,5]==2.


@pytest.mark.parametrize('backend',['reference','resumable'])
@pytest.mark.parametrize('reverse,expected_vx',[('-1',240.),('0',240.),('1',-240.)])
def test_platform_reverse_uses_positive_comparison(tmp_path,backend,reverse,expected_vx):
    result=wave(tmp_path,backend,f'0,Platform,600,330,40,0,240,{reverse}')
    assert result.num_platforms[0]==1
    assert result.platform_table[0,0,4]==expected_vx


@pytest.mark.parametrize('backend',['reference','resumable'])
def test_bonestab_guard_rejects_before_integer_conversion(tmp_path,backend):
    # Both values would become valid direction 0/3 if tested after truncation.
    result=wave(tmp_path,backend,'0,BoneStab,-0.1,20,0,1\n0,BoneStab,3.9,20,0,1')
    assert not np.isfinite(result.geometry_white[0]).all(axis=1).any()


@pytest.mark.parametrize('backend',['reference','resumable'])
@pytest.mark.parametrize('command',['BoneHRepeat','BoneVRepeat'])
def test_bone_repeat_forwarded_extent_is_numeric_local(tmp_path,backend,command):
    result=wave(tmp_path,backend,f'0,{command},200,300,-12.9,0,0,1,140')
    active=result.geometry_white[0]
    active=active[np.isfinite(active).all(axis=1)]
    expected=([187.,300.,200.,310.] if command=='BoneHRepeat'
        else [200.,287.,210.,300.])
    np.testing.assert_array_equal(active,[expected])


@pytest.mark.parametrize('backend',['reference','resumable'])
@pytest.mark.parametrize('source,expected_top',[('literal',-12.),('set',-12.),('mul',-13.)])
def test_sinebones_height_conversion_precedes_numeric_child(tmp_path,backend,source,expected_top):
    prefix,height=supplied(source,'height','-12.9')
    result=wave(tmp_path,backend,prefix+f'0,SineBones,1,140,0,{height}')
    active=result.geometry_white[0]
    active=active[np.isfinite(active).all(axis=1)]
    top_y=result.env_schedule[0,1]+6.
    assert active[0,1]==top_y+expected_top
    assert active[0,3]==top_y
