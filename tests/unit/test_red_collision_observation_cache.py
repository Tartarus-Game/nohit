import numpy as np
import pytest
from nohit.engine.compact_wave import compile_wave
from nohit.engine.cspace import bake_cspace
from nohit.engine.local_relation import full_local_relation
from nohit.engine.red_joint_frontier import AxisFrontier
from nohit.engine.red_dense_frontier import DenseFrontier,unpack_keys
from nohit.engine.red_collision_observation_cache import advance_cached_dense,observation_maps

def scene(tmp_path):
    path=tmp_path/'red.csv';path.write_text('0,HeartMode,0\n0.2,EndAttack\n')
    return compile_wave(path)

def state(x=320.):return np.array([x,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.])

@pytest.mark.parametrize('hold',[1,4])
@pytest.mark.parametrize('plane',['white','blue'])
def test_cache_observation_quotient_matches_full_operator(tmp_path,hold,plane):
    wave=scene(tmp_path);nt=len(wave.env_schedule)
    boxes=np.tile(np.array([1000.,1000.,1010.,1010.]),(nt,1,1))
    # Neighboring floating positions straddle an inclusive white boundary.
    # Blue uses the same location for moving and stationary control results.
    boxes[1,0]=[322.,300.,326.,308.] if plane=='white' else [318.,300.,322.,308.]
    setattr(wave,'geometry_'+plane,boxes)
    wave.env_schedule[1:hold+1,7]=np.resize([.0031,.0067,.0042,.0048],hold)
    space=bake_cspace(wave);initial=np.array([state(),state(np.nextafter(320.,-np.inf))])
    dense=DenseFrontier.from_axis(AxisFrontier.from_states(initial))
    status,out,_=advance_cached_dense(wave,dense,tuple(range(32)),0,hold,space)
    assert status=='complete'
    exact=full_local_relation(wave,0,hold,initial,controls=tuple(range(32)),hold=hold,cspace=space)
    assert {out.state(k)[:4].tobytes() for k in unpack_keys(out.bits,len(out.x)*len(out.y))}=={s[:4].tobytes() for s in exact.states}

def test_cache_maps_preserve_coordinate_bits_and_tick_identity():
    tx=np.zeros((1,2,2,2));ty=np.zeros((1,1,2,2))
    tx[0,:,0,0]=[320.,np.nextafter(320.,np.inf)];tx[0,:,1,0]=320.;ty[:,:,:,0]=304.
    maps,size=observation_maps(tx,ty)
    assert maps[0][0,0,0]!=maps[0][0,1,0]
    assert maps[3][1]>maps[3][0]

def test_slam_damage_domain_is_rejected_and_cache_budget_falls_back(tmp_path):
    wave=scene(tmp_path);space=bake_cspace(wave)
    initial=state();initial[10]=1.
    front=DenseFrontier.from_axis(AxisFrontier.from_states([initial]))
    status,out,_=advance_cached_dense(wave,front,tuple(range(16)),0,1,space)
    assert status=='unsupported' and out is None
    initial[10]=0.;front=DenseFrontier.from_axis(AxisFrontier.from_states([initial]))
    status,out,stats=advance_cached_dense(wave,front,tuple(range(16)),0,4,space,max_cache_bytes=1)
    assert status=='complete' and out.count and stats['cache_budget_fallback']
