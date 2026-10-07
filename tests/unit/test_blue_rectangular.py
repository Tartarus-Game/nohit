import numpy as np
import pytest
from nohit.engine.compact_wave import compile_wave
from nohit.engine.cspace import bake_cspace
from nohit.engine.local_relation import full_local_relation
from nohit.engine.blue_flag_dense import full_flag_states
from nohit.engine.blue_rectangular import ProductFrontier,advance_product,product_predecessor


def setup(tmp_path,slam=8,holes=False):
    path=tmp_path/'product.csv';path.write_text('0,HeartMode,1\n0.1,EndAttack\n')
    wave=compile_wave(path);wave.env_schedule[:,5]=2;wave.env_schedule[slam,6]=1;wave.env_schedule[slam:,5]=0
    x=np.array([[315.,0.,0.],[315.,0.,2.],[325.,0.,0.],[325.,0.,2.]])
    y=np.array([[300.,0.],[377.75,150.]])
    template=np.array([315.,300.,0.,0.,0.,0.,1.,2.,750.,0.,0.])
    rects=[(0,np.arange(4),np.arange(2))] if not holes else [(0,np.arange(2),np.array([0])),(1,np.arange(2,4),np.array([1]))]
    front=ProductFrontier(x,y,rects,template,0)
    initial=np.array([front.state(ix,iy,f) for f in (0,1) for ix in range(4) for iy in range(2) if front.contains(ix,iy,f)])
    return wave,front,initial


@pytest.mark.parametrize('slam',[1,5,8])
@pytest.mark.parametrize('holes',[False,True])
def test_cartesian_union_and_flag_planes_equal_complete_operator(tmp_path,slam,holes):
    wave,front,initial=setup(tmp_path,slam,holes);space=bake_cspace(wave)
    for stop in (4,8,12):
        status,child,maps,stats=advance_product(wave,front,4,space)
        assert status=='complete'
        expected=full_local_relation(wave,0,stop,initial,hold=4,cspace=space,input_latch_quotient=True)
        assert {s.tobytes() for s in full_flag_states(child)}=={s.tobytes() for s in expected.states}
        assert sum(child.counts(include_vertical_aliases=True))==len(expected.states)
        assert sum(child.counts())==sum(child.contains(ix,iy,f) for f in (0,1) for ix in range(len(child.x)) for iy in range(len(child.y)))
        for f in (0,1):
            for ix in range(len(child.x)):
                for iy in range(len(child.y)):
                    if child.contains(ix,iy,f):
                        parent,mask=product_predecessor(wave,front,child,(ix,iy,f),maps,4,space)
                        assert front.contains(*parent)
        front=child


def test_per_axis_strip_collisions_match_joint_cspace(tmp_path):
    wave,front,initial=setup(tmp_path)
    wave.geometry_white=np.full((len(wave.env_schedule),2,4),np.nan)
    wave.geometry_white[1:,0]=[314.,251.,316.,391.]
    wave.geometry_white[1:,1]=[133.,376.,508.,378.]
    space=bake_cspace(wave);status,child,_,_=advance_product(wave,front,4,space)
    assert status=='complete'
    expected=full_local_relation(wave,0,4,initial,cspace=space)
    assert {s.tobytes() for s in full_flag_states(child)}=={s.tobytes() for s in expected.states}


def test_nonseparable_corner_hazard_is_unknown(tmp_path):
    wave,front,_=setup(tmp_path)
    wave.geometry_white=np.full((len(wave.env_schedule),1,4),np.nan);wave.geometry_white[1:]=[314.,299.,316.,301.]
    status,child,_,stats=advance_product(wave,front,4,bake_cspace(wave))
    assert status=='unsupported' and child is None
    assert stats['reason']=='cspace_not_certified_axis_strips'
