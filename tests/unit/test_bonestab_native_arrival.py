"""BoneStab must preserve the native angle condition, not a dot half-plane.

Battle.xml event 9761775752300883 snaps within 0.5 degrees, then event
8580988082190855 decrements StayTime only when BOTH coordinates equal Dest.
The recorded Part4 failure supplies an independent native collision witness.
"""
import json
import math
from pathlib import Path

import numpy as np
import pytest

from nohit.engine.compact_wave import _ActiveBoneStab
from nohit.engine.joint_transition import frame_collision
from nohit.engine.resumable_wave import Frame


FIXTURE = Path(__file__).parents[1] / 'fixtures/bonestab-part4-native-first-damage.json'
DT = 1 / 30
ARENA = [-10., 264., 650., 369.]


def staged_body(direction, stay, remaining, orthogonal=0.):
    body = _ActiveBoneStab(direction, 45, 0., stay)
    body.spawned = True
    body.w = body.h = 53.
    body.dest_x, body.dest_y = 100., 200.
    axis = direction % 2
    sign = 1. if direction in (0, 1) else -1.
    body.x = body.dest_x + (remaining * sign if axis == 0 else orthogonal)
    body.y = body.dest_y + (remaining * sign if axis == 1 else orthogonal)
    return body


@pytest.mark.parametrize('direction', range(4))
@pytest.mark.parametrize('stay', [0., DT, 2 * DT])
@pytest.mark.parametrize('remaining', [15., 7.5])
def test_native_exact_arrival_and_overshoot_decrement_stay(direction, stay, remaining):
    body = staged_body(direction, stay, remaining)
    assert body.step(DT, ARENA)
    assert (body.x, body.y) == (body.dest_x, body.dest_y)
    assert body.stay == max(0., stay - DT)
    assert body.reverse == (stay <= DT)


@pytest.mark.parametrize('direction', range(4))
@pytest.mark.parametrize('stay', [0., 2 * DT])
@pytest.mark.parametrize('orthogonal', [-1e-10, 1e-10])
def test_tiny_orthogonal_drift_at_axis_arrival_does_not_snap(direction, stay, orthogonal):
    body = staged_body(direction, stay, 15., orthogonal)
    assert body.step(DT, ARENA)
    # The bearing to Dest is perpendicular: native 0.5-degree test is false.
    assert not body.reverse
    assert body.stay == stay
    assert (body.x, body.y) != (body.dest_x, body.dest_y)
    # On the next tick it overshoots; now the bearing test passes.
    assert body.step(DT, ARENA)
    assert (body.x, body.y) == (body.dest_x, body.dest_y)
    assert body.reverse == (stay <= DT)


@pytest.mark.parametrize('direction', range(4))
@pytest.mark.parametrize('offset_degrees,should_snap', [(.499, True), (.501, False), (-.499, True), (-.501, False)])
def test_native_snap_respects_half_degree_angle_window(direction, offset_degrees, should_snap):
    body = staged_body(direction, 0., 0.)
    theta = math.radians(direction * 90 + offset_degrees)
    # After the movement, the bearing to Dest has the chosen angular offset.
    angle = (direction * 90.) / (180. / math.pi)
    body.x = body.dest_x - 10. * math.cos(theta) + math.cos(angle) * DT * 450.
    body.y = body.dest_y - 10. * math.sin(theta) + math.sin(angle) * DT * 450.
    body.step(DT, ARENA)
    assert body.reverse is should_snap


def test_native_snap_does_not_replace_equal_positive_zero_with_negative_zero():
    body = _ActiveBoneStab(2, 0, 0., 0.)
    body.spawned = True
    body.dest_x = -0.
    body.step(DT, ARENA)
    assert body.reverse
    assert not np.signbit(body.x)


def native_body_at_damage(direction):
    native = json.loads(FIXTURE.read_text(encoding='utf-8'))
    recorded = next(x for x in native['bodies'] if x['vars'][0] == direction)
    creation = next(x for x in native['lifecycle'] if x['object']['uid'] == recorded['uid'])
    body = _ActiveBoneStab(direction, 45, 0., 0.)
    # Creation is observed after the body has already moved once this tick.
    body.step(native['dt'], native['arena'])
    assert (body.x, body.y) == (creation['object']['x'], creation['object']['y'])
    for _ in range(native['native_damage_tick'] + 1 - creation['tick']):
        body.step(native['dt'], native['arena'])
    return native, recorded, body


@pytest.mark.parametrize('direction', [1, 3])
def test_part4_native_body_at_first_damage(direction):
    _, recorded, body = native_body_at_damage(direction)
    actual = np.asarray([body.x, body.y, body.w, body.h, body.dest_x, body.dest_y, body.stay, body.reverse])
    expected = np.asarray([recorded['x'], recorded['y'], recorded['width'], recorded['height'],
                           *recorded['vars'][2:6]], dtype=np.float64)
    assert actual.tobytes() == expected.tobytes()


def test_part4_native_first_damage_collision_with_identical_player_bytes():
    native, _, body = native_body_at_damage(1)
    player = np.asarray(native['native_player'], dtype=np.float64)
    assert player.tobytes() == np.asarray(native['model_player'], dtype=np.float64).tobytes()
    frame = Frame(1823, np.zeros(22), np.empty((0, 9)),
                  np.asarray([body.bbox()]), np.empty((0, 4)), np.empty((0, 8)), (), ())
    assert frame_collision(frame, player), 'native DamagePlayer hit must not be classified safe'
