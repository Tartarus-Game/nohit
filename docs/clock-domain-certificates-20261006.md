# Configurable fixed-clock certificate experiment

`scratch/certify_clock_domains.py` compiles separate hypothetical literal-dt environments at 60, 120, or 240 Hz. It does not change the native clock, source scripts, running solver, or previous timestamp/literal-240 certificate artifacts. Time boundaries accept exact rational seconds, avoiding accidental sampling-phase differences.

## Multiple-substep containment

The previous diagnostic restricted CustomMovement to one substep. That restriction is unnecessary for the existing outward displacement envelope. In the source operator, the axis displacement `m=fl(v*dt)` is captured before stepping. Each candidate is `fl(start + fl(m*r))`, where `r=i/count` lies in `[0,1]`. On a collision, the restored coordinate uses the same expression with `r=(i-1)/count`, also in `[0,1]`.

Finite correctly rounded multiplication is monotone, so `fl(m*r)` lies between zero and `m`. The envelope computed from outward-rounded `±150*dt` and the outward-rounded addition therefore contains **every intermediate candidate and wall-stop fallback**, not just the final displacement. Cross-axis collision decisions change which candidate is selected but cannot place it outside that hull. The exact conditional-clamp interval proof remains unchanged. The experimental domain bounds dt by `1/30` and checks finite products, fixed red mode/arena, no platforms/slam/teleport, and no target/dialogue boundary.

`tests/unit/test_backward_red_certificate.py` now exercises 2,500 random/boundary four-tick paths at each of 60, 120 and 240 Hz, with arbitrary initial velocities in `[-150,150]` and new independent masks each physical tick. The 60 Hz run explicitly observes movement counts greater than one. Every complete-operator result lies within the predicted successor box. All **4 tests passed in 2.56 seconds**.

## Results

All use the same closed arena domain `[254,393] × [239,378]`, 0.125 cells, and complete conservative successor rectangles. The short interval is exactly `79/15` to `191/30` seconds, corresponding to the earlier 240 Hz ticks 1264→1528.

| Clock | Window | Result at start | First backward-empty layer |
|---|---|---|---|
| literal 60 Hz | 316→382, short interval | 9,328 retained cells: **unknown** | none |
| literal 120 Hz | 632→764, short interval | empty fixed-model domain | 632 = 5.266666… seconds |
| literal 60 Hz | 180→480, 3→8 seconds | empty fixed-model domain | 315 = 5.25 seconds |
| literal 120 Hz | 360→960, 3→8 seconds | empty fixed-model domain | 632 = 5.266666… seconds |

The short 60 Hz experiment does not supply a route: it starts one physical tick after the longer experiment's first empty layer and has a shorter terminal horizon. Extending the window eliminates that relaxed possibility. Thus merely changing the nominal clock to 60 Hz does not establish a solution to the current full opening model. The next useful audit is the original collision/geometry semantics around 5.25 seconds, together with actual runtime dt evidence.

Each result and full resulting grid is saved under `scratch/clock-domain-certificate-<fps>hz-<start>-<stop>.{json,npz}` with source, phase, helper and environment hashes. The two short runs took about 6.8 seconds each; the long runs took 28.4 and 27.1 seconds.

These are conditional certificates about separately compiled fixed models. Empty results are not original-game UNSAT claims. Nonempty conservative sets are unknown, not feasible paths, native acceptance, or authorization to silently replace the game's time protocol.
