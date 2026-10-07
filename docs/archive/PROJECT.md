# Project: Canonical 23 Rounds Full-Coverage Unified FRS-DP Solver & Real HELL Closed-Loop Verification

> 2026-10-06 审计更正：以下是历史规划与声明，不是已完成证明。原版兼容、模型范围及测试层级发现实质缺口；当前结论见 [solver-closure-audit-20261006.md](docs/solver-closure-audit-20261006.md)。全 23 关、完整物理和全局最优均尚未验收完成。

## Continuation Status — 2026-10-05 Night
Survey phase complete. Authentic jcw87/c2-sans-fight (gh-pages) substrate confirmed with 108 authentic assets and bit-for-bit identical SHA-256 hashes for all 24 CSV files.
The unified single Complete Topological DAG-DP (FRS-DP) architecture is selected as the sole solving engine. Phase space explosion is prevented by factoring out environment states into `Schedule[t]` while preserving 45-field float64 product dynamics across 9 perturbation members.
E2E Testing Track and 6 Implementation Milestones are decomposed and ready for dispatch.

## Architecture
- `c2-sans-fight/`: Authentic upstream jcw87/c2-sans-fight (108 assets, 23 canonical `sans_*.csv` attacks, `sans_spare.csv`, `sans_realhell_extreme.csv`).
- `nohit/engine/compact_wave.py`: Universal Wave Compiler parsing CSV attack commands into arena bounds, 4-direction gravity schedules, platform convection schedules, and baking dual-plane C-space hazard bitmasks (`mask_white` for unconditional lethality, `mask_blue` for motion-dependent lethality).
- `nohit/engine/compact_platform.py`: Universal 240Hz microstep physical dynamics stepper supporting 4-direction gravity Blue Heart, 2D omnidirectional Red Heart, SansSlam phase-space boundary collapse, and multi-platform convective landing.
- `nohit/engine/compact_lattice.py`: Single unified Complete Topological DAG-DP (FRS-DP) Bellman folding engine with double-buffered static state queues, flat 1D epoch tables, clearance-maximizing and key-chatter-minimizing Bellman cost, and O(T) linear trace reconstruction.
- `nohit/engine/compact_solver.py`: Universal solver entry point with decoupled microsecond timing instrumentation (`csv_compile`, `cspace_bake`, `hot_search`, `reconstruction`, `wall_clock`).
- `c2-sans-fight/engine_oracle.js`: Authentic Construct 2 240Hz independent offline replay engine (`O.replay`).
- `tools/test_oracle_replay.mjs`: Parameterized 240Hz independent offline replay runner verifying HP 92 / KR 0 / hits 0 across arbitrary attack rounds.
- `c2-sans-fight/tas_runner.js` & `live_acceptance.js`: In-browser TAS driver and acceptance interceptor verifying 3 consecutive rounds of EndAttack with 0 hits and rendering the live HUD badge.
- `tools/verify_and_run_live.mjs`: Parameterized foreground desktop Chrome runner for continuous 3-round live acceptance on port 8103.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F1 | Authentic Substrate & Attack Alignment | Align with upstream jcw87 (108 assets, 23 canonical sans_*.csv) | M1 | ORIGINAL_REQUEST §R1, Survey Miner 1 |
| F2 | Universal Wave Compiler & Geometry Parser | Parse CSV commands (CombatZoneResize, BoneV, BoneStab, Platform, SansSlam, GasterBlaster) into continuous geometry | M1 | Survey Miner 1, Survey Explorer 2 |
| F3 | Dual-Plane C-Space Hazard Bitmask Baker | Pre-bake mask_white (unconditional) and mask_blue (motion-dependent) 64-bit integer bitmasks via Minkowski sum | M1 | Survey Explorer 2 |
| F4 | Universal 240Hz Dynamics Stepper | Support 4-way gravity blue heart, 2D omnidirectional red heart, SansSlam wall collapse, and multi-platform convection | M2 | Survey Explorer 2 |
| F5 | Complete Topological DAG-DP (FRS-DP) Engine | Single unified DAG-DP with double-buffered static queues, 45-field product dynamics, and Bellman folding | M2 | User Directive, Survey Explorer 2 |
| F6 | Decoupled Timing & Performance Profiling | Decouple compilation, C-space baking, hot search, and trace reconstruction (< 1s search wall clock) | M2 | ORIGINAL_REQUEST §R1 |
| F7 | Parameterized 240Hz Independent Replay Engine | Parameterize test_oracle_replay.mjs to verify arbitrary attacks with EngineOracle.replay (0 hits, HP 92, KR 0) | E2E Track | ORIGINAL_REQUEST §R3, Survey Explorer 3 |
| F8 | Parameterized Foreground Live Acceptance Runner | Parameterize verify_and_run_live.mjs for visible desktop Chrome 3-round EndAttack acceptance on port 8103 | E2E Track | ORIGINAL_REQUEST §R4, Survey Explorer 3 |
| F9 | Tier 1 Canonical Rounds Verification (6 waves) | Solve and verify sans_bonegap1/fast/2, sans_bluebone, sans_boneslideh/v offline and in live browser | M3 | ORIGINAL_REQUEST §R2, Miner 1 |
| F10 | Tier 2 Canonical Rounds Verification (8 waves) | Solve and verify sans_platforms1-4/hard, sans_bonestab1-3 offline and in live browser | M4 | ORIGINAL_REQUEST §R2, Miner 1 |
| F11 | Tier 3 Canonical Rounds Verification (8 waves) | Solve and verify sans_intro, sans_randomblaster1-2, sans_platformblaster/fast, sans_multi1-3 | M5 | ORIGINAL_REQUEST §R2, Miner 1 |
| F12 | Tier 4 sans_final 24.7s Ultimate Verification | Solve and verify complete 24.7s final composite attack offline and in live browser | M6 | ORIGINAL_REQUEST §R2, Miner 1 |
| F13 | Extreme Challenge: Real HELL Solving & Benchmark | Deep analysis, horizon solving, and survival benchmarking on Real HELL (4,198 blasters) | M6 | ORIGINAL_REQUEST §R1, Miner 1 |
| F14 | Forensic Integrity Audit & Sentinel Victory Handover | Independent verification against cheating/hardcoding and victory handover to Sentinel | M6 | System Prompt |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| E2E | Parameterized E2E Verification Harness Track | tools/test_oracle_replay.mjs, tools/verify_and_run_live.mjs, tests/e2e/ | none | DONE |
| M1 | Universal Wave Compiler & Dual-Plane C-Space Baker | nohit/engine/compact_wave.py, tests/unit/test_compact_wave_all.py | none | IN_PROGRESS |
| M2 | Universal FRS-DP Solver Engine (45-Field Dynamics) | nohit/engine/compact_platform.py, nohit/engine/compact_lattice.py, compact_solver.py | M1 | PLANNED |
| M3 | Tier 1 Canonical Rounds Full Verification (6 waves) | sans_bonegap1/fast/2, sans_bluebone, sans_boneslideh/v solving & replay | M1, M2, E2E | PLANNED |
| M4 | Tier 2 Canonical Rounds Full Verification (8 waves) | sans_platforms1-4/hard, sans_bonestab1-3 solving & replay | M1, M2, E2E | PLANNED |
| M5 | Tier 3 Canonical Rounds Full Verification (8 waves) | sans_intro, sans_randomblaster1-2, sans_platformblaster/fast, sans_multi1-3 | M1, M2, E2E | PLANNED |
| M6 | Tier 4 (sans_final 24.7s) & Real HELL Benchmark | sans_final, sans_realhell_extreme, Final Forensic Audit, Sentinel Handover | M3, M4, M5 | PLANNED |

## Interface Contracts
### Solver Plan & Result Schema (`tools/operator-results/<attack_name>.json`)
```json
{
  "attack": "sans_bonegap1",
  "status": "candidate_found",
  "frames": 396,
  "actions": [[ux, up], ...],
  "expansions": 4820,
  "timing_ms": {
    "csv_compile": 3.2,
    "cspace_bake": 8.5,
    "hot_search": 142.0,
    "reconstruction": 0.04,
    "wall_clock": 153.74
  },
  "fidelity": {
    "perturbation_members": 9,
    "product_fields": 45,
    "lossy_approximation": false
  }
}
```

### 240Hz Replay Runner Contract (`tools/test_oracle_replay.mjs`)
- Invocation: `node tools/test_oracle_replay.mjs --attack <attack_name> --plan <plan_json_path>`
- Pass criteria: Process exit code 0, console output `[ORACLE REPLAY PASS] attack=<name> frames=<N> hp=92 kr=0 hits=0`.

### Foreground Visible Live Browser Acceptance Contract (`tools/verify_and_run_live.mjs`)
- Invocation: `node tools/verify_and_run_live.mjs --attack <attack_name> --plan <plan_json_path> --continuous 3`
- Pass criteria: 3 consecutive rounds of EndAttack with 0 hits, HUD badge rendered with '实时三回合无伤已通过', exit code 0.

## Code Layout
- `nohit/engine/compact_wave.py`: Universal Wave Compiler & C-Space Baker. Owned by M1 Worker.
- `nohit/engine/compact_platform.py`: Universal microstep dynamics stepper. Owned by M2 Worker.
- `nohit/engine/compact_lattice.py`: Unified Complete Topological DAG-DP solver kernel. Owned by M2 Worker.
- `nohit/engine/compact_solver.py`: Top-level solver API and timing instrumentation. Owned by M2 Worker.
- `tools/solve_attack.py`: General CLI solver for arbitrary attacks. Owned by M2 Worker.
- `tools/test_oracle_replay.mjs`: Independent 240Hz offline replay runner. Owned by E2E Testing Worker.
- `tools/verify_and_run_live.mjs`: Foreground visible browser runner on port 8103. Owned by E2E Testing Worker.
