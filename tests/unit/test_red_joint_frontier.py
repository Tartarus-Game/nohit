import numpy as np
import pytest
from nohit.engine.compact_wave import compile_wave
from nohit.engine.cspace import bake_cspace
from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.local_relation import full_local_relation
from nohit.engine.red_joint_frontier import AxisFrontier,advance_joint


@pytest.mark.parametrize('hold',[1,4])
def test_joint_bitset_preserves_all_final_masks_and_witnesses(tmp_path,hold):
    path=tmp_path/'red.csv';path.write_text('0,HeartMode,0\n0,BoneV,326,280,40,0,0\n0.2,EndAttack\n')
    wave=compile_wave(path);space=bake_cspace(wave)
    initial=np.array([[320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.],
                      [np.nextafter(320.,np.inf),302.,0.,150.,15.,0.,0.,1.,750.,0.,0.]])
    front=AxisFrontier.from_states(initial);layers=[front]
    for tick in range(0,hold*3,hold):
        status,front,stats=advance_joint(wave,front,tuple(range(32)),tick,hold,space)
        assert status=='complete';layers.append(front)
    reference=full_local_relation(wave,0,hold*3,initial,controls=tuple(range(32)),hold=hold,cspace=space)
    assert {s.tobytes() for s in front.terminal_states()}=={s.tobytes() for s in reference.states}
    for i,expected in enumerate(front.representative_states()):
        index=i;word=[]
        for layer in layers[:0:-1]:word.append(int(layer.mask[index]));index=int(layer.parents[index])
        s=initial[layers[0].parents[index]].copy()
        for frame,mask in enumerate(word[::-1]):
            for micro in range(hold):
                tick=frame*hold+micro+1;step_mask_into(s,mask,wave.env_schedule[tick],wave.platform_table[tick],s)
        assert s.tobytes()==expected.tobytes()


def test_unknown_resource_and_boundary_leave_input_intact(tmp_path):
    path=tmp_path/'red.csv';path.write_text('0,HeartMode,0\n0.2,EndAttack\n')
    wave=compile_wave(path);space=bake_cspace(wave)
    initial=np.array([[320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.]])
    front=AxisFrontier.from_states(initial);before=front.joint.tobytes()
    status,out,_=advance_joint(wave,front,tuple(range(16)),0,4,space,max_states=1)
    assert status=='resource_limit' and out is None and front.joint.tobytes()==before
    initial[0,1]=wave.env_schedule[1,1]+13
    status,out,_=advance_joint(wave,AxisFrontier.from_states(initial),tuple(range(16)),0,4,space)
    assert status=='unsupported' and out is None
