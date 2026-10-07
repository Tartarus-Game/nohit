"""Parallel expansion preserves exact edges and the caller's thread mask."""
from types import SimpleNamespace
import numpy as np
import pytest
from numba import get_num_threads,set_num_threads
from nohit.engine.local_relation import _expand
from nohit.engine.cspace import bake_cspace
from nohit.engine.parallel_expansion import expand_parallel


@pytest.mark.parametrize('workers',[1,2,4,8])
@pytest.mark.parametrize('hold',[1,4])
@pytest.mark.parametrize('empty',[False,True])
def test_exact_values_and_parent_control_order(workers,hold,empty):
    env=np.tile(np.array([0,0,100,100,0,1,0,1/240,750,0,0,0,0,0,
                         0,0,100,100,0,0,100,100],float),(10,1))
    platforms=np.zeros((10,4,9),float)
    white=np.full((10,1,4),np.nan);white[2,0]=[38,38,42,42]
    blue=np.full((10,1,4),np.nan);blue[3,0]=[20,20,30,30]
    wave=SimpleNamespace(env_schedule=env,geometry_white=white,geometry_blue=blue,
        geometry_polygons=np.empty((10,0,8)),dimensions=(100,100),origin=(0,0))
    space=bake_cspace(wave,cell_size=8)
    states=np.array([[40,40,0,0,0,0,0,1,750,0,0],
                     [60,60,10,0,0,0,0,1,750,0,0],
                     [25,25,0,0,0,0,0,1,750,0,0]],float)
    if empty:states=states[:0]
    controls=np.array([0,2,0,31,8,4],np.int64)
    before=states.copy()
    params=(states,controls,0,hold,env,platforms,white,blue,space.payload)
    expected=_expand(*params);previous=get_num_threads()
    for _ in range(3):
        actual=expand_parallel(*params,workers=workers)
        for first,second in zip(actual,expected):
            assert first.shape==second.shape and first.dtype==second.dtype
            assert first.tobytes()==second.tobytes()
        assert states.tobytes()==before.tobytes()
        assert get_num_threads()==previous


def test_default_two_workers_restores_mask_on_failure(monkeypatch):
    import nohit.engine.parallel_expansion as module
    previous=get_num_threads()
    try:
        set_num_threads(4)
        def fail(*args):
            assert get_num_threads()==2
            raise RuntimeError('kernel failed')
        monkeypatch.setattr(module,'_expand_parallel_kernel',fail)
        with pytest.raises(RuntimeError,match='kernel failed'):
            module.expand_parallel(*([None]*9))
        assert get_num_threads()==4
    finally:set_num_threads(previous)


@pytest.mark.parametrize('workers',[0,-1,1.5,True])
def test_invalid_workers_does_not_change_mask(workers):
    previous=get_num_threads()
    with pytest.raises(ValueError,match='workers must be an integer'):
        expand_parallel(*([None]*9),workers=workers)
    assert get_num_threads()==previous
