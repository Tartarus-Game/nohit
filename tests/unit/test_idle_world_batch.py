"""Event-free batching must match the independent source interpreter."""
import numpy as np
import pytest
from nohit.engine import resumable_wave as world
from nohit.engine.compact_wave import compile_wave


@pytest.fixture(autouse=True)
def native_kernel():
    from nohit.engine.native_backend import load_backend
    load_backend()


@pytest.mark.parametrize('bones',[0,1,300])
@pytest.mark.parametrize('limit',[2,7,64])
@pytest.mark.parametrize('other_entities',[False,True])
def test_idle_batch_matches_every_source_frame_and_command_boundary(tmp_path,bones,limit,other_entities):
    path=tmp_path/'idle.csv'
    path.write_text('0,HeartMode,0\n0,CombatZoneResizeInstant,100,100,540,420\n'+
        ''.join(f'0,BoneV,{i%20*30-10},{i%7*70},20,{i%4},{i%11*10},{i%2}\n' for i in range(bones))+
        (''.join(f'0,Platform,{i*10},350,60,{i%4},80,0\n' for i in range(20))+
         ''.join(f'0,GasterBlaster,{i%3},100,100,320,100,{i*37-180},0.02,0.08\n' for i in range(15)) if other_entities else '')+
        '0.27,Set,key,3\n0,BlackScreen,1\n0,BoneH,-5,310,20,2,120,1\n0.43,EndAttack\n')
    dt=[1/60,1/240,1/30,0.01700000000000012]*100
    settings=dict(dt_schedule=dt,max_ticks=len(dt))
    reference=compile_wave(path,**settings)
    state=world._enable_bone_arrays(world.initialize(path,**settings),native=True)
    frames=[];batches=0
    while True:
        idle=world._advance_idle_world_owned(state,limit)
        if idle:
            batches+=1;frames.extend(idle);continue
        tick=state.data['tick']
        options={} if state.dialogue_coupled else dict(previous_confirm=False,previous_cancel=False)
        result=world._advance_with_dialogue_input_owned(state,confirm=tick%2==0,cancel=False,**options)
        assert isinstance(result,(world.TickCommitted,world.Terminal))
        frames.append(result.frame)
        if isinstance(result,world.Terminal):break
    assert batches and len(frames)==len(reference.env_schedule)
    for tick,frame in enumerate(frames):
        assert frame.tick==tick
        assert frame.env.tobytes()==reference.env_schedule[tick].tobytes()
        assert frame.platforms.tobytes()==reference.platform_table[tick,:len(frame.platforms)].tobytes()
        for name,tensor in [('white',reference.geometry_white),('blue',reference.geometry_blue),
                            ('polygons',reference.geometry_polygons)]:
            rows=getattr(frame,name)
            assert rows.tobytes()==tensor[tick,:len(rows)].tobytes(),(tick,name)
            assert np.isnan(tensor[tick,len(rows):]).all()
    assert tuple(event for frame in frames for event in frame.events)==reference.source_events
    assert state.stats['ticks_committed']==len(frames)
    assert state.dialogue_last_input==((len(frames)-1)%2==0,False)


@pytest.mark.parametrize('command',['Platform,200,350,60,0,80,1',
    'BoneStab,0,30,1,1','SansText,hello.,'])
def test_idle_batch_declines_unsupported_live_mechanisms(tmp_path,command):
    path=tmp_path/'mechanism.csv';path.write_text(f'0,{command}\n1,EndAttack\n')
    state=world._enable_bone_arrays(world.initialize(path,dt_schedule=[1/60]*200,max_ticks=200),native=True)
    world._advance_with_dialogue_input_owned(state,confirm=False,cancel=False,
        previous_confirm=False,previous_cancel=False)
    assert world._advance_idle_world_owned(state,64)==[]


def test_batch_stops_before_player_read_and_at_finite_clock_budget(tmp_path):
    path=tmp_path/'read.csv';path.write_text('0,HeartMode,0\n0.12,GetHeartPos,x,y\n1,EndAttack\n')
    def initialized(clock):
        state=world._enable_bone_arrays(world.initialize(path,dt_schedule=clock,max_ticks=100),native=True)
        world._advance_with_dialogue_input_owned(state,confirm=False,cancel=False,
            previous_confirm=False,previous_cancel=False)
        return state
    state=initialized([1/60]*100)
    frames=world._advance_idle_world_owned(state,64)
    assert frames and not world._advance_idle_world_owned(state,64)
    request=world._advance_with_dialogue_input_owned(state,confirm=state.data['tick']%2==0,cancel=False)
    assert isinstance(request,world.NeedTarget) and request.request['line']==2
    state=initialized([1/60]*4)
    assert len(world._advance_idle_world_owned(state,64))==3
    result=world._advance_with_dialogue_input_owned(state,confirm=True,cancel=False)
    assert isinstance(result,world.ResourceLimit) and result.reason=='clock_budget'
