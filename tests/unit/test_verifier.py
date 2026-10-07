"""
tests/unit/test_verifier.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for nohit.verifier.replayer:
- Verifies forward simulation consistency
- Verifies collision detection on hazard contact
- Verifies length and action alphabet enforcement
- Verifies integration with real solver outputs
"""

import unittest
import numpy as np

from nohit.common.constants import DEFAULT_W, DEFAULT_H, DEFAULT_T, ACTIONS
from nohit.common.types import BakeResult, VerificationResult
from nohit.engine.solver import solve_lattice_dp
from nohit.verifier.replayer import replay_and_verify


class TestVerifier(unittest.TestCase):
    def test_empty_hazard_feasible_solve_and_replay(self):
        T, H, W = 30, DEFAULT_H, DEFAULT_W
        B = np.zeros((T, H, W), dtype=bool)
        bake = BakeResult(
            B_hazard=B,
            platform_table=[[] for _ in range(T)],
            initial_state=(50, 0),
            metadata={},
        )
        sol = solve_lattice_dp(bake)
        self.assertFalse(sol.is_deadlock)
        self.assertIsNotNone(sol.action_sequence)

        res = replay_and_verify(bake, sol.action_sequence)
        self.assertTrue(res.passed)
        self.assertEqual(len(res.collision_frames), 0)
        self.assertEqual(len(res.kinematic_errors), 0)
        self.assertEqual(len(res.simulated_trajectory), T)
        self.assertEqual(res.simulated_trajectory, sol.trajectory)

    def test_replayer_detects_deliberate_collision(self):
        T, H, W = 20, DEFAULT_H, DEFAULT_W
        B = np.zeros((T, H, W), dtype=bool)
        # Place hazard directly where moving right will hit
        B[5, 0, 50 + 5 * 3] = True
        bake = BakeResult(
            B_hazard=B,
            platform_table=[[] for _ in range(T)],
            initial_state=(50, 0),
            metadata={},
        )
        # Walk right continuously: (1, 0)
        actions = [(1, 0)] * (T - 1)
        res = replay_and_verify(bake, actions)
        self.assertFalse(res.passed)
        self.assertIn(5, res.collision_frames)

    def test_replayer_rejects_invalid_action_length(self):
        T, H, W = 20, DEFAULT_H, DEFAULT_W
        B = np.zeros((T, H, W), dtype=bool)
        bake = BakeResult(
            B_hazard=B,
            platform_table=[[] for _ in range(T)],
            initial_state=(50, 0),
            metadata={},
        )
        res = replay_and_verify(bake, [(0, 0)] * 5)
        self.assertFalse(res.passed)
        self.assertTrue(any("length" in err for err in res.kinematic_errors))


if __name__ == "__main__":
    unittest.main()
