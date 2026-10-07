import math
import numpy as np
from nohit.engine.cspace import quad_intersects_box
from nohit.engine.cspace_slice import quad_y_interval
from nohit.engine.cspace_slice import rect_y_interval, section_collision_bits
from nohit.engine.cspace import _rect_hit


def test_vertical_sections_match_every_original_sat_query_at_rotations_and_tangencies():
    ys=np.sort(np.concatenate((np.linspace(-30,30,1201),np.array([-2.,2.,0.]),
        np.nextafter(np.array([-2.,2.,0.]),-np.inf),np.nextafter(np.array([-2.,2.,0.]),np.inf))))
    for angle in [0.,math.pi/2,math.pi,math.pi/4,-math.pi/3,1.e-12]:
        c,s=math.cos(angle),math.sin(angle)
        base=np.array([[-20.,-2.],[20.,-2.],[20.,2.],[-20.,2.]])
        poly=(base@np.array([[c,s],[-s,c]])).ravel()
        for x in [-25.,-20.,-2.,0.,2.,20.,25.,np.nextafter(2.,np.inf)]:
            first,last=quad_y_interval(poly,x,ys)
            expected=np.array([quad_intersects_box(poly,x,y,2.,2.) for y in ys])
            actual=np.zeros(len(ys),bool);actual[first:last]=True
            np.testing.assert_array_equal(actual,expected)


def test_empty_absent_and_degenerate_sections():
    for poly in [np.full(8,np.nan),np.zeros(8),np.array([0.,0.,1.,0.,2.,0.,3.,0.])]:
        assert quad_y_interval(poly,0.,np.array([]))==(0,0)
        ys=np.linspace(-4,4,101)
        a,b=quad_y_interval(poly,0.,ys)
        assert np.flatnonzero([quad_intersects_box(poly,0.,y,2.,2.) for y in ys]).tolist()==list(range(a,b))


def test_rectangle_sections_match_exact_predicate_with_padding_and_inversion():
    ys=np.sort(np.r_[np.linspace(-10,10,133),[-2.,2.],np.nextafter([-2.,2.],np.inf)])
    for box in [np.array([-2.,-2.,2.,2.]),np.array([0.,1.,0.,-1.]),np.full(4,np.nan),
                np.array([-np.inf,-np.inf,np.inf,np.inf])]:
        for x in [-4.,0.,4.,np.nextafter(4.,np.inf)]:
            a,b=rect_y_interval(box,x,ys)
            assert np.flatnonzero([_rect_hit(box,x,y,2.) for y in ys]).tolist()==list(range(a,b))


def test_section_bit_union_matches_unconditional_and_moving_collision_planes():
    rng=np.random.default_rng(642)
    xs=rng.uniform(-30,30,31);ys=np.sort(rng.uniform(-30,30,139))
    white=np.array([[-20.,-5.,0.,3.],[12.,15.,20.,18.],np.full(4,np.nan)])
    blue=np.array([[-30.,10.,30.,14.]])
    polygons=[]
    for _ in range(9):
        angle=rng.uniform(-math.pi,math.pi);c,s=math.cos(angle),math.sin(angle)
        base=np.array([[-20.,-2.],[20.,-2.],[20.,2.],[-20.,2.]])
        polygons.append((base@np.array([[c,s],[-s,c]])+rng.uniform(-20,20,2)).ravel())
    polygons=np.array(polygons)
    bits=section_collision_bits(xs,ys,white,blue,polygons)
    for ix,x in enumerate(xs):
        for iy,y in enumerate(ys):
            key=ix*len(ys)+iy
            for plane,boxes in enumerate([white,blue]):
                expected=any(_rect_hit(box,x,y,2.) for box in boxes)
                if plane==0:expected|=any(quad_intersects_box(poly,x,y,2.,2.) for poly in polygons)
                assert bool(int(bits[plane,key//64])&(1<<(key%64)))==expected
    capacity=len(xs)*len(ys)
    assert int(bits[0,-1])>>(capacity%64)==0
    assert int(bits[1,-1])>>(capacity%64)==0
