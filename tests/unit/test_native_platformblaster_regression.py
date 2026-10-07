"""Independent native evidence for PlatformRepeat's per-call integer cast.

This recorded route took damage. The model must reproduce that failure rather
than claim safety by accidentally lifting a repeated platform one pixel.
"""
import json
from pathlib import Path

import numpy as np

from nohit.engine.compact_wave import compile_wave
from nohit.engine.cspace import bake_cspace,collision_query
from nohit.engine.discrete_operator import step_mask_into


def test_original_failed_platformblaster_route_has_exact_motion_and_failure_tick():
    root=Path(__file__).resolve().parents[2]
    fixture=json.loads((root/'tests/fixtures/native_platformblaster_failed_prefix.json').read_text())
    cap=fixture['captured']
    wave=compile_wave(root/'c2-sans-fight'/fixture['attack'],seed=fixture['seed'],
                      initial_environment=cap['initial_environment'],clock_start_ms=cap['clock_start_ms'])
    space=bake_cspace(wave)
    observed={row['relative_tick']:row for row in fixture['samples']}
    state=np.array(cap['initial']);out=np.empty(11);hits=[];checked=0
    for tick in range(1,fixture['first_damage_tick']+1):
        mask=fixture['actions'][(tick-1)//4]
        step_mask_into(state,mask,wave.env_schedule[tick],wave.platform_table[tick],out)
        state,out=out,state
        if collision_query(wave.geometry_white,wave.geometry_blue,tick,state,0.,space.payload):
            hits.append(tick)
        if tick in observed:
            row=observed[tick]
            np.testing.assert_array_equal(state[:4],row['position_velocity'],
                                          err_msg=f"native tick {row['absolute_tick']}")
            assert (row['HP'],row['KR'])==((91,10) if tick==fixture['first_damage_tick'] else (92,0))
            checked+=1
    assert checked==73
    assert hits==[1151]
