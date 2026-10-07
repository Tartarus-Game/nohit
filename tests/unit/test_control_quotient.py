import numpy as np
import pytest
from nohit.engine.control_quotient import control_classes
from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.local_relation import full_local_relation,_internal_layer_keys
from nohit.engine.compact_wave import compile_wave


def env(mode=1,direction=0):
    return np.array([0.,0.,100.,100.,mode,direction,0.,1/240,750.,0.,0.,0.,1.,0.,0.,0.,100.,100.,0.,0.,100.,100.])


def test_blue_six_controls_but_direction_change_retains_future_latch():
    row=env();rows=np.tile(row,(4,1))
    assert len(control_classes(rows,range(16),next_environment=row))==6
    assert len(control_classes(rows,range(16)))==16
    nextrow=env(direction=2)
    assert len(control_classes(rows,range(16),next_environment=nextrow))==12
    rows[-1]=nextrow;rows[-1,6]=1
    assert len(control_classes(rows,range(16),next_environment=nextrow))==12
    red=env(mode=0)
    assert len(control_classes(np.tile(red,(4,1)),range(16),next_environment=red))==9


@pytest.mark.parametrize('direction',range(4))
@pytest.mark.parametrize('change',[False,True])
def test_every_alias_has_equal_microphysics_and_next_full_state(direction,change):
    row=env(direction=direction);rows=np.tile(row,(4,1));nextrow=row.copy()
    if change:
        rows[2,6]=1;rows[2:,5]=(direction+2)%4;nextrow=rows[-1].copy()
    groups=control_classes(rows,range(32),next_environment=nextrow)
    platforms=np.array([[30.,70.,40.,8.,0.,0.,1.,1.,0.]])
    for x,y,dx,dy in ((50.,50.,0.,0.),(13.,13.,-750.,150.),(86.5,86.5,150.,750.)):
        for oldmask in (0,15,16,31):
            initial=np.array([x,y,dx,dy,float(oldmask),1.,1.,float(direction),750.,1.,0.])
            for group in groups:
                trajectories=[];ends=[]
                for mask in group:
                    s=initial.copy();trace=[]
                    for row in rows:
                        step_mask_into(s,mask,row,platforms,s)
                        trace.append(s[np.arange(11)!=4].tobytes())
                    trajectories.append(trace);ends.append(s)
                assert all(trace==trajectories[0] for trace in trajectories)
                assert len(set(bytes(k) for k in _internal_layer_keys(np.array(ends),nextrow)))==1
                for nextmask in range(32):
                    outputs=[]
                    for s in ends:
                        s=s.copy();step_mask_into(s,nextmask,nextrow,platforms,s);outputs.append(s.tobytes())
                    assert len(set(outputs))==1


@pytest.mark.parametrize('hold',[1,4])
@pytest.mark.parametrize('mode',[0,1])
def test_complete_terminal_states_and_every_witness_match(tmp_path,hold,mode):
    path=tmp_path/'controls.csv';path.write_text('0,HeartMode,0\n0.1,EndAttack\n')
    wave=compile_wave(path);wave.env_schedule[:,4]=mode;wave.env_schedule[:,5]=0
    wave.env_schedule[hold+1,6]=1;wave.env_schedule[hold+1:,5]=2
    initial=np.array([490.,304.,0.,150.,0.,0.,float(mode),0.,750.,0.,0.])
    results=[full_local_relation(wave,0,hold*3,initial,hold=hold,
                input_latch_quotient=True,control_quotient=enabled) for enabled in (False,True)]
    assert {s.tobytes() for s in results[0].states}=={s.tobytes() for s in results[1].states}
    for i,expected in enumerate(results[1].states):
        s=initial.copy()
        for j,mask in enumerate(results[1].witness(i)):
            for micro in range(1,hold+1):
                tick=j*hold+micro;step_mask_into(s,mask,wave.env_schedule[tick],wave.platform_table[tick],s)
        assert s.tobytes()==expected.tobytes()


def test_rejects_unsafe_use_without_state_latch_quotient(tmp_path):
    path=tmp_path/'controls.csv';path.write_text('0,HeartMode,0\n0.1,EndAttack\n')
    wave=compile_wave(path)
    with pytest.raises(ValueError,match='requires input latch'):
        full_local_relation(wave,0,4,np.zeros(11),control_quotient=True)
