import numpy as np
import pytest
from nohit.engine.compact_wave import compile_wave
from nohit.engine.cspace import bake_cspace,collision_query
from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.factored_red import solve_fixed_red


@pytest.mark.parametrize('mask_count',[16,32])
def test_every_safe_exit_matches_unfactored_operator(tmp_path,mask_count):
    path=tmp_path/'red.csv'
    path.write_text('0,HeartMode,0\n0,BoneV,326,280,40,0,0\n0.2,EndAttack\n')
    wave=compile_wave(path);space=bake_cspace(wave)
    initial=np.array([320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.])
    controls=tuple(range(mask_count));result=solve_fixed_red(wave,0,12,initial,controls=controls,cspace=space)
    front={initial.tobytes():initial};empty=np.empty((0,9))
    for tick in range(0,12,4):
        following={}
        for s in front.values():
            for mask in controls:
                q=s.copy();safe=True
                for micro in range(4):
                    out=np.empty(11);step_mask_into(q,mask,wave.env_schedule[tick+micro+1],empty,out);q=out
                    if collision_query(wave.geometry_white,wave.geometry_blue,tick+micro+1,q,0.,space.payload):
                        safe=False;break
                if safe:following[q.tobytes()]=q
        front=following
    assert {s.tobytes() for s in result.exit_states()}==set(front)
    assert result.exits
    for node,mask in list(result.exits)[:8]:
        word=result.witness(node,mask);assert len(word)==3
        q=initial.copy()
        for frame,control in enumerate(word):
            for micro in range(4):
                out=np.empty(11);step_mask_into(q,control,wave.env_schedule[frame*4+micro+1],empty,out);q=out
                assert not collision_query(wave.geometry_white,wave.geometry_blue,frame*4+micro+1,q,0.,space.payload)
        assert q.tobytes() in front


def test_blue_slice_is_rejected_instead_of_approximated(tmp_path):
    path=tmp_path/'blue.csv';path.write_text('0,HeartMode,1\n0.2,EndAttack\n')
    wave=compile_wave(path)
    with pytest.raises(ValueError,match='not_fixed_red'):
        solve_fixed_red(wave,0,8,[320.,304.,0.,0.,0.,0.,1.,1.,750.,0.,0.])


def test_closed_top_contact_couples_horizontal_motion_and_is_rejected(tmp_path):
    path=tmp_path/'red.csv';path.write_text('0,HeartMode,0\n0.2,EndAttack\n')
    wave=compile_wave(path);top=wave.env_schedule[1,1]+13
    edge=np.array([320.,top,150.,0.,2.,0.,0.,1.,750.,0.,0.])
    inside=edge.copy();inside[1]=np.nextafter(top,np.inf)
    empty=np.empty((0,9));a=np.empty(11);b=np.empty(11)
    step_mask_into(edge,2,wave.env_schedule[1],empty,a)
    step_mask_into(inside,2,wave.env_schedule[1],empty,b)
    assert a[0]==edge[0] and b[0]>inside[0]  # Same x/dx/mask, different x successor.
    with pytest.raises(ValueError,match='not_strict_interior'):
        solve_fixed_red(wave,0,8,edge)
