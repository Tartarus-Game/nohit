"""Signed native ANGLE results affect blaster entry time, not just orientation."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from nohit.engine.cspace import bake_cspace, collision_query, quad_intersects_box
from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.parametric_environment import ParametricEnvironment


@pytest.mark.parametrize('backend', ['reference', 'resumable'])
@pytest.mark.parametrize('target,expected', [
    ((1, -1), -45.), ((-1, -1), -135.), ((1, -2), -63.43494882292201),
    ((-1, 1), 135.), ((1, -8), -82.8749836510982),
    ((1, -0.), -0.), ((0, -1), -90.), ((-1, -0.), -180.),
    ((-1, 0), 180.), ((0, 1), 90.), ((1, 0), 0.),
    ((1, -0.9999999999999998), -44.99999999999999),
    ((1, -1.0000000000000002), -45.00000000000001),
])
def test_angle_preserves_signed_unrounded_degrees(tmp_path, backend, target, expected):
    x, y = target
    path = tmp_path / 'signed-angle.csv'
    path.write_text(f'0,ANGLE,a,0,0,{x},{y}\n'
                    '0,GasterBlaster,1,654,457,499,394,$a,0.66666,0.03333\n'
                    '2,EndAttack\n')
    wave = ParametricEnvironment(path, backend=backend, dt_schedule=[1/240], max_ticks=1).bind().wave
    event = next(event for event in wave.source_events if event[1] == 'gasterblaster')
    # Native Ka(Pa(...)) is (180/pi)*atan2. The (1,-8) case also detects
    # reassociation to atan2*180/pi. GasterBlaster's later int() conversion
    # is separate; ANGLE itself neither rounds nor maps negatives into [0, 360).
    assert event[2][5] == expected
    assert np.signbit(event[2][5]) == np.signbit(expected)


@pytest.mark.parametrize('backend', ['reference', 'resumable'])
def test_signed_angle_keeps_native_blaster_entry_duration(tmp_path, backend):
    path = tmp_path / 'negative-entry.csv'
    path.write_text('0,ANGLE,a,499.17919229133804,394.23907821005173,'
                    '343.74999999994384,268.37500000008424\n'
                    '0,GasterBlaster,1,654.6083845827322,457.1711173150354,'
                    '499.17919229133804,394.23907821005173,$a,0.66666,0.03333\n'
                    '2,EndAttack\n')
    dt = 0.004166666666656965
    wave = ParametricEnvironment(path, backend=backend, dt_schedule=[dt]*330, max_ticks=330).bind().wave
    active = np.flatnonzero(np.isfinite(wave.geometry_polygons).all(axis=2).any(axis=1))
    # Native firing at campaign frame 748 follows creation at frame 461.
    # Normalizing -141 to 219 changes linear interpolation from initial 90
    # and starts the beam ten ticks too early.
    assert active[0] == 748 - 461
    poly = wave.geometry_polygons[-1, 0].reshape(4, 2)
    assert np.linalg.norm(poly[1] - poly[0]) == pytest.approx(52.5, abs=1e-12)


@pytest.mark.parametrize('backend', ['reference', 'resumable'])
def test_native_randomblaster2_first_damage_is_frame_790(tmp_path, backend):
    fixture_path = Path(__file__).resolve().parents[1] / 'fixtures/native_randomblaster2_signed_angle_failure.json'
    fixture = json.loads(fixture_path.read_text())
    path = tmp_path / 'randomblaster2.csv'
    path.write_bytes(fixture['csv'].encode('utf-8'))
    assert hashlib.sha256(path.read_bytes()).hexdigest() == fixture['csv_sha256']
    rows = fixture['native_rows']
    template = ParametricEnvironment(path, backend=backend, seed=fixture['seed'],
        initial_environment=fixture['initial_environment'], initial_arena=fixture['initial_arena'],
        dt_schedule=[row[1] for row in rows], max_ticks=len(rows))
    wave = template.bind(fixture['native_target_history']).wave
    assert len(wave.env_schedule) == len(rows)
    assert all(row[2:4] == [92, 0] for row in rows[:-1])
    assert rows[-1][2:4] == [91, 10]
    cspace = bake_cspace(wave)
    state = np.array(fixture['initial'], dtype=float)
    exact_hits = []
    baked_hits = []
    for tick, (mask, dt, hp, kr, native_state) in enumerate(rows):
        if tick:
            step_mask_into(state, mask, wave.env_schedule[tick], wave.platform_table[tick], state)
        assert state.tobytes() == np.asarray(native_state, dtype=float).tobytes(), tick
        if any(quad_intersects_box(poly, state[0], state[1], 2., 2.)
               for poly in wave.geometry_polygons[tick]):
            exact_hits.append(tick)
        if collision_query(wave.geometry_white, wave.geometry_blue, tick, state, 0., cspace.payload):
            baked_hits.append(tick)
    assert exact_hits == baked_hits == [fixture['first_collision_frame']]
    event = next(event for event in wave.source_events if event[:2] == (461, 'gasterblaster'))
    assert event[2][5] == fixture['native_firing_blaster']['ivs']['9692461505937432'] == -141.
    poly = wave.geometry_polygons[-1, 0].reshape(4, 2)
    assert np.linalg.norm(poly[1] - poly[0]) == pytest.approx(fixture['native_damage_sprite']['w']['h'], abs=1e-12)
