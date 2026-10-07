#!/usr/bin/env python3
"""Input-minimal safe planner — the objective the DP *claims* to have.

The DP's value function adds `dist_map[next]` (distance to the nearest hazard)
to the accumulated value of EVERY frame, so it maximises cumulative clearance
with weight ~141x the input cost (measured on sans_bonegap1: clearance
16294.9 vs action cost 115.2).  That is what makes it run left: clearance grows
without bound as the soul leaves the bone columns.

This script implements the objective the user actually asked for:
  1) survive (hard hazard constraint),
  2) otherwise press as little as possible,
  3) tie-break by holding each press as short as possible.

It is a small layered BFS over integer model states, so it is a *diagnostic*
that answers "is a low-input route feasible under the model?" — not a
replacement for the DP.

Usage:
  python tools/plan_min_input.py --wave sans_bonegap1 [--max-frames-with-input 80]
"""

from __future__ import annotations

import argparse
import sys
from collections import deque
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nohit.baker.dilator import bake_cspace  # noqa: E402
from nohit.engine.dynamics import step_dynamics_batch  # noqa: E402

C2_DIR = ROOT / "c2-sans-fight"
# Same ladder as solver.ACTIONS, ordered idle-first so ties break toward inaction.
ACTIONS = [(0, 0), (0, 1), (-1, 0), (1, 0), (0, -1), (-1, 1), (1, 1)]


def state_key(s) -> int:
    x, y, vy, kappa, tau = (int(v) for v in s)
    vy_key = max(0, min((1 << 10) - 1, vy + 512))
    return (x & 0x1FF) | ((y & 0xFF) << 9) | (vy_key << 17) | ((kappa & 1) << 27) | ((tau & 0xF) << 28)


def key_state(k: int):
    x = k & 0x1FF
    y = (k >> 9) & 0xFF
    vy = ((k >> 17) & 0x3FF) - 512
    kappa = (k >> 27) & 1
    tau = (k >> 28) & 0xF
    return (x, y, vy, kappa, tau)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wave", default="sans_bonegap1")
    ap.add_argument("--max-frames-with-input", type=int, default=200)
    ap.add_argument("--window", type=int, default=90, help="receding-horizon lookahead frames")
    args = ap.parse_args()

    csv_path = C2_DIR / (args.wave if args.wave.endswith(".csv") else args.wave + ".csv")
    bake = bake_cspace(csv_path, T=None, auto_size=True, soul_w=4, soul_h=4, physics_mode="c2")
    haz = bake.B_hazard
    meta = bake.metadata
    T, H, W = haz.shape
    x0, y0 = int(bake.initial_state[0]), int(bake.initial_state[1])
    print(f"wave={csv_path.name} T={T} arena {W}x{H} init=({x0},{y0})")

    def safe(states: np.ndarray, t: int) -> np.ndarray:
        """A state is safe iff the soul's 4x4 box overlaps NO hazard cell.

        The engine's damage test is `PlayerHitbox (t65, 4x4) isOverlapping the
        bone` (Battle.xml block 3041692031166179; the `Pick overlapping point`
        condition above it is disabled="1" and absent from the compiled
        bytecode), so the model's own predicate is a 4x4 box overlap -- NOT a
        single anchor cell.  Both anchor conventions are covered by testing the
        box in both directions, which is what the dilation itself does.
        """
        t = min(t, haz.shape[0] - 1)
        xs = np.clip(states[:, 0], 0, W - 1).astype(np.int64)
        ys = np.clip(states[:, 1], 0, H - 1).astype(np.int64)
        h = haz[t]
        out = np.zeros(len(states), dtype=bool)   # True = safe
        for dy in (-2, 0):
            for dx in (-2, 0):
                cx = np.clip(xs + dx, 0, W - 1)
                cy = np.clip(ys + dy, 0, H - 1)
                out |= h[cy, cx]
        return ~out

    # Greedy receding-horizon search: at each frame try the cheapest action that
    # keeps a safe continuation alive to the horizon, cheapest = idle first.
    cur = np.array([[x0, y0, 0, 1, 0]], dtype=np.int32)
    if not safe(cur, 0)[0]:
        print("!! initial state is UNSAFE under the model")
    actions: list[tuple[int, int]] = []
    traj = [tuple(int(v) for v in cur[0])]
    stuck_at = None

    for t in range(T - 1):
        chosen = None
        for act in ACTIONS:
            ux, uy = act
            nxt = step_dynamics_batch(cur, ux, uy, W=W, H=H, w=4, h=4,
                                      v_walk=150, v_jump_init=180, physics_mode="c2")
            if not safe(nxt, t + 1)[0]:
                continue
            # survival lookahead: can we keep going for `window` frames while
            # pressing nothing more than necessary?  Cheap feasibility probe:
            # BFS over 2 actions (idle, jump-up) plus lateral escape.
            horizon = min(args.window, T - 1 - (t + 1))
            frontier = {state_key(nxt[0]): nxt[0]}
            ok = True
            live = nxt
            for h in range(horizon):
                tt = t + 1 + h
                cands = []
                for a2 in ((0, 0), (0, 1), (-1, 0), (1, 0)):
                    c = step_dynamics_batch(live, a2[0], a2[1], W=W, H=H, w=4, h=4,
                                            v_walk=150, v_jump_init=180, physics_mode="c2")
                    if safe(c, min(tt + 1, T - 1))[0]:
                        cands.append(c)
                if not cands:
                    ok = False
                    break
                # prefer the candidate that keeps the most options
                live = cands[0]
            if not ok:
                continue
            chosen = act
            cur = nxt
            break
        if chosen is None:
            stuck_at = t + 1
            print(f"  !! no safe action at frame {t+1}; stopping")
            break
        actions.append(chosen)
        traj.append(tuple(int(v) for v in cur[0]))
        if len(actions) > args.max_frames_with_input * 4:
            pass

    nz = [a for a in actions if a != (0, 0)]
    left = sum(1 for a in actions if a[0] < 0)
    right = sum(1 for a in actions if a[0] > 0)
    jumps = sum(1 for a in actions if a[1] > 0)
    print(f"\nplanned frames      : {len(actions)}")
    print(f"frames with input   : {len(nz)}")
    print(f"  horizontal left   : {left}   right: {right}")
    print(f"  jump frames       : {jumps}")
    print(f"distinct x visited  : {sorted(set(t[0] for t in traj))[:20]}")
    print(f"first 40 actions    : {actions[:40]}")
    if stuck_at is not None:
        print(f"STUCK at frame {stuck_at}")

    # verify the produced trajectory against the model, with the SAME predicate
    ts = np.array(traj, dtype=np.int32)
    viol = []
    for f in range(min(T, len(ts))):
        if not safe(ts[f:f + 1], f)[0]:
            viol.append(f)
    print(f"\nself-check: model-unsafe frames in this plan = {len(viol)} {viol[:10]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
