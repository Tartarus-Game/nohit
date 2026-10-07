#!/usr/bin/env python3
"""VERIFY_C scratch: emit tools/VERIFY_C_solver_bias.md.

The long repeated action strings are generated programmatically (never typed) so
the raw evidence in the report is exact.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tools" / "VERIFY_C_solver_bias.md"

A_LEFT149 = ";".join(["-1,0"] * 149)
A_IDLE149 = ";".join(["0,0"] * 149)
A_LEFT19 = ";".join(["-1,0"] * 19)

DOC = f"""# VERIFY_C — solver left-bias audit (`nohit/engine/solver.py`, `solve_lattice_dp`)

Audit scope: is the 5D lattice DP systematically biased toward moving LEFT (or toward low x),
independently of the hazard map? Evidence is raw numbers + quoted code only. **No file under
`nohit/` was modified by this audit**; every experiment lives in `tools/scratch_C_*`.

---

## 0. Version warning — `solver.py` changed *during* this audit

| | bytes | lines | mtime | sha256 (first 16) |
|---|---|---|---|---|
| **audit-start revision** ("handed") | 19216 | 486 | (on disk when this audit began) | `40d60d96b70f54f4` (frozen copy) |
| **live revision** at 03:36+ | 21013 | 516 | 2026-10-04 03:34:31 | `02b8926322514947` |

`nohit/engine/solver.py` was rewritten by another process at **03:34:31**, i.e. mid-audit
(19216 -> 21013 bytes). I did not make that change. To keep the audit reproducible I froze the
audit-start revision as `tools/scratch_C_solver_handed.py` and verified the freeze by byte count:

```
live bytes : 21013  sha256: 02b892632251494779dc291e855f903f33f50faf519e48365677b69426ac00bb
restored bytes: 19216  (audit-start revision was 19216)
restored lines: 486
sha256     : 40d60d96b70f54f481bec1df382c62b2792a169a0a95bc2945e575749345c66d
byte-size match with audit-start revision: True
```

A full side-by-side read of both revisions shows the **only** difference is the no-hazard
`else:` dedup block (handed lines 405-412 vs live lines 405-442) plus its comment. Everything
else — the action set, the objective, the hazard branch, the terminal selection and the
backtracking loop — is identical. Line numbers below refer to the **audit-start revision**
unless marked "live".

---

## 1. What the solver does (audit-start revision)

### 1.1 Action set

`nohit/common/constants.py:101-115`:

```python
ACTION_LEFT_RELEASE: int = 0   # (-1, 0)
ACTION_LEFT_HOLD: int = 1      # (-1, 1)
ACTION_NONE_RELEASE: int = 2   # ( 0, 0)
ACTION_NONE_HOLD: int = 3      # ( 0, 1)
ACTION_RIGHT_RELEASE: int = 4  # (+1, 0)
ACTION_RIGHT_HOLD: int = 5     # (+1, 1)

ACTIONS: list[tuple[int, int]] = [
    (-1, 0), (-1, 1), (0, 0), (0, 1), (1, 0), (1, 1),
]
```

=> **`(-1,0)` [LEFT] is index 0, `(+1,0)` [RIGHT] is index 4.** Every candidate array in the DP
is ordered action-index-minor (solver.py:272-277):

```python
rep_states = np.repeat(curr_states, 6, axis=0)
rep_packed = np.repeat(curr_packed, 6)
rep_vals   = np.repeat(curr_vals, 6)
rep_act_idx = np.tile(act_indices, N)      # act_indices = np.arange(6)
rep_ux = actions_arr[rep_act_idx, 0]       # actions_arr = np.array(ACTIONS, dtype=np.int8)
```
so for one parent state the child candidates sit in the order LEFT, LEFT+jump, IDLE, IDLE+jump,
RIGHT, RIGHT+jump.

### 1.2 Objective / reward terms

```python
ACT_COST_HORIZONTAL: float = 0.75     # solver.py:54
ACT_COST_JUMP: float = 1.0            # solver.py:55
...
act_cost = np.abs(rep_ux[safe]) * ACT_COST_HORIZONTAL + rep_uy[safe] * ACT_COST_JUMP   # :384
```

* **Hazard branch (`has_hazards == True`), solver.py:386-389** — value = cumulative clearance
  minus input cost:
  ```python
  dist_scores = dist_map[t + 1, val_states[:, 1], val_states[:, 0]]
  cand_vals = rep_vals[safe] + dist_scores - act_cost
  ```
* **No-hazard branch (`has_hazards == False`), solver.py:405-412** — value carries **no term at
  all**; `act_cost` computed on line 384 is never used:
  ```python
  else:
      # Open arena: no obstacles at all, so there is nothing to trade off
      # and every survivor is equally safe. Keep the high-throughput
      # dedup path (the min-action sort here cost ~40% of the whole solve
      # on the open-arena benchmarks while changing nothing meaningful).
      cand_vals = rep_vals[safe]
      unq_packed, best_idx = np.unique(val_packed, return_index=True)
      curr_vals = cand_vals[best_idx]
  ```
  (This contradicts the comment block at solver.py:375-378, which claims "the action penalty is
  applied to BOTH branches".)
* **Fast path for a provably empty arena, solver.py:221-241** — no DP at all; returns a fabricated
  stationary witness `action_sequence=[(0, 0)] * (T - 1)`, `trajectory=[(x0, y0, vy0, kappa0, tau0)] * T`,
  `peak_alive_states=1`, `total_states_explored=1`. Skipped when any hazard exists, when
  `B_blue`/`B_orange` is present, or when `slam_frames` is non-empty.

### 1.3 How `dist_map` is used

```python
has_hazards = bool(np.any(B_hazard))                       # :192
if has_hazards:
    import scipy.ndimage
    dist_map = np.empty((T, H, W), dtype=np.float32)
    for t_idx in range(T):
        if np.any(B_hazard[t_idx]):
            dist_map[t_idx] = scipy.ndimage.distance_transform_edt(~B_hazard[t_idx])
        else:
            dist_map[t_idx] = 100.0                        # :192-202
else:
    dist_map = None
```

`dist_map` is consumed **only** on line 388, i.e. only in the hazard branch. In an arena with no
hazardous cell anywhere it is `None` and the valued objective disappears completely. (A
hazard-free *frame* inside an otherwise hazardous wave contributes a flat `+100` to every
candidate of that frame, which is a constant offset per path and does not influence ranking.)

### 1.4 `pack_state` / dedup and tie-breaking

`nohit/engine/state.py:98-125,128-170` — 32-bit key, x in the LOW 9 bits:

```
bits  0..8  : x          (9 bits)          <-- least significant field
bits  9..16 : y
bits 17..26 : vy + 500
bit  27     : kappa
bits 28..31 : tau
```

Measured keys for landed floor states `(x, 0, 0, 1, 0)` — monotone in x:

```
x=  0  key= 199753728      x=117  key= 199753845
x=  3  key= 199753731      x=174  key= 199753902
x= 50  key= 199753778      x=320  key= 199754048      x=341 key= 199754069
```

Dedup:

* hazard branch (:391-404): candidates are sorted by the uint64 `(key << 32) | inv_value`
  combo and the first row per key is kept, i.e. **the highest-value parent wins** — the action
  index does not decide;
* no-hazard branch (:411): `np.unique(val_packed, return_index=True)` keeps the **first
  occurrence in the candidate array**, and that array is parent-major / action-index-minor
  (:272-277). The first occurrence of a child key is therefore produced by the **lowest action
  index that can reach it — LEFT (index 0) whenever LEFT reaches it**.

Micro-demonstration (`tools/scratch_C_dedup_demo.py`), parent state `(x=0, y=0, vy=0, kappa=1, tau=0)`:

```
cand[0] action=(-1, 0) -> state (0, 0, 0, 1, 0) key=199753728   <-- LEFT
cand[1] action=(-1, 1) -> state (0, 8, 8, 0, 1) key=335024128
cand[2] action=(0, 0)  -> state (0, 0, 0, 1, 0) key=199753728   <-- IDLE, identical key
cand[3] action=(0, 1)  -> state (0, 8, 8, 0, 1) key=335024128
cand[4] action=(1, 0)  -> state (3, 0, 0, 1, 0) key=199753731
cand[5] action=(1, 1)  -> state (3, 8, 8, 0, 1) key=335024131

np.unique(return_index=True) kept: index 0 -> (-1,0) state (0,0,0,1,0)
                                   index 1 -> (-1,1) state (0,8,8,0,1)
                                   index 4 -> ( 1,0) state (3,0,0,1,0)
                                   index 5 -> ( 1,1) state (3,8,8,0,1)
```

At the `x = 0` clamp the LEFT and IDLE actions are the *same physical transition*, and the dedup
keeps the LEFT one. (At parent x=174 and x=3 all six children are distinct, so no tie exists away
from a wall.) The mirror clamp at `x = W - w` (docs) / `W - 1` (c2) collapses RIGHT with IDLE as
well, but there IDLE (index 2) beats RIGHT (index 4). The two walls therefore resolve the *same*
physical transition differently: **left wall -> LEFT (index 0), right wall -> IDLE (index 2)** —
a one-sided artefact of the action ordering.

### 1.5 Terminal selection and backtracking

```python
# 7. Feature 16: Linear O(T) Backtracking along P
best_term_idx = int(np.argmax(curr_vals))          # :448
curr_target = curr_packed[best_term_idx]
traj_packed = [curr_target]
actions_rev: List[Tuple[int, int]] = []

for t_step in range(T - 2, -1, -1):                # :453-459
    idx = np.searchsorted(P_keys[t_step], curr_target)
    p_act = P_actions[t_step][idx]
    p_par = P_parents[t_step][idx]
    actions_rev.append(ACTIONS[p_act])
    traj_packed.append(p_par)
    curr_target = p_par
```

`curr_packed` is sorted ascending by packed key (`np.unique` in the no-hazard branch; the combo
argsort in the hazard branch). `np.argmax` returns the **first** index attaining the maximum, so
**on ties the state with the smallest packed key wins**, and because x is the least-significant
field the tie-break is "smallest x" among states that share `(tau, kappa, vy, y)`.

Verbatim replication of the forward pass + backtrack (`tools/scratch_C_dp_probe.py`, audited code
copied unchanged), featureless arena, T=150, x0=174:

```
step 148 -> frame 149: alive=   208 x_range=[0,341] min_key=(0, 0, 0, 1, 0) sorted=True init_alive=True curr_vals_all_zero=True

terminal: argmax(curr_vals)=0 of 208  curr_vals[0]=0.0 max=0.0 all_equal=True
  curr_packed[0]      = (0, 0, 0, 1, 0)
  curr_packed[argmax] = (0, 0, 0, 1, 0)
  final alive x range = [0, 341]  n=208
```

At T=20 the same probe reports `alive=39 x_range=[117,231] min_key=(117,0,0,1,0)`, `argmax=0`,
terminal `(117,0,0,1,0)` — i.e. the **leftmost state reachable by the horizon**, not a physically
preferred one.

Note also that the backtracking never checks that the chain reaches the initial state: for a key
absent from `P_keys[t_step]`, `np.searchsorted` silently returns an insertion index and the walk
continues with an unrelated row. In every run reported below the chain did start at the initial
state (max |solver trajectory - replay| = 0), so this is a latent robustness gap rather than an
observed failure.

---

## 2. Featureless arena — raw results

Setup exactly as specified: `B_hazard = np.zeros((150, 114, 349), dtype=bool)`,
`initial_state = (x0, 0)`, `metadata = {{"slam_frames": [148]}}` (forces the DP; without
`slam_frames` the fast path of §1.2 short-circuits — verified on **both** revisions with
`metadata={{}}`: `peak_alive_states=1`, `total_states_explored=1`, `alive_states_history` all 1,
fabricated all-IDLE witness of length 149, x constant at 174). Both `solve_lattice_dp`
revisions were run through `tools/scratch_C_bias_sweep.py`.

### 2.1 Audit-start revision ("handed", 19216 bytes)

| x0 | action_sequence | L / R / idle | x trajectory (RLE) | terminal state | replay | max abs diff |
|---|---|---|---|---|---|---|
| 50 | `(-1,0) x 149` | **149 / 0 / 0** | `50,47,...,2,0` then `[0 x 133]` | `(0,0,0,1,0)` | PASS | 0 |
| 174 | `(-1,0) x 149` | **149 / 0 / 0** | `174,171,...,3,0` (f=58) then `[0 x 92]` | `(0,0,0,1,0)` | PASS | 0 |
| 320 | `(-1,0) x 149` | **149 / 0 / 0** | `320,317,...,2,0` (f=106) then `[0 x 43]` | `(0,0,0,1,0)` | PASS | 0 |

Raw action string (identical for x0 = 50, 174 and 320; `tools/scratch_C_feat_handed_*.txt`):

```
{A_LEFT149}
```

`action RLE = [[[-1,0],149]]` for all three; `peak_alive_states` = 16416 / 14904 / 11232;
solve wall time 1.3 s / 1.2 s / 3.1 s.

Shorter horizon (T=20, x0=174) — the bias is present from the first frames:

```
{A_LEFT19}
```
`action RLE = [[[-1,0],19]]`, x: 174 -> 117 (net -57), terminal `(117,0,0,1,0)`, replay PASS, max diff 0.

**Direction: LEFT in 149/149 frames from every start position; the terminal is pinned to the left
wall (x=0). Not one RIGHT action is ever emitted.**

### 2.2 Live revision (21013 bytes, written 03:34:31)

| x0 | action_sequence | L / R / idle | x trajectory | terminal state | replay | max abs diff |
|---|---|---|---|---|---|---|
| 50 | `(0,0) x 149` | 0 / 0 / **149** | `[50 x 150]` | `(50,0,0,1,0)` | PASS | 0 |
| 174 | `(0,0) x 149` | 0 / 0 / **149** | `[174 x 150]` | `(174,0,0,1,0)` | PASS | 0 |
| 320 | `(0,0) x 149` | 0 / 0 / **149** | `[320 x 150]` | `(320,0,0,1,0)` | PASS | 0 |

Raw action string (identical for all three):

```
{A_IDLE149}
```

**Direction: no drift at all.** The live revision replaced the first-occurrence dedup with a
cost-ranked `np.lexsort((combo, val_packed))` (live lines 428-442), so the only zero-cost route
(all-idle) wins outright and no tie reaches the terminal selection.

---

## 3. Verdict

**Is there a left bias? — Yes, in the audit-start revision, and it is confined to the no-hazard
(`else`) branch; it is absent from the hazard/`dist_map` branch that real waves use.**

### 3.1 Exact lines and mechanism (audit-start revision)

Two mechanisms combine; both are needed for the observed "run to the left wall and hold LEFT
there" witness:

**(A) Dedup tie-break keeps the LEFT parent — `solver.py:411`**

```python
unq_packed, best_idx = np.unique(val_packed, return_index=True)   # :411
```
`return_index` yields the first occurrence in the candidate array, and the candidate array is
built parent-major / action-index-minor (`:272-277`), with `ACTIONS[0] = (-1, 0)` = LEFT
(`constants.py:108-115`). At the `x=0` clamp LEFT and IDLE produce the *same* packed key
(measured: both `(0,0,0,1,0)` -> `199753728`), so the retained `(parent, action)` pair is the LEFT
one. Consequence: the witness presses LEFT while the heart is already against the wall and cannot
move further — 92 such frames in the T=150/x0=174 run.

**(B) Terminal tie-break picks the smallest x — `solver.py:448` with `:410`**

```python
cand_vals = rep_vals[safe]                    # :410  -> every survivor has value 0.0
...
best_term_idx = int(np.argmax(curr_vals))     # :448  -> first maximum
```
With all values tied, `np.argmax` returns 0, and `curr_packed` is sorted ascending by packed key
whose low 9 bits are x; the selected terminal is therefore the **leftmost reachable state**
(measured: `(0,0,0,1,0)` at T=150; `(117,0,0,1,0)` = the leftmost state reachable within 20
frames at T=20). The backtracking then walks back from that leftmost state, and mechanism (A)
labels each step LEFT.

Neither mechanism involves the hazard map, which is why the effect is identical from x0 = 50, 174
and 320 (net drift -50, -174, -320) and for T=20 and T=150.

### 3.2 Answer to "does the direction correlate with the `ACTIONS` ordering?"

**Yes, directly.** `(-1,0)` is index 0 and `(+1,0)` is index 4; the first-occurrence tie-break of
`:411` can only ever select the lower index, and the packed-key tie-break of `:448` selects
low x because x is the least-significant key field. The bias direction is an artefact of the
action ordering, not of the physics or the hazard map: reversing `ACTIONS` would make the same
code produce the mirrored (rightward) artefact.

### 3.3 The hazard (`dist_map`) branch is NOT left-biased

In the hazard branch the dedup is value-ranked (`:391-404`), so action index does not choose the
parent; the only residual tie-break is `:448`. The decisive control is the **mirror test** on the
real wave (§4.3): mirroring the bullet field mirrors the extracted plan exactly. The leftward run
on `sans_bonegap1` is therefore a consequence of the objective
`sum(dist_map clearance) - input cost` (`:386-389`), i.e. the solver walks to the region with the
largest clearance integral — not a bias toward low x.

---

## 4. `sans_bonegap1` — solver trajectory vs replayed trajectory

Config: `bake_cspace(c2-sans-fight/sans_bonegap1.csv, auto_size=True, soul_w=4, soul_h=4,
physics_mode="c2")` -> `W=349, H=114, initial_state=(174, 2)`, hazard density 0.161,
no blue/orange layer, `slam_frames=[]`. Replay through `nohit.verifier.replayer.replay_and_verify`
(independent scalar stepper), comparison over all 5 state components of every frame.

| revision | T | action RLE | L / R / idle | x RLE | replay | **max abs diff (5 comps)** |
|---|---|---|---|---|---|---|
| handed | 150 | `[[0,0],57],[[0,1],6],[[0,0],38],[[0,1],6],[[0,0],42]` | 0 / 0 / 149 | `[[174,150]]` | PASS | **0** |
| live | 150 | identical to handed | 0 / 0 / 149 | `[[174,150]]` | PASS | **0** |
| handed | 385 | see §4.2 | 87 / 0 / 297 | `[[174,92],...,[114,71],...,[54,73],...,[0,65]]` | PASS | **0** |
| live | 385 | identical to handed | 87 / 0 / 297 | identical | PASS | **0** |

### 4.1 T = 150 (the horizon used by the task's featureless spec)

Plan is 137 x `(0,0)` + 12 x `(0,1)`; the heart never leaves x=174. `max |sol.trajectory[f] -
replay[f]| = 0` for all 5 components, first differing frame: none. Same numbers from the
pre-rewrite run captured at the start of the audit (`tools/scratch_C_repro_out.txt`).

### 4.2 T = 385 (the default full-round horizon: `EndAttack = 6.4 s` -> `round(6.4*60)+1 = 385`)

This is the configuration that reproduces the reported symptom **exactly**:

```
x RLE: [[174,92],[172,1],[170,1],...,[116,1],[114,71],[112,1],...,[56,1],[54,73],...,[2,1],[0,65]]
action RLE: [[[0,0],54],[[0,1],6],[[0,0],31],[[-1,0],7],[[-1,1],9],[[-1,0],14],
             [[0,0],33],[[0,1],6],[[0,0],31],[[-1,0],7],[[-1,1],9],[[-1,0],14],
             [[0,0],34],[[0,1],6],[[0,0],32],[[-1,0],6],[[-1,1],8],[[-1,0],13],
             [[0,0],36],[[0,1],6],[[0,0],22]]
left/right/idle = 87 / 0 / 297      terminal = (0, 15, 24, 0, 2)
replay passed = True   max|sol.trajectory - replay| = 0   peak_alive = 122471
```

This matches the reported trajectory (92 idle frames at x=174, waypoints 114 / 54 / 0, final park
at the left wall — 65 frames in this run). Both revisions produce the **byte-identical** plan, so
the 03:34:31 rewrite does not change the real-wave behaviour.

### 4.3 The plan is dictated by the hazard geometry, not by a left bias — mirror control

Mirroring the baked tensor with `B_hazard[:, :, ::-1]` implements `x -> 348 - x`, which is an exact
involution of the reachable domain and **fixes the start (174, 2)**. `tools/scratch_C_mirror_test.py`,
audit-start revision, T=385:

```
ORIGINAL   : left/right/idle = 87 / 0 / 297   x[0], x[-1] = 174, 0     terminal (0,   15, 24, 0, 2)
X-MIRRORED : left/right/idle =  0 / 87 / 297  x[0], x[-1] = 174, 348   terminal (348, 15, 24, 0, 2)

MIRROR CHECK: mirrored-original action == mirrored-run action for 384/384 frames;
              mirrored-original x == mirrored-run x for 385/385 frames
```

A mirrored bullet pattern produces the exactly mirrored plan. Had the leftward run been a
structural preference for low x, the mirrored arena would still have run left; it runs right to
x=348 instead.

### 4.4 Other configurations checked (all `max |sol.trajectory - replay| = 0`)

* c2-baked tensors driven by the docs stepper (`metadata={{}}`): 16 left / 16 right / 117 idle —
  a symmetric left-right shuffle around x=174 (x oscillates 174 -> 150 -> 174 twice).
* Empty hazard tensor with c2 kinematics and `slam_frames` set (the shape a *failed bake* would
  produce): handed revision -> `left/right/idle = 149 / 0 / 0`, x runs 174 -> 0 by frame 87 then
  `[0 x 63]`, replay PASS. This is the only way I could produce "sans_bonegap1 runs to the left
  wall, replay PASS" on a *short* horizon, and it is produced by the §3.1 no-hazard mechanism, not
  by the hazard branch.

### 4.5 Why the replay check cannot see this

Every configuration above, including the left-wall run and the empty-tensor artefact, reports
`max |sol.trajectory - replay| = 0` and `passed = True`. The witness is a physically valid replay
of the *same* tensor the solver planned against, so solver-vs-replay agreement is not evidence
that the plan is sensible; with an empty/incorrect tensor it is guaranteed to pass. The
discriminators are (a) the plan itself (149/149 LEFT actions in an empty arena; 87/0/297 on the
wave), and (b) the mirror control of §4.3.

---

## 5. Reproduction

```powershell
# frozen audit-start revision vs live revision, featureless arena (T=150)
.\\.venv\\Scripts\\python.exe tools\\scratch_C_bias_sweep.py featureless handed 174 150 349 114
.\\.venv\\Scripts\\python.exe tools\\scratch_C_bias_sweep.py featureless live   174 150 349 114

# tie-break micro-demo and verbatim DP replication
.\\.venv\\Scripts\\python.exe tools\\scratch_C_dedup_demo.py
.\\.venv\\Scripts\\python.exe tools\\scratch_C_dp_probe.py 174 150 349 114

# sans_bonegap1 (canonical c2 bake), T=150 and full round T=385, both revisions
.\\.venv\\Scripts\\python.exe tools\\scratch_C_bias_sweep.py wave handed c2auto 150
.\\.venv\\Scripts\\python.exe tools\\scratch_C_bias_sweep.py wave live   c2auto 385
.\\.venv\\Scripts\\python.exe tools\\scratch_C_mirror_test.py handed 385
.\\.venv\\Scripts\\python.exe tools\\scratch_C_wave_emptyhyp.py handed 150
```

Evidence files: `tools/scratch_C_solver_handed.py` (frozen revision),
`tools/scratch_C_feat_handed_{{50,174,320}}.txt`, `tools/scratch_C_feat_live_{{50,174,320}}.txt`,
`tools/scratch_C_wave_handed_c2auto.txt`, `tools/scratch_C_wave_handed_c2auto_T385.txt`,
`tools/scratch_C_wave_live_c2auto_T385.txt`, `tools/scratch_C_wave_handed_docsmeta.txt`,
`tools/scratch_C_mirror_handed_385.txt`, `tools/scratch_C_repro_out.txt`,
`tools/scratch_C_actionstrings.txt`.

## 6. Bottom line

1. **Left bias: yes — audit-start revision, no-hazard branch only.** `solver.py:411`
   (`np.unique(..., return_index=True)`, first occurrence = lowest action index = `(-1,0)` LEFT,
   `constants.py:108-115`) decides *which action is recorded*; `solver.py:410` + `:448`
   (all-tied values -> `argmax` -> first row of a packed-key-sorted array, x in the low bits)
   decides *where the path ends* (the leftmost reachable state). Result: 149/149 LEFT actions from
   x0 = 50, 174 and 320, heart pinned at x = 0.
2. **The live revision (03:34:31) removes it** (cost-ranked `lexsort`, live lines 428-442): the
   same three tests yield 149 idle actions and zero drift.
3. **The hazard branch is not left-biased**: mirroring the bullet field mirrors the plan exactly
   (384/384 actions, 385/385 positions).
4. **`sans_bonegap1` trajectory vs replay: max absolute difference = 0** in every configuration
   tested (T=150 and T=385, both revisions, docs-stepper variant, empty-tensor variant). The
   left-wall plan observed at the full-round horizon T=385 (87 left / 0 right, ending at x=0) is
   reproduced, and the mirror control shows it is hazard-geometry driven, not a low-x preference.
"""


def main() -> int:
    OUT.write_text(DOC, encoding="utf-8")
    print("wrote", OUT, len(DOC.encode()), "bytes")
    assert "(-1,0) x 149" in DOC
    assert A_LEFT149.count("-1,0") == 149
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
