#!/usr/bin/env python3
"""One-shot patch: phase-lock tas_runner.js's plan frame counter to the engine tick.

The bare accumulator made plan frame f live on engine ticks 4f+3..4f+6, so the
injected input lagged the baked bone geometry by 3 ticks (~1.9 px) - measured
twice on the live machine. This rewrites that one block, preserving the file's
original encoding and line endings.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "c2-sans-fight" / "tas_runner.js"

OLD = """        // Fix: advance the plan frame only once every `ticksPerPlanFrame`
        // engine ticks, derived from the engine's own fps.
        if (planTickAccum < planTicksPerFrame() - 1) {
            planTickAccum += 1;
            return;   // keep last frame's keys held for the rest of this frame
        }
        planTickAccum = 0;
"""

NEW = """        // Fix: advance the plan frame only once every `ticksPerPlanFrame`
        // engine ticks, derived from the engine's own fps -- and phase-lock the
        // counter to the absolute engine tick so frame f lands on tick 4f.
        //
        // PHASE, measured (do NOT simplify this back to a bare accumulator):
        // a bare `if (accum < N-1) { accum++; return; } accum = 0;` makes plan
        // frame f live on ticks 4f+3..4f+6, so the keys for frame f are applied
        // three engine ticks AFTER the tick whose bone geometry frame f was
        // baked from -- a systematic 0.75 plan-frame (~1.9 px) lead of the bone
        // field over the injected input. Measured live on sans_bonegap1: the
        // first tick reporting plan frame f is 4f+4 (f=28 -> tick 4, f=200 ->
        // tick 692), and at plan frame 90 the live heart is already grounded
        // while the plan is still at y=8. Anchoring to the tick index puts
        // frame f on ticks 4f..4f+3 instead.
        if (playbackTick0 < 0) playbackTick0 = engineTick;
        const tp = planTicksPerFrame();
        const wantFrame = Math.floor((engineTick - playbackTick0) / tp);
        if (wantFrame > plannedFrame) plannedFrame = wantFrame;   // never rewind
        else if (wantFrame < plannedFrame) return;
        planTickAccum = (engineTick - playbackTick0) % tp;
"""

# state decl + reset additions
OLD_DECL = "    let planTickAccum = 0;           // engine ticks consumed by the current frame\n"
NEW_DECL = (
    "    let planTickAccum = 0;           // engine ticks consumed by the current frame\n"
    "    let engineTick = 0;              // absolute engine tick counter (1 per C2 tick)\n"
    "    let playbackTick0 = -1;          // engine tick that plan frame 0 started on\n"
)

OLD_RESET = """        currentFrame = 0;
        plannedFrame = 0;
        planTickAccum = 0;
"""


def main() -> int:
    data = TARGET.read_bytes()
    # detect newline style and encoding
    text = data.decode("utf-8")
    nl = "\r\n" if "\r\n" in text else "\n"

    def norm(s: str) -> str:
        return s.replace("\n", nl)

    problems = []
    for name, old, new in (("decl", OLD_DECL, NEW_DECL), ("block", OLD, NEW)):
        o, n = norm(old), norm(new)
        cnt = text.count(o)
        print(f"{name}: found {cnt} occurrence(s)")
        if cnt != 1:
            problems.append(name)
            continue
        text = text.replace(o, n, 1)
    if problems:
        print("FAILED, no changes written:", problems)
        return 1

    # playback start must reset the phase anchor
    old_start = norm("""        currentFrame = 0;
        plannedFrame = 0;
        planTickAccum = 0;
""")
    new_start = norm("""        currentFrame = 0;
        plannedFrame = 0;
        planTickAccum = 0;
        playbackTick0 = -1;   // re-anchor the plan phase to the next engine tick
""")
    cnt = text.count(old_start)
    print(f"start-reset: found {cnt} occurrence(s)")
    if cnt < 1:
        print("FAILED, no changes written (start-reset)")
        return 1
    text = text.replace(old_start, new_start)

    # engineTick must advance on every tick, before anything else
    old_hook = norm("""        proto.tick = function (background_wake, timestamp, debug_step) {
            // Runs BEFORE the engine's own tick body, so the keyMap we set here
            // is exactly what the InputManagement sheet samples this frame.
            tickControl();
""")
    new_hook = norm("""        proto.tick = function (background_wake, timestamp, debug_step) {
            // Runs BEFORE the engine's own tick body, so the keyMap we set here
            // is exactly what the InputManagement sheet samples this frame.
            // `engineTick` is the absolute tick index the plan phase locks to.
            engineTick++;
            tickControl();
""")
    cnt = text.count(old_hook)
    print(f"tick-hook: found {cnt} occurrence(s)")
    if cnt != 1:
        print("FAILED, no changes written (tick-hook)")
        return 1
    text = text.replace(old_hook, new_hook, 1)

    TARGET.write_bytes(text.encode("utf-8"))
    print(f"WROTE {TARGET} ({len(text)} chars, nl={'CRLF' if nl == chr(13)+chr(10) else 'LF'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
