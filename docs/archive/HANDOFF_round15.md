# Round 15: original-engine oracle and all 24 examples

Latest state, 2026-10-05. Read this before round 14 or the older HANDOFF claims.

## Latest verified change

RandomBlaster2 seed42 now uses candidate ID `6651b0a97b1d5b892b1a4e07ad2fae2c7e92f36d0678e732ff254134a450271e`. It checks a 2px expanded original hitbox at every240Hz microtick, rather than endpoint offset samples. New route generation62.599s/504inputframes/beam12/segment8; independent original replay and three normal game rounds all HP92/KR0/hits0 with original EndAttack. Trace `tools/real-game/bonesgap1-20261005-000657-119498.json`; proof PNG `bonesgap1-20261005-000726-655544.png`. The normal acceptance endpoint promoted it to `tools/oracle-plans/sans_randomblaster2-42.json` and updated the coverage matrix. Five distinct waves remain real-time accepted; this improves an existing wave.

The prior endpoint-margin DAG candidate (56.884s) passed accelerated replay but failed real-time round2 near frame459 with ~0.6px vertical error. Trace `bonesgap1-20261004-233301-941436.json`; backup `sans_randomblaster2-42-failed-realtime-dag.json`. Candidate publication now saves an isolated content-hash filename; it never overwrites a default. Only three normal EndAttack rounds with constant HP/KR0, matching candidate actions and current CSV/runtime/data.js hashes can promote it. A failed candidate remains isolated.

New success reached60s at440frames and reused that one best safe prefix for the final64frames (2.590s). Its metadata explicitly identifies single-prefix continuation, not full-frontier reuse. New source retains the last completed frontier and parent paths for `solve({resume:true})`, exposes a continuation button, and sums generation time over budgets. A partial interrupted layer alone is recomputed. Original-engine Spare verification stopped at frame1 with2states (42.3ms), resumed to EndAttack frame18, and independently replayed no-hit; total cumulative617.1ms. Trace `bonesgap1-20261005-001153-467765.json`. This is candidate/infrastructure evidence, not additional real-time acceptance. Search remains heuristic, not completeness or shortest-route proof.

Oracle preparation now runs ordinary original menu/dialogue ticks on a timer before initial capture, avoiding background RAF throttling. No oracle hooks run in normal acceptance. The current live observer logs KR-only changes, down/mode/angle/dx and all damaging hazard families, finishes only on original EndAttack (or death), and automatically records the three-round result.

## User constraints

- Only the actual original game can establish no-hit acceptance. No local tests were run. Python/native fast kernels generate candidates only.
- Three consecutive complete real-time rounds, constant HP and KR=0, are the gate. Stop after three. Do not extend to ten.
- Preserve XY choices, landing rest, timing and spatial clearance before reducing input time.
- New-route solve target is roughly 100ms; a cached route does not count.
- Use the Codex internal browser. No external browser is necessary.
- Latest scope: improve the design from the attached report and simulate every original example. All 24 have now executed in the original engine; all-round automatic no-hit remains unfinished.

## What was implemented

- `DESIGN_original_engine.md` records time-DAG/full hybrid-state architecture and corrections to the report. Floor quantization is not injective; beam exhaustion is not deadlock; fixed seed does not remove player-dependent aiming; geometric margins are not a proved invariant tube. The report's timing numbers were not accepted as project measurements.
- `c2-sans-fight/engine_oracle.js` executes shipped C2 ticks directly at nominal 240Hz. Checkpoints contain C2 serialization, RNG, keyboard state, compensated clock and EndAttack state. Starting capture waits for all frame-zero commands (T>0), including multiple teleports. Intro dialogue advances with ordinary Confirm input.
- Oracle exposes observe/checkpoint/restore/step/clearance/replay/solve/cancel. New forward DAG avoids repeatedly recomputing a rolling horizon. Every retained node has its original full snapshot; bounded XY/velocity/key bands and contact/ascent/fall quotas remain heuristic pruning, not state equivalence.
- Visible controls can solve, independently replay the resulting full route, publish a candidate, and open normal three-round acceptance. Time budget/cancel results do not imply no route exists. Old `solveRolling` is retained for comparison, with a 60s default budget; the visible interface uses `solve`.
- `/api/oracle-plan` saves only completed no-damage candidates with validated action/trajectory shapes and original CSV/runtime/data.js hashes. `/api/tas` returns matching saved candidates for normal C2/full-horizon requests, with cache_hit=true. RandomBlaster2's saved plan was republished through the validated endpoint after adding data.js hashing.
- Uncalibrated C2 mechanisms no longer fall through to an idle/incorrect Python TAS plan; they link to the original solver. The local dashboard also no longer labels truncated model failure as absolute deadlock or model agreement as game acceptance.
- Fixed seed uses xorshift32 only for original CSV RND calls and resets at TLPlay. Cosmetic randomness remains separate. The entire original GetHeartPos/aiming behavior runs in each branch.
- `live_acceptance.js` suspends after the third full round and explicitly excludes oracle mode. It observes actual HP/KR/hits and never heals or moves the heart.
- `coverage.html` runs all CSV scenarios, persists/reloads a matrix, exports records, accepts a seed, and links each wave to its original solver. `/api/coverage` stores `tools/real-game/coverage-latest.json` atomically.

## Coverage and real evidence

`tools/real-game/COVERAGE.md`, `wave-catalog.json`, and `coverage-latest.json` contain the full matrix. All 24 examples ran until original EndAttack or game-over. Unsupported routes used a clearly identified idle baseline; their damage/death does not demonstrate solver failure or unavoidable damage.

Seven accelerated no-hit cases: BlueBone, BoneGap1, BoneGap1Fast, BoneGap2, BoneSlideH, RandomBlaster2, Spare.

Five existing **three-round real-time** records, all three HP92→92, KR0, hits0:

| Wave | Trace / matching PNG |
|---|---|
| BlueBone | bonesgap1-20261004-055208-203200 |
| BoneSlideH | bonesgap1-20261004-055014-499162 |
| BoneGap1 | bonesgap1-20261004-060305-885101 |
| BoneGap2 seed42 | bonesgap1-20261004-060407-331745 |
| RandomBlaster2 seed42 | bonesgap1-20261005-000657-119498; PNG bonesgap1-20261005-000726-655544 |

All paths are under `tools/real-game`. Prefix is historical; normalize wave identifiers to `.csv` when matching. RandomBlaster2 had a later fourth-round observed failure, recorded separately. The first-three gate remains the user's criterion; do not claim arbitrary repeat length or other seeds stable.

The previous RandomBlaster2 rolling candidate (51.328s/505frames) remains in `tools/oracle-plans/sans_randomblaster2-42-rolling-three-round-route.json`. Its historical three-round trace is `bonesgap1-20261004-223552-010368`; a later fourth-round failure was observed. The new62.599s route described above is now active. Last rows can move to the menu at EndAttack: outside combat bounds there is normal, not a route defect.

Intro initially timed out waiting for dialogue; the Confirm bootstrap fixed it. The final idle original replay terminates at game-over frame156, not an infrastructure error.

## High difficulty and performance limits

BoneGap1 fresh native candidates approximately224–230ms; BoneGap2 approximately363ms; Blue/SlideH approximately600ms. None of these cache-hit timing claims establish 100ms across all waves.

Platforms4Hard still has no complete candidate. Native platform candidate model initially exhausted frame154; with observed initial dy60.048 exhausted167, about864ms. This is a calibrated approximation, not authoritative physics. Horizontal platform reflection and carry were added, but vertical/rotated contacts need further calibration.

Original rolling search (beam8/depth8/segment4) spent668.8s, exhausted a safe prefix near108. Forward DAG beam24/segment8 exhausted168 in29.8s; ascent/fall diversity advanced264 in45.5s; contact-height diversity also exhausted264 in47.8s. Save and inspect actual original counterexamples rather than declaring deadlock or merely increasing caps. A prior beam96/segment4 attempt hit the60s budget at68.

Original branch measurement on one Hard checkpoint: ~93KB JSON, ~1.0ms restore, ~0.8ms save, ~0.165ms per game microtick. Branch expansion + serialization dominate. The final design should compile calibrated original source kernels and use the original engine for counterexamples/acceptance; do not promise the full general oracle itself will achieve100ms yet.

## Live environment

- Workspace: `<repo>`, not a Git repository.
- Server8099: hidden parent37608, listener child54284, logs `tools/dashboard-r25.log/.err.log`. Command lines were rechecked2026-10-05. Verify command lines and actual listener before stopping those exact PIDs. Store-Python launcher sometimes fails immediately after shutdown; a subsequent hidden Start-Process succeeded without installing anything.
- Internal browser id2. Current managed Tab6 is the refreshed coverage matrix and is a deliverable. The successful RandomBlaster2 real-time page was Tab4; its screenshot shows 实时三回合无伤已通过. Old-session handles became stale, so inspect inventory rather than assuming Tab1/Tab3/Tab4 exist. The spare continuation-check Tab5 was closed after its evidence was saved. Current coverage screenshot: `bonesgap1-20261005-001315-482321.png`.
- CUA handles currently `suiteTab/suiteCdp`, `oracleTab/oracleCdp`, `introNewTab/introCdp` (the latter now RandomBlaster2). Re-read CUA documentation after compaction. Use CUA/CDP for browser execution, not external browser scripts.

## Next work

1. Inspect Hard's surviving contact/velocity diversity at264 and actual hazards. Preserve board trajectories that need an earlier jump, then validate a full candidate in original replay and three normal rounds.
2. Add no-hit candidates for remaining17 examples; idle full coverage is not completion of the universal no-hit solver.
3. Compile source-derived platform/contact/rotated gravity/blaster kernels, without treating the current parser as general truth. Closed-loop aims require branch environment/RNG/script state.
4. Track error envelopes and test operational margins against observed actual dt and skipped input frames. Current oracle checks the expanded original hitbox every240Hz microtick; it is not a disturbance-tube proof.
5. Optimize input time only after reliable actual margins; no global shortest-input proof exists with current pruning.

No memory files were edited. No local test results were used as acceptance.
