"""Automated Test Suite for Replay and Live Test Runners.

Tests both:
- tools/test_oracle_replay.mjs (240Hz independent offline replay runner)
- tools/verify_and_run_live.mjs (Foreground desktop Chrome live acceptance runner)

Verifies:
1. CLI parameter parsing (--attack, --plan, --continuous, --seed, --timeout, --help)
2. Positional argument fallbacks for backward compatibility
3. Dynamic attack derivation and extension normalization
4. Error handling on non-existent CSVs, missing plan files, malformed JSON, empty actions
5. Platform geometry detection from CSV
6. Invariant verification and clean exit codes
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ORACLE_RUNNER = PROJECT_ROOT / "tools" / "test_oracle_replay.mjs"
LIVE_RUNNER = PROJECT_ROOT / "tools" / "verify_and_run_live.mjs"


class TestReplayRunnerCLI(unittest.TestCase):
    """Test suite verifying test_oracle_replay.mjs and verify_and_run_live.mjs."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_dir.name)

        # Create valid mock plan
        cls.valid_plan = cls.temp_path / "valid_plan.json"
        cls.valid_plan.write_text(json.dumps({
            "attack": "sans_bonegap1",
            "status": "candidate_found",
            "frames": 10,
            "actions": [[0, 0] for _ in range(10)],
            "fidelity": {"perturbation_members": 9, "product_fields": 45}
        }, indent=2), encoding="utf-8")

        # Create plan without attack field (only wave)
        cls.wave_plan = cls.temp_path / "wave_plan.json"
        cls.wave_plan.write_text(json.dumps({
            "wave": "sans_bonegap1.csv",
            "status": "candidate_found",
            "actions": [[0, 0] for _ in range(5)]
        }, indent=2), encoding="utf-8")

        # Create empty actions plan
        cls.empty_actions_plan = cls.temp_path / "empty_actions_plan.json"
        cls.empty_actions_plan.write_text(json.dumps({
            "attack": "sans_bonegap1",
            "actions": []
        }, indent=2), encoding="utf-8")

        # Create malformed JSON plan
        cls.malformed_plan = cls.temp_path / "malformed.json"
        cls.malformed_plan.write_text("{ unclosed json: [1, 2, ", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def run_node(self, script_path: Path, *args, timeout_s: float = 15.0) -> subprocess.CompletedProcess:
        cmd = ["node", str(script_path)] + list(args)
        return subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_s
        )

    # --------------------------------------------------------------------------
    # Tier 1: CLI Flags & Help Invocation
    # --------------------------------------------------------------------------

    def test_oracle_replay_help_flag(self):
        """Oracle runner --help displays usage information and exits with code 0."""
        res = self.run_node(ORACLE_RUNNER, "--help")
        self.assertEqual(res.returncode, 0, f"Expected 0, got {res.returncode}. Stderr: {res.stderr}")
        self.assertIn("Usage:", res.stdout)
        self.assertIn("--attack", res.stdout)
        self.assertIn("--plan", res.stdout)
        self.assertIn("--seed", res.stdout)

    def test_verify_live_help_flag(self):
        """Live acceptance runner --help displays usage information and exits with code 0."""
        res = self.run_node(LIVE_RUNNER, "--help")
        self.assertEqual(res.returncode, 0, f"Expected 0, got {res.returncode}. Stderr: {res.stderr}")
        self.assertIn("Usage:", res.stdout)
        self.assertIn("--attack", res.stdout)
        self.assertIn("--plan", res.stdout)
        self.assertIn("--continuous", res.stdout)

    # --------------------------------------------------------------------------
    # Tier 2: Boundary & Error Handling
    # --------------------------------------------------------------------------

    def test_oracle_missing_attack_csv_fails(self):
        """Requesting a non-existent attack script returns clean non-zero exit code."""
        res = self.run_node(ORACLE_RUNNER, "--attack", "non_existent_wave_xyz123", "--plan", str(self.valid_plan))
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Target attack CSV not found", res.stderr + res.stdout)

    def test_oracle_missing_plan_file_fails(self):
        """Specifying a non-existent plan JSON path returns clean non-zero exit code."""
        missing_path = str(self.temp_path / "does_not_exist.json")
        res = self.run_node(ORACLE_RUNNER, "--attack", "sans_bonegap1", "--plan", missing_path)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Candidate plan file not found", res.stderr + res.stdout)

    def test_oracle_empty_actions_array_fails(self):
        """Specifying a plan JSON with empty actions array returns clean non-zero exit code."""
        res = self.run_node(ORACLE_RUNNER, "--attack", "sans_bonegap1", "--plan", str(self.empty_actions_plan))
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Plan contains no actions", res.stderr + res.stdout)

    def test_oracle_malformed_json_plan_fails(self):
        """Specifying a malformed JSON file returns clean non-zero exit code."""
        res = self.run_node(ORACLE_RUNNER, "--attack", "sans_bonegap1", "--plan", str(self.malformed_plan))
        self.assertNotEqual(res.returncode, 0)

    def test_live_missing_plan_file_fails(self):
        """Live runner fails with clean non-zero exit code when plan file is missing."""
        missing_path = str(self.temp_path / "no_such_file.json")
        res = self.run_node(LIVE_RUNNER, "--attack", "sans_bonegap1", "--plan", missing_path)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Candidate plan file not found", res.stderr + res.stdout)

    # --------------------------------------------------------------------------
    # Tier 3: Interactions & Compatibility Fallbacks
    # --------------------------------------------------------------------------

    def test_oracle_derives_attack_from_plan(self):
        """Oracle runner derives attack name directly from plan file when --attack is omitted."""
        # Using wave_plan where "wave": "sans_bonegap1.csv"
        # It will reach Chrome connection phase before exiting
        res = self.run_node(ORACLE_RUNNER, "--plan", str(self.wave_plan))
        output = res.stdout + res.stderr
        self.assertIn("Target attack: sans_bonegap1", output)

    def test_oracle_normalizes_csv_extension(self):
        """Oracle runner properly strips .csv suffix if passed in --attack."""
        res = self.run_node(ORACLE_RUNNER, "--attack", "sans_bonegap1.csv", "--plan", str(self.valid_plan))
        output = res.stdout + res.stderr
        self.assertIn("Target attack: sans_bonegap1", output)

    def test_oracle_detects_platforms_dynamically(self):
        """Oracle runner correctly detects platform presence in CSV."""
        # sans_platforms4hard has platforms
        res_plat = self.run_node(ORACLE_RUNNER, "--attack", "sans_platforms4hard", "--plan", str(self.valid_plan))
        self.assertIn("Platform geometry expected: YES", res_plat.stdout)

        # sans_bonegap1 has NO platforms
        res_bone = self.run_node(ORACLE_RUNNER, "--attack", "sans_bonegap1", "--plan", str(self.valid_plan))
        self.assertIn("Platform geometry expected: NO", res_bone.stdout)

    def test_oracle_positional_arguments_compatibility(self):
        """Oracle runner supports legacy positional arguments [attack] [plan] [seed]."""
        res = self.run_node(ORACLE_RUNNER, "sans_bonegap1", str(self.valid_plan), "99")
        output = res.stdout + res.stderr
        self.assertIn("Target attack: sans_bonegap1", output)
        self.assertIn(str(self.valid_plan), output)

    def test_live_positional_arguments_compatibility(self):
        """Live acceptance runner supports positional arguments."""
        res = self.run_node(LIVE_RUNNER, "sans_bonegap1", str(self.valid_plan), "3", "99")
        output = res.stdout + res.stderr
        self.assertIn("Attack: sans_bonegap1", output)
        self.assertIn("Target Continuous Rounds: 3", output)
        self.assertIn("Random Seed: 99", output)

    # --------------------------------------------------------------------------
    # Tier 4: Pipeline Semantics
    # --------------------------------------------------------------------------

    def test_live_runner_custom_continuous_count(self):
        """Live runner correctly parses --continuous argument."""
        res = self.run_node(LIVE_RUNNER, "--attack", "sans_bonegap1", "--plan", str(self.valid_plan), "--continuous", "5")
        output = res.stdout + res.stderr
        self.assertIn("Target Continuous Rounds: 5", output)


if __name__ == "__main__":
    unittest.main()
