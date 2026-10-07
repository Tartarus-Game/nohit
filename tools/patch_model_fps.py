#!/usr/bin/env python3
"""Switches the model from 60 Hz to 30 Hz, driven by a single MODEL_FPS constant.

Motivation (measured, see tools/fps_vs_solvability.py):

    fps   stride   deadlock  at    peak
     30     5.0    False     None  10542     <- solvable
     60     2.5    True      117    7673
    120     1.2    True       77   11516

30 Hz is both solvable and matches the script timeline's native rate (the CSV
timestamps are 30 Hz: 0.2 s -> frame 6). At 30 Hz the authoritative constants
become whole numbers:

    step     = 150 px/s / 30 = 5.0   px/frame
    jump     = 180 px/s / 30 = 6.0   px/frame
    gravity  = 180 px/s^2 / 30^2 = 0.2 px/frame^2
    terminal = 750 px/s / 30 = 25.0  px/frame

The vy scale stays 40, so gravity is 0.2 * 40 = 8 cells exactly (still zero
quantisation error).

This patch replaces every hard-coded 60 in the c2 branch with MODEL_FPS.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DYN = ROOT / "nohit" / "engine" / "dynamics.py"

text = DYN.read_text(encoding="utf-8")

# 1. Introduce the constant right after VY_SCALE's definition block.
anchor = "GRAVITY_HOLD_FALLBACK: float = 180.0"
if "MODEL_FPS" not in text:
    text = text.replace(
        anchor,
        """MODEL_FPS: int = 30
\"\"\"The model's tick rate. The solver, the stepper and the extracted action
sequence all live at this rate; `tas_runner.js` converts it to engine ticks via
`rt.fps / PLAN_FPS`.

30 Hz is chosen because it is measurably solvable where 60 Hz is not (see
tools/fps_vs_solvability.py) and because the attack scripts are authored at
30 Hz, so a plan frame maps 1:1 onto a timeline frame.\"\"\"

""" + anchor,
        1,
    )

# 2. Replace the hard-coded 60s in the c2 branch (both scalar and batch).
subs = [
    ("dt_frames = 1.0 / 60.0", "dt_frames = 1.0 / MODEL_FPS"),
    ("speed_frame = v_walk / 60.0          # 150 px/s -> 2.5 px/frame",
     "speed_frame = v_walk / MODEL_FPS      # 150 px/s -> 5.0 px/frame at 30 Hz"),
    ("speed_frame = v_walk / 60.0        # 150 px/s -> 2.5 px/frame",
     "speed_frame = v_walk / MODEL_FPS    # 150 px/s -> 5.0 px/frame at 30 Hz"),
    ("jump_frame = v_jump_init / 60.0", "jump_frame = v_jump_init / MODEL_FPS"),
    ("jump_frame = float(v_jump_init) / 60.0", "jump_frame = float(v_jump_init) / MODEL_FPS"),
    ("if uy == 0 and vy_frames > 30.0 / 60.0:", "if uy == 0 and vy_frames > 30.0 / MODEL_FPS:"),
    ("            vy_frames = 30.0 / 60.0", "            vy_frames = 30.0 / MODEL_FPS"),
    ("cutoff = 30.0 / 60.0", "cutoff = 30.0 / MODEL_FPS"),
    ("down_speed = -vy_frames * 60.0", "down_speed = -vy_frames * MODEL_FPS"),
    ("max_fall_frame = 750.0 / 60.0", "max_fall_frame = 750.0 / MODEL_FPS"),
    ("vy_frames = np.maximum(-(750.0 / 60.0), vy_frames)",
     "vy_frames = np.maximum(-(750.0 / MODEL_FPS), vy_frames)"),
]

for old, new in subs:
    if old not in text:
        print(f"  !! MISS: {old.strip()[:66]}")
    text = text.replace(old, new)

DYN.write_text(text, encoding="utf-8")
print("patched", DYN)

# 3. tas_runner.js: PLAN_FPS 60 -> 30
RUNNER = ROOT / "c2-sans-fight" / "tas_runner.js"
rtext = RUNNER.read_text(encoding="utf-8")
rtext = rtext.replace(
    "const PLAN_FPS = 60;             // the solver's nominal tick rate",
    "const PLAN_FPS = 30;             // the solver's tick rate (matches MODEL_FPS in dynamics.py)",
)
rtext = rtext.replace(
    "// The solver plans at PLAN_FPS = 60 Hz: its per-frame displacement is\n"
    "        // HEARTSPEED/60 = 2.5 px. The export runs much faster (measured 240 fps,",
    "// The solver plans at PLAN_FPS = 30 Hz: its per-frame displacement is\n"
    "        // HEARTSPEED/30 = 5.0 px. The export runs much faster (measured 240 fps,",
)
RUNNER.write_text(rtext, encoding="utf-8")
print("patched", RUNNER)
