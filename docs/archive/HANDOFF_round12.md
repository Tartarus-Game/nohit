# HANDOFF — no-hit TAS + self-solving system for "Bad Time Simulator"

Last updated: round 12. Read this top-to-bottom before touching anything.

---

## 1. The goal

Build an end-to-end no-hit TAS for Undertale **"Bad Time Simulator"** (a Construct 2
export) plus a solver that computes the route. Acceptance criterion, stated by the
user and unchanged:

> **The real machine must complete one full round with HP never dropping.**

Only after one round is genuinely no-hit does the work extend to the other waves.

---

## 2. Current status (verified, reproducible)

| Area | State |
|---|---|
| Unit + e2e tests | **212/212 pass** (`.venv\Scripts\python.exe -m pytest tests/ -q`) |
| Node stub runner | **19/19 pass** (`node tools\tas_runner_test.mjs`) |
| Solver on all waves | 9/9 solvable, `replay_and_verify` PASS |
| **Real-machine TAS execution** | **WORKS as of this round** — inputs are actually injected |
| **Real-machine HP** | **FAILS** — 92 → 21, 66 damage events |

### What was broken and is now fixed

**`resetPlayback()` deleted the plan at the end of every round.** In
`c2-sans-fight/tas_runner.js` the attack-finished paths called `resetPlayback()`,
which set `actionSequence = []`. So each round destroyed the very route the next
round needed, and the following `StartAttack` armed a runner with nothing to play.
The heart then merely fell and drifted — which the user correctly described as
"it never jumps and just walks left into the wall".

Fixed by splitting the function:

* `resetPlaybackKeepPlan()` — playback state only; **used by both attack-finished
  paths** (`endattack`/`battlemenu`, and the `Timeline.Running 1->0` edge).
* `resetPlayback({ clearPlan: true })` — also drops the route; used when actually
  **switching waves** (a stale route must not replay against a new wave).

Verified live afterwards:

```
actionCount   = 396            (plan survives the round boundary)
plannedFrame  0 -> 396         (plan advances)
playingTicks = 2549
inputTicks   =  971            L=795  U=320  R=16
```

**Execution accuracy is ±1 px**, so the runner is NOT the current problem:

```
live   f=103: local(147.2, 13.7)
plan   f=103: local(148,   14)     delta 0.9 px / 0.3 px
```

---

## 3. The one remaining bug, with exact coordinates

First damage of the round:

```
tick 415   plannedFrame 103   HP 92 -> 91
heart abs (293.16, 364.30)     -> local (147.2, 13.7)
t65 (playerhitbox, 4x4) bbox abs [291.16, 362.30 .. 295.16, 366.30]

nearby bones (abs):
  h=95  x[282.48, 292.48]  y[257, 352]    x-overlap  1.32 px OK    y-overlap -10.3 px  NO
  h=20  x[282.48, 292.48]  y[366, 386]    x-overlap  1.32 px OK    y-overlap   0.7 px OK-ish
  h=95  x[348.52, 358.52]  (far)
```

**No bone overlaps the 4×4 box on BOTH axes cleanly.** So the damage is not
explained by an axis-aligned bounding-box test. The engine tests **collision
polygons** (`CollisionPoly_`), and the model has only ever reasoned about bboxes:

* `t55` (heart sprite) **does** carry an explicit polygon:
  `[-10,8], [-10,-8], [10,-8], [10,8]` (20 wide × 16 tall).
* `t65` (the 4×4 playerhitbox) polygon list is empty -> falls back to its rect.
* `t31` (BoneV) is a **NinePatch**, hotspot `(0,0)`, so `bbox.left == x`.

### The next measurement (single, decisive)

Print, side by side at the first damage frame:

1. the engine's own verdict: `rt.testOverlap(heartInstance, boneInstance)` for every
   in-range bone, and
2. which object the DamagePlayer path actually tests.

The earlier attempt failed because it identified candidate objects by looking for an
instance variable named `Damage` — **that found 0 types**, so the probe was testing
nothing. Do not repeat that approach. Instead:

* read the *original* project: `repo_badtime/Event sheets/Battle.xml`, the 5
  `DamagePlayer` call sites. Call #1 at offset ~534724 sits under an event whose
  Object param is `PlayerHeart`; the others use `AttackSprite`, `AttackTiled`,
  `Attack9Patch`. Confirm which one covers BoneV (`t31`).
* `tools/dump_damage_conditions.py` already dumps those 5 call sites with their
  conditions — run it first.

Also worth testing directly: whether the damage comes from `t55`'s 20×16 polygon
rather than `t65`. VERIFY_A measured a pinned heart at `abs_y = 360` taking damage
where the 4×4 box overlapped nothing, which points the same way. **The user
explicitly corrected an earlier attempt to widen the model's envelope to 20×16:
the 4×4 is the damage box, the larger one is for frame/solid collision.** Treat
"which box damages" as still open, and settle it from `Battle.xml`, not from
geometric inference.

---

## 4. Version determination — SETTLED, do not re-litigate

The shipped `c2-sans-fight/` build was compiled from **`repo_badtime`** (FVF variant):
`DamagePlayer` paths = 4 there vs 5 in `repo_jcw87`, and the blue-heart Tint constant
`25` appears 36× vs `23.53` appearing 0×. Both repos have identical 113 On-function
handlers and 32 Timeline handlers. **`repo_badtime` is authoritative; rebuilding is
not needed.** All 24 scripts are byte-identical to the export except `sans_intro.csv`,
which is GBK-encoded.

---

## 5. Authoritative facts established by measurement

### Coordinate systems

Construct 2 uses **screen coordinates: origin top-left, y grows downward**
(`c2runtime.js` `CollisionPoly_.update_bbox` assigns `bboxTop` to the smaller y).
Live proof: `c2_floor = 378`, resting heart at `abs_y = 377.9`.

The model's **local arena is the opposite** (y = 0 at the floor, larger = higher).
The two frames meet in exactly one place — the state's `vy`, which follows the engine
(`CustomMovement.dy`: negative = rising). Getting this backwards is what once made a
jump drive the heart into the floor. Conversions:

```
local_x = abs_x - 146        (c2_left)
local_y = 378 - abs_y        (c2_floor)
```

### Blue-heart jump (confirmed against the user's description)

The mechanic is **hold to rise, release to drop, no air jump, finite ceiling**
(`Battle.xml` / `InputManagement.xml`):

```
WHEN VPad.Up > VPad.LastUp  THEN HeartJump  -> dy -= sin(angle)*180   (keydown edge only)
WHEN VPad.Up == 1           THEN dy = -HEARTSPEED
WHEN VPad.Up < VPad.LastUp  THEN dy = -HEART_JUMPHOLD_CUTOFF
```

Constants: `HEARTSPEED=150`, `HEART_JUMP_STRENGTH=180`, `HEART_JUMPHOLD_CUTOFF=30`,
`MaxFallSpeed=750`.

Model output after the fix (60 Hz, `vy_frames` positive = up internally):

```
hold  1 frame  -> apex  5 px        hold 15 -> 41 px
hold  6 frames -> apex 19 px        hold 30 -> 68 px
hold 10 frames -> apex 29 px        hold 60 -> 88 px (saturated)
```

Live `dy` while UP is held decays monotonically under gravity alone
(`-180.00, -179.24, ..., -165.74`), i.e. the impulse simply persists — there is
**no per-frame re-assertion**. Adding one produced a hard 2 px ceiling and was the
bug that made "hold longer = jump higher" impossible. Scalar and batch paths are
verified identical.

### Bones

`BoneVRepeat,128,257,95,0,180,8,120` expands with

```
xi = StartX - cos(Direction*90) * Spacing * loopindex
```

**MINUS is correct.** Confirmed three independent ways: original XML
(`repo_badtime/Event sheets/Battle.xml:4698`, `StartX - cos(Direction*90)*Spacing*loopindex`),
the decoded compiled bytecode (`data.js:6113`), and by calling the live engine's own
`BoneVRepeat`. Do NOT flip the sign — an attempt to do so broke
`test_bone_repeat_expansion` and `test_platform_repeat_expansion` and made positions
worse.

Consequence: direction 0 gives `128 - 120i` = `128, 8, -112, ...`; direction 2 gives
`503 - (-1)*120i` = `503, 623, 743, ...` (spreads rightward because the cosine is
negative). Verified live: the engine reports 32 `t31` instances, 120 px spacing,
`180 px/s`, top-left anchored.

Bone families: `h=95` occupies abs `y[257,352]` and can never reach a floor-level
heart; `h=20` occupies abs `y[366,386]` and is the floor-level killer.

### Dilation

`soul_w // 2 + GRAZE_MARGIN_CELLS` (a previous `(soul_w - 1) // 2` under-covered by a
full cell). The direction of error matters: over-approximating turns a solvable wave
into a loud deadlock; under-approximating turns it into silent damage.

### Solver left-bias — FIXED

`np.unique(val_packed, return_index=True)` in the no-hazard branch kept the FIRST
candidate, and candidates are ordered parent-major / action-minor with
`ACTIONS[0] = (-1, 0)` = LEFT. On a **featureless arena** the extracted path pressed
LEFT on all 149 frames and parked against the left wall from any start x
(50→0, 174→0, 320→0) — pure artefact. Replaced with a `np.lexsort` that ranks by value
first and keeps `P_keys` sorted (the O(T) backtracking uses
`np.searchsorted(P_keys[t], target)`, which silently returns a bogus index on a
non-monotone array). Now a featureless arena yields **zero inputs**.

Important: the mirror control proved the **real-wave** leftward run is hazard-geometry
driven, not this bias (`B[:,:,::-1]` gives 0 left / 87 right).

### `replay_and_verify` cannot catch this class of defect

The trajectory and the replay run against the same tensor, so a plan that is wrong
about the *live engine* still reports max difference 0. Discriminators are the plan
itself, the mirror control, and the real machine.

---

## 6. Performance — diagnosed, not yet fixed

A full-round `sans_bonegap1` solve takes **~23.5 s**, which is far too slow.

```
distance_transform_edt over all frames :  312 ms   (not the bottleneck)
solve_lattice_dp                       : 23579 ms

per frame (N = 37,010 alive -> 6N = 222,060 candidates):
  step_dynamics_batch  28.6 ms
  pack_states_vec       4.3 ms
  subtotal             32.9 ms/frame  -> 13.0 s over 396 frames
```

Root cause: **the alive set nearly fills the arena.** Alive states ≈ safe cell count
(58,642 vs 36,148 at f=50; 30,799 vs 28,872 at f=200). The state merge is not at
fault — it collapses 6N → uniq_child at **5.3–6.8×**, already near the 6x ceiling.

Contributions to N (f=100, N=53,014):

```
drop tau               -> 53,014  (0% — tau is fully determined by (x,y,vy), no redundancy)
drop vy                -> 37,633  (29%)
drop both              ->  7,785  (the (x,y) lower bound is 7,689)
```

`vy` is a **continuum**, not two values: 86 distinct values at f=100, ranging
`-177 .. +114 px/s`, decaying ~3 px/s per frame. That is physically real. The fat is
that every intermediate velocity is carried for the whole horizon.

`MAX_STATES_PER_FRAME = 400_000` **never triggers** (peak 162,062), so the beam does
nothing. Tightening it to 3,000 made things *slower*.

Candidate fixes, in order of expected value:

1. **Dominance pruning** — on the same `(x,y)`, discard states whose reachable future
   is a subset of another's.
2. **Cap vy variants per `(x,y)`** (K = 2/3/5) and measure the speed/optimality
   curve.
3. Reduce the per-frame `astype` count (9,476 calls, 3.75 s) and avoid materialising
   the full `(6N, 5)` int32 array when only two columns are consumed downstream.

---

## 7. Running things

```powershell
$env:PYTHONIOENCODING="utf-8"
$py = ".venv\Scripts\python.exe"

# tests (17 s)
& $py -m pytest tests/ -q -p no:cacheprovider

# node stub runner (19 checks)
node tools\tas_runner_test.mjs

# dashboard + game server on :8099 (start detached so it survives the shell)
$wd = (Get-Location).Path
$null = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
  CommandLine = "`"$wd\.venv\Scripts\python.exe`" start_dashboard.py 8099"; CurrentDirectory = $wd }

# parallel wave sweep (each worker re-loads numpy; >4 workers OOMs)
& $py tools\solve_all_parallel.py --verify --workers 4

# single-wave profile
& $py tools\profile_solve.py sans_bonegap1 --top 16
```

Real-machine test entry point (browser tools are `ego_*`):

```
http://127.0.0.1:8099/game/index.html?mode=single&attack=sans_bonegap1&cb=<nonce>
```

```js
// wait for the plan, then start the round and record
for (let i=0;i<120;i++){ if (await page.evaluate(()=>window.TASRunner.getState().actionCount)>100) break;
                         await new Promise(r=>setTimeout(r,500)); }
// set HP/KR, then c2_callFunction('StartAttack', []) inside a hooked Runtime.prototype.tick
```

**Pitfalls that repeatedly produced false conclusions:**

* Do NOT pin the heart to a fixed position and use that as evidence about the plan.
  The plan moves the heart, so a pinned-heart danger measurement is a different
  scenario. Several rounds were lost to this.
* Do NOT restore HP every tick while measuring damage — it re-triggers damage and
  looks like "constant damage".
* `page.evaluate` times out on long probes; keep each one under ~15 s and split runs.
* The attack **restarts on its own cycle**; `c2_callFunction("RunAttack", ...)` is a
  no-op. `resetPlayback()` (with clearPlan) empties the route — re-fetch before
  measuring from frame 0.
* The browser session can drop (`no active tab to attach session`) — re-navigate.

---

## 8. Files

**Core**
* `nohit/engine/dynamics.py` — scalar + batch steppers. Coordinate frames and the jump
  model live here; both paths must stay in sync.
* `nohit/engine/solver.py` — lattice DP, `MAX_STATES_PER_FRAME`, the value/action
  objective, the no-hazard branch and its lexsort tie-break, backtracking.
* `nohit/engine/state.py` — 32-bit key packing: `x9 + y8 + vy10 + kappa1 + tau4`.
* `nohit/baker/parser.py` — CSV timeline parser; `BoneVRepeat`/`BoneHRepeat`/
  `PlatformRepeat` expansion (`start - cos*spacing*i` — correct, do not flip).
* `nohit/baker/rasterizer.py` — CSV -> occupancy tensor. `RasterizerConfig.FPS` must
  equal `dynamics.MODEL_FPS`.
* `nohit/baker/dilator.py` — `bake_cspace` (T=None => full round from `EndAttack`),
  `dilate_cspace`, `GRAZE_MARGIN_CELLS`.
* `nohit/verifier/replayer.py` — `replay_and_verify` (see the caveat in §5).
* `nohit/dashboard/server.py` — `/api/tas` with a plan cache keyed on request shape +
  CSV mtime/size (20.2 s -> 0.005 s).
* `c2-sans-fight/tas_runner.js` — in-game runner: deep-link wave parsing, tick
  alignment (`planTicksPerFrame`), key injection via the C2 Keyboard `keyMap`,
  `resetPlayback` / `resetPlaybackKeepPlan`.

**Diagnostics written during this work** (all read-only, none touch `nohit/`)
* `tools/solve_all_parallel.py` — parallel sweep with `--verify`.
* `tools/profile_solve.py` — cProfile top functions for one solve.
* `tools/diag_state_explosion.py` — N vs 6N vs unique children per frame.
* `tools/diag_vy_multiplicity.py` — `(vy, kappa, tau)` breakdown per cell.
* `tools/align_bones.py`, `tools/align_live_bones.py`, `tools/check_repeat_culling.py`
  — model vs live bone positions.
* `tools/dump_damage_conditions.py` — the 5 `DamagePlayer` call sites. **Start here.**
* `tools/dump_frames.py`, `tools/find_heart_size.py`, `tools/find_damage_object.py`
  — sprite dimensions / hotspots / damage object.
* `tools/VERIFY_A_live_danger.md`, `tools/VERIFY_B_bone_source.md`,
  `tools/VERIFY_C_solver_bias.md` — three independent verification reports. Read
  their caveats; A's headline "the engine uses the 16×16 sprite bbox" was
  **contradicted by the user** and is not settled.

---

## 9. What to do next

1. **Settle the damage primitive from `Battle.xml`** (§3). Run
   `tools/dump_damage_conditions.py`, then drive the engine's own `rt.testOverlap`
   against the heart for every bone at the first damage frame. Do not infer it
   geometrically — three rounds were spent on inferences that the user then
   corrected.
2. Fix the model so its hazard map agrees with the live verdict at that frame.
3. **Re-run the real machine until HP never drops for a full round.** That is the
   only acceptance criterion.
4. Only then extend to the other waves, and address the 23.5 s solve time (§6).

Keep the run behind a background job when it is long, and keep probes short.
