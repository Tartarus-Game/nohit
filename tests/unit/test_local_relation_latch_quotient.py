"""Next-step congruence and complete future-language tests, no position bins."""
from itertools import product
import numpy as np
import pytest
from nohit.engine.compact_wave import compile_wave
from nohit.engine.cspace import bake_cspace,collision_query
from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.local_relation import full_local_relation,_internal_layer_keys


@pytest.mark.parametrize('mode,slam,direction',[(0,0,1)]+[(m,s,d) for m,s in ((1,0),(0,1)) for d in range(4)])
def test_equal_keys_have_bit_identical_next_state_for_every_physical_mask(mode,slam,direction):
    env=np.array([0.,0.,100.,100.,mode,direction,slam,1/240,750.,0.,0.,0.,1.,0.,0.,0.,100.,100.,0.,0.,100.,100.])
    platforms=np.zeros((0,9))
    # Include both wall-adjacent and interior inputs, with persistent slam
    # metadata. Only input mask is projected, so all other reads remain exact.
    for x,y,dx,dy in ((13.5,13.5,0.,0.),(50.,86.5,150.,-60.)):
        states=np.tile([x,y,dx,dy,0.,1.,1.,1.,750.,1.,0.],(32,1));states[:,4]=np.arange(32)
        keys=_internal_layer_keys(states,env)
        groups={}
        for i,key in enumerate(keys):groups.setdefault(bytes(key),[]).append(i)
        for indices in groups.values():
            for mask in range(32):
                outcomes=[]
                for i in indices:
                    out=states[i].copy();step_mask_into(out,mask,env,platforms,out)
                    outcomes.append(out.tobytes())
                assert len(set(outcomes))==1


def test_next_gravity_and_slam_determine_latch_not_current_red_mode():
    env=np.array([0.,0.,100.,100.,0.,3.,1.,1/240,750.,0.,0.,0.,0.,0.,0.,0.,100.,100.,0.,0.,100.,100.])
    states=np.tile([50.,13.5,0.,0.,0.,0.,0.,1.,750.,0.,0.],(2,1));states[1,4]=8.
    keys=_internal_layer_keys(states,env)
    assert keys[0]!=keys[1]
    out=[]
    for s in states:
        s=s.copy();step_mask_into(s,8,env,np.zeros((0,9)),s);out.append(s.tobytes())
    assert out[0]!=out[1]


@pytest.mark.parametrize('hold',[1,4])
@pytest.mark.parametrize('transition',['red','blue','slam'])
def test_all_exact_terminal_exits_and_real_witnesses_match_unquotiented(tmp_path,hold,transition):
    path=tmp_path/'latch.csv';path.write_text('0,HeartMode,0\n0.1,EndAttack\n')
    wave=compile_wave(path)
    # Deliberately put a mode/slam boundary immediately after an internal
    # relation layer, where a stale current-mode latch projection would fail.
    if transition!='red':
        wave.env_schedule[hold+1:,4]=1.
        wave.env_schedule[hold+1:,5]=3.
        if transition=='slam':wave.env_schedule[hold+1,6]=1.
    space=bake_cspace(wave)
    initial=np.array([320.,wave.env_schedule[0,1]+13.5,0.,0.,0.,0.,0.,1.,750.,0.,0.])
    baseline=full_local_relation(wave,0,hold*3,initial,hold=hold,cspace=space,max_states=100000)
    quotient=full_local_relation(wave,0,hold*3,initial,hold=hold,cspace=space,max_states=100000,input_latch_quotient=True)
    assert baseline.status==quotient.status=='complete'
    assert {s.tobytes() for s in baseline.states}=={s.tobytes() for s in quotient.states}
    if transition=='red':assert quotient.counts[1][1]<baseline.counts[1][1]
    for index,expected in enumerate(quotient.states):
        s=initial.copy()
        for frame,mask in enumerate(quotient.witness(index)):
            for micro in range(1,hold+1):
                tick=frame*hold+micro
                step_mask_into(s,mask,wave.env_schedule[tick],wave.platform_table[tick],s)
                assert not collision_query(wave.geometry_white,wave.geometry_blue,tick,s,0.,space.payload)
        assert s.tobytes()==expected.tobytes()


def test_internal_projection_never_modifies_representative_state():
    states=np.array([[50.,50.,0.,0.,31.,0.,0.,1.,750.,0.,0.]])
    before=states.tobytes();env=np.zeros(22)
    keys=_internal_layer_keys(states,env)
    assert states.tobytes()==before
    assert bytes(keys[0])!=before
