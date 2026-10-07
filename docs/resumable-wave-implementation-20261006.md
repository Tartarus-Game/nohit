# Resumable environment operator implementation

`nohit/engine/resumable_wave.py` is an independent single-tick execution loop. It shares the original compiler's entity classes, scalar argument conversion and arena arithmetic, but never calls `TimelineVM.run`, never replays an earlier source prefix, and never uses native runtime checkpoints.

API:

- `initialize(path_or_rows, seed, initial_environment, termination_policy, dt_schedule, clock_start_ms, max_ticks)` creates `EnvState`.
- `advance_one_tick(state)` returns `TickCommitted`, `Terminal`, `NeedTarget`, `NeedDialogue` or `ResourceLimit`.
- `supply_target(NeedTarget_or_state, (x,y))` returns a continuation state. Call `advance_one_tick` to continue that same physical tick.
- `state.clone()` and `copy.deepcopy(state)` preserve every live object and in-flight local while sharing static Program data.
- `preview_observation_frame(NeedTarget_or_state)`, also `sample_context`, evaluates only the suspended tick's remaining environment/frame phases on a clone. It dispatches no later instructions, guesses no target, modifies no input state and returns `Frame.committed=False`. It supplies the established player observation operator's previous/middle arena and platform fields; it is not an executable/committed frame certificate.

`Frame` exposes `tick`, `env` (22 values), `platforms` (ordered Nx9), `white`/`blue` (ordered Nx4), `polygons` (ordered Nx8), per-tick `events`, `target_history`, and `callback_events`. A collector may build compatibility arrays without forcing historical arrays into mathematical state.

The ordinary state boundary is after one complete physical tick. A target request suspends **before** its delay subtraction, command count increment and source event emission. The loaded instruction, current dt, previous arena, pulses, removed-platform rows, run count and earlier transactional events are retained. Repeated same-tick observations therefore neither restart physics nor double-count instructions. `stats.commands_executed` and `stats.ticks_committed` count actual work on that path; parents remain unchanged when children advance.

Clock options retain either the full immutable supplied dt tuple or the native binary64 timestamp recurrence. Supplying a target does not advance that clock again. Budget and exhausted-clock returns do not set a semantic terminal. Raising `state.max_ticks` permits continuation from the retained state. Unknown dialogue remains suspended under the explicit EOF policy; this implementation preserves the existing compiler's default preparation conventions rather than claiming newly complete dialogue behavior.

Program identity stores length-delimited full source bytes and both environment modules' source bytes, rather than trusting a digest alone. It is shared across branches. A future memo key must still include the selected clock protocol/current state and the complete dynamic environment/player state. This implementation does not enable a Real HELL history quotient or drop variables.

Initial direct differential check matched every env/platform/white/blue/polygon bit against the unchanged monolithic compiler for Intro2145 ticks, PlatformBlaster2162, Platforms4Hard1754 and BoneStab31513. `tests/unit/test_resumable_wave.py` independently covers continuation, branching, observations, clock, lifecycle and resource boundaries. Passing these comparisons proves compatibility with the current modeled operator; it is not a full native Real HELL no-hit result.
