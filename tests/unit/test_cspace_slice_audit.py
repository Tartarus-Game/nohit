"""Independent ordered-domain audit against the unchanged scalar predicates."""
import numpy as np
import pytest
from nohit.engine.cspace import quad_intersects_box
from nohit.engine.cspace_slice import quad_y_interval, section_collision_bits


def test_sections_keep_duplicates_signed_zero_and_exact_projection_order():
    rng=np.random.default_rng(774201)
    for scale in (1.e-100,1.,1.e12,1.e100):
        for _ in range(30):
            # Finite arbitrary vertices also test degenerate/concave SAT inputs:
            # equality is to the original predicate, not an altered polygon model.
            poly=rng.uniform(-3,3,8)*scale
            x=rng.uniform(-2,2)*scale
            coordinates=np.r_[rng.uniform(-5,5,50)*scale,poly[1::2],[-0.,0.]]
            ys=np.sort(np.r_[coordinates,np.nextafter(coordinates,-np.inf),np.nextafter(coordinates,np.inf)])
            first,last=quad_y_interval(poly,x,ys)
            expected=np.array([quad_intersects_box(poly,x,y,2.,2.) for y in ys])
            actual=np.zeros(len(ys),bool);actual[first:last]=True
            np.testing.assert_array_equal(actual,expected)


def test_planes_are_unconditional_plus_blue_not_two_complete_movement_states():
    xs=np.array([0.]);ys=np.array([-20.,-1.,0.,1.,20.])
    white=np.array([[-1.,-1.,1.,1.]])
    blue=np.array([[-1.,19.,1.,21.]])
    bits=section_collision_bits(xs,ys,white,blue,np.empty((0,8)))
    unconditional=int(bits[0,0]);blue_only=int(bits[1,0])
    assert unconditional==0b01110
    assert blue_only==0b10000
    assert unconditional | blue_only == 0b11110
    # Padding never becomes a spurious endpoint.
    assert unconditional >> len(ys) == blue_only >> len(ys) == 0


@pytest.mark.parametrize('box',[[319.,305.,321.,303.],[-1.e30,-1.e30,1.e30,1.e30]])
def test_dense_section_falls_back_outside_grid_geometry_contract(tmp_path,box):
    from nohit.engine.compact_wave import compile_wave
    from nohit.engine.cspace import bake_cspace
    from nohit.engine.red_joint_frontier import AxisFrontier
    from nohit.engine.red_dense_frontier import DenseFrontier,advance_dense
    from nohit.engine.red_section_frontier import advance_section_dense
    path=tmp_path/'inverted.csv';path.write_text('0,HeartMode,0\n0.2,EndAttack\n')
    wave=compile_wave(path)
    # Scalar _rect_hit accepts overlap with this inverted but narrow box.
    # The existing C-space bake skips it, so its flag-zero collision_query
    # short circuit differs; section must not silently change that contract.
    wave.geometry_white=np.tile(box,(len(wave.env_schedule),1,1))
    space=bake_cspace(wave)
    state=np.array([[320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.]])
    front=DenseFrontier.from_axis(AxisFrontier.from_states(state))
    status,expected,_=advance_dense(wave,front,(0,),0,1,space)
    other,actual,stats=advance_section_dense(wave,front,(0,),0,1,space)
    assert status==other=='complete'
    assert stats['section_domain_fallback']
    assert actual.count==expected.count==1
    np.testing.assert_array_equal(actual.bits,expected.bits)


@pytest.mark.parametrize('origin,size', [((0.,0.),1.e-30),((1.e30,0.),1.),
    ((np.inf,0.),1.),((0.,0.),np.nan),((0.,0.),0.)])
def test_section_domain_rejects_unsafe_grid_index_arithmetic(tmp_path,origin,size):
    from types import SimpleNamespace
    from nohit.engine.red_section_frontier import section_domain
    wave=SimpleNamespace(geometry_white=np.empty((2,0,4)),geometry_blue=np.empty((2,0,4)))
    space=SimpleNamespace(polygons=np.empty((2,0,8)),origin=origin,cell_size=size)
    trace=np.zeros((1,1,1,2))
    assert not section_domain(wave,space,0,1,[trace,trace])
