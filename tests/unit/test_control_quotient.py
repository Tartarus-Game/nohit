import numpy as np
import pytest
from nohit.engine.control_quotient import control_classes
from nohit.engine.discrete_operator import step_mask_into
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


def test_batch_contexts_keep_original_control_representatives():
    from nohit.engine.control_quotient import single_tick_control_table,control_classes
    rng=np.random.default_rng(770)
    env=np.zeros((601,22));env[:,4]=rng.integers(0,2,len(env));env[:,5]=rng.choice([0.,1.,2.,3.,.5,7.],len(env))
    env[:,6]=rng.choice([0.,1.,750.],len(env))
    table,counts=single_tick_control_table(env,tuple(range(32)))
    for tick in range(len(env)-1):
        next_row=env[tick+2] if tick+2<len(env) else None
        expected=[g[0] for g in control_classes(env[tick+1:tick+2],tuple(range(32)),next_environment=next_row)]
        assert table[tick,:counts[tick]].tolist()==expected
