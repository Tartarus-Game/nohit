"""CSV Timeline passes nine parameters; absent array cells are numeric zero.

Timeline.xml:331 reads TLCurrentLine.At(2..10). This differs from a bare
Function call with no argument: CSV BoneStab receives parameter zero=0.
"""
import numpy as np
import pytest

from nohit.engine.parametric_environment import ParametricEnvironment


def compile_case(tmp_path,backend,name,args):
    path=tmp_path/(name+'.csv')
    path.write_text('0,BoneStab'+(','+','.join(args) if args else '')+'\n2,EndAttack\n')
    return ParametricEnvironment(path,backend=backend,dt_schedule=(1/30,)*30,max_ticks=30).bind().wave


@pytest.mark.parametrize('backend',['reference','resumable'])
@pytest.mark.parametrize('count',range(5))
def test_missing_csv_bonestab_fields_equal_native_numeric_zero(tmp_path,backend,count):
    supplied=['3','45','0.5','0.2'][:count]
    actual=compile_case(tmp_path,backend,'missing',supplied)
    expected=compile_case(tmp_path,backend,'explicit',supplied+['0']*(4-count))
    for field in ('env_schedule','platform_table','geometry_white','geometry_blue','geometry_polygons'):
        assert np.asarray(getattr(actual,field)).tobytes()==np.asarray(getattr(expected,field)).tobytes()
    assert actual.terminal_details['active_stabs']==expected.terminal_details['active_stabs']
    if count==0:
        assert actual.terminal_details['active_stabs']==1


@pytest.mark.parametrize('backend',['reference','resumable'])
def test_missing_tail_does_not_change_supplied_direction_guard(tmp_path,backend):
    result=compile_case(tmp_path,backend,'guard',['3.9'])
    assert result.terminal_details['active_stabs']==0


@pytest.mark.parametrize('backend',['reference','resumable'])
def test_explicit_empty_cells_remain_supported(tmp_path,backend):
    actual=compile_case(tmp_path,backend,'empty',['3','','',''])
    expected=compile_case(tmp_path,backend,'zero',['3','0','0','0'])
    assert actual.geometry_white.tobytes()==expected.geometry_white.tobytes()
