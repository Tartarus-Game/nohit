"""Native CompareOpacity rounds the normalized percentage before comparing."""
import pytest

from nohit.engine.compact_wave import _ActiveGasterBlaster


@pytest.mark.parametrize('blast_time,fire_ticks', [(.1, 80), (.2, 104), (.5, 176)])
def test_captured_clock_disables_damage_at_native_rounded_80_percent(blast_time, fire_ticks):
    # Battle.xml condition 7139969211329192 compares opacity <= 80, then
    # action 4837433704481348 clears Damage before the PlayerDamage group.
    # c2runtime.js CompareOpacity uses lb(100 * opacity), where lb rounds to
    # six decimals. The captured 240 Hz dt leaves raw opacity slightly above 80.
    blaster = _ActiveGasterBlaster(1, 319, 306, 319, 306, 0, 0, blast_time)
    dt = .004166666666627862
    active_ticks = 0
    for _ in range(fire_ticks + 100):
        assert blaster.step(dt)
        if blaster.state == 3:
            active_ticks += 1
            if active_ticks == fire_ticks - 1:
                assert blaster.damage
                assert blaster.polygon() is not None
            if active_ticks == fire_ticks:
                break
    assert active_ticks == fire_ticks
    assert 80. < blaster.opacity < 80.0000005
    assert not blaster.damage
    assert blaster.polygon() is None


def test_opacity_above_rounding_threshold_still_damages():
    blaster = _ActiveGasterBlaster(1, 319, 306, 319, 306, 0, 0, .2)
    blaster.state = 3
    blaster.damage = True
    blaster.base_size = 70.
    dt = .004166666666627862
    target_opacity = 80.0000006
    blaster.beam_timer = .2 + (5. + (100. - target_opacity) / 10.) / 30. - dt
    assert blaster.step(dt)
    assert blaster.opacity > 80.0000005
    assert blaster.damage
    assert blaster.polygon() is not None
