"""Native entity storage preserves original scalar transitions bit for bit."""
import numpy as np
from nohit.engine.compact_wave import _ActiveGasterBlaster
from nohit.engine.resumable_wave import _BlasterArrays
from nohit.engine.native_backend import neutral_rollout
from nohit.engine.source_oracle import scalar_module
from types import SimpleNamespace


def test_blasters_match_every_original_field_and_polygon():
    original=[]
    for size in (0,1,2):
        for angle in (-725,-335,-180,-90,0,33,45,90,270,650):
            for timer in (0.,.15):
                original.append(_ActiveGasterBlaster(size,320,240,320 if timer else 0,240 if timer else 0,angle,timer,.3))
    packed=_BlasterArrays(original)
    for tick in range(600):
        dt=(1/60,1/30,1/240)[tick%3]
        original=[item for item in original if item.step(dt)];packed.advance(dt)
        expected=np.asarray([[getattr(item,key) for key in packed.fields] for item in original],dtype=float).reshape(-1,17)
        assert expected.tobytes()==packed.rows[:len(packed)].tobytes(),tick
        polygons=np.asarray([p for item in original if (p:=item.polygon()) is not None],dtype=float).reshape(-1,8)
        assert polygons.tobytes()==packed.polygons().tobytes(),tick
        assert [vars(item) for item in original]==[vars(item) for item in packed]


def test_neutral_forecast_preserves_scalar_physics_at_every_boundary():
    player=scalar_module('discrete_operator')
    initial=np.array([320,370,30,-100,4,0,1,1,750,0,0.])
    frames=[];state=initial.copy()
    for tick in range(180):
        env=np.array([100,100,540,400,1,tick//45,0,1/60,750,0,0,0,0,0,100,100,540,400,100,100,540,400.])
        platforms=np.array([[240,350,80,7,0,0,1,1,0.]])
        frames.append(SimpleNamespace(env=env,platforms=platforms))
        player.step_mask_into(state,0,env,platforms,state)
        if tick%23==0 or tick==179:
            assert neutral_rollout(initial,frames).tobytes()==state.tobytes()
