#!/usr/bin/env python3
"""
Root entry point: run_benchmark.py
Executes the full automated benchmark and verification suite.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from nohit.benchmark import run_benchmark

if __name__ == "__main__":
    results = run_benchmark()
    # Check that all verified flags are True
    if all(r.verified for r in results):
        print(">> ALL BENCHMARKS & OBJECTIVE VERIFICATIONS PASSED SUCCESSFULLY.")
        sys.exit(0)
    else:
        print(">> SOME VERIFICATIONS FAILED.")
        sys.exit(1)
