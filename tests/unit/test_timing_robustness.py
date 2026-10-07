import itertools
from types import SimpleNamespace
import numpy as np
from nohit.engine.canonical_lattice import step,collision
from nohit.engine.timing_robustness import advance_bundle,certify_timing_radius


def fixture():
    return SimpleNamespace(
        env_schedule=np.tile([133.,251.,508.,391.,1.,1.,0.,1/240],(9,1)),
        platform_table=np.zeros((9,0,7)),
        geometry_white=np.full((9,1,4),np.nan),
        geometry_blue=np.full((9,1,4),np.nan))


def explicit(w,initial,actions,radius):
    final=set();safe=True
    for first,second in itertools.product(range(radius+1),range(-radius,radius+1)):
        q=initial.copy()
        for tick in range(8):
            action=(0,0) if tick<first else actions[0]
            if tick>=4+second:action=actions[1]
            q=step(q,*action,w.env_schedule[tick+1],w.platform_table[tick+1])
            safe &= not collision(w.geometry_white,w.geometry_blue,tick+1,q,0.)
        final.add(q.tobytes())
    return safe,final


def test_bundle_matches_every_independent_early_and_late_boundary():
    w=fixture();s=np.array([320.,377.81875,0.,0.,0.]);actions=[(1,1),(-1,0)]
    for radius in (0,1,2):
        states=s.reshape(1,5);old=(0,0)
        for f,action in enumerate(actions):
            status,states=advance_bundle(w.geometry_white,w.geometry_blue,w.env_schedule,
                w.platform_table,states,f,*old,*action,radius)
            assert status==0
            old=action
        safe,expected=explicit(w,s,actions,radius)
        assert safe
        assert {row.tobytes() for row in states}==expected


def test_nominal_safe_is_not_timing_robust():
    w=fixture();s=np.array([320.,377.81875,0.,0.,0.]);actions=[(1,0),(1,0)]
    w.geometry_white[-1,0]=[133.,251.,321.5,391.]
    assert certify_timing_radius(w,s,actions,0)['status']=='certified'
    assert certify_timing_radius(w,s,actions,2)['status']=='counterexample'


def test_resource_limit_never_claims_a_counterexample():
    w=fixture();s=np.array([320.,377.81875,0.,0.,0.])
    assert certify_timing_radius(w,s,[(1,1),(-1,0)],2,max_states=1)['status']=='resource_limit'
