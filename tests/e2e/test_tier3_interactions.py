"""Tier 3: Cross-Feature Interactions E2E Tests (Pairwise Combinations).

Requirements:
- Pairwise combination testing of interdependent game mechanics:
  1. Jumping + Platform convection (airborne vs grounded friction cutoff)
  2. BoneStab warning + Jump cut (variable jump height vs timed hazards)
  3. SansSlam + Platform landing (phase space reset vs surface adsorption)
  4. Platform convection + Wall clamping (sliding against arena boundaries)
  5. Inelastic landing + Immediate jump re-trigger (landing reset & new jump)
  6. One-way platform upward pass-through (jumpthrough mechanics)
  7. Platform running off edge (surface detachment and gravity fall)
  8. Staggered BoneV gap crossing (multi-bone navigation and jump clearance)
"""

import unittest
import numpy as np

from tests.e2e.harness import (
    ACTIONS,
    DEFAULT_H,
    DEFAULT_W,
    G_ASCEND,
    G_DESCEND,
    SOUL_H,
    SOUL_W,
    TAU_MAX,
    V_JUMP_INIT,
    V_MIN,
    V_MAX,
    V_WALK,
    BakeResult,
    PlatformInstance,
    SolveResult,
    VerificationResult,
    get_baker,
    get_engine,
    get_verifier,
    step_dynamics,
)


class TestTier3CrossFeatureInteractions(unittest.TestCase):
    """Pairwise cross-feature interactions validating complex physical phenomena."""

    def setUp(self):
        self.engine = get_engine()
        self.verifier = get_verifier()

    def test_i1_jumping_and_platform_convection(self):
        """Interaction 1: Platform convection applies when kappa=1, ceases when airborne kappa=0."""
        plat = PlatformInstance(plat_id=1, x_min=50.0, x_max=150.0, y_top=30.0, vx=4.0)

        # 1. Standing on moving platform at y=30, x=80
        s0 = (80, 30, 0, 1, 0)
        # Walk right while on platform: dx = V_WALK (3) + plat.vx (4) = 7
        s1 = step_dynamics(s0, (1, 0), platforms=[plat])
        self.assertEqual(s1[0], 87)
        self.assertEqual(s1[1], 30)
        self.assertEqual(s1[3], 1)

        # 2. Jump off platform: uy = 1 -> airborne
        s2 = step_dynamics(s1, (1, 1), platforms=[plat])
        self.assertEqual(s2[3], 0)  # airborne
        self.assertEqual(s2[2], V_JUMP_INIT)  # 8

        # 3. Next airborne frame: NO platform convection! Horizontal movement is ONLY V_WALK (3)
        s3 = step_dynamics(s2, (1, 1), platforms=[plat])
        self.assertEqual(s3[3], 0)  # still airborne
        # Movement should be purely s2.x + V_WALK (no platform vx added!)
        self.assertEqual(s3[0], s2[0] + V_WALK)

    def test_i2_bonestab_warning_and_jump_cut(self):
        """Interaction 2: Releasing jump early (jump cut) clears obstacle without hitting ceiling."""
        # Full jump holding uy=1 reaches high apex (~32 pixels)
        s = (96, 0, 0, 1, 0)
        heights_full = []
        for _ in range(8):
            s = step_dynamics(s, (0, 1))
            heights_full.append(s[1])
        apex_full = max(heights_full)

        # Low jump: release jump at frame 2 (jump cut)
        s_cut = (96, 0, 0, 1, 0)
        heights_cut = []
        for step in range(8):
            act = (0, 1) if step < 2 else (0, 0)
            s_cut = step_dynamics(s_cut, act)
            heights_cut.append(s_cut[1])
        apex_cut = max(heights_cut)

        # Jump cut apex must be strictly lower than full jump apex
        self.assertLess(apex_cut, apex_full)
        self.assertGreater(apex_cut, 10, "Cut jump still clears moderate obstacles")

    def test_i3_sans_slam_and_platform_landing(self):
        """Interaction 3: SansSlam operator resets state to floor regardless of prior vertical state."""
        plat = PlatformInstance(plat_id=1, x_min=50.0, x_max=150.0, y_top=60.0, vx=0.0)

        # Player at height y=100 above platform
        state = (96, 100, 5, 0, 3)
        slam_res = step_dynamics(state, (0, 0), platforms=[plat], is_slam=True)

        # R_slam strictly resets to floor y=0, vy=0, kappa=1, tau=0
        self.assertEqual(slam_res, (96, 0, 0, 1, 0))

    def test_i4_platform_convection_and_wall_clamping(self):
        """Interaction 4: Fast moving platform pushing player into right wall clamps safely."""
        max_x = DEFAULT_W - SOUL_W  # 192
        # Fast platform moving right at 8 px/frame near right wall
        plat = PlatformInstance(plat_id=1, x_min=150.0, x_max=220.0, y_top=0.0, vx=8.0)
        state = (190, 0, 0, 1, 0)

        # Walk right on platform: 190 + 3 + 8 = 201 -> clamped to 192
        s_next = step_dynamics(state, (1, 0), platforms=[plat])
        self.assertEqual(s_next[0], max_x)
        self.assertEqual(s_next[1], 0)

    def test_i5_inelastic_landing_and_immediate_jump(self):
        """Interaction 5: Landing resets kappa=1, tau=0; next frame can immediately jump again."""
        # Falling toward ground
        falling = (96, 6, -8, 0, TAU_MAX)
        landed = step_dynamics(falling, (0, 0))
        self.assertEqual(landed[1], 0)
        self.assertEqual(landed[3], 1)  # kappa = 1
        self.assertEqual(landed[4], 0)  # tau = 0

        # Immediate jump on next frame
        re_jump = step_dynamics(landed, (0, 1))
        self.assertEqual(re_jump[2], V_JUMP_INIT)  # fresh jump impulse = 8
        self.assertEqual(re_jump[3], 0)            # airborne
        self.assertEqual(re_jump[4], 1)            # tau = 1

    def test_i6_one_way_platform_upward_pass_through(self):
        """Interaction 6: One-way jumpthrough platform does not obstruct upward jump."""
        plat = PlatformInstance(plat_id=1, x_min=80.0, x_max=120.0, y_top=15.0, vx=0.0)

        # Starting below platform at y=10, moving upward with vy=8
        s_below = (96, 10, 8, 0, 1)
        s_above = step_dynamics(s_below, (0, 1), platforms=[plat])

        # Jump passes straight through: y = 10 + (8 - 1) = 17 > plat.y_top (15)
        self.assertGreater(s_above[1], plat.y_top)
        self.assertEqual(s_above[3], 0, "Must not adsorb when passing upward")

        # Now when falling down across y=15:
        s_falling = (96, 18, -5, 0, TAU_MAX)
        s_landed = step_dynamics(s_falling, (0, 0), platforms=[plat])
        self.assertEqual(s_landed[1], plat.y_top, "Must adsorb when falling onto surface")
        self.assertEqual(s_landed[3], 1, "Must be grounded on platform")

    def test_i7_platform_running_off_edge(self):
        """Interaction 7: Walking off the edge of a platform triggers immediate gravity fall."""
        plat = PlatformInstance(plat_id=1, x_min=50.0, x_max=100.0, y_top=40.0, vx=0.0)

        # Positioned right at right edge: x = 98 (soul width is 8, so x+w = 106 > 100)
        # Soul steps to x=101, completely past plat.x_max (100)
        s_on_edge = (98, 40, 0, 1, 0)
        s_off = step_dynamics(s_on_edge, (1, 0), platforms=[plat])

        # Soul walked off platform, no support -> falling
        self.assertGreater(s_off[0], 100)
        self.assertEqual(s_off[3], 0, "Must lose ground support")
        self.assertLess(s_off[2], 0, "Vertical velocity must start falling downward")

    def test_i8_staggered_bonev_gap_crossing(self):
        """Interaction 8: Moving bone obstacle with safe vertical gap solved and verified."""
        T = 20
        B_hazard = np.zeros((T, 160, 200), dtype=bool)

        # Create moving vertical bones with a safe passage gap between y=20 and y=50
        for t in range(5, 15):
            bone_x = 180 - t * 8
            if 0 <= bone_x < 200:
                # Lower bone: y in [0, 20]
                B_hazard[t, :20, max(0, bone_x - 5):min(200, bone_x + 5)] = True
                # Upper bone: y in [50, 160]
                B_hazard[t, 50:, max(0, bone_x - 5):min(200, bone_x + 5)] = True

        bake_res = BakeResult(
            B_hazard=B_hazard,
            platform_table=[[] for _ in range(T)],
            initial_state=(50, 0),
        )

        sol = self.engine(bake_res)
        self.assertFalse(sol.is_deadlock, "A safe jump through the gap should be found")
        self.assertIsNotNone(sol.action_sequence)

        # Verify through independent replayer
        v_res = self.verifier(bake_res, sol.action_sequence)
        self.assertTrue(v_res.passed, f"Collision detected at frames: {v_res.collision_frames}")
        self.assertEqual(len(v_res.collision_frames), 0)


if __name__ == "__main__":
    unittest.main()
