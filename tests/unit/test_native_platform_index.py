"""Platform pruning must preserve source contacts and ordered carry updates."""
import numpy as np
import pytest

from nohit.engine.native_backend import step_batch
from nohit.engine.source_oracle import scalar_module
from nohit.engine import resumable_wave as world


def test_packed_platform_frames_and_source_keys_survive_birth_reverse_and_clear(tmp_path):
    path=tmp_path/'platforms.csv'
    path.write_text('0,PlatformRepeat,538,346,45,2,100,100,240,\n'
        '0,PlatformRepeat,43,301,45,0,100,100,240,\n'
        '0.3,Platform,200,340,30,0,20,1\n0.2,BlackScreen,1\n'
        '0,PlatformRepeat,43,301,45,0,100,100,240,\n0.3,EndAttack\n')
    reference=world.initialize(path,dt_schedule=[1/60]*200,max_ticks=200)
    packed=world._enable_bone_arrays(reference.clone(),native=True)
    saw_packed=saw_reverse=False
    while True:
        a=world._advance_owned_tick(reference);b=world._advance_owned_tick(packed)
        assert type(a) is type(b)
        assert a.frame.platforms.tobytes()==b.frame.platforms.tobytes()
        assert world.state_environment_key(a.state)==world.state_environment_key(b.state)
        platforms=b.state.data['active_platforms']
        saw_packed|=isinstance(platforms,world._PlatformArrays)
        saw_reverse|=any(p.reverse for p in platforms)
        reference,packed=a.state,b.state
        if isinstance(a,world.Terminal):break
    assert saw_packed and saw_reverse


@pytest.mark.parametrize('direction',[1.,3.])
@pytest.mark.parametrize('nonfinite',[False,True])
def test_many_platforms_match_every_scalar_state_bit(direction,nonfinite):
    rng=np.random.default_rng(437)
    platforms=np.zeros((200,9))
    platforms[:,:2]=rng.uniform(-1000,1000,(200,2))
    platforms[:,2:4]=rng.uniform(-20,90,(200,2))
    platforms[:,4:6]=rng.uniform(-100,100,(200,2))
    platforms[:,6:8]=rng.integers(0,2,(200,2))
    platforms[:,8]=rng.uniform(-100,100,200)
    platforms[:16,:4]=np.column_stack((np.full(16,20.),np.linspace(300,306,16),np.full(16,40.),np.full(16,7.)))
    platforms[:16,6:8]=1.
    platforms[:16,5]=platforms[:16,8]=0.
    if nonfinite:platforms[30,:4]=(np.nan,np.inf,10.,7.)
    env=np.array([-2000.,-2000.,2000.,2000.,1.,direction,0.,1/60,750.,0.,0.,0.,1.,0.,
        -2000.,-2000.,2000.,2000.,-2000.,-2000.,2000.,2000.])
    states=np.zeros((240,11));states[:,:2]=rng.uniform(-1100,1100,(240,2))
    states[:,2:4]=rng.uniform(-750,750,(240,2));states[:,4]=rng.integers(0,16,240)
    states[:,5]=rng.integers(0,2,240);states[:,6:10]=(1.,direction,750.,1.)
    states[:80,:2]=(40.,292.);states[:80,2:4]=(-0.,0.)
    for index in range(16):
        x=platforms[index,0]-8.;y=platforms[index,1]-8.
        states[80+index*3:83+index*3,:2]=[(np.nextafter(x,-np.inf),y),(x,y),(np.nextafter(x,np.inf),y)]
    masks=rng.integers(0,16,len(states),dtype=np.int64)
    expected=np.empty_like(states);player=scalar_module('discrete_operator')
    for before,mask,after in zip(states,masks,expected):
        player.step_mask_into(before,int(mask),env,platforms,after)
    assert step_batch(states,masks,env,platforms).tobytes()==expected.tobytes()
