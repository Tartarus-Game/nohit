# Round 4: original Normal and Haoge Sans

## What was checked

The original nohit C2 game completed a fresh continuous Normal campaign through Win2: 24 rounds, 17,804 native ticks, 14,016 matched inputs, and 153,912 nonterminal state components exactly matching the reference runtime. HP remained 92, KR remained 0, and no DamagePlayer call occurred. `round4-normal60-final/verdict.json` is the independent verifier output.

The Haoge deployed export is pinned in `HAOGE_UPSTREAM.md` and included under `haogesans-export/`. Its C2 runtime and event data were replayed directly. Sixteen of 24 attacks currently have candidate routes that passed native replay. For these checks, literal negative DamagePlayer calls are explicitly admitted as the original script's healing; the health contract is survival with no nonnegative DamagePlayer call, not constant HP. The physical movement trajectory is compared against the original event runtime. The runtime source was not modified; the test adapter only aliases two renamed runtime properties.

Seven Haoge attacks remain unresolved under the recorded search budgets: BlueBone, BoneGap1Fast, BoneStab2, Platforms1, Platforms3, RandomBlaster1, RandomBlaster2. Final contains positive scripted DamagePlayer branches, so this collision-only operator rejects it rather than claiming a no-damage route. These are solver/model limitations or unsupported contracts, not proofs of unsolvability.

## Correctness fix

Same-tick event ordering matters when SansSlam dispatches at zero speed and a later event changes HeartMaxFallSpeed. The operator now captures the speed at the Slam dispatch point and carries it as an explicit marker through the compact environment. This fixed Haoge Multi1 and Multi2, which previously had model/native divergence. Four directional tests compare the compact/resumable and native C++ paths.

## Verification

Focused regression: 118 tests passed in 13.85 seconds. The 60 Hz original Normal result is independently verified in the bundled verdict JSON. Each successful Haoge proof includes its route, captured entry state, full native replay record, and source hashes.

## Limits

The package is a source snapshot plus original project assets and audit records; it is not a binary distribution. Haoge attacks that trigger explicit healing must be interpreted under the stated health contract. Search-budget exhaustion and unsupported scripted positive damage do not establish impossibility. The 240 Hz original Final case remains unresolved.
