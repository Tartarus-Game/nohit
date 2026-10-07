import itertools
import numpy as np
from nohit.engine.adaptive_dag import search
from nohit.engine.canonical_lattice import collision,step


def fixture(ticks=9):
    env=np.tile(np.array([133.,251.,508.,391.,1.,1.,0.,1/240]),(ticks,1))
    platforms=np.zeros((ticks,0,7))
    white=np.full((ticks,1,4),np.nan)
    return white,white.copy(),env,platforms,np.array([320.,377.81875,0.,0.,0.])


def exhaustive(args):
    white,blue,env,platforms,initial=args
    alphabet=list(itertools.product(range(-1,2),range(2)))
    witnesses=[]
    layers=(len(env)-1+3)//4
    for route in itertools.product(alphabet,repeat=layers):
        q=initial.copy();safe=not collision(white,blue,0,q,0.)
        for f,(ux,up) in enumerate(route):
            for micro in range(1,5):
                tick=f*4+micro
                if tick>=len(env): break
                q=step(q,ux,up,env[tick],platforms[tick])
                safe &= not collision(white,blue,tick,q,0.)
        if safe: witnesses.append(tuple(route))
    return witnesses


def test_bad_initial_preference_does_not_discard_the_only_route():
    args=fixture()
    args[0][-1,0]=[133,251,321,391]
    witnesses=exhaustive(args)
    # No forward hint: center/neutral is preferred and dies. Success requires
    # returning to a previously deferred first-frame rightward input.
    status,frame,expanded,_,route=search(*args,max_nodes=1000,lookahead=0)
    assert status==0 and frame==2 and expanded>2
    assert tuple(map(tuple,route)) in witnesses


def test_exhaustive_empty_frontier_agrees_with_brute_force():
    args=fixture()
    args[0][-1,0]=[0,0,640,480]
    assert exhaustive(args)==[]
    status,_,expanded,_,_=search(*args,max_nodes=1000,lookahead=0)
    assert status==1 and expanded>2


def test_resource_limit_is_not_empty_frontier():
    assert search(*fixture(),max_nodes=2,lookahead=0)[0]==2
    assert search(*fixture(),max_expansions=1,lookahead=0)[0]==2


def test_initial_and_partial_terminal_microtick_are_checked():
    args=fixture(6)
    args[0][-1,0]=[0,0,640,480]
    assert search(*args,max_nodes=1000,lookahead=0)[0]==1
    args=fixture()
    args[0][0,0]=[0,0,640,480]
    assert search(*args,max_nodes=1000)[0:3]==(1,0,0)


def test_heuristic_changes_order_only_on_small_graphs():
    for boundary in (315.,318.,321.,324.,327.):
        args=fixture()
        args[0][-1,0]=[133,251,boundary,391]
        possible=bool(exhaustive(args))
        for hint in (0,1,4,60):
            status,*_=search(*args,max_nodes=1000,lookahead=hint)
            assert (status==0)==possible
            assert status in (0,1)


def test_capacity_growth_preserves_deferred_nodes_and_parent_chains():
    args=fixture()
    args[0][-1,0]=[133,251,321,391]
    large=search(*args,max_nodes=1000,lookahead=0)
    growing=search(*args,max_nodes=1000,lookahead=0,initial_capacity=2)
    assert large[:3]==growing[:3]
    np.testing.assert_array_equal(large[3],growing[3])
    np.testing.assert_array_equal(large[4],growing[4])


def test_preferred_margin_never_removes_a_narrow_only_route():
    args=fixture()
    args[0][-1,0]=[133,251,321,391]
    witnesses=exhaustive(args)
    # Only moving right avoids the bone, with less than 10 px clearance.
    status,frame,expanded,_,route=search(*args,max_nodes=2000,margin=10.,lookahead=0,initial_capacity=2)
    assert status==0 and frame==2 and expanded>2
    assert tuple(map(tuple,route)) in witnesses


def test_initial_preferred_margin_overlap_does_not_mean_collision():
    args=fixture()
    args[0][0,0]=[310.,370.,317.,385.]
    assert not collision(args[0],args[1],0,args[-1],0.)
    assert collision(args[0],args[1],0,args[-1],4.)
    assert search(*args,max_nodes=1000,margin=4.)[0]==0


def test_weights_change_style_but_not_whether_a_safe_route_exists():
    # Compare against every input sequence, including a case with no route.
    profiles=[np.zeros(4),np.array([1.,1.,1.,0.]),np.array([0.,0.,1000.,10.])]
    for boundary in (315.,321.,327.):
        args=fixture()
        args[0][-1,0]=[133.,251.,boundary,391.]
        witnesses=exhaustive(args)
        for weights in profiles:
            status,_,_,_,route=search(*args,max_nodes=2000,margin=10.,lookahead=4,weights=weights)
            assert (status==0)==bool(witnesses)
            assert status in (0,1)
            if witnesses:
                assert tuple(map(tuple,route)) in witnesses


def test_zero_weights_and_center_preference_produce_different_safe_styles():
    args=fixture()
    args[-1][0]=250.
    unweighted=search(*args,max_nodes=1000,lookahead=0,weights=np.zeros(4))
    centered=search(*args,max_nodes=1000,lookahead=0,weights=np.array([0.,0.,1.,0.]))
    assert unweighted[0]==centered[0]==0
    assert tuple(map(tuple,unweighted[-1]))==((0,0),(0,0))
    assert tuple(map(tuple,centered[-1]))==((1,0),(1,0))


def test_a_bad_style_preference_cannot_remove_the_only_safe_branch():
    args=fixture()
    args[-1][0]=350.
    args[0][-1,0]=[133.,251.,352.,391.]
    # Center is left of the player; the only safe escape is right.
    witnesses=exhaustive(args)
    status,_,expanded,_,route=search(*args,max_nodes=2000,lookahead=0,
        weights=np.array([0.,0.,1000.,10.]),initial_capacity=2)
    assert status==0 and expanded>2
    assert tuple(map(tuple,route)) in witnesses
