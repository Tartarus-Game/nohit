"""Compiled holds preserve the source operator at nonzero binding offsets."""
from types import SimpleNamespace
import numpy as np
import pytest

from nohit.engine.parametric_dag import ParametricRouteIterator, _Node
from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.cspace import collision_query


@pytest.mark.parametrize('hold', [1, 4])
@pytest.mark.parametrize('first', [0, 7])
@pytest.mark.parametrize('blocked', [False, True])
def test_hold_uses_absolute_motion_and_local_collision_ticks(tmp_path, hold, first, blocked):
    path=tmp_path/'hold.csv'
    path.write_text('0.1,EndAttack\n')
    initial=[40.,40.,0.,0.,0.,0.,0.,1.,750.,0.,0.]
    environment=[0,0,100,100,0,1,0,1/240,750,0,40,40,0,0,0,0,100,100]
    search=ParametricRouteIterator(path,initial,initial_environment=environment,
        decision_ticks=hold,weights=[0,0,0,0])
    original=search.stack[0].binding
    wave=original.wave
    # Motion rows deliberately differ so an accidental relative index is visible.
    wave.env_schedule[:,7]=np.arange(len(wave.env_schedule))*.00001+.004
    wave.geometry_white=np.full((len(wave.env_schedule),1,4),np.nan)
    tick=first+3
    if blocked:wave.geometry_white[tick+1,0]=[0,0,100,100]
    binding=SimpleNamespace(identity=b'test-hold',wave=wave,
        history=((first,0,40.,40.),) if first else (),pending_target=None,complete=True)
    node=_Node(tick,np.array(initial),binding,0)
    state=node.state.copy()
    start,view,baked,_=search._environment(binding)
    collided=False
    stop=min(tick+hold,len(wave.env_schedule)-1)
    for future in range(tick+1,stop+1):
        step_mask_into(state,2,wave.env_schedule[future],wave.platform_table[future],state)
        if collision_query(view.geometry_white,view.geometry_blue,future-start,state,0.,baked.payload):
            collided=True
            break
    child=search._advance(node,2)
    if collided:
        assert child is None
    else:
        assert child.tick==stop
        assert child.state.tobytes()==state.tobytes()
    assert node.state.tobytes()==np.array(initial).tobytes()
