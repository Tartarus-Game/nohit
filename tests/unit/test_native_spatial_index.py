"""Conservative broad phase must preserve exact original collision predicates."""
from types import SimpleNamespace
import numpy as np
import pytest
from nohit.engine.native_backend import collision_batch
from nohit.engine.source_oracle import scalar_module
from nohit.engine.source_verification import scalar_frame_collision
from nohit.engine import resumable_wave as world


def test_cells_match_scalar_at_boundaries_holes_and_nonfinite_rectangles():
    rng=np.random.default_rng(273)
    rects=rng.uniform(-80,720,(140,4));rects[:,2:]=rects[:,:2]+rng.uniform(-5,90,(140,2))
    rects[0]=(-np.inf,200,20,np.inf);rects[1]=(np.nan,0,100,100)
    rects[2]=(100,100,100,100);rects[3]=(10,np.nan,20,30)
    white,blue=rects[:90],rects[90:]
    polygons=np.array([[80,180,210,210,160,260,50,230],[np.nan]*8])
    states=np.zeros((800,11));states[:,:2]=rng.uniform(-40,700,(800,2));states[:,2]=rng.integers(0,2,800)
    states[:10,:2]=[(0,0),(640,480),(16,16),(98,98),(102,102),(20,200),(-2,200),(642,482),(80,180),(210,210)]
    states[-2:,10]=1
    source=scalar_module('cspace');payload=(np.empty((1,2,0,0),np.uint8),polygons[None],0.,0.,1.)
    expected=np.array([source.collision_query(white[None],blue[None],0,s,0.,payload) for s in states])
    actual=collision_batch(states,white,blue,polygons)
    assert np.array_equal(actual,expected)
    frame=SimpleNamespace(white=white,blue=blue,polygons=polygons)
    assert np.array_equal([scalar_frame_collision(frame,s) for s in states],expected)


@pytest.mark.parametrize("native",[False,True])
def test_owned_bone_arrays_match_every_public_frame_and_environment_key(tmp_path,native):
    path=tmp_path/'dense.csv'
    path.write_text('0,BoneVRepeat,700,200,70,2,135,100,13\n'
        '0,BoneHRepeat,100,-150,45,1,180,100,17\n'
        '0,BoneV,270,260,20,3,35,1\n0.4,BlackScreen,1\n'
        '0,BoneVRepeat,-40,250,90,0,120,100,14\n0.8,EndAttack\n')
    left=world.initialize(path,dt_schedule=[1/60]*200,max_ticks=200)
    right=world._enable_bone_arrays(left.clone(),native=native)
    while True:
        a=world._advance_owned_tick(left);b=world._advance_owned_tick(right)
        assert type(a) is type(b)
        for name in ('env','platforms','white','blue','polygons'):
            assert getattr(a.frame,name).tobytes()==getattr(b.frame,name).tobytes()
        assert world.state_environment_key(a.state)==world.state_environment_key(b.state)
        left,right=a.state,b.state
        if isinstance(a,world.Terminal):break
    # An owned vector continuation still obeys ordinary clone independence.
    cloned=right.clone();cloned.data['active_bones'].clear()
    assert cloned.data['active_bones'] is not right.data['active_bones']


def test_native_bone_arrays_preserve_nonfinite_and_signed_zero():
    from nohit.engine.compact_wave import _ActiveBone
    rows=np.zeros((256,8));rows[:,2:4]=(20.,30.);rows[:,6]=np.arange(256)%2
    rows[:8,:2]=[(0.,-0.),(-0.,0.),(640.,480.),(-20.,-30.),(np.nan,10.),(10.,np.inf),(np.inf,20.),(10.,20.)]
    rows[8:,:2]=np.random.default_rng(551).uniform(-50,700,(248,2))
    rows[8:,4:6]=np.random.default_rng(552).uniform(-200,200,(248,2))
    rows[:,7]=np.arange(256)%4;rows[7,2]=np.nan;rows[6,4]=np.nan
    a=world._BoneArrays();b=world._BoneArrays(native=True)
    for row in rows:
        item=_ActiveBone.__new__(_ActiveBone)
        for key,value in zip(_ActiveBone.__slots__,row):setattr(item,key,float(value))
        a.append(item);b.append(item)
    for dt in (0.,1/60,.25,0.):
        a.advance(dt);b.advance(dt)
        assert a.rows[:len(a)].tobytes()==b.rows[:len(b)].tobytes()
        for left,right in zip(a.geometry(),b.geometry()):assert left.tobytes()==right.tobytes()
