import importlib.util
from pathlib import Path
import numpy as np
from nohit.engine.compact_wave import compile_wave
from nohit.engine.cspace import bake_cspace
from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.local_relation import full_local_relation

spec=importlib.util.spec_from_file_location('stream_control_helper',Path(__file__).resolve().parents[2]/'scratch/stream_local_relation.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)


def test_chunked_control_homomorphism_has_same_complete_exits_and_origins(tmp_path):
    path=tmp_path/'blue.csv';path.write_text('0,HeartMode,1\n0.1,EndAttack\n')
    wave=compile_wave(path);wave.env_schedule[:,5]=0;wave.env_schedule[5:,5]=2;wave.env_schedule[5,6]=1
    space=bake_cspace(wave)
    initial=np.array([[320.,304.,0.,0.,0.,0.,1.,0.,750.,0.,1.],
                      [320.,304.,0.,0.,0.,0.,1.,0.,750.,0.,0.]])
    expected=full_local_relation(wave,0,8,initial,cspace=space,input_latch_quotient=True)
    result,states=helper.stream_relation(wave,space,0,8,initial,tmp_path/'stream',max_states=1,
        chunk_size=1,control_quotient=True,initial_artifact=True)
    assert result['status']=='resource_limit' and result['reached_tick']==0
    result,states=helper.stream_relation(wave,space,0,8,initial,tmp_path/'stream',max_states=10000,
        chunk_size=3,control_quotient=True,initial_artifact=True,resume=True)
    assert result['status']=='complete'
    assert {s.tobytes() for s in states}=={s.tobytes() for s in expected.states}
    assert 'attempted_tick' not in result
    source_indices=np.load(tmp_path/'stream/initial.npz')['source_indices']
    assert source_indices.tolist()==[1]
    for i,expected_state in enumerate(states):
        origin,word=helper.witness(tmp_path/'stream',i);s=initial[source_indices[origin]].copy()
        for j,mask in enumerate(word):
            for micro in range(1,5):
                tick=j*4+micro;step_mask_into(s,mask,wave.env_schedule[tick],wave.platform_table[tick],s)
        assert s.tobytes()==expected_state.tobytes()
