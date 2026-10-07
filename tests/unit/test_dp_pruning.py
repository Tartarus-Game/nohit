import itertools
import numpy as np
from nohit.engine.dp_pruning import forced_vertical_collision
from nohit.engine.discrete_operator import initial_state,step_action_into
from nohit.engine.canonical_lattice import collision


def fixture():
    row=np.array([133.,251.,508.,391.,1.,1.,0.,1/240,750.,0.,0.,0.,0.,0.,133.,251.,508.,391.])
    env=np.tile(row,(9,1));platforms=np.empty((9,0,7));white=np.full((9,1,4),np.nan)
    white[-1,0]=[100.,290.,540.,310.]
    state=initial_state([320.,300.,0.,0.,0.],row)
    return white,env,platforms,state


def test_full_width_certificate_matches_every_two_control_continuation():
    white,env,platforms,state=fixture()
    assert forced_vertical_collision(white,env,platforms,0,state)
    blue=np.empty((9,0,4))
    for route in itertools.product(range(32),repeat=2):
        q=state.copy();hit=False
        for frame,mask in enumerate(route):
            for m in range(1,5):
                tick=frame*4+m
                step_action_into(q,mask,0,env[tick],platforms[tick],q)
                hit |= collision(white,blue,tick,q,0.)
        assert hit


def test_certificate_stops_before_any_unmodeled_control_influence():
    for change in ('mode','arena','teleport','slam','platform'):
        white,env,platforms,state=fixture()
        if change=='mode':env[4:,4]=0.
        elif change=='arena':env[4:,0]+=1.
        elif change=='teleport':env[4,9]=1.
        elif change=='slam':env[4,6]=1.
        else:
            platforms=np.zeros((9,1,7));platforms[4,0,6]=1.
        assert not forced_vertical_collision(white,env,platforms,0,state)
    white,env,platforms,state=fixture();white[-1,0,0]=300.
    assert not forced_vertical_collision(white,env,platforms,0,state)


def test_vertical_relaxation_keeps_a_safe_jump_and_cache_is_optimistic():
    from nohit.engine.dp_pruning import make_vertical_cache
    white,env,platforms,state=fixture()
    state[1]=377.96875
    white[-1,0]=[100.,375.,540.,400.]
    cache=make_vertical_cache(white,env,platforms)
    assert not forced_vertical_collision(white,env,platforms,0,state,cache)
    # Only position/velocity/jump latch influence this relaxation; changing
    # a reachable x cannot turn a safe abstract jump into a dead certificate.
    for x in (146.,250.,495.):
        state[0]=x
        assert not forced_vertical_collision(white,env,platforms,0,state,cache)
    q=state.copy()
    q[0]=320.
    for tick in range(1,9):
        step_action_into(q,4,0,env[tick],platforms[tick],q)
        assert not collision(white,np.empty((9,0,4)),tick,q,0.)


def test_relaxed_jump_witness_is_replayable_and_uses_same_certificate_cache():
    from nohit.engine.dp_pruning import make_vertical_cache,preferred_axis_jump
    white,env,platforms,state=fixture()
    state[1]=377.96875
    white[-1,0]=[100.,375.,540.,400.]
    cache=make_vertical_cache(white,env,platforms)
    assert not forced_vertical_collision(white,env,platforms,0,state,cache)
    assert preferred_axis_jump(white,env,platforms,0,state,cache)==4
    q=state.copy()
    for frame in range(2):
        mask=preferred_axis_jump(white,env,platforms,frame,q,cache)
        assert mask in (0,4)
        for micro in range(1,5):
            tick=frame*4+micro
            step_action_into(q,mask,0,env[tick],platforms[tick],q)
            assert not collision(white,np.empty((9,0,4)),tick,q,0.)
    white,env,platforms,state=fixture()
    assert preferred_axis_jump(white,env,platforms,0,state)==-1


def test_each_gravity_axis_certificate_agrees_with_every_two_input_sequence():
    for direction in range(4):
        white,env,platforms,state=fixture()
        env[:,5]=direction;state[7]=direction
        normal=0 if direction%2==0 else 1
        if normal==0:white[-1,0]=[310.,0.,330.,480.]
        assert forced_vertical_collision(white,env,platforms,0,state)
        blue=np.empty((9,0,4))
        for route in itertools.product(range(32),repeat=2):
            q=state.copy();hit=False
            for frame,mask in enumerate(route):
                for micro in range(1,5):
                    tick=frame*4+micro
                    step_action_into(q,mask,0,env[tick],platforms[tick],q)
                    hit |= collision(white,blue,tick,q,0.)
            assert hit


def test_initial_side_contact_is_never_folded_and_interior_cannot_reach_it():
    white,env,platforms,state=fixture()
    for direction in range(4):
        env[:,5]=direction;state[7]=direction
        normal=0 if direction%2==0 else 1;tangent=1-normal
        for edge in (env[0,tangent]+13.,env[0,tangent+2]-13.):
            state[tangent]=edge
            assert not forced_vertical_collision(white,env,platforms,0,state)
        state[:4]=[320.,300.,0.,0.]
        lo=env[0,tangent]+13.;hi=env[0,tangent+2]-13.
        for position in (lo+1.e-9,hi-1.e-9):
            for mask in range(32):
                q=state.copy();q[tangent]=position
                for tick in range(1,9):
                    step_action_into(q,mask,0,env[tick],platforms[tick],q)
                    assert q[tangent]-8.>env[tick,tangent]+5.
                    assert q[tangent]+8.<env[tick,tangent+2]-5.
