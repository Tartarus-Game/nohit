"""Short entity CSV rows use Timeline's numeric-zero missing cells."""
import numpy as np
import pytest

from nohit.engine.parametric_environment import ParametricEnvironment


def compile_case(tmp_path,backend,command,name,args):
    path=tmp_path/(name+'.csv')
    path.write_text('0,'+command+(','+','.join(args) if args else '')+'\n2,EndAttack\n')
    return ParametricEnvironment(path,backend=backend,dt_schedule=(1/30,)*5,max_ticks=5).bind().wave


@pytest.mark.parametrize('backend',['reference','resumable'])
@pytest.mark.parametrize('command',['BoneV','BoneH','Platform'])
@pytest.mark.parametrize('count',range(7))
def test_short_csv_entity_rows_match_numeric_zero_defaults(tmp_path,backend,command,count):
    supplied=['240','300','20','2','30','1'][:count]
    actual=compile_case(tmp_path,backend,command,'missing',supplied)
    expected=compile_case(tmp_path,backend,command,'explicit',supplied+['0']*(6-count))
    for field in ('env_schedule','platform_table','geometry_white','geometry_blue','geometry_polygons'):
        assert np.asarray(getattr(actual,field)).tobytes()==np.asarray(getattr(expected,field)).tobytes()


@pytest.mark.parametrize('backend',['reference','resumable'])
@pytest.mark.parametrize('command',['BoneV','BoneH','Platform'])
def test_explicit_empty_entity_cells_keep_existing_behavior(tmp_path,backend,command):
    actual=compile_case(tmp_path,backend,command,'empty',['240','300','20','','',''])
    expected=compile_case(tmp_path,backend,command,'zero',['240','300','20','0','0','0'])
    for field in ('platform_table','geometry_white','geometry_blue'):
        assert np.asarray(getattr(actual,field)).tobytes()==np.asarray(getattr(expected,field)).tobytes()
