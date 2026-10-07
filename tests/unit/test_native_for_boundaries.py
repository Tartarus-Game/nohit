"""Source System.For descends when EndIndex < StartIndex; no Count guard."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import numpy as np
import pytest
from nohit.engine.parametric_environment import ParametricEnvironment


def wave(tmp_path,backend,text):
    path=tmp_path/'for-boundary.csv'
    path.write_text(text+'\n1,EndAttack\n')
    return ParametricEnvironment(path,backend=backend,dt_schedule=[1/240],
        max_ticks=1).bind().wave


@pytest.mark.parametrize('backend',['reference','resumable'])
@pytest.mark.parametrize('command',['PlatformRepeat','BoneHRepeat','BoneVRepeat'])
@pytest.mark.parametrize('source,indices',[
    ('0',[0,-1]),('-1',[0,-1,-2]),('2',[0,1]),
    ('-0.1',[0,-1]),('$n',[0,-1,-2]),
])
def test_repeat_uses_inclusive_native_for_direction(tmp_path,backend,command,source,indices):
    prefix='0,MUL,n,-0.1,1\n' if source=='$n' else ''
    result=wave(tmp_path,backend,prefix+f'0,{command},200,300,20,0,0,{source},10')
    if command=='PlatformRepeat':
        xs=result.platform_table[0,:result.num_platforms[0],0]
    else:
        boxes=result.geometry_white[0]
        xs=boxes[np.isfinite(boxes).all(axis=1),0]
    np.testing.assert_array_equal(xs,[200.-10.*i for i in indices])


@pytest.mark.parametrize('backend',['reference','resumable'])
@pytest.mark.parametrize('count,indices',[('0',[0,-1]),('-1',[0,-1,-2]),('2',[0,1])])
def test_sinebones_uses_inclusive_native_for_direction(tmp_path,backend,count,indices):
    result=wave(tmp_path,backend,f'0,SineBones,{count},10,0,20')
    boxes=result.geometry_white[0]
    xs=boxes[np.isfinite(boxes).all(axis=1),0]
    right=result.env_schedule[0,2]
    np.testing.assert_array_equal(xs,[right+10.*i for i in indices for _ in range(2)])


@pytest.mark.parametrize('backend',['reference','resumable'])
@pytest.mark.parametrize('spacing',['0','0.9'])
def test_sinebones_zero_spacing_keeps_default_x_local(tmp_path,backend,spacing):
    result=wave(tmp_path,backend,f'0,SineBones,1,{spacing},0,20')
    boxes=result.geometry_white[0]
    xs=boxes[np.isfinite(boxes).all(axis=1),0]
    np.testing.assert_array_equal(xs,[0.,0.])
