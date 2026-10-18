"""SansSlam guards its raw parameter, then uses its numeric floored angle."""
import numpy as np
import pytest

from nohit.engine.compact_wave import compile_wave
from nohit.engine import resumable_wave as world


@pytest.mark.parametrize('argument,direction,active',[
    ('HandLeft',1.,False), ('-1',1.,False), ('3.5',1.,False),
    ('2.9',2.,True), ('0x2',2.,True), ('2e0',2.,True),
    ('1e2',1.,False), ('',0.,True), ('3',3.,True),
])
def test_slam_matches_guarded_raw_coercion_on_both_source_backends(tmp_path,argument,direction,active):
    path=tmp_path/'slam.csv'
    path.write_text('0,HeartMode,0\n0,SansSlam,'+argument+'\n0.1,EndAttack\n')
    reference=compile_wave(path,dt_schedule=[1/60]*20,max_ticks=20)
    state=world.initialize(path,dt_schedule=[1/60]*20,max_ticks=20)
    frames=[]
    while True:
        result=world._advance_owned_tick(state)
        frames.append(result.frame.env)
        state=result.state
        if isinstance(result,world.Terminal):break
    assert np.asarray(frames).tobytes()==reference.env_schedule.tobytes()
    assert reference.env_schedule[0,5]==direction
    assert bool(reference.env_schedule[0,6]) is active
    assert reference.env_schedule[0,4]==float(active)
