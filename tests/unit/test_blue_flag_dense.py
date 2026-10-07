import numpy as np
import pytest
from nohit.engine.compact_wave import compile_wave
from nohit.engine.cspace import bake_cspace
from nohit.engine.local_relation import full_local_relation
from nohit.engine.blue_dense import BlueFrontier,advance_blue
from nohit.engine.blue_flag_dense import lift_completed_blue,advance_flag_blue,full_flag_states,flag_predecessor


def setup(tmp_path,slam_tick):
    path=tmp_path/'blueflag.csv';path.write_text('0,HeartMode,1\n0.1,EndAttack\n')
    wave=compile_wave(path);wave.env_schedule[:,5]=2
    wave.env_schedule[slam_tick,6]=1;wave.env_schedule[slam_tick:,5]=0
    states=np.array([[320.,377.75,0.,150.,0.,0.,1.,2.,750.,0.,0.],
                     [494.75,304.,0.,0.,0.,0.,1.,2.,750.,0.,0.]])
    return wave,states


@pytest.mark.parametrize('slam_tick',[5,6,8])
def test_slam_and_perpendicular_flag_clear_match_all_full_operator_states(tmp_path,slam_tick):
    wave,initial=setup(tmp_path,slam_tick);space=bake_cspace(wave)
    front,_,_=BlueFrontier.from_states(initial,0)
    status,blue,_,_=advance_blue(wave,front,4,space);assert status=='complete'
    front,_=lift_completed_blue(blue)
    for stop in (8,12):
        status,child,maps,stats=advance_flag_blue(wave,front,4,space)
        assert status=='complete'
        expected=full_local_relation(wave,0,stop,initial,hold=4,cspace=space,input_latch_quotient=True)
        assert {s.tobytes() for s in full_flag_states(child)}=={s.tobytes() for s in expected.states}
        for ix in range(len(child.x)):
            for iy in range(len(child.y)):
                for flag in (0,1):
                    if child.contains(ix,iy,flag):
                        parent,mask=flag_predecessor(wave,front,child,(ix,iy,flag),maps,4,space)
                        assert front.contains(*parent)
        front=child
    assert stats['flag0']>0 and stats['flag1']>0


def test_multiple_slam_resets_in_one_block(tmp_path):
    wave,initial=setup(tmp_path,5);wave.env_schedule[7,6]=1;wave.env_schedule[7:,5]=2
    space=bake_cspace(wave);front,_,_=BlueFrontier.from_states(initial,0)
    _,front,_,_=advance_blue(wave,front,4,space);front,_=lift_completed_blue(front)
    status,child,_,_=advance_flag_blue(wave,front,4,space)
    assert status=='complete'
    expected=full_local_relation(wave,0,8,initial,hold=4,cspace=space)
    assert {s.tobytes() for s in full_flag_states(child)}=={s.tobytes() for s in expected.states}


@pytest.mark.parametrize('invalid',['damage','platform','vertical','teleport'])
def test_unmodeled_coupling_is_unknown_not_an_empty_relation(tmp_path,invalid):
    wave,initial=setup(tmp_path,8);space=bake_cspace(wave)
    front,_,_=BlueFrontier.from_states(initial,0);_,front,_,_=advance_blue(wave,front,4,space);front,_=lift_completed_blue(front)
    if invalid=='damage':wave.env_schedule[6,12]=1
    elif invalid=='platform':
        wave.platform_table=np.zeros((len(wave.env_schedule),1,9));wave.platform_table[6,0,6]=1
    elif invalid=='vertical':wave.env_schedule[6,5]=1
    else:wave.env_schedule[6,9]=1
    status,child,maps,_=advance_flag_blue(wave,front,4,space)
    assert status=='unsupported' and child is None and maps is None
