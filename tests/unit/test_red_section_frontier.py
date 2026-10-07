import numpy as np
import pytest
from nohit.engine.compact_wave import compile_wave
from nohit.engine.cspace import bake_cspace
from nohit.engine.red_joint_frontier import AxisFrontier
from nohit.engine.red_dense_frontier import DenseFrontier,advance_dense,unpack_keys,predecessor
from nohit.engine.red_section_frontier import advance_section_dense,bake_observations


@pytest.mark.parametrize('hold',[1,4])
@pytest.mark.parametrize('plane',['white','blue','polygon'])
def test_sections_preserve_complete_relation_and_witnesses(tmp_path,hold,plane):
    path=tmp_path/'red.csv';path.write_text('0,HeartMode,0\n0.2,EndAttack\n')
    wave=compile_wave(path);nt=len(wave.env_schedule)
    boxes=np.tile(np.array([1000.,1000.,1010.,1010.]),(nt,1,1))
    boxes[1,0]=[321.,300.,325.,308.]
    if plane=='polygon':
        wave.geometry_polygons=np.tile(np.array([321.,299.,325.,303.,321.,307.,317.,303.]),(nt,1,1))
    else:setattr(wave,'geometry_'+plane,boxes)
    wave.env_schedule[1:hold+1,7]=np.resize([.0031,.0067,.0042,.0048],hold)
    space=bake_cspace(wave)
    states=np.array([[x,y,0.,0.,0.,0.,0.,1.,750.,0.,0.] for x,y in
        [(320.,304.),(np.nextafter(320.,-np.inf),304.),(315.,308.),(320.,315.)]])
    front=DenseFrontier.from_axis(AxisFrontier.from_states(states));controls=tuple(range(32))
    status,actual,_=advance_section_dense(wave,front,controls,0,hold,space)
    expected_status,expected,_=advance_dense(wave,front,controls,0,hold,space)
    assert status==expected_status=='complete' and actual.count==expected.count
    for name in ['x','y','bits','template']:
        np.testing.assert_array_equal(getattr(actual,name),getattr(expected,name))
    for key in unpack_keys(actual.bits,len(actual.x)*len(actual.y)):
        predecessor(wave,front,actual.state(key),controls,0,hold,space)
    status,fallback,stats=advance_section_dense(wave,front,controls,0,hold,space,max_cache_bytes=1)
    assert status=='complete' and stats['section_budget_fallback']
    np.testing.assert_array_equal(fallback.bits,actual.bits)


def test_signed_coordinates_are_sorted_numerically_without_dynamic_merge():
    tx=np.zeros((1,5,1,2));ty=np.zeros_like(tx)
    tx[0,:,0,0]=[-2.,-0.,0.,2.,np.nextafter(2.,np.inf)]
    ty[0,:,0,0]=[2.,-2.,-0.,0.,1.]
    white=np.array([[[0.,-1.,0.,1.]],[[0.,-1.,0.,1.]]])
    blue=np.empty((2,0,4));polys=np.empty((2,0,8))
    obs,_=bake_observations(tx,ty,white,blue,polys,0,10000)
    xmap,ymap,ny,offsets,hit=obs
    assert len(set(xmap.ravel()))==5 and len(set(ymap.ravel()))==5
    assert ymap[0,1,0]<ymap[0,4,0]<ymap[0,0,0]


def test_inverted_rectangles_use_grid_query_semantics(tmp_path):
    path=tmp_path/'red.csv';path.write_text('0,HeartMode,0\n0.2,EndAttack\n')
    wave=compile_wave(path)
    wave.geometry_white=np.tile(np.array([319.,305.,321.,303.]),(len(wave.env_schedule),1,1))
    space=bake_cspace(wave)
    front=DenseFrontier.from_axis(AxisFrontier.from_states(
        [np.array([320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.])]))
    status,out,stats=advance_section_dense(wave,front,(0,),0,1,space)
    assert status=='complete' and stats['section_domain_fallback'] and out.count==1
