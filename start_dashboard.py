#!/usr/bin/env python3
"""
Root entry point: start_dashboard.py
Launches the Web/HTML5 Interactive Inspection & Trajectory Replay Dashboard.
"""

import os
import sys
import time
from pathlib import Path

boot_started = time.perf_counter()

# Sleeping workers leave the serial deduplication/selection phases CPU time.
# Set this before any Numba/OpenMP initialization; preserve explicit operator settings.
os.environ.setdefault('OMP_WAIT_POLICY', 'PASSIVE')

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from nohit.native_runtime import select_built_runtime
select_built_runtime()

from nohit.dashboard.server import start_server

if __name__ == "__main__":
    from nohit.engine.canonical_solver import warm_kernel
    from nohit.engine.csv_warmup import warm_csv_kernels
    print(f"  Adaptive DAG code ready: {warm_kernel():.1f} ms (startup only; no route cache)", flush=True)
    csv_warmup = warm_csv_kernels()
    print(f"  CSV kernel code ready: {csv_warmup['wall_seconds']*1000:.1f} ms (synthetic inputs; no route cache)", flush=True)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = start_server(port=port)
    server.startup_ms = (time.perf_counter() - boot_started) * 1000
    print(f"  Cold startup to ready: {server.startup_ms:.1f} ms", flush=True)
    print("=" * 70)
    print(f"  SANS BULLET HELL LATTICE VERIFICATION DASHBOARD")
    print(f"  Open your browser at: http://127.0.0.1:{port}")
    print("=" * 70)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n>> Server stopped.")
        server.server_close()
