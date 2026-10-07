import numpy as np
import pytest

from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.terminal_invariant import certify_release_invariant, settle_release_to_invariant


def fixture(*, mode=1, direction=1, x=100., y=186.9, dx=0., dy=0.):
    bounds = [0., 0., 200., 200.]
    s = np.array([x, y, dx, dy, 0., 0., mode, direction, 750., 0., 0.])
    e = np.array([*bounds, mode, direction, 0., 1/240, 750., 0., 0., 0., 0., 0., *bounds, *bounds])
    d = dict(active_bones=0, active_stabs=0, active_blasters=0, active_platforms=0,
             arena_settled=True, timeline_exhausted=True, pending_callbacks=[], pending_dialogue=None)
    return s, e, d


@pytest.mark.parametrize('direction,x,y', [(0,186.9,100.),(1,100.,186.9),(2,13.1,100.),(3,100.,13.1)])
def test_contact_certificate_survives_all_gravity_directions_and_varying_dt(direction,x,y):
    s,e,d=fixture(direction=direction,x=x,y=y)
    s[4]=31.;s[5]=1.  # Releasing inputs is allowed; no movement can trigger a slam.
    proof=certify_release_invariant(s,e,d)
    assert proof['status']=='proven'
    expected=np.array(proof['invariant_state'])
    for dt in [1/240,1/30,1/1000,0.0041666666666860695]*10:
        e[7]=dt;out=np.empty(11);step_mask_into(s,0,e,np.zeros((0,9)),out)
        np.testing.assert_array_equal(out,expected)
        s=out


def test_red_stationary_interior_needs_no_support():
    s,e,d=fixture(mode=0,y=100.)
    assert certify_release_invariant(s,e,d)['status']=='proven'


@pytest.mark.parametrize('change', ['preheat','callback','unknown_callbacks','platform','moving_arena','outside','falling','slam_damage','negative_fall','old_phase','pulse'])
def test_empty_raster_is_not_a_terminal_certificate(change):
    s,e,d=fixture()
    if change=='preheat':d['active_blasters']=1
    if change=='callback':d['pending_callbacks']=['spawn_later']
    if change=='unknown_callbacks':del d['pending_callbacks']
    if change=='platform':d['active_platforms']=1
    if change=='moving_arena':d['arena_settled']=False
    if change=='outside':s[0]=-100.
    if change=='falling':s[1]=100.
    if change=='slam_damage':s[9]=e[12]=1.
    if change=='negative_fall':s[8]=e[8]=-300.
    if change=='old_phase':e[14]=1.
    if change=='pulse':e[9]=1.
    assert certify_release_invariant(s,e,d)['status']=='unknown'


def test_safe_settling_preserves_exact_replay_inputs_and_clock_without_mutating_env():
    s,e,d=fixture(y=100.,dx=150.,dy=-180.)
    s[4]=4.
    original=e.copy();dts=np.array([1/240,0.004166666666668561,0.004166666666665719]*700)
    result=settle_release_to_invariant(s,e,d,dts)
    assert result['status']=='proven'
    assert result['actions'] and all(a==0 for a in result['actions'])
    np.testing.assert_array_equal(e,original)
    q=s.copy();env=np.array(result['static_environment'])
    for dt,expected in zip(result['dt_sequence'],result['states'][1:]):
        env[7]=dt;out=np.empty(11);step_mask_into(q,0,env,np.zeros((0,9)),out)
        np.testing.assert_array_equal(out,expected);assert out[10]==0.;q=out
    assert certify_release_invariant(q,env,d)['status']=='proven'


def test_eof_pulses_are_cleared_in_private_tail_environment_not_reapplied():
    s,e,d=fixture(y=100.,dy=50.)
    e[6]=e[9]=e[13]=1.;e[10:12]=999.;e[14:18]=[2.,2.,198.,198.]
    original=e.copy()
    result=settle_release_to_invariant(s,e,d,np.full(1000,1/240))
    assert result['status']=='proven'
    assert all(row[0]==100. for row in result['states'])
    np.testing.assert_array_equal(e,original)


def test_budget_and_missing_clock_are_unknown_never_infeasible():
    s,e,d=fixture(y=100.,dy=100.)
    assert settle_release_to_invariant(s,e,d,[1/240]*100,max_steps=1)['reasons']==['step_budget_exhausted']
    assert settle_release_to_invariant(s,e,d,[])['reasons']==['dt_sequence_exhausted']
    assert settle_release_to_invariant(s,e,d,[0.])['reasons']==['invalid_dt_sequence']
    s[10]=1.
    assert settle_release_to_invariant(s,e,d,[1/240])['status']=='unknown'
