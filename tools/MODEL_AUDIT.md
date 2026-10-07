# MODEL_AUDIT — is the baked hazard tensor the engine's damage predicate?

Audit only. No file under `nohit/` was modified. All Python citations are `file:line` into the
repo at `<repo>`. Engine citations are into the shipped export
(`c2-sans-fight/c2runtime.js`, `c2-sans-fight/data.js`) and the authoritative original project
(`repo_badtime/Event sheets/Battle.xml`).

**Headline:** the model's hazard predicate is a *strict over-approximation* of the engine's real
damage test, and the engine's real damage test does **not** include the "Pick overlapping point"
condition at all — that condition is `disabled="1"` in `Battle.xml` and is **absent from the
compiled bytecode** (`c2runtime.js`'s `Condition` decoder has no "disabled" field, so a disabled
condition is simply not exported). The model therefore cannot be "too permissive" on the predicate
axis; the live HP loss must come from geometry/timing/execution, not from a missing point test.

---

## 0. What the engine actually does (settled from the shipped build)

### 0.1 Tick order (asked for explicitly)

`Runtime.prototype.tick` → `c2runtime.js:5281`, which calls `this.logic(raf_time)` at
`c2runtime.js:5335`. Inside `Runtime.prototype.logic` (`c2runtime.js:5360`) the order is:

| # | line | what |
|---|---|---|
| 1 | 5406–5411 | `ClearDeathRow()` / `system.runWaits()` |
| 2 | 5412–5414 | `objects_to_pretick` pretick pass |
| 3 | **5415–5425** | **behaviour `tick()` for every instance** (`inst.behavior_insts[k].tick()`) |
| 4 | 5426–5438 | behaviour `posttick()` pass |
| 5 | 5439–5441 | `objects_to_tick` tick pass |
| 6 | **5448–5451** | **`this.running_layout.event_sheet.run()`** |
| 7 | 5455–5467 | behaviour `tick2()` pass |
| 8 | 5468–5470 | `objects_to_tick2` pass |

So: **behaviours tick before the event sheet** (behaviour `tick()` at 5422, event sheet at 5451),
and the behaviour `tick2()`/`objects_to_tick2` passes run *after* the event sheet. There is no
`tickBehaviors()`/`events_.run()` pair by those names in this build — the equivalent pair is
`behinstProto.tick()` (5415–5425) versus `event_sheet.run()` (5448–5451). Consequence: the
CustomMovement integrator moves `PlayerHeart` first, then the event sheet runs the damage test
against the *post-movement* position, and objects created/moved by the event sheet (bones) are
positioned for this tick but have not yet been integrated by their own behaviour.

### 0.2 The damage predicate (the only Attack9Patch damage path)

`Battle.xml:7942` is block `sid=3041692031166179`. Its conditions are:

* `Battle.xml:7944` — `System | Pick overlapping point`, object `Attack9Patch`, X `PlayerHeart.X`,
  Y `PlayerHeart.Y` — **`disabled="1"`**. The same is true of the sibling paths
  (`Battle.xml:7817` AttackSprite, `Battle.xml:7904` AttackTiled).
* `Battle.xml:7949` — `PlayerHitbox | Is overlapping another object | Attack9Patch`
* `Battle.xml:7952` — `Attack9Patch | Compare instance variable Damage != 0`
* sub-events: `Battle.xml:7960` `Color == 0` → `DamagePlayer`; `Battle.xml:7992`
  `Color == 1` **and** `PlayerHeart | CustomMovement | Is moving` → `DamagePlayer`.

The compiled copy of that block (decoded from `data.js` → `project[6][0]` = sheet `Battle`,
`Battle/35/s7/s2`, `sid` in `m[4]`) has exactly two conditions:

```
[65, 181, None, 0, False, False, False, 216628994048020, False, [[4, 70]]]
[70, 123, None, 0, False, False, False, 1580583761025439, False, [[10,0],[8,4],[7,[0,0]]]]
```

Decoding with the loaders (`c2runtime.js:9753` `EventBlock(m[4]=sid, m[5]=conditions, m[6]=actions,
m[7]=subevents)`, `c2runtime.js:10051` `Condition(m[0]=type, m[1]=funcref, m[5]=inverted, m[7]=sid)`)
and the object-ref table at `c2runtime.js:23284ff` (index 181 = `cr.plugins_.Sprite.prototype.cnds.IsOverlapping`,
index 123 = `NinePatch.prototype.cnds.CompareInstanceVar`, index 227 =
`cr.system_object.prototype.cnds.PickOverlappingPoint`):

* condition 1 = type 65 (`PlayerHitbox`), `Sprite.IsOverlapping`, object param `[4,70]` = family
  index **70** = `Attack9Patch` (from `data.js` `project[4]` = `[70, 30, 37, 36, 38, 31, 34, 35]`,
  i.e. BoneH, BoneStabH, BoneStabV, BoneStabWarn, BoneV, Platform1, Platform2 — exactly the family
  the brief names);
* condition 2 = type 70 (the family), `CompareInstanceVar` var 0 `!= 0` (= `Damage`, since the
  `DamagePlayer` call passes var 0 and var 1 as `Damage`/`Karma`);
* **index 227 never appears anywhere in that block** — the point test is gone.

The runtime confirms both halves of the remaining test reduce to plain AABB:

* `Runtime.prototype.testOverlap` (`c2runtime.js:6130`) → `a.bbox.intersects_rect(b.bbox)`
  (6141), `a.bquad.intersects_quad(b.bquad)` (6143), and **if neither instance has a collision
  polygon it returns `true`** (6151–6154): `haspolya = (a.collision_poly && !a.collision_poly.is_empty())`.
* NinePatch instances never define `collision_poly`; the loader defaults it to `null`
  (`c2runtime.js:5891-5892`: `if (typeof inst.collision_poly === "undefined") inst.collision_poly = null;`)
  → `inst_contains_pt` (`c2runtime.js:13761`) returns `true` after the bbox/bquad checks.
* `Rect.prototype.contains_pt` (`c2runtime.js:186-188`) is inclusive on all four edges.
* `update_bbox` (`c2runtime.js:13710-13728`) gives `bbox = [x - hsX*w, y - hsY*h, x - hsX*w + w, ...]`;
  `BoneV`'s default instance is `[96,96,0,10,48,0,0,1,0,0,0]` (w=10, h=48, hotspotX=0, hotspotY=0)
  so `bbox.left == x`, `bbox.top == y` — matching HANDOFF §3.

⇒ For bones (angle never set: see §2) the engine's damage test is exactly
**"the 4×4 PlayerHitbox centred on `PlayerHeart.(x,y)` has an inclusive-AABB overlap with the bone
rect `[x, x+w] × [y, y+h]`"**, plus the instance-variable gates.

### 0.3 The hitbox really is the 4×4, not the 16×16 sprite

`Battle.xml:7713-7736`: `PlayerHitbox` is created on start of layout at `PlayerHeart.X/Y` and every
tick `Set position to another object → PlayerHeart, image point 0`. `t65`'s only frame is
`["images/playerhitbox-sheet0.png", 112, 0, 0, 4, 4, 1, 0.5, 0.5, [], [], 0]` — 4×4, hotspot
(0.5, 0.5), empty polygon list. The heart `t55` frame is 16×16 hotspot (0.5,0.5), also with an empty
custom polygon (it falls back to the full 16×16 rect) — but `t55` never participates in the damage
test, so HANDOFF §3's "is it the 20×16 polygon?" question is **closed: no**. The 4×4 is the damage
box, and the heart's image point 0 is (0,0) relative to its origin, so the hitbox centre is exactly
`PlayerHeart.(x,y)` (independently confirmed by the live bbox `[291.16,362.30..295.16,366.30]`
around `(293.16,364.30)` in HANDOFF §3).

With that, HANDOFF §3's "no bone overlaps the 4×4 on BOTH axes" is a mis-reading: at tick 415 the
h=20 bone `y[366,386]` overlaps the hitbox `y[362.30,366.30]` by **0.30 px** (and x by 1.32 px), so
the AABB test alone explains that hit.

---

## Q1 — What geometric predicate does the baked tensor represent?

**Answer: (iv) something else — a conservative (over-approximating) Chebyshev dilation of the bone's
integer cell cover. The "point inside hazard bbox" test is not implemented, and the engine does not
run it either.** The model errs on the **safe** side (it can invent danger, it cannot miss a static
AABB hit), with one important caveat about how thin that margin is (§Q6 #3).

Decision chain, in order:

1. **Bone rect → integer cells** (`nohit/baker/rasterizer.py:467-475`):

```python
ix0 = int(math.floor(x0)) if x0 > 0 else 0
ix1 = int(math.floor(x1)) + 1
...
iy0 = int(math.floor(y0)) if y0 > 0 else 0
iy1 = int(math.floor(y1)) + 1
```

`x0,x1,y0,y1` come from `bone.get_box(t)` (`rasterizer.py:89-94`), i.e. the model's local-frame
rectangle. The marked cell set is therefore `[floor(x0) .. floor(x1)] × [floor(y0) .. floor(y1)]`
(the `+1` then `floor` is equivalent to `floor(x1)`, i.e. the right/top cell is included even when
the edge is exactly on a boundary) — the comment at `rasterizer.py:451-466` states the intent:
"guarantees the cell SPAN covers the bone, at the cost of over-covering by at most one cell -- which
can only mark MORE cells dangerous, never fewer."

2. **Which tensor gets dilated** (`nohit/baker/dilator.py:252-253`, `:303`): for the live path
`physics_mode == "c2"` forces `soul_w = soul_h = 4` and `centered = True`
(`dilator.py:237-253`), then `b_hazard = dilate_cspace(raster_res.O, soul_w=4, soul_h=4, centered=True)`.

3. **The dilation kernel** (`nohit/baker/dilator.py:112-135`):

```python
half_w = soul_w // 2 + GRAZE_MARGIN_CELLS      # 4//2 + 1 = 3
half_h = soul_h // 2 + GRAZE_MARGIN_CELLS      # 3
dx_shifts = range(-half_w, half_w + 1)         # -3..+3
dy_shifts = range(-half_h, half_h + 1)
```

with `GRAZE_MARGIN_CELLS: int = 1` at `dilator.py:32`. It is a separable OR-dilation, so the result
is a full **7×7 box (Chebyshev radius 3) Minkowski sum**:

```
B[y, x] == True  ⇔  ∃ obstacle cell (j, i) with |i - x| <= 3 and |j - y| <= 3
```

4. **How the solver consumes it** (`nohit/engine/solver.py:326-327`): one tensor frame per model
step,

```python
B_t1 = B_hazard[t + 1]
safe = ~B_t1[next_y, next_x]
```

plus the initial-frame probe at `solver.py:127` (`if B_hazard[0, y0, x0]: deadlock at t=0`). Verified
empirically: for the current bake of `sans_bonegap1` the extracted trajectory satisfies
`not B_hazard[i, y_i, x_i]` for all 397 frames (0 violations), i.e. the model's plan is exactly the
model's safe set.

**Direction of the error.** For a bone at `[bx0,bx1]×[by0,by1]` and a heart centre `(x,y)`:

* engine: danger ⇔ `x ∈ [bx0-2, bx1+2]` and `y ∈ [by0-2, by1+2]` (4×4 box, inclusive);
* model: danger ⇔ `x ∈ [floor(bx0)-3, floor(bx1)+3]` and `y ∈ [floor(by0)-3, floor(by1)+3]`.

Since `floor(bx0)-3 ≤ bx0-3 < bx0-2` and `floor(bx1)+3 ≥ bx1+2`, the model's integer danger set is a
**superset** of the engine's on every axis. (This also holds under the brief's reading, where the
engine's predicate were `point ∈ bbox` — `[bx0,bx1] ⊆ [floor(bx0)-3, floor(bx1)+3]`.) Numeric check
at the `sans_bonegap1` frame-103 configuration: model danger band x∈[132,148] for a bone the model
places at local x0=135.0; engine band for that same bone = [133,147] ⇒ over-cover ≈1 px/side, exactly
as the docstrings claim. **The model never uses a weaker predicate than the engine; the failure mode
it can produce is over-approximation (reported deadlock / detour), not silent damage.**

The one thing that eats the margin is not the predicate but the *phase* of the bone positions (§Q3):
the model's bone is ~1 engine tick (0.75 px) ahead of the engine's at the same tick index, which
reduces the ~1 px/side overshoot to ~0.25 px on the leading edge.

---

## Q2 — Which hazard object types are baked, with what rectangles?

### 2.1 Type-code mapping (from `data.js` `project[3]`, `project[4]`)

| idx | object | plugin | default size (w×h) | hotspot | family | Damage | baked as hazard? |
|---|---|---|---|---|---|---|---|
| 30 | `BoneH` (`images/boneh.png`) | NinePatch | 48 × **10** | 0,0 | 67, 70 | set to **1** by the handler | yes (`rasterizer.py:379-397`) |
| 31 | `BoneV` (`images/bonev.png`) | NinePatch | **10** × 48 | 0,0 | 67, 70 | set to **1** | yes (`rasterizer.py:343-377`) |
| 36 | `BoneStabV` (`images/bonestabv.png`) | NinePatch | 12 × 48 | 0,0 | 66, 70 | set to **1** | yes, approximated (`rasterizer.py:399-405`) |
| 37 | `BoneStabH` | NinePatch | 48 × 12 | 0,0 | 66, 70 | set to **1** | yes, approximated |
| 38 | `BoneStabWarn` | NinePatch | 16 × 16 | 0,0 | 70 | left at default **0** | correctly **not** a hazard |
| 34 | `Platform1` | NinePatch | 61 × 7 | 0,0 | 70 | left at default **0** | correctly **not** a hazard (only `platform_table`) |
| 35 | `Platform2` | NinePatch | 61 × 7 | 0,0 | 70 | left at default **0** | correctly **not** a hazard |

Damage-default evidence: every type's layout initial-instance record has all-zero instance variables
(`data.js` project[5], e.g. `t34` → `vars=[[0],[0],[0],[0],[0],[0]]`), and the compiled `Platform`
handler (`Battle/27/s0`) sets only vars 3 (Direction), 4 (Speed) and the bool 5 — it never writes
Damage. So `Platform1/Platform2` are Attack9Patch *members* whose `Damage == 0` gate fails: the
engine's damage block cannot fire on them. The model's choice to keep them out of `O` is **correct**.

### 2.2 The rectangles the rasterizer builds

`BoneV` (`rasterizer.py:343-377`, when `y > eff_H` → C2 canvas space):

```python
lx = x - c2_left
ly = c2_floor - (y + h)
vx, vy = _calc_velocity(d, spd, is_c2=True)
active_bones.append(_ActiveBone(lx, ly, 10.0, h, vx, vy, color, t))
```

⇒ rect `[x-146, x-146+10] × [378-(y+h), 378-y]`. `BoneH` (`rasterizer.py:379-397`) is the transpose:
`ly = c2_floor - (y + 10.0)`, rect `[x-146, x-146+w] × [ly, ly+10]`. Width 10 for BoneV and height 10
for BoneH match the engine's *default* instance dimensions, which the handlers never overwrite:
`Battle/29/s1` does `SetHeight(Param2)` only (BoneV keeps width 10), `Battle/29/s0` does
`SetWidth(Param2)` only (BoneH keeps height 10).

The y-flip `ly = c2_floor - (y + h)` is right: the CSV `y` is the NinePatch's top edge (hotspot 0,0),
so the C2 band is `[y, y+h]` and its reflected local band is `[c2_floor-(y+h), c2_floor-y]`. Live
cross-check for `sans_bonegap1`: `h=20, y=366` ⇒ local `[-8, 12]`; the model's rows for that bone are
`0..12` after the `y0<=0 → 0` clamp, and the dilation extends them to `0..15` — matching the live
`abs y[366,386]` and the live damage at `(147.16,13.70)`.

`BoneV` (t31, `h=95, y=257`) ⇒ local `[26,121]`; `h=20, y=366` ⇒ local `[-8,12]`. Both match
HANDOFF §5 and the `tools/align_*.py` probes (row 30 for h=95, row 2 for h=20).

### 2.3 Rotation

**No bone or platform is ever rotated.** The compiled events contain no `SetAngleOfMotion`-style
rotation for `t30/t31` (only `SetX/SetY/SetHeight|SetWidth/SetInstanceVar/MoveToBottom`), the layout
default instance angle is `0` for all of them, and `t34`'s motion is driven by
`CustomMovement.SetAngleOfMotion(direction*90)` which changes *velocity direction*, not the sprite
angle. So the engine's bbox is always the axis-aligned rect, and the model's zero-rotation
assumption is correct *for hazard geometry*. (`update_bbox` at `c2runtime.js:13717-13724` does expand
the bbox to the rotated quad's AABB, so if a future wave ever sets an angle the model would
under-cover — today nothing does.)

---

## Q3 — Frame indexing: model frame f vs engine tick

**Mechanically the pipeline is self-consistent; the residual error is a ~1 engine tick (0.25 model
frame) phase lead of the tensor, not a whole-frame off-by-one.**

* CSV seconds → model frames: `nohit/baker/parser.py:181-182`
  `clock += delay; frame = int(round(clock * self.fps))`, parsed at the model rate
  (`dilator.py:264-268`, `parse_csv_timeline(path, fps=int(MODEL_FPS))`).
* Horizon: `dilator.py:278-291` (`T = round(max(EndAttack.time_s) * 60) + 1`) and
  `rasterizer.py:552-560` (`duration_frames = int(round(duration_s * fps)) + 1`). For
  `sans_bonegap1` EndAttack is at clock 6.6 s ⇒ frame 396, `T = 397`, so the last frame index is 396
  and the horizon covers the closing frame rather than cutting it.
* Rate agreement: `RasterizerConfig.FPS` defaults to `constants.FPS = 30`
  (`rasterizer.py:36`, `constants.py:34`) while `dynamics.MODEL_FPS = 60` (`dynamics.py:62`);
  `bake_cspace` overrides it (`dilator.py:295` `RasterizerConfig(..., FPS=int(_MODEL_FPS))`) so the
  live path is consistent, but any *direct* `rasterize_timeline`/`rasterize_csv` call inherits 30 Hz
  (`tools/align_bones.py:39` and `align_live_bones.py:53` pass `FPS=60` by hand). One tensor frame ==
  one solver step (`solver.py:326` `B_hazard[t + 1]`), and the initial state is checked against frame
  0 (`solver.py:127`) — no index skew inside the model.

**Measured phase.** Two independent live dumps tie the engine's bone motion to
`x(tick) = 128 + 0.75*(tick - 49)`:

* `rasterizer.py:451-456` — live tick 290, first damage, h=20 bone at abs `[308.738, 318.738]`;
  `128 + 0.75*(290-49) = 308.75` ✓.
* HANDOFF §3 — live tick 415, h=20 bone at abs `[282.48, 292.48]`; `128 + 0.75*(415-49) - 120 = 282.5` ✓
  (the second member of the 120 px repeat group).

The model's bone is at `128 + 3*(f - 12)`; setting them equal gives **model frame f ≡ engine tick
4f + 1** (equivalently: at engine tick 4f the model's tensor is 0.75 px ahead in the travel
direction). Two candidate sources, both ≤1 tick:

1. **Spawn phase.** `BoneVRepeat` sits on a 0.2 s delay ⇒ model frame 12 ⇒ tick 48. The measurement
   above puts the bone *at* 128 during tick 49 and 128.75 at tick 50, i.e. the first command fires
   one engine tick later than `round(0.2*60)=12` maps to. The tensor therefore treats frame 12 as
   "bone at 128" while the engine has it at 128 for ticks 49–48+1.
2. **EndAttack anchoring.** Model frame 396 = 6.6 s = tick 1584; the engine's `EndAttack` lands ~tick
   1585. `+1` in `duration_frames` absorbs this, so the horizon is not truncated.

The model's *heart* side is anchored differently (the initial state comes from `HeartTeleport`,
`rasterizer.py:206-288`, and `kappa=1, vy=0` at frame 0), which is exact.

**The bigger, non-model part of the same problem** (`c2-sans-fight/tas_runner.js`):
`tickControl()` is hooked *before* the engine body (`tas_runner.js:1236-1241`), but it only injects on
the **4th** tick of each group:

```js
if (planTickAccum < planTicksPerFrame() - 1) { planTickAccum += 1; return; }   // tas_runner.js:753-756
```

so plan frame `f`'s keys are applied at engine tick `4f+3 … 4f+6` instead of `4f … 4f+3` — a
**systematic 3-tick (≈0.75 model frame, up to 1.875 px of horizontal travel) input lag**, including a
3-tick gap at the very start of the attack. The closed-loop drift check cannot see it because it
compares `trajectory[plannedFrame]` against a heart position sampled at the same lagged tick
(`tas_runner.js:760-774`, `848-861`) and `DRIFT_DEADZONE = 2` (`tas_runner.js:43`) is exactly the size
of the lag it should be correcting.

---

## Q4 — Arena / clamp geometry: model vs engine

**Engine** (`Battle.xml:6810-6873`, block `sid=1591886703018009`): while `PlayerHeart` overlaps
`CombatZone`:

```
CombatZone.BBoxLeft + 5   > PlayerHeart.BBoxLeft   → Set X = BBoxLeft + 5 + 8
CombatZone.BBoxTop  + 5   > PlayerHeart.BBoxTop    → Set Y = BBoxTop  + 5 + 8
CombatZone.BBoxRight - 5  < PlayerHeart.BBoxRight  → Set X = BBoxRight - 5 - 8
CombatZone.BBoxBottom - 5 < PlayerHeart.BBoxBottom → Set Y = BBoxBottom - 5 - 8
```

i.e. the heart's **16×16 bbox** is clamped to the zone inset by the 5 px border, and the `±8`
accounts for the heart's centred origin. With `CombatZoneResize(133,251,508,391)` from
`sans_bonegap1.csv:1` the heart's centre is confined to
`x ∈ [146, 495]`, `y ∈ [264, 378]` (C2 screen y, downward).

**Model** (`rasterizer.py:239-246`):

```python
eff_W = int(round(init_x2 - init_x1 - 26))   # 349
eff_H = int(round(init_y2 - init_y1 - 26))   # 114
c2_left = init_x1 + 13                       # 146
c2_floor = init_y2 - 13                      # 378
```

and the clamp lives in the stepper, not in the arena: `dynamics.py:151`
`next_x = max(0, min(W - 1, int(round(raw_x))))` and `dynamics.py:260`
`next_y = max(0, min(H - 1, int(np.floor(y_next_star))))`, with the floor as `surfaces = [0.0]`
(`dynamics.py:243`, `:328`).

**Agreement:** `13 = 5 + 8` is exactly the engine's border+half-heart inset, so the model's local
frame is the heart-centre frame the engine uses (verified live: resting heart `abs y = 377.94` ⇒
local `y ≈ 0`, `c2_left = 146`). The model allows `x ∈ [0,348] ↔ abs [146,494]` and
`y ∈ [0,113] ↔ abs [378,265]`, i.e. **1 px short at the right wall and 1 px short at the ceiling** —
strictly conservative.

**Two divergences worth recording:**

1. `coords.CombatZone` and the *non*-`auto_size` rasterizer branch use the raw border 5:
   `coords.py:17-50` (`border_thickness: float = 5.0`, `inner_bottom = y2 - 5`) and
   `rasterizer.py:244-246` (`c2_floor = init_y2 - B`, `c2_left = init_x1 + B`). With
   `auto_size=False` the same CSV yields `c2_left = 138`, `c2_floor = 386`, `W = DEFAULT_W = 200`,
   `H = 160` (`constants.py:13-16`) — a *different* arena and frame from the live one. `/api/tas`
   always passes `auto_size=True` (`server.py:343-350`), so the live path is correct; every other
   caller is a latent trap.
2. The zone is sampled once and never updated: `rasterizer.py:197-205` keeps the first
   `CombatZoneResize`, and `rasterizer.py:536` writes a constant
   `zone_bounds_history.append((0, eff_W, 0, eff_H))`. The CSVs do resize/move the zone mid-attack
   (26 × `CombatZoneResize`, 23 × `CombatZoneResizeInstant`, 3 × `CombatZoneSpeed` across the 24
   scripts; `sans_final.csv` and `sans_platforms3.csv` among them), and `Battle.xml:6600-6790` shows
   the zone's bbox genuinely moves — so for those waves the model's arena and clamp are wrong in both
   directions. `sans_bonegap1` sets the zone once at t=0, so this does not affect the current target.

---

## Q5 — `/api/tas`: exact request/response shape

Handler: `nohit/dashboard/server.py:267` `handle_get_tas` (GET only; `do_GET` routes it at
`server.py:96-97`). Request parameters (`server.py:269-284`):

```python
params = urllib.parse.parse_qs(query_str)
wave_name = params.get("wave", ["sans_bonegap1.csv"])[0]
T_param = params.get("T", [None])[0]
T = int(T_param) if T_param not in (None, "", "0") else 0      # 0/omitted ⇒ full attack
soul_w = int(params.get("soul_w", [4])[0])
soul_h = int(params.get("soul_h", [4])[0])
physics_mode = params.get("physics_mode", ["c2"])[0]           # "c2" | "docs"
```

Those five keys are the *only* accepted parameters. `T = 0` triggers a one-frame probe bake to read
`attack_duration_frames` (`server.py:323-333`) and then the real bake with
`auto_size=True, soul_w, soul_h, physics_mode` (`server.py:343-350`). Results are cached on
`(wave, T, soul_w, soul_h, physics_mode, csv mtime_ns, csv size)` (`server.py:303-316`). The response
(`server.py:355-382`):

```python
res = {
    "wave": wave_name,
    "T": bake.T,
    "fps": 30,                                   # ← hard-coded, see below
    "physics_mode": meta.get("physics_mode", physics_mode),
    "is_deadlock": sol.is_deadlock,
    "deadlock_frame": sol.deadlock_frame,
    "action_sequence": sol.action_sequence,      # list[T-1] of [ux, uy]
    "trajectory": sol.trajectory,                # list[T] of [x, y, vy, kappa, tau]
    "initial_state": list(bake.initial_state),   # [x0, y0] local
    "arena": {"c2_left": ..., "c2_floor": ..., "W": bake.W, "H": bake.H,
              "soul_w": ..., "soul_h": ..., "v_walk": ..., "v_jump": ...},
    "stats": {"bake_ms": ..., "dp_ms": ..., "total_ms": ..., "peak_states": ...},
}
```

To reproduce a run you need `action_sequence` (indexed by model frame), `trajectory` (same indexing,
for `initial_state`/drift), `arena.c2_left`/`arena.c2_floor` (to convert heart `(x,y)` back to local)
and `arena.W/H` + `soul_w/soul_h` (to sanity-check the geometry); `physics_mode` should be `c2` and
`T`/`soul_w`/`soul_h` must match the request or the geometry differs. **`res["fps"] = 30` is a bug in
the response**: the bake, the solver and `action_sequence` all run at 60 Hz
(`dynamics.MODEL_FPS = 60`); `tas_runner.js` ignores the field and derives ticks-per-frame from
`rt.fps` (`tas_runner.js:44-57`), so nothing is broken today, but any client that trusts `fps` would
run the route at half speed. The runner's local conversions use `arena` (`tas_runner.js:483-497`).

---

## Q6 — Ranked divergences (model vs engine)

Legend for the last column: **M>S** = model calls it safe while the engine can damage (this is the
class that produces "plan looks clean, HP drops"); **M>D** = model is over-conservative (loud
deadlock/detour, harmless for HP).

| # | Divergence | Evidence | Direction | Can it explain the live damage? |
|---|---|---|---|---|
| 1 | **Hazards never baked at all**: `GasterBlaster` (348 CSV lines, 21 in `sans_intro` alone ×… see §2 note), `SineBones` (12), direct CSV `DamagePlayer` (3 in `sans_intro`), `SansSlam`/`SansSlamDamage` bodies. The rasterizer's dispatch handles only `SansSlam`, `BoneV`, `BoneH`, `BoneStab`, `Platform` (`rasterizer.py:340-424`); everything else falls through silently. | command census over `c2-sans-fight/sans_*.csv`; `Battle.xml:4781-4831` shows `SineBones` calling `BoneV` with a sine-driven height; `Battle.xml:5974` (blaster), `Battle.xml:5389` (stab cleanup) | **M>S** | Not for `sans_bonegap1` (no such commands). Fatal for `sans_intro`, `sans_multi2/3`, `sans_randomblaster*`, `sans_platformblaster*`, `sans_final`. |
| 2 | **Runner input lag (3 engine ticks)**: frame `f`'s keys are injected at tick `4f+3…4f+6`; the closed-loop drift uses a sample from the same lagged tick and a 2 px deadzone, so it cannot detect the ~1.9 px systematic offset. | `tas_runner.js:753-757`, `1236-1241`, `760-774`, `848-861`, `43` | **M>S** (execution, not model) | **Yes — this is the leading explanation** for `sans_bonegap1`'s live HP loss: the current plan crosses the h=20 bone band with a 2 px x-margin and a 1-cell y-margin (plan `traj[103]=(150,14)`, `traj[104]=(148,16)`; live was `(147.2,13.7)`, ~2.8 px left / 1.3 px below the plan). |
| 3 | **Tensor is ~1 engine tick (0.25 frame) ahead of the engine's bone positions**: live `x = 128 + 0.75*(tick-49)` vs model `128 + 3*(f-12)` ⇒ model frame `f` ≡ tick `4f+1`. Eats ~0.75 px of the ~1 px/side dilation overshoot. | `rasterizer.py:451-456`; HANDOFF §3 dump; `parser.py:181-182`; measured `c2_floor/left` frame | **M>S** (thin) | Contributes (≈0.25 px of remaining margin at the tight frames) but is too small to explain the observed 1.3–2.8 px miss on its own. Fixing the spawn phase (10-line change: the CSV clock should be sampled one engine tick later, or the dilation widened by one more cell) removes it. |
| 4 | **BoneStab ramp is 2× too fast**: `n_ext = n_ret = 3` is commented "0.1s extension at 30 FPS" but the model runs at 60 Hz and the engine's travel time is `Distance / Speed` with `Speed = BoneStab.Distance * 10` ⇒ exactly 0.1 s = **6 frames**. Extension therefore reaches full depth 3 frames early (M>D), and the retraction finishes 3 frames early ⇒ the last 3 frames of every stab are uncovered while the engine's bone still stands up to 12.5 px proud. | `rasterizer.py:120-134` (`n_ext = 3 … 0.1s extension at 30 FPS`, `:132` retract ratio); `Battle.xml:5288-5326` (`Speed = BoneStab.Distance * 10`); `Battle.xml:5102-5104` (`Set size = CombatZone.Width × (BoneStabWarn.Distance + 8)`) | both (**M>S** in the retraction tail) | Explains damage in the three `sans_bonestab*` waves; irrelevant to `sans_bonegap1` (no stabs). |
| 5 | **Bone culling at the arena edge, not the layout edge**: model drops a bone once `x0 >= eff_W` / `x1 <= 0` etc. (`rasterizer.py:436-443`) and skips any bone whose rect misses the arena (`:448`); the engine keeps it until `Bone.X > LayoutWidth` (640), `Bone.X < -Bone.Width`, `Bone.Y > LayoutHeight` (480) or `Bone.Y < -Bone.Height`. | `Battle.xml:4852-4915`; `rasterizer.py:436-448` | **M>S** | Bounded hole of ~1–2 px of bone travel at each arena edge (a bone with `x0 = abs 495` still overlaps a heart pinned at local 348). Could bite `sans_bonegap1` only if the plan hugs the right wall at the exact frame a dir-0 bone crosses; the current plan does not (its rightmost frames are x≈156–174 in mid-air). |
| 6 | **Zone resize / move not modelled** (constant `zone_bounds_history`, arena fixed from the first `CombatZoneResize`). | `rasterizer.py:197-205`, `:536`; `Battle.xml:6600-6790` | either | Yes for waves that resize (`sans_final`, `sans_platforms3`, `sans_multi*`); not for `sans_bonegap1`. |
| 7 | **`Color == 2` (orange) has no damage path in the engine** — only `Color == 0` and `Color == 1` sub-events exist — while the model builds a separate `B_orange` layer that the solver treats as "damages when NOT moving" (`dilator.py:310-312`, `solver.py:334-337`). Also `is_moving` in the solver (`ux!=0 | vy!=0 | kappa==0`) is broader than the engine's `CustomMovement.IsMoving` = `dx != 0 || dy != 0` (a heart at the apex with no key held is "not moving" to the engine, "moving" to the model). | `Battle.xml:7960-8006`; `c2runtime.js:23041-23043`; `solver.py:331,336` | **M>D** | No: both mismatches over-approximate. Worth fixing because it can convert a solvable blue/orange wave into a false deadlock. |
| 8 | **`BoneVRepeat`/`BoneHRepeat`/`PlatformRepeat` colour is read from the CSV (`args[7]`) but the engine's repeat handler calls `BoneV(X,Y,H,Dir,Speed)` with five args, so `Color = Param(5) = 0` (always white ⇒ always damages)**. | `parser.py:383`, `:399`, `:471`; compiled `BoneVRepeat` block (`Battle/29/s3`) → `CallFunction "BoneV"` with 5 params; `BoneV` handler sets `Color = Param(5)` | **M>S** | Latent only: no shipped CSV passes a colour to a `*Repeat` line (all trailing colour columns are empty), so it cannot explain current damage — but it is a loaded gun for any new script. |
| 9 | **Non-`auto_size` arena frame** (5 px border, 200×160 window) as in Q4.1. | `coords.py:17-50`, `rasterizer.py:244-246`, `constants.py:13-16` | either | Not on the `/api/tas` path; a trap for direct callers/tools. |
| 10 | **Nine-patch bbox size**: model hard-codes 10 px thickness (`constants.py:70-71`) and ignores the NinePatch margins. | default instances `t31 = 10×48`, `t30 = 48×10`; handlers set only the long axis | **correct** (no divergence) | No. The nine-patch *draw* margins never affect the collision bbox (`c2runtime.js:13710-13728` uses `width`/`height` only). |
| 11 | **Rotation expansion**: no angle is ever set on bones/stabs/platforms, so the axis-aligned assumption is exact today; `update_bbox` would expand the AABB if a wave ever set one. | compiled action census on types 30/31/34-38; layout instance angles all 0; `c2runtime.js:13717-13724` | correct today, latent later | No. |
| 12 | **Point-in-bbox test**: absent from the model *and* absent from the engine. | `Battle.xml:7944` `disabled="1"`; compiled block has 2 conditions; `c2runtime.js:6151-6154` (no-poly ⇒ AABB only) | model is a superset ⇒ **M>D** | No — the model is *more* restrictive than the engine, by ~1 px/side. |
| 13 | Cosmetic/API: `/api/tas` reports `"fps": 30` while everything runs at 60 Hz. | `server.py:358`, `dynamics.py:62` | n/a | No (runner ignores it), but misleading. |

### Answers to the specific hypotheses in the brief

* **Nine-patch bbox size / rotation expansion** — correct as implemented (10 px, hotspot 0,0, no
  rotation ever applied). Not a divergence.
* **Bone culling** — real but bounded: cull at the arena (349×114) instead of the layout (640×480)
  ⇒ ≤~2 px of bone travel of missing coverage at each edge (item 5).
* **Dilation direction** — the model over-covers by construction (`soul_w//2 + 1` = 3 cells vs the
  engine's 2 px half-extent, plus the `floor(x1)+1` cell span); it cannot under-cover a static
  correctly-placed bone. The margin is only ~1 px/side and ~0.25 px after the phase lead, which is
  why item 2's 1.9 px execution lag is enough to break the plan.
* **1-frame offset** — no whole-frame skew: the tensor is 1 *engine tick* (0.25 model frame) ahead of
  the engine's bone positions (item 3); the horizon (`T = 397` for a 6.6 s attack) is correct.
* **Hitbox-vs-point** — moot: the engine tests the 4×4 hitbox against the bone's AABB and the point
  test is disabled/not exported. The 4×4 is the damage box, not the 20×16 sprite polygon.

### Repro commands used (read-only)

```powershell
$py = ".venv\Scripts\python.exe"
# decoded the compiled event block + ref table + type/family tables from data.js / c2runtime.js
& $py -c "..."            # see MODEL_AUDIT notes; all reads, nothing written under nohit/
# baked the live configuration and inspected the tensor around the first live damage frame
& $py -c "from nohit.baker.dilator import bake_cspace; ..."   # T=397, W=349, H=114, soul 4x4, c2
# solved and checked trajectory-vs-tensor consistency: 0 violations over 397 frames
```
