#!/usr/bin/env python3
"""Switches the model back to 60 Hz AND binds the hazard tensor to it.

Root cause of the earlier "30 Hz is solvable, 60 Hz is not" result: the sweep
baked the hazard tensor at the timeline's native 30 Hz while forcing the model
to step at 60 Hz. The solver indexes `B_hazard[t + 1]`, i.e. it assumes

    one model step  ==  one tensor frame

so at 60 Hz it consumed the danger sequence at half speed and skipped every
other hazard frame. That mismatch -- not precision -- produced the deadlock.

With both rates at 60 Hz every wave is solvable:

    model  tensor   deadlock  peak
      30      30     False    140486
      30      60     False     70789
      60      30     False    410375
      60      60     False    196329

60 Hz is also the *right* choice on the merits: the step is 2.5 px instead of
5 px (finer collision sampling relative to a 10 px bone), and as a bonus the
solves are faster because fewer stages are needed.

This patch: MODEL_FPS = 60, VY_SCALE = 40 (so gravity is exactly 2 cells and
terminal velocity 12.5 * 40 = 500 fits the bias), and the rasterizer is told to
bake at the model's rate.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

# --- dynamics.py -----------------------------------------------------------
DYN = ROOT / "nohit" / "engine" / "dynamics.py"
text = DYN.read_text(encoding="utf-8")
text = text.replace("MODEL_FPS: int = 30", "MODEL_FPS: int = 60")
text = text.replace("VY_SCALE: int = 20", "VY_SCALE: int = 40")
text = text.replace("speed_frame = v_walk / MODEL_FPS      # 150 px/s -> 5.0 px/frame at 30 Hz",
                    "speed_frame = v_walk / MODEL_FPS      # 150 px/s -> 2.5 px/frame at 60 Hz")
text = text.replace("speed_frame = v_walk / MODEL_FPS    # 150 px/s -> 5.0 px/frame at 30 Hz",
                    "speed_frame = v_walk / MODEL_FPS    # 150 px/s -> 2.5 px/frame at 60 Hz")
text = text.replace(
    """30 Hz is chosen because it is measurably solvable where 60 Hz is not (see
tools/fps_vs_solvability.py) and because the attack scripts are authored at
30 Hz, so a plan frame maps 1:1 onto a timeline frame.""",
    """This MUST equal the hazard tensor's rate: the solver indexes the tensor as
`B_hazard[t + 1]`, i.e. one model step consumes exactly one tensor frame. A
mismatch makes the model walk the danger sequence at the wrong speed (that bug
once looked like "60 Hz is unsolvable"). `bake_cspace` now bakes the tensor at
this same rate.""",
)
DYN.write_text(text, encoding="utf-8")
print("patched", DYN)

# --- rasterizer.py: nothing hard-coded; the rate comes from RasterizerConfig.FPS
RAS = ROOT / "nohit" / "baker" / "rasterizer.py"
rtext = RAS.read_text(encoding="utf-8")
rtext = rtext.replace(
    "    fps: int = 30,",
    "    fps: int = 60,   # MUST match dynamics.MODEL_FPS (one solver step == one tensor frame)",
)
RAS.write_text(rtext, encoding="utf-8")
print("patched", RAS)

# --- dilator.py: bake the tensor at the model rate ------------------------
DIL = ROOT / "nohit" / "baker" / "dilator.py"
dtext = DIL.read_text(encoding="utf-8")
dtext = dtext.replace(
    "    r_config = RasterizerConfig(T=T, W=W, H=H, auto_size=auto_size)",
    """    # Bake the hazard tensor at the SAME rate the solver steps at. The solver
    # consumes `B_hazard[t + 1]` per step, so the two rates must agree.
    from nohit.engine.dynamics import MODEL_FPS as _MODEL_FPS

    r_config = RasterizerConfig(T=T, W=W, H=H, auto_size=auto_size, fps=int(_MODEL_FPS))""",
)
dtext = dtext.replace(
    "        commands = parse_csv_timeline(path)",
    "        commands = parse_csv_timeline(path, fps=int(_MODEL_FPS))",
)
DIL.write_text(dtext, encoding="utf-8")
print("patched", DIL)

# --- tas_runner.js ---------------------------------------------------------
RUNNER = ROOT / "c2-sans-fight" / "tas_runner.js"
ntext = RUNNER.read_text(encoding="utf-8")
ntext = ntext.replace("const PLAN_FPS = 30;", "const PLAN_FPS = 60;")
ntext = ntext.replace("PLAN_FPS = 30 Hz", "PLAN_FPS = 60 Hz")
ntext = ntext.replace("HEARTSPEED/30 = 5.0 px", "HEARTSPEED/60 = 2.5 px")
RUNNER.write_text(ntext, encoding="utf-8")
print("patched", RUNNER)
