"""Public search and EOF continuation use the declared clock throughout."""
from types import SimpleNamespace

import numpy as np
import pytest

from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.execution_schedule import execution_schedule
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.terminal_completion import complete_eof_tail

INITIAL = [320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.]
ZERO = dict(clearance=0,lookahead=0,center=0,switches=0)


def test_eof_bridge_consumes_explicit_future_and_never_nominal_240():
    bounds=[0.,0.,200.,200.]
    row=np.array([*bounds,0.,1.,0.,1/30,750.,0.,0.,0.,0.,0.,*bounds,*bounds])
    details=dict(active_bones=0,active_stabs=0,active_blasters=0,active_platforms=0,
                 arena_settled=True,timeline_exhausted=True,pending_callbacks=[],pending_dialogue=None)
    wave=SimpleNamespace(termination_reason='eof_hazards_drained',complete=True,
                         env_schedule=np.tile(row,(6,1)),terminal_details=details)
    state=np.array([100.,100.,150.,0.,2.,0.,0.,1.,750.,0.,0.])
    schedule=[1/30]*6+[1/60,1/30,1/120,1/60,1/30]
    result=complete_eof_tail(wave,state,last_mask=2,dt_schedule=schedule,max_ticks=100)
    assert result['status']=='proven'
    assert result['dt_sequence']==schedule[6:6+len(result['actions'])]
    q=state.copy()
    for index,(mask,dt) in enumerate(zip(result['actions'],result['dt_sequence'])):
        row[7]=dt
        step_mask_into(q,mask,row,np.empty((0,9)),q)
        assert q.tobytes()==np.asarray(result['states'][index+1]).tobytes()
    short=complete_eof_tail(wave,state,last_mask=2,dt_schedule=schedule[:7],max_ticks=100)
    assert short['status']=='unknown'
    assert short['actions']==[]
