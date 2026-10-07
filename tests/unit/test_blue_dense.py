import numpy as np
import pytest
from nohit.engine.compact_wave import compile_wave
from nohit.engine.cspace import bake_cspace
from nohit.engine.local_relation import full_local_relation
from nohit.engine.blue_dense import BlueFrontier,advance_blue,full_states,predecessor


def setup(tmp_path,direction=2):
    path=tmp_path/'blue.csv';path.write_text('0,HeartMode,1\n0.1,EndAttack\n')
    wave=compile_wave(path);wave.env_schedule[:,5]=direction
    states=[]
    # Includes near-side and near-perpendicular-wall behavior, but all starts
    # are strictly interior. Not every Cartesian pair is initially reachable.
    for x,y,dx,dy,mask in ((147.1,264.25,-150.,-150.,2),(320.,304.,0.,0.,0),(494.75,377.5,150.,150.,10),
                         (146.25,365.,0.,0.,0),(494.75,265.,0.,750.,0)):
        states.append([x,y,dx,dy,float(mask),0.,1.,float(direction),750.,0.,0.])
    return wave,np.array(states)


@pytest.mark.parametrize('direction',[0,2])
@pytest.mark.parametrize('hold',[1,4])
def test_dense_blue_matches_every_full_operator_exit(tmp_path,direction,hold):
    wave,states=setup(tmp_path,direction);space=bake_cspace(wave)
    front,keys,origins=BlueFrontier.from_states(states,0)
    assert len(keys)==len(origins)==len(states)
    for start in (0,hold):
        status,child,maps,stats=advance_blue(wave,front,hold,space)
        assert status=='complete'
        expected=full_local_relation(wave,0,start+hold,states,hold=hold,cspace=space,input_latch_quotient=True)
        assert {s.tobytes() for s in full_states(child)}=={s.tobytes() for s in expected.states}
        for ix in range(len(child.x)):
            for iy in range(len(child.y)):
                if child.contains(ix,iy):
                    parent,mask=predecessor(wave,front,child,(ix,iy),maps,hold,space)
                    assert front.contains(*parent) and 0<=mask<16
        front=child


def test_joint_hazards_do_not_turn_marginal_axes_into_reachable_pairs(tmp_path):
    wave,states=setup(tmp_path)
    wave.geometry_white=np.full((len(wave.env_schedule),1,4),np.nan)
    wave.geometry_white[1:]=[314.9,299.9,315.1,300.1]
    states=np.array([[x,y,0.,0.,0.,0.,1.,2.,750.,0.,0.] for x in (315.,325.) for y in (300.,310.)])
    space=bake_cspace(wave);front,_,_=BlueFrontier.from_states(states,0)
    status,child,maps,stats=advance_blue(wave,front,4,space)
    assert status=='complete'
    expected=full_local_relation(wave,0,4,states,hold=4,cspace=space)
    assert {s.tobytes() for s in full_states(child)}=={s.tobytes() for s in expected.states}
    assert child.count()<len(child.x)*len(child.y)


@pytest.mark.parametrize('change',['slam','platform','teleport','gravity','touch'])
def test_unsupported_coupling_keeps_original_frontier(tmp_path,change):
    wave,states=setup(tmp_path);space=bake_cspace(wave)
    if change=='slam':wave.env_schedule[2,6]=1
    elif change=='platform':
        wave.platform_table=np.zeros((len(wave.env_schedule),1,9));wave.platform_table[2,0,6]=1
    elif change=='teleport':wave.env_schedule[2,9]=1
    elif change=='gravity':wave.env_schedule[2,5]=1
    else:states[0,1]=wave.env_schedule[1,1]+13.
    front,_,_=BlueFrontier.from_states(states,0);snapshot=front.bits.tobytes()
    status,child,maps,stats=advance_blue(wave,front,4,space)
    assert status=='unsupported' and child is None and maps is None
    assert front.bits.tobytes()==snapshot


def test_resource_limit_never_publishes_partial_layer(tmp_path):
    wave,states=setup(tmp_path);space=bake_cspace(wave);front,_,_=BlueFrontier.from_states(states,0)
    status,child,maps,stats=advance_blue(wave,front,4,space,max_product=1)
    assert status=='resource_limit' and child is None and maps is None
