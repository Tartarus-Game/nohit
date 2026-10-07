import numpy as np
import pytest
from nohit.engine.compact_wave import compile_wave
from nohit.engine.cspace import bake_cspace,collision_query
from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.red_joint_frontier import AxisFrontier,advance_joint
from nohit.engine.red_dense_frontier import DenseFrontier,advance_dense,unpack_keys,predecessor

@pytest.mark.parametrize('hold',[1,4])
def test_dense_complete_relation_and_backward_witness(tmp_path,hold):
    path=tmp_path/'red.csv';path.write_text('0,HeartMode,0\n0,BoneV,326,280,40,0,0\n0.2,EndAttack\n')
    wave=compile_wave(path);space=bake_cspace(wave)
    states=np.array([[320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.],
                     [np.nextafter(320.,np.inf),302.,0.,150.,15.,0.,0.,1.,750.,0.,0.]])
    reference=AxisFrontier.from_states(states);dense=DenseFrontier.from_axis(reference);layers=[dense]
    for tick in range(0,hold*3,hold):
        status,reference,_=advance_joint(wave,reference,tuple(range(32)),tick,hold,space);assert status=='complete'
        status,dense,_=advance_dense(wave,dense,tuple(range(32)),tick,hold,space);assert status=='complete'
        assert np.array_equal(dense.x.view(np.uint64),reference.x.view(np.uint64))
        assert np.array_equal(dense.y.view(np.uint64),reference.y.view(np.uint64))
        assert np.array_equal(unpack_keys(dense.bits,len(dense.x)*len(dense.y)),np.sort(reference.joint))
        layers.append(dense)
    for key in unpack_keys(dense.bits,len(dense.x)*len(dense.y)):
        target=dense.state(key)
        for n in range(len(layers)-2,-1,-1):
            parent,mask=predecessor(wave,layers[n],target,tuple(range(32)),n*hold,hold,space)
            initial=layers[n].state(parent);s=initial.copy()
            for tick in range(n*hold+1,(n+1)*hold+1):
                step_mask_into(s,mask,wave.env_schedule[tick],wave.platform_table[tick],s)
                assert not collision_query(wave.geometry_white,wave.geometry_blue,tick,s,0.,space.payload)
            assert np.array_equal(s[:4].view(np.uint64),target[:4].view(np.uint64))
            target=initial

def test_dense_resource_limit_keeps_complete_input(tmp_path):
    path=tmp_path/'red.csv';path.write_text('0,HeartMode,0\n0.2,EndAttack\n');wave=compile_wave(path);space=bake_cspace(wave)
    front=DenseFrontier.from_axis(AxisFrontier.from_states(np.array([[320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.]])))
    old=front.bits.copy()
    status,new,_=advance_dense(wave,front,tuple(range(16)),0,4,space,max_product_cells=1)
    assert status=='resource_limit' and new is None and np.array_equal(old,front.bits)
