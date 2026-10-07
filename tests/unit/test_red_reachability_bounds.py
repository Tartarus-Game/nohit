"""Sound interval certificates against exhaustive real operator words."""
from itertools import product
import numpy as np
import pytest
from nohit.engine.red_reachability_bounds import red_box_deadline,red_box_deadline_details
from nohit.engine.discrete_operator import step_mask_into


def world(ticks=4):
    env=np.zeros((ticks,22));env[:,[2,3,16,17,20,21]]=100.
    env[:,5]=1.;env[:,7]=1/240;env[:,8]=750.
    return np.full((ticks,1,4),np.nan),env,np.zeros((ticks,0,9))


def state(x=50.,y=50.,dx=150.,dy=-150.):
    return np.array([x,y,dx,dy,6.,0.,0.,1.,750.,0.,0.])


def test_all_control_words_remain_in_outward_box_with_irregular_dt():
    white,env,platforms=world()
    env[:,7]=[1/240,0.004166666744,0.004166666821,0.004166666512]
    initial=state(dx=75.,dy=-75.)
    certificate=red_box_deadline_details(white,env,platforms,0,initial,3)
    dead,death,checked,xlo,ylo,xhi,yhi=certificate
    assert not dead and death==-1 and checked==3
    # Include all 32 physical masks, opposing arrows, Cancel, and all latch
    # combinations. No constant-direction extremum is assumed by this check.
    for masks in product(range(32),repeat=3):
        s=initial.copy()
        for tick,mask in enumerate(masks,1):
            step_mask_into(s,mask,env[tick],platforms[tick],s)
        assert xlo<=s[0]<=xhi and ylo<=s[1]<=yhi


def test_certificate_implies_all_operator_words_hit_closed_white_rectangle():
    white,env,platforms=world()
    white[3,0]=[0.,0.,100.,51.]
    initial=state()
    assert red_box_deadline(white,env,platforms,0,initial,3)
    for masks in product(range(32),repeat=3):
        s=initial.copy()
        for tick,mask in enumerate(masks,1):
            step_mask_into(s,mask,env[tick],platforms[tick],s)
        box=white[3,0]
        assert s[0]+2>=box[0] and s[0]-2<=box[2]
        assert s[1]+2>=box[1] and s[1]-2<=box[3]


@pytest.mark.parametrize('change',['teleport','blue','slam','resize','platform','clamp','large_dt','old_fast'])
def test_unsupported_transition_is_unknown_even_with_a_later_covering_hazard(change):
    white,env,platforms=world();white[3,0]=[-100.,-100.,200.,200.]
    initial=state()
    if change=='teleport':env[1,9]=1.
    if change=='blue':env[1,4]=1.
    if change=='slam':env[1,6]=1.
    if change=='resize':env[1,18]=1.
    if change=='platform':
        platforms=np.zeros((4,1,9));platforms[1,0,7]=1.
    if change=='clamp':initial[0]=13.
    if change=='large_dt':env[1,7]=0.02
    if change=='old_fast':initial[2]=600.
    result=red_box_deadline_details(white,env,platforms,0,initial,3)
    assert not result[0] and result[2]==0


def test_unknown_beyond_requested_observation_window_cannot_certify():
    white,env,platforms=world();white[3,0]=[-100.,-100.,200.,200.]
    assert not red_box_deadline(white,env,platforms,0,state(),2)
    assert red_box_deadline(white,env,platforms,0,state(),3)


def test_a_small_spatial_gap_must_remain_unknown_and_has_a_real_safe_word():
    white,env,platforms=world();white[3,0]=[0.,0.,100.,48.]
    initial=state(dx=0.,dy=150.)
    assert not red_box_deadline(white,env,platforms,0,initial,3)
    s=initial.copy()
    for tick in range(1,4):step_mask_into(s,8,env[tick],platforms[tick],s)
    assert s[1]-2>48.


@pytest.mark.parametrize('tick,y,dy',[(1484,274.8749999993824,-150.),(1488,276.1249999994057,150.)])
def test_realhell_top_slab_deadline_requires_earlier_branch(tick,y,dy):
    # Exact recorded source rectangle/state values at the opening bottleneck.
    # The bounded model need not contain the full RealHELL source or caches.
    count=1497-tick+1
    white,env,platforms=world(count)
    for offset in (0,14,18):env[:,offset:offset+4]=[241.,226.,406.,391.]
    env[:,7]=0.004166666666744277
    white[-1,0]=[241.,206.75000000090824,406.,279.75000000090824]
    initial=state(x=299.62499999947676 if tick==1484 else 302.12499999952337,y=y,dy=dy)
    result=red_box_deadline_details(white,env,platforms,0,initial,count-1)
    assert result[0] and result[1]==count-1
    assert result[6]-2<=white[-1,0,3]


def test_rounding_near_step_count_threshold_is_not_treated_as_single_step():
    white,env,platforms=world();white[3,0]=[-100.,-100.,200.,200.]
    env[1,7]=0.01
    result=red_box_deadline_details(white,env,platforms,0,state(),3)
    assert not result[0] and result[2]==0
