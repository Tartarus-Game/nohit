from itertools import product
import numpy as np
from nohit.engine.compact_wave import compile_wave
from nohit.engine.cspace import bake_cspace,collision_query
from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.local_relation import full_local_relation


def test_all_exit_bits_and_witnesses_at_closed_border(tmp_path):
    path=tmp_path/'red.csv';path.write_text('0,HeartMode,0\n0.2,EndAttack\n')
    wave=compile_wave(path);space=bake_cspace(wave)
    initial=np.array([320.,wave.env_schedule[1,1]+13,150.,0.,2.,0.,0.,1.,750.,0.,0.])
    result=full_local_relation(wave,0,8,initial,cspace=space)
    expected=set()
    for word in product(range(16),repeat=2):
        s=initial.copy()
        for frame,mask in enumerate(word):
            for micro in range(4):
                tick=frame*4+micro+1
                step_mask_into(s,mask,wave.env_schedule[tick],wave.platform_table[tick],s)
                assert not collision_query(wave.geometry_white,wave.geometry_blue,tick,s,0.,space.payload)
        expected.add(s.tobytes())
    assert result.status=='complete'
    assert {s.tobytes() for s in result.states}==expected
    for index,exit_state in enumerate(result.states):
        s=initial.copy()
        for frame,mask in enumerate(result.witness(index)):
            for micro in range(4):
                tick=frame*4+micro+1
                step_mask_into(s,mask,wave.env_schedule[tick],wave.platform_table[tick],s)
        assert s.tobytes()==exit_state.tobytes()


def test_budget_is_unknown_and_retains_last_complete_frontier(tmp_path):
    path=tmp_path/'red.csv';path.write_text('0,HeartMode,0\n0.2,EndAttack\n')
    wave=compile_wave(path)
    initial=np.array([320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.])
    result=full_local_relation(wave,0,8,initial,max_states=1)
    assert result.status=='resource_limit' and result.reached_tick==0
    assert len(result.states)==1 and result.states[0].tobytes()==initial.tobytes()
