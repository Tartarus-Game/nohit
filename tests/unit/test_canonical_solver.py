import itertools
import pytest
import numpy as np
from nohit.engine.compact_wave import ROOT


def fixture(ticks=9):
    env=np.tile(np.array([133.,251.,508.,391.,1.,1.,0.,1/240]),(ticks,1))
    platforms=np.zeros((ticks,0,7))
    white=np.full((ticks,1,4),np.nan)
    blue=white.copy()
    initial=np.array([320.,377.81875,0.,0.,0.])
    return white,blue,env,platforms,initial


def test_vm_does_not_return_a_completed_wave_when_endattack_is_unreachable():
    from nohit.engine.compact_wave import TimelineVM
    wave=TimelineVM(max_ticks=8).run([['200','EndAttack']])
    assert wave['complete'] is False
    assert wave['termination_reason']=='tick_budget'
    assert wave['ticks']==8
