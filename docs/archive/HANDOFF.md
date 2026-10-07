# HANDOFF — round 13. no-hit TAS + self-solving system, "Bad Time Simulator"

**Read `HANDOFF_round15.md` first.** It supersedes the claims below and records
the original-engine oracle, all24-example coverage, five real-time three-round
records, report-based design changes and unresolved high difficulty/performance.
`HANDOFF_round14.md` is older source calibration history.

Supersedes round 12 (kept as `HANDOFF_round12.md`). Read §1–§4 before touching
anything; §5 is the honest status, §7 is what to do next.

---

## 1. Goal (unchanged)

End-to-end **no-hit TAS** for Undertale *Bad Time Simulator* (a Construct 2
export) plus a solver that computes the route. Acceptance criterion, from the
user:

> **The real machine must complete one full round with HP never dropping.**

Only then extend to other waves. Target wave: `sans_bonegap1`.

---

## 2. THE DAMAGE PRIMITIVE IS SETTLED — do not re-litigate

This consumed most of round 12. It is now proven from the shipped build, three
independent ways. **The model was never the problem at the predicate level.**

From `repo_badtime/Event sheets/Battle.xml`, the only Attack9Patch damage block
is `sid=3041692031166179`:

```
System     | Pick overlapping point (Attack9Patch, PlayerHeart.X, PlayerHeart.Y)   <-- disabled="1"
PlayerHitbox(t65, 4x4) | Is overlapping another object (Attack9Patch family = t70)
Attack9Patch | Compare instance variable Damage != 0
  -> sub-event Color == 0  -> DamagePlayer
```

* The `Pick overlapping point` condition carries **`disabled="1"`** and is
  **absent from the compiled bytecode** (`data.js`). So the engine's damage test
  is exactly: **the 4×4 `PlayerHitbox` (centred on `PlayerHeart.(x,y)`) AABB
  overlapping the bone's AABB.** Nothing else. The 16×20 heart sprite polygon is
  irrelevant (t55 is not in the damage path).
* `Attack9Patch` = family `t70`, members `t30 (BoneH), t31 (BoneV), t34/35
  (Platform1/2), t36/37 (BoneStabV/H?), t38 (BoneStabWarn)`. Only the bones carry
  `Damage != 0`; platforms/warn are correctly excluded.
* `runtime.testOverlap` reduces to an AABB test because NinePatch instances have
  `collision_poly = null` (`c2runtime.js`).
* HANDOFF §3's mystery ("no bone overlaps on both axes") was a **misread**: the
  `h=20` bone at `y[366,386]` overlaps the hitbox at `y[362.30,366.30]` by
  0.30 px, which is a hit.

### Independently verified this round

`tools/validate_hazard.py` recomputes the hazard from the rasterizer's own
occupancy tensor using the exact engine predicate and diffs it against the baked
`B_hazard`:

```
cells the MODEL MISSES (engine would hit, model says safe): 0
cells the MODEL ADDS  (model says dangerous, engine is safe): 599215
frames with any MISS: 0 / 397
```

**The baked hazard tensor is a strict, conservative superset of the engine's
predicate.** A plan that satisfies the model cannot be hit by the model's own
notion of the attack. This kills every "the model under-covers" hypothesis.

### Corollary — this is the key insight for whoever picks this up

Because the model is *conservative*, and because the plan is verified *safe
against the model* (`0` anchor-violations, `0/396` action-sequence replay
mismatches — see §4.4), **the remaining real-machine damage cannot come from
geometry at all. It must come from TIME**: the engine's bone field and the
injected input are not on the same clock. That is exactly what §4.1–§4.3 fix.

---

## 3. Real-machine status

| Measurement | Value |
|---|---|
| Round-12 runner, full round | HP 92 → 21 (66 damage events) |
| + tick-phase fix (`4f` vs `4f+3`) | HP 92 → 12 (72 events) — **not sufficient** |
| + script-clock sync | **NOT YET MEASURED** (acceptance run was cancelled) |
| Controller tracking (phase-fixed run) | plan frame advances correctly, heart follows to ±2 px |

The last clean acceptance attempt was cancelled mid-run, so **the current
patched runner has never been measured end-to-end.** That is the first thing to
do (§7 step 1).

---

## 4. What was actually found and fixed this round

### 4.1 `tas_runner.js` — playback was killed at every attack end (FIXED in r12, retained)

`resetPlayback()` emptied `actionSequence`; split into
`resetPlaybackKeepPlan()` (attack-finished paths) vs `resetPlayback({clearPlan:
true})` (wave switch). Without this the next round had no route at all.

### 4.2 `tas_runner.js` — tick-phase lead (FIXED this round)

The naive plan-frame accumulator made plan frame `f` live on engine ticks
`4f+3 … 4f+6`, i.e. the keys for frame `f` were applied **three engine ticks
after** the tick whose bone geometry frame `f` was baked from — a systematic
0.75 plan-frame (~1.9 px) lead of the bone field over the input.

Measured live: the first tick reporting plan frame `f` was `4f+4`
(`f=28 → tick 4`, `f=200 → tick 692`).

Fix: phase-lock the counter to the absolute engine tick, so `f` lives on
`4f … 4f+3`. New state: `engineTick`, `playbackTick0`
(`getState().syncMode` reports which source is in use).

### 4.3 `tas_runner.js` — STRICT SYNC to the game's own script clock (ADDED this round)

The proper synchronization source is the **Timeline sheet's `T` variable**
(`repo_badtime/Event sheets/Timeline.xml`):

```xml
<event-block sid="2435027366513959">
  <conditions><condition name="Compare variable">
      <param name="Variable">Running</param> ... Value 0   (Running != 0)
  </condition></conditions>
  <actions><action name="Add to">
      <param name="Variable">T</param><param name="Value">dt</param></action></actions>
</event-block>
```

`T` advances by `dt` every engine tick while an attack runs, and **every CSV
command is fired by comparing against exactly this clock**
(`T >= float(TLCurrentLine.At(0))`). So `T` is the game's own attack clock in
seconds, and it is the only quantity guaranteed to stay in step with the bone
geometry the solver baked.

How to read it (this took a while to find — the sheets have no `localvardict`):

```js
// Construct 2 indexes EVERY variable in runtime.varsBySid, keyed by source sid.
rt.varsBySid[3521916820909801]   // Timeline `T`      (static sheet local)
rt.varsBySid[164016619418963]    // Timeline `Running`
```

`findSheetVar()` in `tas_runner.js` now checks `varsBySid` first, then falls back
to the old (non-working) tree walk.

The runner now derives the plan frame as
`floor((T - T0) * PLAN_FPS)` where `T0` is captured at the tick playback starts
(`T` is **not** reset per round). `getState()` exposes
`clockT`, `clockFrame`, `syncMode`. Measured with `tools/probe_sync.mjs`:
`planned` and `clockFrame` advance in lockstep (12 vs 13 frames over 47 ticks),
engine confirmed at exactly **240 Hz**, 4 ticks per 60 Hz plan frame.

### 4.4 Solver — the objective was wrong (DIAGNOSED, NOT YET FIXED)

`nohit/engine/solver.py` `solve_lattice_dp` ranks paths by

```
cand_vals = rep_vals + dist_map[next_state] - act_cost
```

`dist_map` is the distance to the nearest hazard and it is added on **every
frame**, so it is an unbounded per-frame bonus for standing far from danger.
Measured on `sans_bonegap1`:

```
plan total CLEARANCE term : 16294.9
plan total ACTION-COST term:   115.2     ratio 141 : 1
```

Consequence: the extracted route **buys clearance by walking left** — 87 frames
pressing LEFT in three long strafes, ending parked against the left wall — when
this wave only needs four short vertical jumps near the start x. The `+ x * 0.05`
drift term was removed in an earlier round, but the same runaway survives through
`dist_map`, which is why "encourage doing nothing" never took effect.

Evidence the plan is internally sound (so the objective, not the DP, is at
fault):

* `0` anchor-cell violations against the model over 397 frames;
* action sequence re-simulated through `step_dynamics_batch` reproduces the
  reported trajectory exactly: **0 / 396 mismatches**;
* all measurements reproducible with `tools/check_plan_vs_model.py`.

### 4.5 What was added for the objective fix

* **`nohit/engine/mininput.py`** — exact A* over the model's own integer
  micro-state with a lexicographic objective: survive → fewest frames holding an
  input → least hold pressure. Verified exact against short horizons
  (`A*` gives 1 input frame at T=60, 27 at T=120, 64 at T=200; all
  self-verified with 0 unsafe frames). Includes a scalar `step_one_c2` stepper
  proven **bit-exact against `step_dynamics_batch` over 6000 random transitions**
  (`tools/fast_step_check.py`), giving a ~4× speedup.
  **Known limitation: it deadlocks at the full 397-frame horizon** (436k
  expansions then exhausted) because the reachable set over exact dynamics is too
  large. Needs a stronger admissible heuristic, or a waypoint/intermediate-goal
  decomposition, to finish the round.
* **`solver.py` `objective="min_input"`** — a lexicographic mode added to the
  lattice DP (`HOLD_CAP`, `CLEARANCE_CAP`). **It is currently WORSE than the
  legacy objective** (217 input frames vs 111) and must not be trusted yet: with
  clearance fully demoted the DP loses its safety gradient. Clearance should
  instead be **saturating** (0 beyond ~1–2 cells, counted once) while the primary
  term becomes "frame with any input". The DP merges states by a coarse packed
  key, and the exact A* on the same wave finds strictly better solutions
  (27 vs 78 input frames at T=120; 64 vs 119 at T=200), so the lattice
  discretization is also losing optimality — worth understanding before
  re-tuning.

### 4.6 Small fixes

* `nohit/dashboard/server.py`: the game files are now served with
  `Cache-Control: no-store`. Without it the browser silently served the **old**
  `tas_runner.js` and every "fix" measured the previous build. This cost real
  time; keep it.
* `/api/tas` still reports `"fps": 30` while everything runs at 60 Hz
  (cosmetic, `server.py`).

### 4.7 Probes that were written and are worth keeping

| Tool | What it proves |
|---|---|
| `tools/probe_sync.mjs` | plan frame vs script clock `T`; the sync regression test |
| `tools/probe_sync_detail.mjs` | per-tick `dWall / dT / planned / clockFrame` burst |
| `tools/acceptance_round.mjs` | **one clean round from the HP:=MaxHP boundary** (the acceptance run) |
| `tools/validate_hazard.py` | model-misses vs model-adds against the exact engine predicate |
| `tools/check_plan_vs_model.py` | plan vs model violations + input breakdown |
| `tools/dump_corridor.py` | floor-band safe corridor with the plan overlaid |
| `tools/dump_model_frame.py` | model occupancy/hazard at one frame, absolute coords |
| `tools/probe_rates.mjs` | engine Hz and plan Hz |
| `tools/fast_step_check.py` | scalar-vs-batch stepper equivalence |
| `tools/plan_min_input.py` | small greedy min-input feasibility check |
| `tools/patch_tick_phase.py` | the (already applied, idempotency-checked) tick-phase patch |

**Dead ends — do not repeat these:**

* `tools/probe_ground_truth.mjs` / `probe_gt2.mjs`: identify damage carriers by
  scanning `inst.instance_vars` — **the family members have no `instance_vars` of
  their own**, so both probes found 0 carriers and silently measured nothing.
  Use `rt.varsBySid` (above) or `inst.type.family_var_map[family_index] + offset`.
* `tools/probe_gt3.mjs` / `probe_bone_truth.mjs`: same class of bug, and they
  also time out inside `Runtime.evaluate` when the first scan walks every
  instance. `probe_bone_truth.mjs` reports `carriers: 3` but those are not the
  bones.
* Pinning the heart to a fixed position and using that as evidence about the
  plan (from round 12 — still true).
* Restoring HP every tick while measuring damage (re-triggers damage).

---

## 5. Honest status

**Solved / proven this round**

1. The damage predicate, from the shipped build, with the disabled-condition
   trap identified. **No more guessing about what damages.**
2. The baked hazard tensor provably never misses a hit cell (`0` misses / 397
   frames) — so the model is conservative, and "model under-covers" is dead.
3. The solver's plan is provably self-consistent against the model (`0`
   violations, `0/396` replay mismatches).
4. Three concrete runner defects, with measurements: plan deleted at round end,
   3-tick input phase lead, and no synchronization to the game's script clock.
5. The objective defect, quantified (clearance outweighs input cost 141:1), and
   an exact minimal-input planner that works on short horizons.

**NOT solved**

* **A clean no-hit round has never been measured.** The criterion is still not
  met. The script-clock sync (§4.3) is in place but **unverified on the real
  machine** — the acceptance run was cancelled.
* The minimal-input objective is not deliverable yet: the DP mode is worse than
  the legacy one, and the exact A* cannot finish a full round.
* Remaining suspected contributors, in order, if damage persists after §7 step 1:
  1. A residual **1–2 plan-frame phase offset** (model frame `f` vs engine tick
     `4f`) — the model is conservative by ~1 cell/side, which is roughly the same
     margin, so a 1-frame offset can still land a hit.
  2. **Unbaked hazards**: `GasterBlaster` and other attack types appear in ~348
     CSV lines and are never rasterized. **This does not affect `sans_bonegap1`**
     (only `BoneVRepeat` + `EndAttack` there) but it is fatal for
     `sans_intro`, `sans_multi2/3`, `sans_randomblaster*`,
     `sans_platformblaster*`. Must be fixed before extending to other waves.
  3. `BoneStab` ramp is modelled with `n_ext = n_ret = 3` frames, while the
     engine's travel is exactly 0.1 s = **6 frames at 60 Hz** — 3 frames of
     retraction tail are uncovered (bonestab waves only).
  4. Bone culling uses the arena instead of the 640×480 layout → ≤2 px holes at
     the edges.
  5. Zone resize is not modelled; `Color == 2` has no engine damage path, so the
     model's `B_orange` layer is spurious.

---

## 6. Running things

```powershell
$env:PYTHONIOENCODING="utf-8"
$py = ".venv\Scripts\python.exe"

# Dashboard + game server on :8099 (REQUIRED for every real-machine probe).
# Use a managed background job; a foreground Start-Process blocks the tool call.
& $py start_dashboard.py 8099

# The unit/e2e suite (round 12 reported 212/212). NOTE: the user asked us not to
# trust the local suite this round because the model was suspect -- but the model
# has since been proven conservative by tools/validate_hazard.py, so the suite is
# meaningful again. Prefer the targeted checks above over the full suite.
& $py -m pytest tests/ -q -p no:cacheprovider

# Node stub runner
node tools\tas_runner_test.mjs
```

Real-machine probes (ego-browser; CDP port is auto-discovered from
`%LOCALAPPDATA%\ego-lite-linux\browser.json`):

```powershell
node tools\probe_sync.mjs 1700 tools\.sync.json       # sync regression
node tools\acceptance_round.mjs tools\.acc.json       # ONE clean round
node tools\validate_hazard.py --wave sans_bonegap1    # model vs engine
```

Offline checks:

```powershell
& $py tools\check_plan_vs_model.py --plan tools\.plan_bonegap1.json
& $py tools\fast_step_check.py 6000
& $py tools\dump_corridor.py --wave sans_bonegap1 --y 2 --f0 0 --f1 210 --step 3
```

Game entry point:

```
http://127.0.0.1:8099/game/index.html?mode=single&attack=sans_bonegap1&cb=<nonce>
```

---

## 7. What to do next — in order

1. **Measure the current build.** Start the dashboard, then
   `node tools\acceptance_round.mjs`. It records from the exact round boundary
   (the tick where `HP` is restored to `MaxHP`) and reports HP over the whole
   round plus sync quality (`maxSyncDiff`). If HP never drops: **stop, the
   criterion is met**, go to step 4. If HP still drops, the trace names the exact
   plan frame of each hit.
2. **If damage persists, measure the residual phase, do not guess.** For each
   hit, print the engine's own bone AABBs and the hitbox AABB at that tick
   (`rt.testOverlap(hb, bone)` is authoritative and needs no carrier guessing),
   plus the model's hazard cell for the heart. Determine whether the engine is
   testing frame `f` while the plan holds frame `f±1`. If so, shift the plan
   frame by that constant and re-measure. This is the last unexplained variable.
3. **Fix the objective properly** (independent of 1–2, and required for
   "操作时间最短"):
   * replace `dist_map` with a **saturating margin counted once**, and rank
     primarily by **frames on which any input is held**;
   * keep `objective="min_input"` but re-tune — it currently loses to the legacy
     objective (217 vs 111 input frames), and the lattice DP itself is
     suboptimal (proven by A*: 27 vs 78 at T=120);
   * finish the exact A* for a full round: give it a stronger admissible
     heuristic (e.g. "must hold UP during a specific blocked interval", computed
     from the tensor column-by-column) or decompose the round into segments at
     the known safe windows, then stitch.
4. **Only then extend to other waves**, and fix in this order: unbaked
   `GasterBlaster`, the `BoneStab` 6-frame ramp, culling bounds.
5. Performance is still open: a full-round `sans_bonegap1` DP solve is ~18–23 s
   (`tools/profile_solve.py`), dominated by `solve_lattice_dp` itself. The scalar
   stepper in `nohit/engine/mininput.py` plus a tighter objective is the natural
   place to start if solve time matters.

---

## 8. Files touched this round

**Modified**

* `c2-sans-fight/tas_runner.js` — tick-phase lock (`engineTick`, `playbackTick0`),
  strict script-clock sync (`scriptClockT0`, `readScriptClock()`), `findSheetVar`
  via `varsBySid`, new `getState()` telemetry (`clockT`, `clockFrame`,
  `syncMode`). Backup of the pre-patch file: `c2-sans-fight/tas_runner.js.bak_phase`.
* `nohit/engine/solver.py` — `objective: str = "clearance"` parameter;
  `"min_input"` mode; `HOLD_CAP`, `CLEARANCE_CAP`.
* `nohit/dashboard/server.py` — `no-store` cache headers on game files.

**Added**

* `nohit/engine/mininput.py` — exact lexicographic A* + bit-exact scalar stepper.
* `tools/` — `validate_hazard.py`, `check_plan_vs_model.py`, `dump_corridor.py`,
  `dump_model_frame.py`, `probe_sync.mjs`, `probe_sync_detail.mjs`,
  `probe_rates.mjs`, `acceptance_round.mjs`, `fast_step_check.py`,
  `plan_min_input.py`, `patch_tick_phase.py`, `probe_gt3.mjs`,
  `probe_bone_truth.mjs` (last two are known-broken carrier detection — see §4.7).

**Audit report**: `tools/MODEL_AUDIT.md` (independent audit of the baked tensor
against the engine predicate; independently reproduced the `0 misses` result and
the disabled-condition finding).

---

## 9. Standing warnings

* The browser will happily serve a stale `tas_runner.js` — the `no-store` header
  is the fix; verify with
  `Invoke-WebRequest http://127.0.0.1:8099/game/tas_runner.js` and grep for your
  change.
* Start the dashboard as a **managed background job**; a foreground
  `Start-Process` + polling loop blocks the tool call and gets cancelled.
* `page.evaluate`-style calls time out on long probes and when the first scan
  walks every instance. Keep each probe short; write to a file instead of
  returning large JSON.
* The attack restarts on its own cycle, and `T` keeps counting across rounds.
  Any measurement that starts mid-round is comparing a restored HP value against
  a stale plan frame — always anchor to the `HP == MaxHP` boundary.

