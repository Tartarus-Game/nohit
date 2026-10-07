"""Audit the independent certificate helpers against complete scalar operators."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest
from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.cspace import quad_intersects_box,_rect_hit

spec=importlib.util.spec_from_file_location('backward_certificate',Path(__file__).resolve().parents[2]/'scratch/certify_backward_red.py')
certificate=importlib.util.module_from_spec(spec);spec.loader.exec_module(certificate)


@pytest.mark.parametrize('fps',[60,120,240])
def test_outward_successor_cells_enclose_boundary_and_random_full_transitions(fps):
    rng=np.random.default_rng(84231)
    bounds=np.array([241.,226.,406.,391.])
    xd=certificate.clamp_domain(bounds[0],bounds[2]);yd=certificate.clamp_domain(bounds[1],bounds[3])
    xe=certificate.edges(xd,.125);ye=certificate.edges(yd,.125)
    dt=np.array([1.,.9999999999,1.0000000001,.98])/fps
    xl,xh=certificate.successors(xe,dt,xd,bounds[0],bounds[2])
    yl,yh=certificate.successors(ye,dt,yd,bounds[1],bounds[3])
    empty=np.empty((0,9))
    observed_multistep=False
    for trial in range(2500):
        ix=trial%len(xl) if trial<1112 else int(rng.integers(len(xl)))
        iy=(len(yl)-1-ix) if trial<1112 else int(rng.integers(len(yl)))
        fraction=[0.,1.,rng.random()][trial%3]
        x=xe[ix]+fraction*(xe[ix+1]-xe[ix]);y=ye[iy]+fraction*(ye[iy+1]-ye[iy])
        s=np.array([x,y,rng.uniform(-150,150),rng.uniform(-150,150),0.,0.,0.,1.,750.,0.,0.])
        for duration in dt:
            observed_multistep |= bool(np.any(np.floor(np.abs(s[2:4]*duration)+.5)>1))
            row=np.array([*bounds,0.,1.,0.,duration,750.,0.,0.,0.,0.,0.,*bounds,*bounds])
            step_mask_into(s,int(rng.integers(32)),row,empty,s)
        assert xl[ix]<=s[0]<=xh[ix] and yl[iy]<=s[1]<=yh[iy]
    assert observed_multistep == (fps==60)
    assert xe[-1]==xd[1] and ye[-1]==yd[1]
    a,b=certificate.indices(xe,np.array([xe[-1]]),np.array([xe[-1]]))
    assert a.tolist()==[len(xe)-2] and b.tolist()==[len(xe)-1]


def test_fully_blocked_cells_have_same_obstacle_witness_everywhere_sampled():
    xe=np.linspace(-5.,5.,41);ye=np.linspace(-5.,5.,41)
    white=np.array([[-4.,-4.,-2.,-2.],[2.,2.,4.,4.]])
    polygons=np.array([[-3.,0.,0.,-3.,3.,0.,0.,3.]])
    bits=certificate.fully_blocked(xe,ye,white,polygons)
    hit=np.unpackbits(bits.view(np.uint8),bitorder='little')[:1600].reshape(40,40)
    for ix,iy in zip(*np.nonzero(hit)):
        # Same-obstacle four-corner proof, not a union-of-corners shortcut.
        corners=[(x,y) for x in xe[ix:ix+2] for y in ye[iy:iy+2]]
        assert any(all(_rect_hit(b,x,y,2.) for x,y in corners) for b in white) or any(
            all(quad_intersects_box(p,x,y,2.,2.) for x,y in corners) for p in polygons)
        for fx,fy in ((.1,.7),(.5,.5),(.9,.3)):
            x=xe[ix]+fx*(xe[ix+1]-xe[ix]);y=ye[iy]+fy*(ye[iy+1]-ye[iy])
            assert any(_rect_hit(b,x,y,2.) for b in white) or any(quad_intersects_box(p,x,y,2.,2.) for p in polygons)
