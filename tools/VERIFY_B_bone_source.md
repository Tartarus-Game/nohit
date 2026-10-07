# VERIFY_B — BoneVRepeat source analysis (authoritative)

**Question under test:** does the model's repeat expansion `xi = start_x - cos(direction)*spacing*i`
match the real engine, or should it be `+`?

**Verdict: MINUS is correct.** The original C2 project *and* the compiled export both use
`X = StartX - cos(Direction*90)*Spacing*loopindex`, and the live compiled engine, called with the
exact CSV arguments, produces `128, 8, -112, …` (minus) and `503, 623, 743, …` (also minus, because
`cos(180°) = -1`).

No code under `nohit/` was modified. Scratch artifacts: `tools/scratch_B_*.py`, `tools/scratch_B_*.mjs`.

---

## 0. Execution environment / provenance of the live check

| Fact | Value | How obtained |
|---|---|---|
| HTTP server already serving the export | `http://127.0.0.1:8099/game/index.html` | `Invoke-WebRequest` |
| Served `c2runtime.js` bytes | `932011` — identical to `c2-sans-fight/c2runtime.js` | HTTP `RawContentLength` vs `Get-Item` |
| Served `data.js` bytes | `858415` — identical to `c2-sans-fight/data.js` | idem |
| Only `c2runtime.js` in the tree | 1 file (no patched copy) | recursive `Get-ChildItem` |
| Bone object type in the live engine | `t31` (`images/bonev.png`, `is_world: true`) | live `rt.types_by_index` |

So the live engine I probed is byte-identical to the compiled export analysed below. There is no
patched runtime in the workspace.

Round start (needed because `RunAttack` is what actually moves the timeline) came from
`prove_timeline_gate.mjs` plus the event sheets:
`?mode=single&attack=<wave>` → `StartAttack` → `RunAttack(1)`.

---

## 1. The exact XML that spawns repeat bones (quoted)

### 1a. `repo_badtime/Event sheets/Battle.xml`, lines 4629–4720 — the `BoneVRepeat` function

Parameter capture (lines 4649–4678, abridged — the `…` marks omitted actions):

```xml
<event-block sid="2472030495346477">
    <conditions>
        <condition id="-1" name="Every tick" sid="511186914115708" type="System" />
    </conditions>
    <actions>
        <action id="-9" name="Set value" sid="1921417768379967" type="System">
            <param id="0" name="Variable">StartX</param>
            <param id="1" name="Value">Function.Param(0)</param>
        </action>
        ...
        <action id="-9" name="Set value" sid="9872068619262539" type="System">
            <param id="0" name="Variable">Count</param>
            <param id="1" name="Value">int(Function.Param(5))</param>
        </action>
        <action id="-9" name="Set value" sid="1610581451054986" type="System">
            <param id="0" name="Variable">Spacing</param>
            <param id="1" name="Value">int(Function.Param(6))</param>
        </action>
    </actions>
</event-block>
```

The spawn loop (lines 4679–4718) — **this is the load-bearing quote**:

```xml
<event-block sid="5730075193726498">
    <conditions>
        <condition id="-10" name="For" sid="7059627040753894" type="System">
            <param id="0" name="Name">&quot;&quot;</param>
            <param id="1" name="Start index">0</param>
            <param id="2" name="End index">Count-1</param>
        </condition>
    </conditions>
    <actions />
    <sub-events>
        <variable constant="0" name="X" sid="8995826170165568" static="0" type="number">0</variable>
        <variable constant="0" name="Y" sid="189405798698284" static="0" type="number">0</variable>
        <event-block sid="6006720074805655">
            <conditions>
                <condition id="-1" name="Every tick" sid="604141026195968" type="System" />
            </conditions>
            <actions>
                <action id="-9" name="Set value" sid="8270178689385789" type="System">
                    <param id="0" name="Variable">X</param>
                    <param id="1" name="Value">StartX - cos(Direction*90)*Spacing*loopindex</param>
                </action>
                <action id="-9" name="Set value" sid="5795819707185205" type="System">
                    <param id="0" name="Variable">Y</param>
                    <param id="1" name="Value">StartY - sin(Direction*90)*Spacing*loopindex</param>
                </action>
            </actions>
        </event-block>
        <event-block sid="4470889229613242">
            <conditions>
                <condition id="-1" name="Every tick" sid="7427359563618654" type="System" />
            </conditions>
            <actions>
                <action id="0" name="Call function" sid="9908391695264444" type="Function">
                    <param id="0" name="Name">&quot;BoneV&quot;</param>
                    <param id="1" name="Parameter {n}">X{###}Y{###}Height{###}Direction{###}Speed</param>
                </action>
            </actions>
        </event-block>
    </sub-events>
</event-block>
```

Reading this directly off the XML:

* **Loop bounds:** `For` index `0 → Count-1`, i.e. exactly `Count` iterations (8 here).
* **`loopindex` starts at 0**, so the `i = 0` bone sits at exactly `StartX`.
* **The sign is `-`**, applied to `cos(Direction*90)*Spacing*loopindex`.
* **No offset of any kind** is added: not the sprite hotspot, not `CombatZone.BBoxLeft`, not a
  generation-order term. `X` and `Y` are the *only* inputs to the `BoneV` call.

### 1b. `Battle.xml` lines 4492–4535 — the `BoneV` function (where `X` becomes the transform)

```xml
<event-block sid="4945953763224302">
    <conditions>
        <condition id="0" name="On function" sid="6688792887696073" type="Function">
            <param id="0" name="Name">&quot;BoneV&quot;</param>
        </condition>
    </conditions>
    <actions>
        <action id="-3" name="Create object" sid="1921768329956219" type="System">
            <param id="0" name="Object to create">BoneV</param>
            <param id="1" name="Layer">&quot;CombatZoneClipped&quot;</param>
            <param id="2" name="X">0</param>
            <param id="3" name="Y">0</param>
        </action>
        <action id="-1" name="Set X" sid="2138972822860598" type="BoneV">
            <param id="0" name="X">int(Function.Param(0))</param>
        </action>
        <action id="-2" name="Set Y" sid="4944328469401855" type="BoneV">
            <param id="0" name="Y">int(Function.Param(1))</param>
        </action>
        <action id="-6" name="Set height" sid="218884723663614" type="BoneV">
            <param id="0" name="Height">int(Function.Param(2))</param>
        </action>
        ...
```

Two things worth flagging:

1. **`X` is truncated with `int()`** before it becomes the transform. That is why every spawn
   position below is an exact integer, and why the live values are integers rather than
   fractionals.
2. The object is created at `(0,0)` and then immediately repositioned, so there is no
   creation-order accumulation.

### 1c. `AttackLoader.xml` / `Timeline.xml` — the CSV → function path, and no hidden offset

`Timeline.xml` line 331 dispatches a CSV row to a function by **name = token 1**, passing
tokens 2..10 as parameters:

```xml
<action id="0" name="Call function" sid="9188948149072351" type="Function">
    <param id="0" name="Name">TLCurrentLine.At(1)</param>
    <param id="1" name="Parameter {n}">TLCurrentLine.At(2){###}TLCurrentLine.At(3){###}TLCurrentLine.At(4){###}TLCurrentLine.At(5){###}TLCurrentLine.At(6){###}TLCurrentLine.At(7){###}TLCurrentLine.At(8){###}TLCurrentLine.At(9){###}TLCurrentLine.At(10)</param>
</action>
```

For `0.2,BoneVRepeat,128,257,95,0,180,8,120` the tokens are `[0]=0.2`, `[1]=BoneVRepeat`,
`[2]=128`, … so `Function.Param(0) = 128`, `Param(5) = 8`, `Param(6) = 120` — **passed straight
through, no transformation**. The model's arg mapping (`start_x, start_y, height, direction,
speed, count, spacing`) is correct.

> **Inferred, not read:** the `Every tick` condition nested inside an `On function` block is the
> game's idiom for "run this on the call" (the same shape is used by `SineBones`). The live probe
> in §5 confirms empirically that one call creates exactly 8 bones and the loop terminates, so the
> nesting does not cause repeated spawning.

---

## 2. Cross-check in the compiled `data.js` (second, independent reading)

### 2a. The repeat formula — `c2-sans-fight/data.js` lines 6107–6139

```js
[0, null, false, null, 6006720074805655, [
        [-1, 38, null, 0, false, false, false, 604141026195968, false]
    ],
    [
        [-1, 21, null, 8270178689385789, false, [
            [11, "X"],
            [7, [5, [23, "StartX"],
                [6, [6, [19, 85, [
                            [6, [23, "Direction"],
                                [0, 90]
                            ]
                        ]],
                        [23, "Spacing"]
                    ],
                    [19, 102]
                ]
            ]]
        ]],
        [-1, 21, null, 5795819707185205, false, [
            [11, "Y"],
            [7, [5, [23, "StartY"],
                [6, [6, [19, 119, [
                            [6, [23, "Direction"],
                                [0, 90]
                            ]
                        ]],
                        [23, "Spacing"]
                    ],
                    [19, 102]
                ]
            ]]
        ]]
    ]
],
```

Decoding this bytecode. The opcodes are verified, not guessed:

* `m[0]` selects an entry from the jump table at `c2runtime.js:10741–10766`:
  `this.get = [this.eval_int, this.eval_float, this.eval_string, this.eval_unaryminus,
  this.eval_add, this.eval_subtract, this.eval_multiply, this.eval_divide, …]`.
* The second element of a `[19, n, …]` node is an index into `cr.getObjectRefTable()`
  (`c2runtime.js:23283` onward), which I enumerated programmatically.

| Token | Meaning | Confirmed by |
|---|---|---|
| `[11, "X"]` | destination variable `X` | plain name node |
| `[5, a, b]` | `a − b` (**subtract**) | jump table position 5 = `eval_subtract` (`c2runtime.js:10747`, body at 11094) |
| `[6, a, b]` | `a × b` | position 6 = `eval_multiply` (`c2runtime.js:10748`, body at 11105) |
| `[7, a, b]` | `a ÷ b` | position 7 = `eval_divide` |
| `[23, "StartX"]` | variable `StartX` | `case 23: // eventvar_exp` (`c2runtime.js:10858`) |
| `[19, 85, …]` | **`cos(…)`** | table index **85** = `cr.system_object.prototype.exps.cos` |
| `[19, 119, …]` | **`sin(…)`** | table index **119** = `cr.system_object.prototype.exps.sin` |
| `[19, 71, …]` | **`int(…)`** | table index **71** = `cr.system_object.prototype.exps["int"]` |
| `[19, 102]` | **`loopindex`** | table index **102** = `cr.system_object.prototype.exps.loopindex` |
| `[6, [23, "Direction"], [0, 90]]` | `Direction * 90` | as above |

(Table indices were read out of the reference table at `c2runtime.js:23283`, entry 0 being
`cr.plugins_.NinePatch`.)

So the compiled expression is literally `X = StartX - cos(Direction*90) * Spacing * loopindex`.
**The XML and the compiled JS agree exactly. There is no divergence to report.**

### 2b. The `int()` truncation on the `Set X` action — `data.js` lines 5840–5846

```js
[31, 111, null, 2138972822860598, false, [
    [0, [19, 71, [
        [20, 3, 39, false, null, [
            [0, 0]
        ]]
    ]]]
]],
```

`[31, 111, …]` = action 111 on object type `t31` (= `BoneV`), with SID `2138972822860598`, which
matches the `Set X` SID in the XML at line 4505. The argument is `[19, 71, …]` = `int(Function.Param(0))`.

### 2c. `int()` semantics — `c2runtime.js` line 12601

```js
SysExps.prototype["int"] = function(ret, x) {
    if (cr.is_string(x)) {
        ret.set_int(parseInt(x, 10));
        if (isNaN(ret.data))
            ret.data = 0;
    } else
        ret.set_int(x);
};
```

`ExpValue.set_int` truncates toward zero (not floor). Consequence: `int(-0.5) === 0`, not `-1`.
This is a real edge case for `direction 2`, see §3.

---

## 3. Derived spawn-x formula and the 8 absolute x values

### 3a. Formula (read directly off the source)

```
for i in 0 .. Count-1:
    X_i = int( StartX - cos(Direction*90) * Spacing * i )      # Battle.xml:4698
    Y_i = int( StartY - sin(Direction*90) * Spacing * i )      # Battle.xml:4702
```

Expanding `cos` for the four 90°-aligned directions:

| `direction` | `cos(dir*90)` | `X_i` |
|---|---|---|
| 0 (right) | `1` | `StartX - Spacing*i` → **descending** |
| 1 (down) | `0` | `StartX` (no x spread) |
| 2 (left) | `-1` | `StartX + Spacing*i` → **ascending** |
| 3 (up) | `0` | `StartX` (no x spread) |

Note the asymmetry, because it is easy to misread: the formula is *always* minus, but for
`direction 2` the minus applied to a negative cosine makes the group spread **rightward**
(increasing x). The model's `DIR_COS` (`parser.py:25`, `{0: 1.0, 1: 0.0, 2: -1.0, 3: 0.0}`)
reproduces exactly this.

**Computed independently of `nohit`** by `tools/scratch_B_compute.py` (raw CSV read with
`encoding="gbk"`, then the formula above).

### 3b. Line 1 — `0.2,BoneVRepeat,128,257,95,0,180,8,120`

`start_x=128, start_y=257, height=95, direction=0, speed=180, count=8, spacing=120`
`cos(0°)=1`, so `X_i = 128 - 120*i`:

| i | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| **X** | **128** | **8** | **−112** | **−232** | **−352** | **−472** | **−592** | **−712** |
| Y | 257 | 257 | 257 | 257 | 257 | 257 | 257 | 257 |

### 3c. Line 2 — `0,BoneVRepeat,503,257,95,2,180,8,120`

`start_x=503, start_y=257, height=95, direction=2, speed=180, count=8, spacing=120`
`cos(2*90°)=cos(180°)=-1`, so `X_i = 503 - (-1)*120*i = 503 + 120*i`:

| i | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| **X** | **503** | **623** | **743** | **863** | **983** | **1103** | **1223** | **1343** |
| Y | 257 | 257 | **256** | **256** | **256** | **256** | **256** | **256** |

The `Y` transition from 257 to 256 on this line is a genuine engine quirk, not an error in the
table: `sin(180°) = 1.2246e-16` (not exactly 0), so `Y_i = 257 - 1.2246e-16*120*i` evaluates to
just *under* 257 for `i >= 2`, and `int()` truncates toward zero → **256**. Measured directly in
the live engine (§5). It is a 1 px difference on one line and is almost certainly harmless, but it
is a real asymmetry if the model floors instead of truncating.

---

## 4. Hotspot / anchor: does `bbox.left == x`?

**Yes — for `BoneV`, `bbox.left == x` exactly. The sprite anchors top-left.**

Four independent pieces of evidence:

**(a) `BoneV` is not a Sprite at all — it is a NinePatch.** `repo_badtime/Bad Time Simulator
(Sans Fight).caproj` line 541:

```xml
<object-type name="BoneV" sid="3868174782291034">
    <plugin id="NinePatch" />
    <texture />
</object-type>
```

(For contrast, other objects read `<plugin id="Sprite" />`, e.g. `GasterBlaster` at line 563.)
So there is no sprite "hotspot" in the animation-frame sense to worry about.

**(b) Its initial instance record has hotspot `(0, 0)`.** `data.js` line 429:

```js
["t31", 0, false, [2353520185577067, 8541710245044527, 6677681737098705, 6030229564139285, 821640292253391], 0, 0, ["images/bonev.png", 221, 0], null, [], false, false, 3868174782291034, [], null],
```

The `3868174782291034` SID ties `t31` to the `BoneV` object type above. Its initial-instance world
record is `[0, 0, 0, 0, 0, 0, 0, 1, 0, 0, …]`, i.e.
`x=0, y=0, z=0, width=0, height=0, depth=0, angle=0, opacity=1, hotspotX=0, hotspotY=0`
(field order read off `c2runtime.js:5820–5830`: `inst.hotspotX = wm[8]; inst.hotspotY = wm[9];`).

**(c) `hotspotX/Y` are never assigned for NinePatch anywhere in the runtime.** Every assignment in
`c2runtime.js` is inside a Sprite/World path or from an animation frame:

```
19247: frameobj.hotspotX = frame[7];      // Sprite frame objects only
19365: this.hotspotX = curanimframe.hotspotX;
19451: this.hotspotX = this.curFrame.hotspotX;
19600: this.hotspotX = next_frame.hotspotX;
 5828: inst.hotspotX = wm[8];             // world start-up instances (uses the 0 above)
 7519: inst.hotspotX = world.hasOwnProperty("hX") ? world["hX"] : 0.5;   // non-world instances
```

NinePatch has no animation frames (`data.js` gives it `null` for the animations slot), so none of
the `19xxx` lines can run for it; the value stays at the `0` from line 5828.

**(d) The generic bbox computation therefore yields `bbox.left == x`.** `c2runtime.js:13715–13716`:

```js
bbox.set(this.x, this.y, this.x + this.width, this.y + this.height);
bbox.offset(-this.hotspotX * this.width, -this.hotspotY * this.height);
```

With `hotspotX = 0`, the offset is `-0`, so `bbox.left = x` and `bbox.top = y`.

Confirmation from the compiled NinePatch draw path (`c2runtime.js:19036`):
`var drawX = -(this.hotspotX * this.width);` — with `hotspotX = 0` the quad is drawn starting at
the instance's own x, again top-left. Also `CombatZoneClipped` has `scale = 1`, `parallaxX = 1`,
`parallaxY = 1` (verified live and in `data.js:777`), so layout space and canvas space coincide:
**absolute canvas x == instance x**.

The model's `tools/check_repeat_culling.py` already assumes `abs = local + C2_LEFT`, i.e. it treats
`x0` as an absolute top-left anchor (line 69: `xi_local = (x0 - cosv*spacing*i) - C2_LEFT`). That
matches the source.

---

## 5. Live engine confirmation (same binaries as above)

I drove the actual compiled export in a headless Chrome over CDP, called the game's own
`BoneVRepeat` with the exact CSV argument vectors, and read back every created `t31` — calling from
*inside* the wrapped tick so positions are captured at the spawn instant (age 0 ticks).

Raw probe output (`tools/scratch_B_spawn.mjs`):

```
================ SPAWN-INSTANT (age = 0, inside the tick) ================

### L1  dir0 start_x=128   args=[128,257,95,0,180,8,120]
created=8
  i    x          y      h    bbox.left  bbox.top   hot
  0        128    257    95        128      257   0,0
  1          8    257    95          8      257   0,0
  2       -112    257    95       -112      257   0,0
  3       -232    257    95       -232      257   0,0
  4       -352    257    95       -352      257   0,0
  5       -472    257    95       -472      257   0,0
  6       -592    257    95       -592      257   0,0
  7       -712    257    95       -712      257   0,0
  x list:    [128,8,-112,-232,-352,-472,-592,-712]
  bbox.left: [128,8,-112,-232,-352,-472,-592,-712]
  deltas:    [-120,-120,-120,-120,-120,-120,-120]

### L2  dir2 start_x=503   args=[503,257,95,2,180,8,120]
created=8
  i    x          y      h    bbox.left  bbox.top   hot
  0        503    257    95        503      257   0,0
  1        623    257    95        623      257   0,0
  2        743    256    95        743      256   0,0
  3        863    256    95        863      256   0,0
  4        983    256    95        983      256   0,0
  5       1103    256    95       1103      256   0,0
  6       1223    256    95       1223      256   0,0
  7       1343    256    95       1343      256   0,0
  x list:    [503,623,743,863,983,1103,1223,1343]
  bbox.left: [503,623,743,863,983,1103,1223,1343]
  deltas:    [120,120,120,120,120,120,120]
```

Movement rule, measured over 151 engine ticks (`tools/scratch_B_why.mjs`):

```
tick 1  uid135 x=131.0059999999995   (spawned at 128  -> +3.006 px/tick, moving RIGHT)
tick 2  uid135 x=134.01199999999898  (+3.006)
tick 1  uid143 x=499.99400000000054  (spawned at 503  -> -3.006 px/tick, moving LEFT)
```

180 px/s at 60 engine fps = 3.0 px/tick; the ~0.006 offset is the engine's sub-pixel position
quantisation (x-coordinates land on a 1/167 grid, consistent with the 640 px viewport scale).
Signs match `direction 0 → +x`, `direction 2 → −x`, as the model's `_calc_velocity` assumes.

**This is a direct, empirical refutation of the "plus" hypothesis:** the live engine produced
`8, -112, -232, …` for line 1 and `623, 743, 863, …` for line 2. The `+` variant would have
produced `248, 368, 488, …` and `383, 263, 143, …` respectively — neither was observed.

---

## 6. Verdict

### **MINUS.** The model's `xi = start_x - cos(direction) * spacing * i` is correct.

The exact evidence, quoted:

> `Battle.xml:4698` — `<param id="1" name="Value">StartX - cos(Direction*90)*Spacing*loopindex</param>`

> `Battle.xml:4683-4684` — `<param id="1" name="Start index">0</param> <param id="2" name="End index">Count-1</param>`

> `data.js:6113` — `[7, [5, [23, "StartX"], [6, [6, [19, 85, [ [6, [23, "Direction"], [0, 90] ]], [23, "Spacing"] ], [19, 102] ]]]]` where `[5,…]` is subtract, `[19,85,…]` is `cos`, `[19,102]` is `loopindex`.

> Live engine, `BoneVRepeat(128,257,95,0,180,8,120)` → `x = [128, 8, -112, -232, -352, -472, -592, -712]`

**XML and compiled JS agree; no disagreement to report.** An offset such as
`CombatZone.BBoxLeft` or a hotspot correction is **not** present — the transform x is *exactly*
the loop value after `int()` truncation.

### Confidence

| Claim | Confidence | Basis |
|---|---|---|
| Formula is `minus` | **Very high** | Read in original XML **and** independently decoded from compiled bytecode **and** reproduced live |
| No extra offset is applied | **Very high** | `X`/`Y` are the only args to `BoneV`; `BoneV` sets transform x to `int(Param(0))` with no additive term |
| `bbox.left == x` (top-left anchor) | **High** | `hotspotX/Y = 0` in the instance record; no NinePatch hotspot assignment exists in the runtime; `update_bbox` uses `-hotspotX*width`; `bbox.left == x` confirmed live |
| The 8 x-values per line | **Very high** | Computed from source, then matched exactly by the live engine |
| `direction 2` drives x **upward**, not downward | **Very high** | `cos(180°) = -1`; live `[503, 623, …, 1343]` |
| `int()` truncates toward zero (not floor) | **High** | `c2runtime.js:12601` → `set_int`; live `-112` (not `-113`) at i=2 |

### One thing this analysis could **not** explain

The supplied empirical snapshot does not match **either** arithmetic:

```
21.49  141.49  249.51  261.49  369.51  381.49  489.51  609.51
Δ:     120     108.02   11.98   108.02   11.98   108.02   120
```

For `sans_bonegap1`, the only `h=95` bones are the two lines analysed above (verified by scanning
every `*.csv` for `BoneVRepeat` with `,95,`), so any `h=95` bone must lie on `128 − 120i` *or*
`503 + 120i` at spawn. A single group can therefore only ever show gaps of exactly 120; the
observed `108.02 / 11.98` sub-split is not producible by this formula. The same applies to the
second snapshot `0.5 120.5 240.5 390.5 510.5 630.5` (gaps 120, 120, **150**, 120, 120).

So I am **not** disputing that those numbers were observed, but I **cannot** attribute them to a
sign error in this formula — the sign is provably `-`, and the live engine reproducing the formula
to the digit rules out a `-`/`+` mistake. If the parent still needs that snapshot explained, the
open questions are: (i) which engine build/tick rate produced it (the live run quantises x to
`1/167`, i.e. integers here, whereas the snapshot shows `.49/.51`); (ii) whether the probe was
sampling a *different* attack or an interpolated/downscaled canvas coordinate. Those are outside
this task's source-analysis scope.

---

## 7. Reproduction

```powershell
# arithmetic only, no nohit import, reads the CSV as GBK
.venv\Scripts\python.exe tools\scratch_B_compute.py

# live: needs the export served on 8099 and Chrome with --remote-debugging-port=9444
#   http://127.0.0.1:8099/game/index.html  ==  c2-sans-fight/  (byte-identical)
node tools\scratch_B_spawn.mjs 9444     # spawn-instant x/y/bbox for both CSV lines
node tools\scratch_B_why.mjs  9444      # per-tick x, to measure speed sign per direction
node tools\scratch_B_direct.mjs 9444    # single-call diff of created instances
node tools\scratch_B_live2.mjs 8099 9444 sans_bonegap1 5   # end-to-end round trace
```

Files read for this report:

* `repo_badtime/Event sheets/Battle.xml` (lines 4492–4535, 4629–4720)
* `repo_badtime/Event sheets/Timeline.xml` (lines 204–356)
* `repo_badtime/Event sheets/AttackLoader.xml`
* `repo_badtime/Bad Time Simulator (Sans Fight).caproj` (line 541)
* `repo_badtime/Files/sans_bonegap1.csv`, `repo_badtime/Documentation/Attacks.md`
* `c2-sans-fight/data.js` (lines 429, 5828–5846, 6028–6139, 760–779)
* `c2-sans-fight/c2runtime.js` (lines 5818–5830, 12596–12608, 13693–13728, 18982–19001, 19036)
* `c2-sans-fight/sans_bonegap1.csv` (GBK)
* `nohit/baker/parser.py`, `nohit/baker/rasterizer.py`, `tools/align_live_bones.py`, `tools/check_repeat_culling.py`
