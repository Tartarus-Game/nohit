"""
tests/unit/test_common.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Unit test suite covering nohit.common: constants, data types, bit-packing, and coordinate bijection.
"""

import math
import unittest
import numpy as np

from nohit.common.constants import (
    DEFAULT_W,
    ARENA_WIDTH,
    DEFAULT_H,
    ARENA_HEIGHT,
    SOUL_W,
    SOUL_WIDTH,
    SOUL_H,
    SOUL_HEIGHT,
    SOUL_MAX_X,
    SOUL_MAX_Y,
    NUM_X_CELLS,
    NUM_Y_CELLS,
    FPS,
    V_MIN,
    V_MAX,
    NUM_VY_CELLS,
    TAU_MAX,
    NUM_TAU_CELLS,
    NUM_KAPPA_CELLS,
    TOTAL_STATE_CAPACITY,
    SLAM_COLLAPSE_BOUND,
    ACTIONS,
)
from nohit.common.types import (
    State,
    Action,
    ALL_ACTIONS,
    PlatformInstance,
    Command,
    BakeResult,
    SolveStats,
    SolveResult,
    VerificationResult,
)
from nohit.common.coords import (
    CombatZone,
    c2_to_cspace_point,
    cspace_to_c2_point,
    c2_to_cspace_box,
    cspace_to_c2_box,
    c2_to_cspace_velocity,
    cspace_to_c2_velocity,
    c2_to_grid,
    grid_to_c2,
)


class TestConstants(unittest.TestCase):
    """Verifies physics constants, array cardinalities, and theoretical bounds."""

    def test_spatial_grid_cardinalities(self):
        self.assertEqual(ARENA_WIDTH, 200)
        self.assertEqual(ARENA_HEIGHT, 160)
        self.assertEqual(SOUL_WIDTH, 8)
        self.assertEqual(SOUL_HEIGHT, 8)
        self.assertEqual(SOUL_MAX_X, 192)
        self.assertEqual(SOUL_MAX_Y, 152)
        self.assertEqual(NUM_X_CELLS, 193)
        self.assertEqual(NUM_Y_CELLS, 153)
        self.assertEqual(NUM_X_CELLS, ARENA_WIDTH - SOUL_WIDTH + 1)
        self.assertEqual(NUM_Y_CELLS, ARENA_HEIGHT - SOUL_HEIGHT + 1)

    def test_velocity_and_timer_cardinalities(self):
        self.assertEqual(V_MIN, -12)
        self.assertEqual(V_MAX, 8)
        self.assertEqual(NUM_VY_CELLS, 21)
        self.assertEqual(NUM_VY_CELLS, V_MAX - V_MIN + 1)
        self.assertEqual(TAU_MAX, 15)
        self.assertEqual(NUM_TAU_CELLS, 16)
        self.assertEqual(NUM_TAU_CELLS, TAU_MAX + 1)
        self.assertEqual(NUM_KAPPA_CELLS, 2)

    def test_total_phase_space_capacity(self):
        expected_cap = 193 * 153 * 21 * 2 * 16
        self.assertEqual(TOTAL_STATE_CAPACITY, expected_cap)
        self.assertEqual(TOTAL_STATE_CAPACITY, 19843488)
        self.assertEqual(SLAM_COLLAPSE_BOUND, 193)

    def test_bit_packing_budget(self):
        # x: 8 bits, y: 8 bits, vy: 5 bits, kappa: 1 bit, tau: 4 bits -> 26 bits <= 32 bits
        bits_needed = 8 + 8 + 5 + 1 + 4
        self.assertLessEqual(bits_needed, 32)
        self.assertEqual(bits_needed, 26)


class TestTypes(unittest.TestCase):
    """Verifies micro-state packing, discrete actions, and platform entities."""

    def test_state_pack_unpack_roundtrip(self):
        test_states = [
            State(0, 0, -12, 0, 0),
            State(192, 152, 8, 1, 15),
            State(96, 76, 0, 1, 7),
            State(100, 50, -5, 0, 10),
            State(1, 1, -1, 1, 1),
            State(190, 150, 5, 0, 14),
        ]
        for s in test_states:
            packed = s.pack()
            self.assertIsInstance(packed, int)
            self.assertGreaterEqual(packed, 0)
            self.assertLess(packed, 1 << 32)
            recovered = State.unpack(packed)
            self.assertEqual(recovered, s)
            self.assertEqual(recovered.to_tuple(), s.to_tuple())

    def test_state_tuple_and_indexing(self):
        s = State(10, 20, 3, 1, 5)
        self.assertEqual(s.to_tuple(), (10, 20, 3, 1, 5))
        self.assertEqual(s[0], 10)
        self.assertEqual(s[1], 20)
        self.assertEqual(s[2], 3)
        self.assertEqual(s[3], 1)
        self.assertEqual(s[4], 5)
        x, y, vy, kappa, tau = s
        self.assertEqual((x, y, vy, kappa, tau), (10, 20, 3, 1, 5))
        with self.assertRaises(IndexError):
            _ = s[5]

    def test_action_discrete_mapping(self):
        self.assertEqual(len(ALL_ACTIONS), 6)
        for i, a in enumerate(ALL_ACTIONS):
            self.assertEqual(a.action_index, i)
            recovered = Action.from_index(i)
            self.assertEqual(recovered, a)
            ux, uy = a
            self.assertEqual((ux, uy), a.to_tuple())

        with self.assertRaises(ValueError):
            Action.from_index(-1)
        with self.assertRaises(ValueError):
            Action.from_index(6)

    def test_platform_instance_properties_and_support(self):
        plat = PlatformInstance(plat_id=1, x_left=20.0, x_right=80.0, y_surf=40, vx=2.5)
        self.assertEqual(plat.plat_id, 1)
        self.assertEqual(plat.x_left, 20.0)
        self.assertEqual(plat.x_right, 80.0)
        self.assertEqual(plat.y_surf, 40)
        self.assertEqual(plat.vx, 2.5)

        # Compatibility properties for E2E harness
        self.assertEqual(plat.x_min, 20.0)
        self.assertEqual(plat.x_max, 80.0)
        self.assertEqual(plat.y_top, 40.0)

        # Keyword compatibility
        plat2 = PlatformInstance(plat_id=2, x_min=30.0, x_max=90.0, y_top=50.0, vx=-1.0)
        self.assertEqual(plat2.x_left, 30.0)
        self.assertEqual(plat2.x_right, 90.0)
        self.assertEqual(plat2.y_surf, 50)

        # Support overlaps with 8px soul
        # Soul interval [x, x+8] overlaps [20, 80] if x+8 > 20 and x < 80
        self.assertTrue(plat.is_supporting(soul_x=15))   # [15, 23] overlaps [20, 80]
        self.assertTrue(plat.is_supporting(soul_x=50))   # [50, 58] overlaps [20, 80]
        self.assertTrue(plat.is_supporting(soul_x=75))   # [75, 83] overlaps [20, 80]
        self.assertFalse(plat.is_supporting(soul_x=10))  # [10, 18] completely left of 20
        self.assertFalse(plat.is_supporting(soul_x=80))  # [80, 88] completely right of 80

    def test_bake_result_methods(self):
        tensor = np.zeros((10, 160, 200), dtype=bool)
        tensor[0, 50, 50] = True
        res = BakeResult(
            B_hazard=tensor,
            platform_table=[[] for _ in range(10)],
            initial_state=(96, 0),
        )
        self.assertEqual(res.T, 10)
        self.assertEqual(res.H, 160)
        self.assertEqual(res.W, 200)
        self.assertEqual(res.initial_state, (96, 0))
        packed = res.packed_tensor()
        self.assertEqual(packed.shape, (10, 160, 25))
        self.assertEqual(packed.dtype, np.uint8)


class TestCoords(unittest.TestCase):
    """Verifies coordinate transforms and bijective mappings."""

    def setUp(self):
        # Real sans combat zone
        self.zone = CombatZone(x1=133.0, y1=251.0, x2=508.0, y2=391.0, border_thickness=5.0)

    def test_combat_zone_inners(self):
        self.assertEqual(self.zone.inner_left, 138.0)
        self.assertEqual(self.zone.inner_right, 503.0)
        self.assertEqual(self.zone.inner_top, 256.0)
        self.assertEqual(self.zone.inner_bottom, 386.0)
        self.assertEqual(self.zone.inner_width, 365.0)
        self.assertEqual(self.zone.inner_height, 130.0)

    def test_point_bijection(self):
        for xc2 in [138.0, 200.0, 320.0, 450.0, 503.0]:
            for yc2 in [256.0, 300.0, 350.0, 386.0]:
                x, y = c2_to_cspace_point(xc2, yc2, self.zone)
                rec_xc2, rec_yc2 = cspace_to_c2_point(x, y, self.zone)
                self.assertAlmostEqual(xc2, rec_xc2, places=6)
                self.assertAlmostEqual(yc2, rec_yc2, places=6)

    def test_golden_wave_anchor(self):
        # Canvas floor (Y=386) must map to local ground y=0
        x, y = c2_to_cspace_point(138.0, 386.0, self.zone)
        self.assertEqual((x, y), (0.0, 0.0))

        # Canvas ceiling (Y=256) must map to local height y=130
        x, y = c2_to_cspace_point(138.0, 256.0, self.zone)
        self.assertEqual((x, y), (0.0, 130.0))

    def test_box_bijection_and_gap(self):
        # Lower bone: X=128, Y=366, W=10, H=20
        # C-space:
        # xmin = 128 - 138 = -10, xmax = 0
        # ymax = 386 - 366 = 20, ymin = 20 - 20 = 0 -> y in [0, 20]
        xmin, ymin, xmax, ymax = c2_to_cspace_box(128.0, 366.0, 10.0, 20.0, self.zone)
        self.assertEqual(ymin, 0.0)
        self.assertEqual(ymax, 20.0)
        self.assertEqual(xmin, -10.0)
        self.assertEqual(xmax, 0.0)

        # Upper bone: X=128, Y=257, W=10, H=95
        # ymax = 386 - 257 = 129, ymin = 129 - 95 = 34 -> y in [34, 129]
        uxmin, uymin, uxmax, uymax = c2_to_cspace_box(128.0, 257.0, 10.0, 95.0, self.zone)
        self.assertEqual(uymin, 34.0)
        self.assertEqual(uymax, 129.0)

        # Exact safe gap: 34 - 20 = 14 pixels
        gap = uymin - ymax
        self.assertEqual(gap, 14.0)

        # Box roundtrip
        c2_box = cspace_to_c2_box(xmin, ymin, xmax, ymax, self.zone)
        self.assertEqual(c2_box, (128.0, 366.0, 10.0, 20.0))

    def test_velocity_transform(self):
        vx_c2, vy_c2 = 10.0, 15.0
        vx, vy = c2_to_cspace_velocity(vx_c2, vy_c2)
        self.assertEqual(vx, 10.0)
        self.assertEqual(vy, -15.0)
        rec_vx_c2, rec_vy_c2 = cspace_to_c2_velocity(vx, vy)
        self.assertEqual((rec_vx_c2, rec_vy_c2), (vx_c2, vy_c2))

    def test_grid_mappings(self):
        cx, cy = 133.0 + 100.0, 251.0 + 80.0
        gx, gy = c2_to_grid(cx, cy, 133.0, 251.0, 508.0, 391.0, W=200, H=160)
        self.assertGreaterEqual(gx, 0)
        self.assertLess(gx, 200)
        self.assertGreaterEqual(gy, 0)
        self.assertLess(gy, 160)


if __name__ == "__main__":
    unittest.main()
