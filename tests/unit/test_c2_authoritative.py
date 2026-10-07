"""
Regression tests locking the authoritative Construct 2 semantics discovered from
``repo_badtime`` (the authoritative source) and from live measurement of the
compiled export.

These are deliberately narrow: each test pins ONE transcribed fact so a future
edit cannot silently drift back to the "immediate 5 px per frame" assumption.
"""

from __future__ import annotations

import math

import pytest

from nohit.engine import c2spec
from nohit.engine.c2step import initial_state, step_c2
from nohit.baker.rasterizer import RasterizerConfig, rasterize_timeline
from nohit.common.types import Command, PlatformInstance


# ---------------------------------------------------------------------------
# c2spec: transcribed constants
# ---------------------------------------------------------------------------
class TestSpecConstants:
    def test_heart_speed_is_150_px_per_second(self):
        assert c2spec.HEARTSPEED == 150.0

    def test_jump_strength_and_cutoff(self):
        assert c2spec.HEART_JUMP_STRENGTH == 180.0
        assert c2spec.HEART_JUMPHOLD_CUTOFF == 30.0

    def test_max_fall_speed(self):
        assert c2spec.MAX_FALL_SPEED_DEFAULT == 750.0

    def test_landing_offset_is_fractional(self):
        assert c2spec.PLATFORM_LAND_OFFSET == 8.05

    def test_heart_sprite_is_not_square(self):
        # Measured live on the export: 16x20, while the colliding PlayerHitbox is 4x4.
        assert c2spec.HEART_SPRITE_SIZE == (16, 20)
        assert c2spec.HITBOX_SIZE == 4

    def test_custom_movement_properties_are_horizontal_then_vertical(self):
        step_mode, _speed, px_per_step = c2spec.CUSTOM_MOVEMENT_PROPS
        assert step_mode == 2, "stepMode 2 = horizontal then vertical"
        assert px_per_step == 1, "one collision probe per pixel of travel"

    def test_frame_order_matches_the_event_sheet(self):
        names = [s.name for s in c2spec.FRAME_ORDER]
        assert names == [
            "solid_probe",
            "speed_assignment",
            "platform_probe_and_snap",
            "horizontal_step",
            "reset_cancel_step",
            "vertical_step",
        ]


class TestGravityLadder:
    @pytest.mark.parametrize(
        "down_speed,expected",
        [
            (241.0, 540.0),
            (240.0, 180.0),
            (100.0, 180.0),
            (16.0, 180.0),
            (15.0, 180.0),
            (0.0, 180.0),
            (-29.0, 180.0),
        ],
    )
    def test_matching_bands(self, down_speed, expected):
        assert c2spec.gravity_for_down_speed(down_speed) == expected

    @pytest.mark.parametrize("down_speed", [-30.0, -60.0, -119.0])
    def test_hold_band_returns_none(self, down_speed):
        # The source's conditions leave (-120, -30] unmatched, so Gravity keeps
        # its previous value instead of being recomputed.
        assert c2spec.gravity_for_down_speed(down_speed) is None

    def test_far_negative_band(self):
        assert c2spec.gravity_for_down_speed(-120.0) == 180.0
        assert c2spec.gravity_for_down_speed(-500.0) == 180.0

    def test_gravity_starts_at_zero(self):
        assert c2spec.GRAVITY_INITIAL == 0.0


class TestSubStepCount:
    def test_zero_move_takes_no_step(self):
        assert c2spec.sub_step_count(0.0) == 0

    def test_always_at_least_one_step(self):
        assert c2spec.sub_step_count(0.1) == 1

    def test_one_probe_per_pixel(self):
        assert c2spec.sub_step_count(5.0) == 5
        assert c2spec.sub_step_count(-5.0) == 5

    def test_rounding_matches_the_runtime(self):
        # c2runtime.js: Math.round(Math.sqrt(x*x+y*y)/pxPerStep)
        assert c2spec.sub_step_count(2.5) == 2
        assert c2spec.sub_step_count(3.5) == 4


# ---------------------------------------------------------------------------
# c2step: behaviour
# ---------------------------------------------------------------------------
class TestC2Step:
    def test_initial_state_is_at_rest(self):
        s = initial_state(10.0, 100.0)
        assert s[2] == 0.0 and s[3] == 0.0
        assert s[4] == 1, "kappa=1 means resting"
        assert s[5] == c2spec.GRAVITY_INITIAL

    def test_red_mode_no_input_does_not_move(self):
        s = initial_state(0.0, 100.0)
        s2 = step_c2(s, ux=0, uy=0, dt=1.0 / 60.0, is_blue=False)
        assert s2[0] == 0.0

    def test_red_mode_right_input_moves_two_point_five_px_at_60hz(self):
        # HEARTSPEED is 150 px/s; at dt = 1/60 that is exactly 2.5 px of travel
        # IN THE SAME TICK (the speed is assigned, then the behaviour steps with
        # it). The "docs"/"c2" steppers hard-code 5 px/frame, which is double the
        # source speed -- part of the motion-model mismatch.
        s = initial_state(100.0, 100.0)
        nxt = step_c2(s, ux=1, uy=0, dt=1.0 / 60.0, is_blue=False)
        assert nxt[0] == pytest.approx(100.0 + c2spec.HEARTSPEED / 60.0)
        assert nxt[0] == pytest.approx(102.5)

    def test_speed_is_reassigned_every_tick_from_input(self):
        # The sheet re-derives dx/dy from VPad each tick, so a released key means
        # "no travel" rather than "keep coasting".
        s = initial_state(100.0, 100.0)
        moving = step_c2(s, ux=1, uy=0, dt=1.0 / 60.0, is_blue=False)
        stopped = step_c2(moving, ux=0, uy=0, dt=1.0 / 60.0, is_blue=False)
        assert stopped[0] == pytest.approx(moving[0]), "no coasting on release"

    def test_displacement_scales_with_dt(self):
        # dt is wall-clock derived in the engine, so the same input yields
        # framerate-dependent (but time-correct) displacement: halving dt halves
        # the travel. This is why the build's frame rate changes how the heart
        # feels, and why a "5 px per frame" constant cannot be right at any frame
        # rate other than the one it was tuned for.
        s = initial_state(100.0, 100.0)
        at30 = step_c2(s, ux=1, uy=0, dt=1.0 / 30.0, is_blue=False)
        at60 = step_c2(s, ux=1, uy=0, dt=1.0 / 60.0, is_blue=False)
        at120 = step_c2(s, ux=1, uy=0, dt=1.0 / 120.0, is_blue=False)
        assert (at30[0] - 100.0) == pytest.approx(5.0)
        assert (at60[0] - 100.0) == pytest.approx(2.5)
        assert (at120[0] - 100.0) == pytest.approx(1.25)
        assert (at30[0] - 100.0) == pytest.approx(2.0 * (at60[0] - 100.0))

    def test_blue_mode_gravity_accumulates_along_the_facing_axis(self):
        # facing 90 == C2 "down": gravity pulls dy negative in C-space.
        s = initial_state(0.0, 200.0)
        s1 = step_c2(s, ux=0, uy=0, dt=1.0 / 60.0, is_blue=True)
        assert s1[5] == 180.0, "first band is 180 px/s^2"
        assert s1[3] < 0.0, "dy must go negative (falling)"

    def test_gravity_hold_band_retains_previous_value(self):
        # Hand-craft a state in the hold band and confirm gravity is untouched.
        x, y, dx, dy, kappa, gravity, facing = initial_state(0.0, 200.0)
        state = (x, y, dx, -60.0, kappa, 450.0, facing)  # DownSpeed = -60 -> hold band
        nxt = step_c2(state, ux=0, uy=0, dt=1.0 / 60.0, is_blue=True)
        assert nxt[5] == 450.0, "hold band keeps the previous Gravity"

    def test_terminal_velocity_is_clamped(self):
        max_fall_speed = c2spec.MAX_FALL_SPEED_DEFAULT
        x, y, dx, dy, kappa, gravity, facing = initial_state(0.0, 200.0)
        state = (x, y, dx, -max_fall_speed, kappa, gravity, facing)
        for _ in range(20):
            state = step_c2(state, ux=0, uy=0, dt=1.0 / 60.0, is_blue=True)
        assert state[3] >= -max_fall_speed - 1e-9

    def test_landing_is_fractional_not_integer(self):
        # A platform whose top is at y=100: contact must snap to top + 8.05.
        plat = PlatformInstance(plat_id=0, x_left=-100.0, x_right=100.0, y_surf=100, vx=0.0)
        x, y, dx, dy, kappa, gravity, facing = initial_state(0.0, 101.0)
        state = (x, y, dx, -50.0, 0, 180.0, facing)
        nxt = step_c2(state, ux=0, uy=0, platforms=[plat], dt=1.0 / 60.0, is_blue=True)
        assert nxt[1] == pytest.approx(100.0 + c2spec.PLATFORM_LAND_OFFSET)

    def test_swept_step_probes_every_pixel(self):
        # A thin platform-free arena must not clip a multi-pixel move.
        x, y, dx, dy, kappa, gravity, facing = initial_state(0.0, 500.0)
        state = (x, y, 0.0, dy, kappa, gravity, facing)
        # 10 px of travel at 600 px/s, dt=1/60
        t1 = step_c2((0.0, 500.0, 0.0, 0.0, 1, 0.0, 90.0), ux=0, uy=0, dt=1.0 / 60.0, is_blue=False)
        assert t1[1] == 500.0

    def test_slam_resets_to_origin_with_max_fall_speed(self):
        s = initial_state(120.0, 77.0)
        nxt = step_c2(s, ux=0, uy=0, dt=1.0 / 60.0, is_slam=True)
        assert (nxt[0], nxt[1]) == (0.0, 0.0)
        assert math.hypot(nxt[2], nxt[3]) == pytest.approx(c2spec.MAX_FALL_SPEED_DEFAULT)


# ---------------------------------------------------------------------------
# rasterizer: same-frame teleport semantics
# ---------------------------------------------------------------------------
def _teleport(x, y):
    return Command(
        frame=0,
        time_s=0.0,
        cmd_type="HeartTeleport",
        params={"x": x, "y": y},
        raw_args=[str(x), str(y)],
    )


def _cz(x1, y1, x2, y2):
    return Command(
        frame=0,
        time_s=0.0,
        cmd_type="CombatZoneResize",
        params={"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        raw_args=[str(x1), str(y1), str(x2), str(y2)],
    )


class TestSameFrameTeleport:
    """Same-frame teleports run in timeline order; the LAST one wins.

    This mirrors the real custom-attack format documented in
    ``repo_badtime/Documentation`` -- several scripts teleport twice on frame 0
    (``sans_platforms4``) or up to thirteen times (``sans_multi3``).
    """

    def _rasterize(self, cmds, soul_h=4):
        return rasterize_timeline(
            cmds,
            config=RasterizerConfig(T=2, W=1, H=1, auto_size=True),
            T=2,
            W=1,
            H=1,
        )

    def test_last_teleport_in_a_frame_wins(self):
        cmds = [_cz(113, 231, 548, 391), _teleport(320, 376), _teleport(175, 327)]
        res = self._rasterize(cmds)
        # auto_size: c2_left = 113+13 = 126, c2_floor = 391-13 = 378
        # last teleport (175, 327) -> local (49, 51)
        assert res.initial_heart_pos == (49, 51)

    def test_first_teleport_is_not_used(self):
        cmds = [_cz(113, 231, 548, 391), _teleport(320, 376), _teleport(175, 327)]
        res = self._rasterize(cmds)
        # (320, 376) would have given (194, 2); that must NOT be the anchor.
        assert res.initial_heart_pos != (194, 2)

    def test_single_teleport_unaffected(self):
        cmds = [_cz(133, 251, 508, 391), _teleport(320, 376)]
        res = self._rasterize(cmds)
        # c2_left = 146, c2_floor = 378 -> (174, 2)
        assert res.initial_heart_pos == (174, 2)
