"""Reachability/Bellman properties of the production operator injection seam."""
import numpy as np
from numba import njit
from nohit.engine.adaptive_dag import create_search_kernel
from tests.unit.test_adaptive_dag import fixture


@njit
def merged_transition(state, ux, up, env, platforms, out):
    out[:] = state
    out[0] = 10. * (1 - ux) if env[7] <= 4 else 0.
    out[4] = up


@njit
def no_collision(white, blue, tick, state, margin, payload):
    return False


@njit
def latent_transition(state, ux, up, env, platforms, out):
    out[:] = state
    if env[7] == 1:
        out[5] = ux
    out[4] = up


@njit
def latent_collision(white, blue, tick, state, margin, payload):
    return tick == 8 and state[5] != payload


def test_bellman_improvement_updates_an_already_inserted_successor_parent():
    args = list(fixture(13))
    args[2][:, 0] = -10
    args[2][:, 2] = 10
    args[2][:, 7] = np.arange(13)
    args[4][:] = 0.
    kernel = create_search_kernel(merged_transition, no_collision)
    result = kernel(*args, lookahead=0, weights=np.array([0., 0., 1., 0.]))
    assert result[0] == 0
    # Neutral is inserted before right. Their next neutral successors are
    # physically identical, but right's prefix has zero rather than .5 cost.
    assert tuple(map(tuple, result[-1])) == ((1, 0), (0, 0), (0, 0))
    # All safe layers were evaluated, including the final one.
    assert tuple(result[3]) == (1, 6, 6, 6)


def test_generic_markov_state_and_collision_payload_are_not_ignored():
    args = list(fixture())
    args[2][:, 7] = np.arange(9)
    args[4] = np.zeros(7)
    kernel = create_search_kernel(latent_transition, latent_collision)
    for required in (-1, 0, 1):
        status, _, _, _, route = kernel(*args, collision_data=required)
        assert status == 0 and route[0, 0] == required


def test_limited_discrepancy_defers_branches_without_proving_them_dead():
    from nohit.engine.adaptive_dag import create_demand_kernel
    args=list(fixture(9));args[2][:,7]=np.arange(9);args[4]=np.zeros(7)
    kernel=create_demand_kernel(latent_transition,latent_collision)
    greedy=kernel(*args,collision_data=1,weights=np.zeros(4),discrepancy_limit=0)
    # Greedy takes neutral first and fails later. Other controls remain unknown.
    assert greedy[0]==2 and len(greedy[-1])==0
    broader=kernel(*args,collision_data=1,weights=np.zeros(4),discrepancy_limit=1)
    complete=kernel(*args,collision_data=1,weights=np.zeros(4))
    assert broader[0]==complete[0]==0
    assert broader[-1][0,0]==complete[-1][0,0]==1


def test_weights_preserve_the_entire_layer_reachable_counts():
    args = list(fixture(13))
    args[2][:, 7] = np.arange(13)
    kernel = create_search_kernel(merged_transition, no_collision)
    off = kernel(*args, weights=np.zeros(4))
    on = kernel(*args, weights=np.array([1000., 1000., 1000., 1000.]))
    assert off[0] == on[0] == 0
    np.testing.assert_array_equal(off[3], on[3])


def test_demand_and_forward_recurrences_match_exhaustive_routes():
    from nohit.engine.adaptive_dag import demand_search, search
    from tests.unit.test_adaptive_dag import exhaustive
    for boundary in (315., 318., 321., 324., 327.):
        args = fixture()
        args[0][-1,0] = [133.,251.,boundary,391.]
        witnesses = exhaustive(args)
        for weights in (np.zeros(4), np.ones(4), np.array([0.,0.,1000.,10.])):
            forward = search(*args, max_nodes=5000, weights=weights)
            demand = demand_search(*args, max_nodes=5000, weights=weights)
            assert forward[0] == demand[0] == (0 if witnesses else 1)
            if demand[0] == 0:
                assert tuple(map(tuple,demand[-1])) in witnesses


@njit
def mask_transition(state, mask, unused, env, platforms, out):
    out[:] = state
    out[4] = mask


@njit
def only_mask(white, blue, tick, state, margin, payload):
    return tick > 0 and int(state[4]) != payload


@njit
def input_dependent_certificate(white,env,platforms,frame,state,cache):
    return int(state[4])==0


def test_dead_end_certificates_do_not_fold_different_jump_latches():
    from nohit.engine.adaptive_dag import create_demand_kernel
    args=list(fixture(5));args[4]=np.zeros(11)
    kernel=create_demand_kernel(mask_transition,no_collision,control_masks=True,
        dead_end_query=input_dependent_certificate)
    status,_,_,_,actions=kernel(*args,weights=np.zeros(4))
    assert status==0 and actions[0,0]!=0


def test_coast_hint_checks_every_tick_stops_at_bound_and_preserves_state():
    from nohit.engine.adaptive_dag import create_coast_hint
    args=list(fixture(9));args[4]=np.zeros(7)
    args[2][:,7]=np.arange(9)
    hint=create_coast_hint(latent_transition,latent_collision)
    white,blue,env,platforms,state=args
    assert hint(state,1,0,8,env,platforms,white,blue,1)==8
    assert hint(state,0,0,8,env,platforms,white,blue,1)==7
    assert hint(state,0,0,4,env,platforms,white,blue,1)==4
    np.testing.assert_array_equal(state,np.zeros(7))


def test_ballistic_landing_hint_ranks_toward_support_without_changing_state():
    from nohit.engine.adaptive_dag import create_landing_hint
    from nohit.engine.discrete_operator import step_action_into,initial_state
    _,_,env,_,_=fixture(9)
    platforms=np.zeros((9,1,9));platforms[:,:,0]=250.;platforms[:,:,1]=336.
    platforms[:,:,2]=41.;platforms[:,:,3]=7.;platforms[:,:,6]=1.
    state=initial_state(np.array([320.,325.,0.,120.,0.]),env[0])
    original=state.copy()
    hint=create_landing_hint(step_action_into)
    assert 0.<hint(state,1,0,8,env,platforms)<hint(state,2,0,8,env,platforms)
    np.testing.assert_array_equal(state,original)
    state[0]=275.;state[1]=327.95;state[3]=0.
    assert hint(state,0,0,8,env,platforms)==0.


@njit
def preferred_margin_only_collision(white,blue,tick,state,margin,payload):
    return tick>0 and margin>0. and int(state[4])==0


def test_disabled_clearance_weight_does_not_leak_margin_into_coast_order():
    from nohit.engine.adaptive_dag import create_demand_kernel
    args=list(fixture(9));args[4]=np.zeros(11)
    kernel=create_demand_kernel(mask_transition,preferred_margin_only_collision,control_masks=True)
    routes=[]
    for margin in (0.,4.):
        result=kernel(*args,weights=np.array([0.,1.,0.,0.]),margin=margin,coast_ticks=4)
        assert result[0]==0
        routes.append(result[-1])
    np.testing.assert_array_equal(routes[0],routes[1])
    assert np.all(routes[1]==0)


def test_demand_enumerates_all_32_masks_including_slow_opposed_keys():
    from nohit.engine.adaptive_dag import create_demand_kernel
    args = list(fixture(5))
    args[4] = np.zeros(11)
    kernel = create_demand_kernel(mask_transition, only_mask, control_masks=True)
    for required in range(32):
        result = kernel(*args, collision_data=required)
        assert result[0] == 0 and result[-1][0,0] == required


def test_demand_preserves_limits_and_partial_final_tick_collision():
    from nohit.engine.adaptive_dag import demand_search
    assert demand_search(*fixture(), max_nodes=1)[0] == 2
    assert demand_search(*fixture(), max_expansions=1)[0] == 2
    args = fixture(6)
    args[0][-1,0] = [0.,0.,640.,480.]
    assert demand_search(*args)[0] == 1


def test_next_jump_latch_projection_is_an_exact_one_tick_bisimulation():
    from nohit.engine.discrete_operator import initial_state, step_action_into
    from nohit.engine.adaptive_dag import next_jump_latch
    env=np.array([133.,251.,508.,391.,1.,1.,0.,1/240,750.,0.,0.,0.,0.,0.,133.,251.,508.,391.])
    platforms=np.empty((0,7))
    for mode in (0.,1.):
        for direction in range(4):
            env[4],env[5]=mode,direction
            latch=next_jump_latch(env[None,:],0)
            s=initial_state([320.,377.81875,0.,0.,0.],env)
            for previous in range(32):
                full=s.copy();full[4]=previous
                reduced=s.copy();reduced[4]=previous&latch
                for mask in range(32):
                    a=np.empty(11);b=np.empty(11)
                    step_action_into(full,mask,0,env,platforms,a)
                    step_action_into(reduced,mask,0,env,platforms,b)
                    np.testing.assert_array_equal(a.view(np.uint64),b.view(np.uint64))


def test_control_quotient_preserves_each_microtick_and_future_jump_latch():
    from nohit.engine.discrete_operator import initial_state,step_action_into
    from nohit.engine.adaptive_dag import equivalent_controls,projected_equal,next_jump_latch
    base=np.array([133.,251.,508.,391.,1.,1.,0.,1/240,750.,0.,0.,0.,0.,0.,133.,251.,508.,391.])
    platforms=np.empty((0,7))
    for modes,directions in [([0]*6,[1]*6),([1]*6,[1]*6),([0,0,1,1,1,1],[1,1,0,2,3,1])]:
        env=np.tile(base,(6,1));env[:,4]=modes;env[:,5]=directions
        initial=initial_state([320.,377.81875,0.,0.,1.],env[0])
        for a in range(32):
            for b in range(a):
                if not equivalent_controls(a,b,env,0):continue
                sa=initial.copy();sb=initial.copy()
                for tick in range(1,5):
                    step_action_into(sa,a,0,env[tick],platforms,sa)
                    step_action_into(sb,b,0,env[tick],platforms,sb)
                    np.testing.assert_array_equal(np.delete(sa,4).view(np.uint64),np.delete(sb,4).view(np.uint64))
                assert projected_equal(sa,sb,next_jump_latch(env,1))


def test_float_lattice_hash_does_not_collapse_a_time_layer_into_one_bucket():
    from nohit.engine.adaptive_dag import finalize_hash,projected_hash
    buckets=set()
    state=np.zeros(11)
    state[6:9]=[0.,1.,750.]
    for x in range(64):
        for y in range(64):
            state[:2]=[200.+x*.625,250.+y*.625]
            raw=np.uint64(projected_hash(state,0)) ^ np.uint64((120*0x9e3779b97f4a7c15)&((1<<64)-1))
            buckets.add(int(finalize_hash(raw)) & 2047)
    # These exact IEEE coordinates have identical low mantissa bits. Before
    # avalanche their raw FNV hashes all used the same table bucket.
    assert len(buckets)>1024


def test_single_mode_control_domain_excludes_cancel_during_search():
    from nohit.engine.adaptive_dag import create_demand_kernel
    args=list(fixture(5));args[4]=np.zeros(11)
    kernel=create_demand_kernel(mask_transition,only_mask,control_masks=True)
    assert kernel(*args,collision_data=31,allowed_mask_count=32)[0]==0
    assert kernel(*args,collision_data=31,allowed_mask_count=16)[0]==1
    result=kernel(*args,collision_data=15,allowed_mask_count=16)
    assert result[0]==0 and result[-1][0,0]==15
