import numpy as np
import pytest

from nohit.engine.compact_wave import compile_wave
from nohit.engine.native_backend import step_batch
from nohit.engine.parametric_environment import ParametricEnvironment
from nohit.engine.source_oracle import scalar_module


@pytest.mark.parametrize('direction',range(4))
def test_slam_reads_speed_at_dispatch_before_later_same_tick_change(tmp_path,direction):
    path=tmp_path/'slam.csv'
    path.write_text(f'0,HeartMode,1\n0.05,HeartMaxFallSpeed,0\n0,SansSlam,{direction}\n'
                    '0,HeartMaxFallSpeed,700\n0,HeartTeleport,320,304\n0.05,EndAttack\n')
    settings=dict(dt_schedule=[1/60]*30,max_ticks=30)
    wave=compile_wave(path,**settings)
    resumable=ParametricEnvironment(path,backend='resumable',**settings).bind().wave
    np.testing.assert_array_equal(wave.env_schedule,resumable.env_schedule)
    tagged=np.flatnonzero(wave.env_schedule[:,13]>=2.)
    assert len(tagged)==1
    tick=int(tagged[0]);env=wave.env_schedule[tick]
    assert env[6]==0 and env[8]==700 and env[13]==3
    player=scalar_module('discrete_operator')
    state=np.array([320,304,0,0,0,0,1,1,750,0,0],dtype=float)
    expected=state.copy();player.step_mask_into(state,0,env,wave.platform_table[tick],expected)
    actual=step_batch(state.reshape(1,11),np.array([0],dtype=np.int32),env,
                      wave.platform_table[tick])[0]
    assert actual.tobytes()==expected.tobytes()
    # A zero-speed slam receives one gravity increment, not a 700-speed kick.
    assert np.hypot(actual[2],actual[3])==pytest.approx(3.)
