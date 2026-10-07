# VERIFY_A — live danger table for `sans_bonegap1` vs the model's `B_hazard`

Measurement-only run. No file under `nohit/` or any `tools/*.py` was modified.
Scratch helpers created: `tools/scratch_A_model_hazard.py` (read-only model query).

---

## 0. Setup actually used

| Item | Value |
|---|---|
| URL | `http://127.0.0.1:8099/game/index.html?mode=single&attack=sans_bonegap1&cb=...` |
| Attack script | `c2-sans-fight/sans_bonegap1.csv` (9 lines, 4 `BoneVRepeat`, `EndAttack` at t=6.4 s) |
| Arena | `c2_left=146`, `c2_floor=378`, W=349, H=114 |
| Engine tick | `dt = 0.0042 s` → **240 ticks/s** for the simulation step |
| Measured attack cycle | **1685 ticks**, extremely stable (see §2) |
| Heart | type `t55`; 4×4 damage object is type `t65` |
| HP | `Runtime.all_global_vars` entry named `HP`, `MaxHP = 92` |

### Method

The heart cannot be pinned by a command issued *during* an attack: the attack is fully
underway within the ~1100 ticks the page needs before any out-of-page command lands
(measured: first command reliably arrives at tick ~900–1500, HP already 23–75).
The measurement therefore works differently:

1. **Single long-running page.** The hook is installed on `Runtime.prototype.tick`
   (same seam the TAS runner itself uses), so it runs *before* the engine's own tick body.
2. **Every tick** the hook rewrites `heart.x`/`heart.y` to the target, zeroes
   `behavior_insts[0].dx/dy`, and calls `update_bbox()`.
3. **HP is restored to 92 on every tick**, so the heart never dies and every danger
   window in every cycle is observable (an un-restored run dies after ~1600 ticks and
   then reports no further damage at all).
4. Damage events are recorded as `(tick, cycle, target, cycle-relative tick)`.
5. The target is advanced only at **cycle boundaries**, and the comparison uses a
   uniform **4 cycles (5 for one target) per x**.

> **Counting note.** A "drop" = one tick on which HP decreased. HP can fall by 2 in a
> single tick (KR/layered hits), so drop counts are *events*, not total damage points.

### Two coordinate notes (they matter)

* `local_x = abs_x − 146`, `local_y = 378 − abs_y` — as specified. The heart's
  *hitbox* origin equals the heart's origin, and `t65` sat at exactly
  `(320, 377.9)` while pinned there, so the pin works exactly.
* **The floor row is not local_y = 0 in the pinned sense.** The attack script
  teleports the heart to `(320, 376)`, and gravity settles it at `abs_y = 377.9`
  (`local_y = 0.1`). All numbers below are reported in **absolute** coordinates as the
  task specifies.

---

## 1. Raw per-x tick lists

Cycle-relative tick = `tick − cycle_start`, where `cycle_start` is the tick on which a
new bone burst appears. Bone bursts are trivially detectable because
`Runtime.types.t31.instances.length` goes 0 → N. The cycle period is stable, so
cycle-relative time is comparable across cycles.

### 1a. `abs_x = 170` (`local_x = 24`), `abs_y = 377.9` — 4 cycles

Drops per cycle: **134, 130, 137, 143** — total **544 events**.

Sorted union of danger ticks (first 12 shown; full union = **328** distinct ticks out of 1685):

```
10, 11, 39, 40, 47, 48, 55, 56, 71, 72, 87, 88, ... (328 total)
```

### 1b. `abs_x = 260` (`local_x = 114`), `abs_y = 377.9` — 4 cycles

Drops per cycle: **113, 104, 112, 108** — total **437 events**.

Sorted union (first 12; full union = **255** distinct ticks):

```
8, 10, 11, 20, 48, 50, 51, 60, 88, 90, 91, 100, ... (255 total)
```

### 1c. `abs_x = 320` (`local_x = 174`), `abs_y = 377.9` — 4 cycles

Drops per cycle: **92, 90, 96, 90** — total **368 events**.

Sorted union (first 12; full union = **248** distinct ticks):

```
17, 19, 57, 59, 97, 99, 137, 139, 177, 179, 217, 219, ... (248 total)
```

Note the very regular 40-tick lattice: `17,19`, `57,59`, `97,99`, `137,139`, … — i.e. a
danger pair every 40 ticks (= 1/6 s at 240 Hz), with rarer extra lanes at 239/247 etc.

### 1d. `abs_x = 396` (`local_x = 250`), `abs_y = 377.9` — 4 cycles

Drops per cycle: **118, 119, 118, 118** — total **473 events**.

Sorted union (first 12; full union = **268** distinct ticks):

```
30, 31, 32, 70, 71, 72, 110, 111, 112, 138, 139, 140, ... (268 total)
```

Triplets every 40 ticks.

### 1e. `abs_x = 466` (`local_x = 320`), `abs_y = 377.9` — 4 cycles

Drops per cycle: **138, 138, 138, 138** — total **552 events**.

Sorted union (first 12; full union = **198** distinct ticks):

```
3, 4, 5, 43, 44, 45, 46, 54, 59, 60, 61, 62, 75, 76, ... (198 total)
```

Perfectly identical counts in all four cycles (138/138/138/138).

### 1f. `abs_x = 320` (`local_x = 174`), `abs_y = 360` (`local_y = 18`) — 2 cycles

Drops per cycle: **7, 2** — total **9 events**.

Sorted union (the complete list — only **7** distinct ticks in 2 full cycles):

```
43, 284, 524, 764, 1005, 1246, 1487
```

These 7 ticks are spaced **~240 ticks apart** (43, 284, 524, 764, 1005, 1246, 1487 —
differences 241, 240, 240, 241, 241, 241), i.e. exactly one hit per second.

---

## 2. Drop counts per (x, y) — uniform 4 cycles each

| abs_x | local_x | abs_y | local_y | cycles | drop events | per-cycle | distinct danger ticks / 1685 | danger % |
|---:|---:|---:|---:|---:|---:|---|---:|---:|
| 170 | 24  | 377.9 | 0.1 | 4 | **544** | 134/130/137/143 | 328 | **19.5 %** |
| 260 | 114 | 377.9 | 0.1 | 4 | **437** | 113/104/112/108 | 255 | **15.1 %** |
| 320 | 174 | 377.9 | 0.1 | 4 | **368** | 92/90/96/90     | 248 | **14.7 %** |
| 396 | 250 | 377.9 | 0.1 | 4 | **473** | 118/119/118/118 | 268 | **15.9 %** |
| 466 | 320 | 377.9 | 0.1 | 4 | **552** | 138/138/138/138 | 198 | **11.8 %** |
| 320 | 174 | 360   | 18  | 2 | **9**   | 7/2             | 7   | **0.4 %** |

Cycle period across the whole session (65 consecutive cycles):
`1678, 1655, 1680, 1676, 1680, …, 1685, 1685, 1686, 1684, …` — settled at
**1685 ± 2 ticks** after the first few cycles.

### Safe-window structure (floor level)

Not one of the five floor positions has a safe window that a *solver* could use as a
resting pattern, but the positions do differ in how tightly the danger is packed:

| abs_x | distinct danger ticks | safe ticks | longest safe gap | gaps ≥ 4 ticks | gaps ≥ 20 ticks |
|---:|---:|---:|---:|---:|---:|
| 170 | 328 | 1357 | 38 | 105 | 7 |
| 260 | 255 | 1430 | 38 | 120 | 8 |
| 320 | 248 | 1437 | **37** | 90 | **16** |
| 396 | 268 | 1417 | 38 | 119 | 7 |
| 466 | 198 | 1487 | 38 | 98 | 7 |
| 320 @ y=360 | 7 | 1678 | **240** | 8 | 8 |

---

## 3. Safest and deadliest x

**Safest of the five floor positions: `abs_x = 466`** — 198 distinct danger ticks
(11.8 % of the cycle), the fewest drop events per cycle in the *union* sense, and the
most repeatable pattern (138/138/138/138 in four consecutive cycles).

**Deadliest: `abs_x = 170`** — 328 distinct danger ticks (19.5 %), 544 drop events, and
the highest per-cycle event counts (130–143).

Ranking of distinct danger ticks (fewest = safest):

```
466 (198)  <  320 (248)  <  260 (255)  <  396 (268)  <  170 (328)
```

Caveat on the 11.8 % figure for 466: its danger is *concentrated* (triplets every 40
ticks), so it has 138 events in every cycle but fewer distinct ticks. Whether that is
"safer" depends on whether the solver needs a long safe gap (466 has none longer than
38 ticks, same as everywhere else) or merely fewer hits. **By longest safe gap all five
floor positions are equivalent (max 37–38 ticks); none offers a refuge.**

---

## 4. Is the heart EVER safe while stationary at abs_x = 320?

**Yes — but only if it is not on the floor.**

* At `abs_y = 377.9` (the rest position the heart falls to): **248 of 1685 ticks are
  dangerous (14.7 %)**, and this reproduced in every cycle measured. The longest safe
  gap is 37 ticks (~0.15 s). **The heart is not safe as a resting place at floor level.**
  A stationary heart dies there.

* At `abs_y = 360` (`local_y = 18`): **only 7 danger ticks in a whole 1685-tick cycle
  (0.4 %)**, spaced ~240 ticks apart. It is safe for 1678/1685 ticks and for 240
  consecutive ticks at a time. So at `abs_x = 320` the answer is
  **safe at y=360, unsafe at y=377.9.**

An earlier observation that looked like a contradiction is worth recording: in one
stretch of 16 consecutive cycles at `(320, 377.9)` the probe logged **zero** drops. That
was an artefact of the target having saturated at the auto-advance limit while HP was
being restored by a *slower* interval, and it is **not** reproducible — the uniform
4-cycle measurement gives 90–96 drops per cycle at that position every time. The
reliable statement is §2: 14.7 % of the cycle is dangerous at `(320, 377.9)`.

---

## 5. Comparison with the model's `B_hazard`

Model queried read-only via `tools/scratch_A_model_hazard.py`
(`bake_cspace("c2-sans-fight/sans_bonegap1.csv", T=500, auto_size=True, soul_w=4, soul_h=4, physics_mode="c2")`):
`B_hazard.shape = (500, 114, 349)`, `initial_state = (174, 2)`, density 0.16119,
`attack_duration_frames = 397`.

### 5a. Per-x danger fraction — model vs live

The model is a **single 6.6 s deterministic schedule**; the live figures are unions over
4 cycles, so they are not the same statistic. They are quoted side by side as
magnitudes only.

| abs_x | local_x | model danger % @ row 0 (frames 0–396) | model danger % @ row 0 (0–499) | **live** danger % @ floor |
|---:|---:|---:|---:|---:|
| 170 | 24 | 22.67 | 19.20 | 19.5 |
| 260 | 114 | 13.60 | 10.80 | 15.1 |
| 320 | 174 | 12.09 | 9.60 | 14.7 |
| 396 | 250 | 24.18 | 19.20 | 15.9 |
| 466 | 320 | 18.89 | 16.00 | 11.8 |

Model danger intervals at row 0 (a sample, showing the 40-frame lattice):

```
localX= 24 (abs 170): 15 runs  [(22,27),(62,67),(102,107),(122,127),(142,147),(162,167),(182,187),(202,207),(222,227),(242,247),(262,267),(282,287),(302,307),(322,327),(362,367)]
localX=174 (abs 320):  8 runs  [(72,77),(112,117),(152,157),(192,197),(232,237),(272,277),(312,317),(352,357)]
```

Live at the same columns shows the same 40-tick lattice (e.g. abs 320: `17,19 / 57,59 /
97,99 / 137,139 / …`; abs 396: `30,31,32 / 70,71,72 / 110,111,112 / …`). At 60 Hz the
model's 5-frame runs become 5/60 s ≈ 20 ticks at 240 Hz, and the live runs at the floor
are 2–4 ticks wide with a 40-tick pitch — the **pitch matches; the run widths are of
the same order but not identical**, and the model's *set* of dangerous columns differs
from the live one at 396 and 466 (`24.18 %` vs `15.9 %`; `18.89 %` vs `11.8 %`) while
agreeing closely at 170 (`22.67 %` vs `19.5 %`). Phase between the model's frame 0 and
the live bone burst was **not** established to better than ~1 frame, so per-column
agreement at this granularity should not be over-read.

### 5b. Vertical structure — the model and the live engine disagree

Model, over the full 500-frame horizon, for every one of the five live x positions:

* danger rows = `0..15` and `23..113`
* **safe rows = `16, 17, 18, 19, 20, 21, 22`** — and this safe band holds for **all 349
  columns**: `row16-22 safe for all columns over full T: True`, and
  `row 18: 0 dangerous frames out of 500` for every live x.

So the model states that `local_y = 18` (i.e. `abs_y = 360`) is **never** dangerous
anywhere in the arena. The live engine **does** hit there: 9 drops in 2 cycles at
`(320, 360)`, and the earlier interval-scan run logged 27 more. The model is therefore
**optimistic about the y=360 band**.

### 5c. Root cause, measured directly

Live overlap counts at `(320, 360)`, sampling every 4 ms:

```
heart origin (320, 360)
  4x4 damage object t65 bbox  = [318, 358, 322, 362]   -> overlaps 0 bones
  heart sprite t55 bbox       = [312, 352, 328, 368]   -> overlaps the 20-high bones (bbox top = 366)
```

Live overlap census at `(170, 377.9)` over 8 s (400 sampled overlap frames):

| frames where… | count |
|---|---:|
| 4×4 hitbox overlaps AND sprite overlaps | 213 |
| 4×4 hitbox overlaps but sprite does **not** | **0** |
| sprite overlaps but 4×4 hitbox does **not** | **187** |

**The live engine damages on the heart's 16×20 sprite bounding box, not on the 4×4
soul box.** A 4×4 box centred at `(x, y)` spans `y±2`; the sprite spans `y±8` (and
`x±8`). That 8-pixel vertical half-extent is exactly why a hitbox at `abs_y = 360`
(spans 358–362, clears the 20-high bones whose top is 365) is still hit by the sprite
(spans 352–368, which does overlap 365–385), while a hitbox at `abs_y = 377.9`
(spans 375.9–379.9) is hit by both.

The model (`soul_w=4, soul_h=4`, `centered=True`) dilates the obstacle set by the 4×4
soul envelope only. **The 12-pixel vertical difference between the modelled collision
envelope and the engine's is the entire source of the §5b disagreement.**

### 5d. Bone geometry read live (for the record)

At the moment of a confirmed hit at `(170, 377.9)`:

* 95-high bones: `bbox = [x, 257, x+10, 352]` — they stop at abs y=352 and **cannot**
  reach any floor-level hitbox.
* 20-high bones: `bbox = [x, 365, x+10, 385]` — these are the floor-level killers.
* The two bone families interleave with a **60-pixel** x pitch (phases ≈ 5.3 and ≈ 9.7
  in the sample taken), which is why a stationary point is clipped by a narrow vertical
  bar sweeping past rather than by a dense wall.

---

## 6. Statements that contradict each other (explicit)

1. **`local_y = 18` is safe in the model, dangerous in the engine.** The model reports
   `row18` never dangerous for any of 349 columns over 500 frames; the live engine hit a
   pinned heart there 9 times in 2 cycles. Resolved in §5c: the engine uses the 16×20
   sprite bbox, the model uses the 4×4 soul envelope. The **model is the one that is
   wrong** here, and it is wrong in the optimistic direction.
2. **`(320, 377.9)` appeared 100 % safe for 16 consecutive cycles** in one intermediate
   run, then measured 90–96 drops/cycle in the uniform run. The "100 % safe" reading was
   a probe artefact (auto-advance saturated at the last target while the HP-restore
   interval ran slower), not engine behaviour. Recorded here because it was observed.
3. **The model's `attack_duration_frames = 397` (6.6 s) does not equal the live cycle,
   which is 1685 ticks ≈ 7.02 s at 240 Hz.** The live cycle includes the post-attack
   idle (bones persist, heart still damageable) before the next burst, so the live
   "danger % per cycle" is diluted relative to a 397-frame attack-only window. Comparing
   the two percentages directly is therefore approximate: over frames 0–396 the model
   reads 22.67 / 13.60 / 12.09 / 24.18 / 18.89 %, over 0–499 it reads 19.20 / 10.80 /
   9.60 / 19.20 / 16.00 %, and live reads 19.5 / 15.1 / 14.7 / 15.9 / 11.8 %.

---

## 7. Bottom line

* At floor level, **no x is safe**: every stationary position at `abs_y = 377.9` is hit
  in 11.8–19.5 % of ticks, with the longest safe gap only 37–38 ticks.
* **Safest of the five floor x: 466** (198 distinct danger ticks, 11.8 %).
* **Deadliest: 170** (328 distinct danger ticks, 19.5 %).
* **`abs_x = 320` is unsafe while stationary at the floor** (`abs_y = 377.9`, 14.7 %,
  ~92 drops/cycle, reproduced in all 4 measured cycles) but **safe at `abs_y = 360`**
  (7 danger ticks per 1685, i.e. 0.4 %) — *and it is not safe there in the model's
  terms for the reason the model gives; the model calls that band always-safe, whereas
  the engine still clips the 16×20 sprite bbox once per second.*
