"""Unified E2E Test Suite Runner.

Invokes tests across all 4 tiers or selected tiers:
  Tier 1: Feature Coverage (Features 1-24)
  Tier 2: Boundary & Corner Cases
  Tier 3: Cross-Feature Interactions
  Tier 4: Real-World Scenarios

Usage:
  python tests/run_e2e.py [--tier {1,2,3,4,all}] [--backend {auto,nohit,reference}] [--verbose] [--json <path>]
"""

import argparse
import json
import os
import sys
import time
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.e2e.harness import set_backend


def run_e2e(tier: str = "all", backend: str = "auto", verbose: bool = True, json_path: str = None) -> int:
    set_backend(backend)
    os.environ["NOHIT_TEST_BACKEND"] = backend

    test_modules = []
    if tier in ("1", "all"):
        test_modules.append("tests.e2e.test_tier1_features")
    if tier in ("2", "all"):
        test_modules.append("tests.e2e.test_tier2_boundaries")
    if tier in ("3", "all"):
        test_modules.append("tests.e2e.test_tier3_interactions")
    if tier in ("4", "all"):
        test_modules.append("tests.e2e.test_tier4_scenarios")
    if tier in ("runner", "all"):
        test_modules.append("tests.e2e.test_replay_runner")

    suite = unittest.TestSuite()
    loader = unittest.TestLoader()

    for mod_name in test_modules:
        mod_suite = loader.loadTestsFromName(mod_name)
        suite.addTests(mod_suite)

    total_tests = suite.countTestCases()
    print("=" * 70)
    print("  UNDERTALE SANS FIGHT DEAD-END VERIFICATION - E2E TEST RUNNER")
    print(f"  Target Tiers: {tier} | Backend: {backend} | Total Cases: {total_tests}")
    print("=" * 70)

    start_time = time.perf_counter()
    runner = unittest.TextTestRunner(verbosity=2 if verbose else 1)
    result = runner.run(suite)
    elapsed = time.perf_counter() - start_time

    passed = total_tests - len(result.failures) - len(result.errors) - len(result.skipped)
    success = result.wasSuccessful()

    print("\n" + "=" * 70)
    print("  E2E TEST RUN SUMMARY")
    print(f"  Passed:   {passed:3d} / {total_tests:3d}")
    print(f"  Failures: {len(result.failures):3d}")
    print(f"  Errors:   {len(result.errors):3d}")
    print(f"  Skipped:  {len(result.skipped):3d}")
    print(f"  Duration: {elapsed:.3f} s")
    print(f"  Status:   {'PASSED' if success else 'FAILED'}")
    print("=" * 70)

    if json_path:
        report = {
            "tier": tier,
            "backend": backend,
            "total": total_tests,
            "passed": passed,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
            "duration_s": round(elapsed, 4),
            "status": "PASSED" if success else "FAILED",
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"Report written to: {json_path}")

    return 0 if success else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Undertale Sans Fight E2E Tests")
    parser.add_argument("--tier", choices=["1", "2", "3", "4", "runner", "all"], default="all", help="Target test tier")
    parser.add_argument("--backend", choices=["auto", "nohit", "reference"], default="auto", help="Execution backend")
    parser.add_argument("--verbose", "-v", action="store_true", default=True, help="Verbose test execution")
    parser.add_argument("--json", type=str, default=None, help="Path to write JSON summary")
    args = parser.parse_args()

    sys.exit(run_e2e(tier=args.tier, backend=args.backend, verbose=args.verbose, json_path=args.json))
