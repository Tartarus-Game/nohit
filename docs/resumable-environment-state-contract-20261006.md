# Resumable source environment state contract

This document specifies the conservative refactoring of compact_wave TimelineVM into the implemented resumable_wave environment operator. It is based on the current code, including loaded-line substitution, native timestamp arithmetic, explicit termination reasons and all four live-entity classes. The monolithic VM remains an explicit reference oracle. Neither path uses native checkpoint search.

The first implementation should preserve every current source-operator result. It should not simultaneously change physics, simplify floating arithmetic, infer missing controls, or enable the RealHELL history quotient. Exact continuation removes the repeated source-prefix execution even before any state merging is enabled.

## Operator boundary

Use a committed end-of-physics-tick boundary as the ordinary immutable state. Store the index of the next tick to execute. Tick zero retains the compiler's current initialization convention: compiling the first environment row already dispatches timeline events and advances environment entities. The solver's captured player state must not accidentally receive that movement twice.

The interface can be expressed without a monolithic wave:

    initialize(program, initial_environment, clock) -> EnvState
    advance_one_tick(EnvState) ->
        TickCommitted(next_state, frame)
        | NeedTarget(suspension, request)
        | NeedDialogue(suspension, request)
        | Terminal(next_state, frame, reason)
    supply_target(suspension, exact_position) -> continuation

A frame contains only this tick's 22 environment values, ordered platform rows, ordered white/blue rectangles, beam polygons, and local event/evidence records. A separate append-only collector may materialize CompiledWave arrays for compatibility. Normal branch search consumes the local frame and shared immutable parent/segment references, rather than recompiling or copying all preceding frames.

Suspending at an observation is necessary because the timeline can perform multiple GetHeartPos calls in one physical tick. A request is not a tick completion. The held action and remaining microsteps belong to the coupled search continuation, not to a new independent action choice.

## Static program and external configuration

These may be referenced by an immutable identifier instead of copied into every state:

| Current names | Required contract |
| --- | --- |
| parsed_rows, labels | Immutable source program with source digest, parser/semantic version, and exact label-to-row mapping. Preserve blank-row indexing and current jump conventions. |
| initial_cz, initial_heart_mode, initial_heart_pos; cz_initialized, heart_pos_initialized, heart_mode_initialized; has_end_attack | Initialization-only scan results. They are not recurrent state after initialization, but must be identical to the existing initializer. |
| self.initial_environment | Immutable initial conditions. Preserve all provided dimensions and binary64 bits; initial_cz alone is not its whole identity. |
| self.termination_policy | Semantic configuration. EndAttack and EOF-hazards-drained have different accepted terminals and dialogue behavior. |
| self.dt_schedule / dt_nominal / native_fixed_dt configuration | A precise clock protocol, described below. An arbitrary finite schedule is immutable input identified by its full content or collision-checked digest. |
| self.max_ticks, allow_partial | Resource/request policy. These control when to return unknown or request input; they do not change physical state. Keep them outside the mathematical physical-state key when continuation across a raised budget is intended. Never memoize a resource stop as false. |
| self.heart_samples | Existing replay adapter input. It becomes an observation provider/evidence stream, not persistent world state and not the new state's identity. |

Program identity must include all source equations involved in environment evolution, not just the CSV filename. A source edit invalidates both continuation states and their certificates.

## Persistent environment locals at committed tick boundaries

The following is the conservative field inventory actually read by later iterations of TimelineVM.run:

| Field | Why it persists / exact representation |
| --- | --- |
| tick | Next physical-tick index. The relative ordering of events and the implicit _last_slam_tick comparison depend on it. |
| pc | Index of the current or next source row. Preserve negative/out-of-range handling and source-line identity. |
| loaded_line | None, or the already-loaded tuple (delay, lowercased command, typed argument tuple). It can survive many ticks while its delay is pending. It must not be reconstructed from current vars. |
| time_acc | Binary64 timeline accumulator. It is decremented by each executed line's delay and incremented once at the end of a running tick. |
| running | Timeline-running state. The current single-attack adapter treats TLPause/TLResume as preparation no-ops, but retaining this field avoids silently baking that limitation into a future global operator. |
| self.vars | Exact property-key strings to typed values, including implicit _last_slam_tick. A missing key is distinct from stored zero where the interpreter's direct get differs. |
| self.rng.state | Current uint32 XorShift state. Initial seed alone is insufficient after branches or different numbers of random draws. |
| self.heart_pos | Last sampled or teleported position used by later same-tick observations and emitted environment rows. Retain it initially; proving some components dead is a separate quotient. |
| cz | Current arena bounds [left,top,right,bottom], with exact stored bits. |
| cz_size | Independently stored width/height. Do not recompute it from right-left or bottom-top: source update order and cancellation can produce different binary64 results. |
| tgt_cz | Target arena bounds for ongoing resize. Equal current bounds do not imply equal future motion. |
| cz_speed | Resize speed. |
| heart_mode, gravity_dir | Current mode and gravity orientation. HeartMode also resets gravity direction in current source semantics. |
| max_fall_speed, slam_damage | Current movement parameters, which persist until overwritten. |
| active_bones, active_platforms, active_stabs, active_blasters | Ordered sequences of complete live entity states. Their fields are enumerated below. Empty current collision geometry does not imply an empty sequence. |
| ended, termination_reason | Semantic lifecycle label at a terminal. Preserve EndAttack versus drained EOF. A tick-budget return must not set ended. |
| eof_tick | Needed to reproduce current reporting and EOF lifecycle history. It is initially None and records the first processed EOF tick. Retain until its irrelevance to a narrower future key is explicitly proved. |
| pending_dialogue | Current unknown dialogue boundary when present. Resume support must model the source continuation and world evolution through the pause; it cannot simply skip the text or freeze physics. |
| unproven_callbacks | Conservative record of resize callbacks whose execution/effects are not modeled. Current initial_environment has no native EndResize callback payload and assumes none; exact equality of the current modeled state is not evidence that an unknown callback can be ignored. |
| end_resize | Pending native resize callback, or None. The audited TLResume callback fires once after all four bounds settle; its function and source provenance must survive continuation and state equality. |

There is no need to retain the local names d_tok, sd, cmd, cmd_l, args, x, y, k, etc. between fully committed ticks, except where their values have become loaded_line, an entity field, or the explicit in-flight suspension described next.

## Exact loaded-line and target suspension semantics

Native TLLoadLine substitutes all dollar-prefixed tokens once, including a destination name. The current load_line returns an immutable loaded tuple. SET stores its loaded value without converting every string into a number. Therefore:

- Store the loaded command, delay and every argument with type tags.
- Do not resolve the same argument again during resume.
- Do not replace a loaded destination with its original source spelling.
- Preserve the exact result of variable_key; do not reinterpret a numeric-looking property name during deserialization.
- Do not normalize a SET string such as "1.0" into a Number merely because a later arithmetic command might convert it.

For example, equality of vars after two different histories does not permit merging if one has a pending loaded target argument equal to an old value and the other has a different captured value. The dictionary and loaded instruction are separate state components.

The current run loop is not yet a resumable state machine. Immediately before an unresolved GetHeartPos it already:

1. Sets loaded_line to None.
2. Subtracts the instruction delay.
3. Increments run_count.
4. Appends a source event.
5. Discovers the missing sample and breaks out of timeline dispatch.

After that break, it still steps all live entities, emits a partial row, resizes the arena, increments time_acc and increments tick. Its returned final arrays are a useful unresolved-boundary view, but not a snapshot from which the interrupted command can simply continue.

Capture the actual suspension before executing the missing observation's side effects. Its additional fields must include:

| In-flight field | Required meaning |
| --- | --- |
| phase | Explicitly AWAIT_TARGET_AFTER_ACCOUNTING (or an equivalently documented pre-accounting convention). Never infer it solely from pending_target being non-None. |
| pending_call | Exact (pc, delay, loaded command, typed arguments), because loaded_line has already been cleared in the current loop. |
| instruction_accounted | Whether delay subtraction, run_count increment and source-event emission have happened. Prefer a single fixed suspension convention rather than multiple optional flags. |
| run_count | Number of commands already dispatched this tick. Resetting it on resume would bypass the current 1000-command tick guard and could change the script clock. |
| dt_current | The already-selected binary64 dt for this tick. The clock cursor must not advance again when supplying the sample. |
| previous_cz | Bounds captured at the beginning of this tick, before timeline modifications. They feed the player CustomMovement contact phase. |
| teleport_pulse, mode_pulse | Accumulated pulses from earlier commands in this same tick. |
| removed_platforms | Ordered tombstone rows for supports removed earlier this tick. The player's earlier movement can still depend on them. |
| request identity | Exact tick, source row, loaded variable destinations, sample phase and preceding-teleport data. A row number alone is insufficient if a loop reaches it repeatedly. |
| any earlier pending event records | A separate transactional output cursor, so resume does not duplicate already-issued evidence. |

The implemented resumable_wave chooses the pre-accounting convention: it suspends before clearing loaded_line, subtracting delay, increasing run_count or recording the unresolved command. The captured loaded_line itself therefore serves as pending_call, and request.instruction_accounted is False. Supplying a sample resumes that one instruction; repeated calls on an unsupplied suspension are idempotent.

The live entity sequences and arena/vars/RNG fields in this suspension are their state after preceding commands in the tick but before this tick's entity-update phase. Supplying a target writes the two loaded destination keys, updates heart_pos, appends that actual observation once, increments pc once, and resumes timeline dispatch with the same run_count and pulses.

Repeated GetHeartPos calls in the same tick suspend and resume this same transaction. A preceding HeartTeleport takes precedence over the pre-timeline movement sample according to the existing request metadata. The coupled player operator must not integrate CustomMovement again for the second request.

The first equivalence implementation can use externally supplied exact observation samples to validate the environment state machine independently. For automatic coupling, construct the pre-timeline movement view using the same old-bounds and platform phase as the current operator. If compatibility needs the old partial-row view, produce it from a throwaway copy of the suspended current tick; do not commit that copy or replay the whole source prefix. Validate this view against the current boundary row before replacing the current sampling adapter.

## Tick phases and single-commit rule

Use the current equations and statement order without algebraic simplification:

1. Begin tick: read exactly one dt; save previous_cz; reset teleport/mode pulses, run_count and removed-platform tombstones.
2. Dispatch due timeline rows. Load a row at its native loading point; preserve loaded_line across a delay; perform jumps with their existing pc/reload semantics. Suspend before unresolved target side effects.
3. Save middle_cz after dispatch. Preserve the initial-heart-position diagnostic capture rule separately.
4. Advance ordinary bones and perform their direction-specific off-screen deletion.
5. Advance old platforms, keep newborn behavior distinct, capture pre_active and pre_dy, then apply direction-specific reflection using the current arena.
6. Step BoneStab and GasterBlaster objects in existing list order, retaining warning/enter/wait phases even when they have no collision polygon.
7. Emit the frame: slam pulse, environment phases, all platform rows including removed-platform tombstones, rectangles and beam polygons.
8. If running, add dt to time_acc. This precedes the regular CombatZoneTick callback; TLResume from that callback can affect the following timeline tick but cannot retroactively add time in this tick.
9. Apply _resize_combat_zone in source x/y/width/height assignment order, overwrite the frame's final current bounds, dispatch the audited resize callback when settled, and increment tick once.
10. Evaluate EOF lifecycle and form the committed next state.

EndAttack executes inside phase 2 but the current compiler still emits the cleared final tick, including removed platform information. Returning a terminal before the rest of that tick is committed would change its collision/movement descriptor.

Only phase-2 target suspensions are required initially. Make phases 3–10 atomic; then no per-entity iteration cursor is needed in the persistent state. If future cooperative yielding is allowed inside those phases, add the active list kind and index plus the partially accumulated frame explicitly rather than restarting the phase.

For dialogue, expose a typed unresolved continuation and return unknown until its interaction/time semantics are implemented. A compiler-return label is not permission to invent a resume action. World physics continuing while timeline text is paused must be represented in a later global state machine.

## Complete live entity records

Preserve sequence order and every existing field for the first implementation:

| Entity | Current stored fields |
| --- | --- |
| _ActiveBone | x, y, w, h, vx, vy, color, direction |
| _ActivePlatform | x, y, w, h, vx, vy, reverse, born, direction, pre_active, pre_dy |
| _ActiveBoneStab | direction, height, warn_time, stay, spawned, reverse, x, y, w, h, dest_x, dest_y |
| _ActiveGasterBlaster | size, x, y, end_x, end_y, end_ang, angle, timer, blast_time, state, leave_speed, beam_timer, base_size, damage, opacity, scale_y, scale_x |

Do not replace a blaster by its currently visible beam. ENTER and WAIT have no damaging polygon but determine future FIRE. Do not replace a stab by its current bounding box; its warning timer, destination and reversal state determine future geometry. Do not derive platform direction from velocity during restoration: trigonometric residuals and explicit direction comparisons matter. Even mathematically derivable fields should initially be restored directly to avoid changing rounding.

A serialized tuple or immutable dataclass per entity is enough initially. Shared immutable containers may follow after equality tests. Reordering entities as a multiset requires a separate commutation proof, particularly for platform contact selection and deterministic output ordering.

## Clock state

There are two valid minimal clock implementations:

- Immutable supplied dt sequence plus next index, retaining its content identity. Running out returns a resource boundary; repeating the last value is not allowed.
- The current native_fixed_dt recurrence represented by the current binary64 timestamp, first-tick flag/initial_dt, and exact addition constant 1000/240. Compute next_timestamp by addition, then subtract the old timestamp before division/clamping, in current order.

Do not compute timestamp as start + tick * step: repeated addition is not bit-equivalent. Do not replace native-derived dt with 1/240. Dialogue of different physical duration can lead to a different timestamp and thus different later dt even at the same source pc; keep the clock in the key unless a stronger invariance theorem has been demonstrated.

## Exact key and separate evidence

The first key is a collision-checked structural encoding of:

    semantic_program_id
    clock_protocol_id and clock_state
    phase, tick, pc, loaded_line or pending_call
    time_acc, running
    typed vars and RNG state
    heart_pos, cz, cz_size, tgt_cz, cz_speed
    heart_mode, gravity_dir, max_fall_speed, slam_damage
    ordered complete entity records
    semantic lifecycle state
    in-flight fields if the phase is suspended

Number encodings preserve binary64 bits including signed zero. Preserve string/number distinctions and any Python numeric subtypes that still affect the current interpreter until a native-number normalization proof exists. Encode None explicitly. Dictionary keys can be sorted for serialization because current lookup semantics do not iterate dictionary insertion order; object lists must retain order. Compare serialized state on hash collisions.

For coupled Bellman nodes add the full player state and control phase/held mask, or the previously proved input-latch quotient at a valid decision boundary. Environment equality alone does not merge different positions or velocities. At microstep suspensions the remaining held-action duration is part of the state.

Keep target_history, source_events, diagnostic prefixes, action predecessors and full replay traces outside this future key. Each path retains its own evidence parent chain. Two paths may share a future false memo or a continuation result without sharing their past trace.

The following current locals are output/build metadata, not causal world state: env_schedule, platform_table storage, num_platforms storage, flat_white_list, flat_blue_list, counts_white, counts_blue, polygon_frames, platform_frames, max_w, max_b, max_all, capacity, p_count, cw and cb. They belong in a collector or current frame. initial_heart_pos_captured and player_dependent are reporting metadata; preserve them in the evidence/compatibility layer. Historical geometry array widths must not prevent equal futures from sharing a state.

## Implementation and proof sequence

1. Extract immutable program data and explicit state without changing any equations. Implement full typed state serialization/restoration. Keep the existing monolithic compiler as an independent oracle.
2. Add one-tick execution and phase-2 target suspension. Feed the same predetermined observation trace to old and new compilers. Compare every committed environment value, platform row, rectangle and polygon with exact bits and order; compare events and target history separately.
3. Verify compositionality: running k+j ticks equals running k, serializing/restoring, then running j. Repeat at every small-fixture tick and every unresolved target, including several observations in one tick.
4. Cover loaded-row delays, SET string/numeric distinctions, dynamic destination keys, jumps/RNG, zero-delay instruction guards, platform birth/removal/reflection, instant resize, slam pulse, blaster phase changes, EndAttack and budget/EOF boundaries. Native replay remains a linear differential check, never an oracle for candidate generation.
5. Replace parametric binding's full-history recompile with advance from the actual parent EnvState. First keep complete state keys and existing evidence history; no quotient is needed for this correctness/performance step.
6. Only then enable equality-based Markov sharing. Equal full current states are a direct sufficient future-equivalence relation.
7. Integrate RealHELL-specific or general CFG liveness/taint certificates to omit dead variables and extinct sample provenance. Validate loaded_line and same-tick phase conditions at every proposed clear cut. The current restricted straight-line certificate remains off by default and must not be promoted to a RealHELL certificate merely because a seed-42 trace agrees.

The key correctness statement is a commuting diagram: deserialize(serialize(S)) advances under the same observation input to a state and frame identical to advancing S; concatenating these exact single-tick transitions matches the current full compilation. A history quotient is applied only after that operator equality is established.

## What this changes mathematically

Today, one history binding can re-execute every earlier instruction and regenerate every earlier array. The proposed state is a sufficient statistic for future evolution, so each branch advances from its actual current state. Cost is proportional to the newly explored transitions and current live entities, rather than necessarily proportional to every historical prefix again.

This does not promise polynomial search, constant live-object count, or millisecond whole-score solving. It removes dependence on irrelevant past execution. Complete search must still retain every inequivalent exit at a segment boundary and return unknown on unresolved model/resource boundaries.

## Implemented preliminary step: full committed-state keys

The compiler now optionally captures structural state bytes at each committed row with capture_state_keys=True. CompiledWave.environment_state_keys is normally empty; when enabled it aligns with env_schedule and contains None at the pseudo-committed row produced by an unresolved target/dialogue. The encoder requires all committed fields listed above, including loaded_line, the full typed variable map, current RNG, arena size and target, all ordered entity internals, dt_nominal, lifecycle and unproven callbacks. It deliberately does not perform liveness projection.

The serializer in environment_state_key.py has distinct tags and unambiguous lengths for None, bool, arbitrary integers, binary64 numbers, strings, bytes, tuples, lists and string-key dictionaries. NumPy scalar dtypes/bits remain distinguished conservatively. Dictionary insertion order is ignored; entity sequence order is retained. Encoded state bytes are compared directly, not accepted solely through a hash.

ParametricEnvironment forwards capture_state_keys. ParametricRouteIterator(environment_state_quotient=True) uses a captured current key only when it exists, its binding belongs to the same immutable source/seed/initial-state/clock/budget base, and the binding has no already-bound observation after the current node tick. Otherwise it retains exact history identity. The tick and existing full player/latch key remain outside the environment key. Every path still owns its actual binding and observation history.

The current immutable base includes max_ticks conservatively, unlike the proposed budget-independent physical-state key above. This does not affect correctness, but prevents cross-budget sharing. No default or original RealHELL production path enables the state quotient option. Capturing full typed bytes at every tick has memory and serialization cost; this remains an opt-in merge experiment, independent of the now-implemented resumable execution backend.

Tests cover type/signed-zero distinctions, every required state field, equal-state merges with unequal histories, live-variable inequality, pending-row refusal, prebound-future refusal, foreign seed/clock refusal and default-off behavior. A complete tiny declared search drops actual false memo entries/expansions from 5/5 to 4/4 while retaining its exhausted result. This confirms a real shared-future reduction without claiming a whole-score complexity bound.

## Implemented resumable consumer and measured work

The new source operator exposes initialize, advance_one_tick, supply_target, immutable-parent clone behavior, and typed TickCommitted/Terminal/NeedTarget/NeedDialogue/ResourceLimit results. Its clone shares immutable program data and copies only current causal state. The test suite explicitly forbids invoking TimelineVM.run from this operator.

preview_observation_frame supplies the old consumer's pre-observation environment/platform context from a transaction copy. It does not guess a target or execute subsequent timeline commands, does not mutate the parent or its counters, and marks its result committed=False. The compatibility collector may include that row for sampling but supplies no state key for it.

ParametricEnvironment now defaults to backend='resumable'; backend='reference' retains full-history compilation for explicit comparison. ParametricRouteIterator likewise exposes environment_backend. Each binding retains its true suspension plus references to committed frames. Extending a branch supplies its sample to that suspension and executes only the new suffix. Its path history and predecessor evidence remain independent.

The first compatibility collector still materializes full prefix-plus-segment matrices. It eliminates prefix execution, not all prefix copying. Prefix frames are shared by reference across sibling bindings, and their immutable parent continuations survive branching. Sparse/chunked matrix interfaces and more efficient cloning are subsequent implementation work, not prerequisites for the mathematical continuation property.

Tests compare every frame's env22, ordered platform metadata, white/blue rectangles and beam polygons by raw bits against the unchanged monolithic oracle. They resume from every tick in a fixture, fork at NeedTarget, cover multiple same-tick observations and dynamic destination names, exercise RNG/jump reloads, clock/callback/EOF boundaries, and verify full tiny-solver routes with an independent microtick replay. The consumer additionally compares each binding's exact typed environment keys and reports environment_backend plus environment_work.

Run the reproducible work experiment:

    .\tools\uv_py.bat scratch/benchmark-parametric-resume.py

For 32 observations and a final 113-tick timeline, full-history compilation executed 2049 world ticks and accounted for 1122 source commands. Resumable execution performed 113 committed ticks plus 32 preview ticks, 145 total, and 66 commands. Thus executed world work fell by 14.13 times, with final arrays and observation history exactly equal. In the recorded small run, wall time was about 35.9 ms versus 42.3 ms: current cloning/collector overhead outweighed the lower executed work. This is a structural work reduction, not a demonstrated small-case latency improvement. Results are saved in scratch/resume-benchmark-results.json.
