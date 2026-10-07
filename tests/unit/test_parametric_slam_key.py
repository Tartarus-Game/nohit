"""A slam forces blue movement before the next-tick input latch is read."""
from types import SimpleNamespace

import numpy as np
import pytest

from nohit.engine.cspace import bake_cspace
from nohit.engine.local_relation import full_local_relation
from nohit.engine.parametric_dag import ParametricRouteIterator, _Node


def context(direction=1):
    env=np.tile([0.,0.,100.,100.,0.,direction,0.,.001,750.,0.,0.,0.,
                 0.,0.,0.,0.,100.,100.,0.,0.,100.,100.],(4,1))
    env[1,6]=1.  # The operator forces blue, even when the supplied mode is red.
    env[2:,4]=1.
    white=np.full((4,1,4),np.nan)
    white[2,0]=[0.,88.6,100.,90.]
    wave=SimpleNamespace(env_schedule=env,platform_table=np.zeros((4,1,9)),
        geometry_white=white,geometry_blue=np.full((4,0,4),np.nan),
        geometry_polygons=np.full((4,0,8),np.nan),origin=(0.,0.),dimensions=(100,100),
        pending_target=None,termination_reason='endattack',source_events=())
    binding=SimpleNamespace(identity=b'slam-key-regression',pending_target=None,wave=wave)
    search=SimpleNamespace(bindings={},environment_state_quotient=False,future_history_key=None)
    return search,binding


def key(search,binding,mask):
    state=np.array([50.,86.,0.,0.,float(mask),0.,0.,1.,750.,0.,0.])
    return ParametricRouteIterator._key(search,_Node(0,state,binding,mask)),state


def test_forced_blue_key_does_not_merge_a_viable_state_with_a_dead_state():
    search,binding=context()
    released_key,released=key(search,binding,0)
    held_key,held=key(search,binding,4)
    space=bake_cspace(binding.wave)
    options=dict(hold=1,cspace=space,expansion_backend='scalar',dedup_backend='numpy')
    released_relation=full_local_relation(binding.wave,0,2,released,**options)
    held_relation=full_local_relation(binding.wave,0,2,held,**options)
    # A rising Up edge reduces the slam velocity to 570; a held Up leaves750.
    # At the next tick y=86.57 is clear while y=86.75 hits the spanning hazard.
    assert released_relation.status=='complete' and len(released_relation.states)>0
    assert held_relation.status=='exhausted' and not len(held_relation.states)
    assert released_key!=held_key


@pytest.mark.parametrize('direction,jump',[(0,1),(1,4),(2,2),(3,8)])
def test_forced_blue_projection_retains_exactly_its_direction_jump_bit(direction,jump):
    search,binding=context(direction)
    no_jump,_=key(search,binding,0)
    with_jump,_=key(search,binding,jump)
    other_buttons,_=key(search,binding,31^jump)
    all_buttons,_=key(search,binding,31)
    assert no_jump!=with_jump
    assert no_jump==other_buttons
    assert with_jump==all_buttons
