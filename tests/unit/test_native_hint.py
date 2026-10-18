"""Request-local proposals are replayed against every new world frame."""
import numpy as np
import pytest

from nohit.engine.compact_wave import compile_wave
from nohit.engine.native_backend import replay_hint
from nohit.engine.source_oracle import scalar_module


def test_small_observed_forecasts_do_not_force_a_compiler(tmp_path):
    import os,subprocess,sys
    from pathlib import Path
    path=tmp_path/'observed.csv'
    path.write_text('0,HeartMode,0\n0.1,GetHeartPos,x,y\n0.2,EndAttack\n')
    cache=tmp_path/'cache';cache.mkdir()
    script='''
import sys
from pathlib import Path
from nohit.engine.csv_solver import solve_csv
r=solve_csv(sys.argv[1],[320.,304.,0.,0.,0.,0.,0.,1.,750.,0.,0.],
    dt_schedule=[1/60]*120,max_ticks=120,seconds=3,observation_chunk_ticks=6,observation_preview_ticks=6)
assert r['verified'] and not list(Path(sys.argv[2]).iterdir())
assert 'numba' not in sys.modules
'''
    result=subprocess.run([sys.executable,'-c',script,str(path),str(cache)],
        cwd=Path(__file__).resolve().parents[2],capture_output=True,text=True,timeout=10,
        env=dict(os.environ,NOHIT_NATIVE_CACHE=str(cache),CXX='compiler-that-does-not-exist'))
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('mode',[0,1])
def test_hint_replay_preserves_all_scalar_state_bits(tmp_path,mode):
    path=tmp_path/'hint.csv'
    path.write_text(f'0,HeartMode,{mode}\n0,Platform,200,350,80,0,30,1\n1,EndAttack\n')
    wave=compile_wave(path,dt_schedule=[1/60]*100,max_ticks=100)
    player=scalar_module('discrete_operator')
    initial=player.initial_state([320,304,0,0,0,0,mode,1,750,0,0],wave.env_schedule[0])
    actions=np.random.default_rng(79).integers(0,16,len(wave.env_schedule)-1)
    expected=[initial.copy()];state=initial.copy()
    for tick,mask in enumerate(actions,1):
        player.step_mask_into(state,int(mask),wave.env_schedule[tick],wave.platform_table[tick],state)
        expected.append(state.copy())
    actual=replay_hint(initial,wave,actions)
    assert actual is not None and actual.tobytes()==np.asarray(expected).tobytes()


def test_hint_replay_rejects_changed_world_and_scripted_damage(tmp_path):
    path=tmp_path/'hint.csv';path.write_text('0,HeartMode,0\n1,EndAttack\n')
    wave=compile_wave(path,dt_schedule=[1/60]*100,max_ticks=100)
    initial=np.array([320,304,0,0,0,0,0,1,750,0,0.],dtype=float)
    actions=[0]*(len(wave.env_schedule)-1)
    assert replay_hint(initial,wave,actions) is not None
    wave.geometry_white=np.full((len(actions)+1,1,4),np.nan)
    wave.geometry_white[12,0]=[319,303,321,305]
    assert replay_hint(initial,wave,actions) is None
    wave.geometry_white[:]=np.nan;initial[10]=1
    assert replay_hint(initial,wave,actions) is None
