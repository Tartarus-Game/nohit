# Future-language state quotient for exact no-hit reachability

The complete observation history currently identifies an environment binding. It is a sufficient description, but is not a minimal state: histories can differ while every possible future control has the same effect. The correct reduction is to identify equal futures, while retaining each actual past as separate route evidence. It is not valid to erase history solely because an attack cleared the screen or teleported the player.

## Controlled transition system and sufficient state

Let a decision state be

\[
q=(n,\phi,x,e),
\]

where n is the logical tick, phi is the decision/event phase, x is the full player state (subject only to independently proved input-latch equivalence), and e is a sufficient environment state. An action a is a legal physical key mask held for the declared number of physics ticks. Define

\[
T(q,a)=q',\qquad D(q,a)\in\{0,1\},
\]

where D records damage anywhere along that action's microsteps, not only at the endpoint. The environment state must contain all data subsequently read by the source program: current instruction and already-loaded argument values, timer/phase, RNG, variables, arena state, and every surviving entity's full internal state. A list of current collision rectangles is insufficient.

The model is deterministic only after fixing its clock protocol, external inputs, source semantics and control domain. Dialogue input must either be modeled or cause an unknown boundary. A compilation budget is not a game terminal.

Let G be a verified terminal set. For a finite control word w, let

\[
\mathcal L(q)=\{w:\text{the execution of }w\text{ from }q
 \text{ is legal, has no damage, and ends in }G\}.
\]

The exact future-language relation is q ~ r iff their languages are equal. Computing that coarsest relation can itself be as hard as solving reachability. A useful, checkable sufficient relation R is an action-labeled bisimulation:

1. q R r implies equal terminal and current-safety labels.
2. They admit the same actions.
3. For each admitted a, damage labels agree and T(q,a) R T(r,a).

Induction on word length proves equal execution labels, terminal membership and language for every finite continuation. For an infinite survival objective, the corresponding safety bisimulation also preserves all finite prefixes; a finite completed battle and infinite survival must not be conflated.

## Exact snapshot theorem and Bellman compatibility

If two source histories produce bit-identical sufficient current states at the same phase, they are bisimilar. Proof: the next primitive reads equal values and receives the same input; deterministic source operations therefore produce equal outputs and next states. Apply induction to all primitives in the microstep, all microsteps of the control action, and then all future actions. Historical samples not present in, or reachable from, the sufficient state cannot influence the future.

This proof requires actual read dependencies. In particular, native TLLoadLine captures variable substitutions when the instruction is loaded. Equal current dictionaries do not suffice if loaded arguments differ. The recent compiler fix preserves this distinction, including destination-name substitution and SET string values.

For a real finite horizon, the Boolean Bellman recurrence is

\[
W(q)=1_G(q)\ \lor\
 \bigvee_{a\in A(q)}\bigl(\neg D(q,a)\land W(T(q,a))\bigr),
\]

with explicit exclusion of already-damaged states. Equivalent states have equal W, so evaluating one future and sharing its result is exact. A false memo entry is permitted only after every legal alternative has been proved false. Budget exhaustion, dialogue boundaries, skipped actions and previously yielded successful terminals are not false states.

Time remains in the state, so the time-expanded graph remains a DAG. Removing historical data does not justify merging different times or assuming every transition graph is acyclic after a time quotient.

## Environment identity and past evidence are different objects

Each search path retains its actual immutable binding, observation history, predecessor and control. A future-equivalence key is used only to share future reachability work. Replacing path B's binding with path A's binding would corrupt B's reconstructed target reads and its independent native replay, even if their futures are equivalent.

For feasibility, one representative state per equivalence class suffices. To enumerate distinct accepted control histories, retain all predecessor alternatives or a predecessor DAG. Successful-terminal deduplication must not masquerade as a false Bellman certificate.

Weights that only order actions do not affect this argument. If claiming globally optimal weighted paths, either the quotient must preserve transition rewards and relevant reward-memory state, or the algorithm must retain distinct nondominated reward labels. No optimum claim follows merely from Boolean language equivalence.

## Reset certificates and why simple resets are insufficient

BlackScreen(1) destroys bones, stabs, blasters and platforms. It does not generally erase variables, RNG, arena motion, loaded instructions, clock, or player velocity/input edges. HeartTeleport changes position; in blue mode different vertical velocities survive it. A teleport using a sampled variable is not even a constant-position reset.

A sufficient reset certificate can instead prove:

- Source control flow, timing, RNG evolution and persistent non-entity state are independent of the discarded samples up to the cut.
- All target-dependent surviving entities have been destroyed.
- Every remaining variable derived from those samples is dead: on every feasible continuation, it is overwritten before it can influence a read.
- Already-loaded arguments and same-tick transients cannot retain a discarded value.
- The compared nodes have equal remaining player state, clock and phase.

For source-variable liveness the standard recurrence is

\[
LiveIn(i)=Use(i)\cup
 \left(\bigcup_{j\in Succ(i)}LiveIn(j)\setminus Def(i)\right).
\]

Use and Def must follow native loaded-argument semantics, including dynamic destination names. An unknown branch or indirect use requires a conservative superset, not the single branch visited by seed 42. A variable already captured in loaded_line is a live state component independently of dictionary liveness.

## Minimal implemented quotient

The new history_quotient module supplies an opt-in FutureHistoryKey. It admits only fixed-delay straight-line programs with classified commands and direct destination names. It rejects branches, text, dynamic delays, indirect destinations and target-tainted persistent arena/dynamics state. It certifies a literal BlackScreen(1) only when the entire explicit future-variable live set at that cut is empty.

For this restricted language, source pc, timer, RNG count, arena values, and loaded-instruction behavior at a fixed tick are independent of old samples. The clear removes all old entities. Subsequent identical samples therefore regenerate identical future entities and outputs. This is a static sufficient-state proof; it does not compare baked future arrays or require the next player observation to be bound.

Projection is enabled only when the node tick is strictly later than the actual clear tick in that binding's source-event trace. A future clear found during compilation never authorizes early forgetting. All observations on the clear tick or later are retained conservatively, so same-tick post-clear objects cannot lose their origin. Source identity, seed, initial environment, clock, termination policy and current tick remain distinguished. Sample floats retain exact packed bits.

ParametricRouteIterator can opt in with history_quotient=True. Its physical-state key is unchanged, including the previously proved active jump-latch quotient. The default remains exact-history mode. RealHELL deliberately receives no certificate from this restricted analyzer until the stronger source/CFG proof and native argument semantics are integrated.

## Reproducible evidence

Run:

    .\tools\uv_py.bat scratch/markov-quotient-experiment.py
    .\tools\uv_py.bat -m pytest tests/unit/test_history_quotient.py -q

The standalone experiment creates only small synthetic sources and never edits the original score or searches native snapshots.

1. Two target samples, (20,40) and (80,90), produce different objects. Both are cleared at tick 3, followed by the same teleport. If the old hx is later read, their newly generated bones differ at tick 6: clear plus teleport does not imply equivalence.
2. If hx and hy are overwritten before use, all emitted environment, bone, beam and platform arrays from the cut onward agree, despite unequal full-history identities.
3. Equal teleported positions (320,304) can retain vertical velocities 0.75 and 22.25. Position-only folding fails.
4. The tests enumerate 4 controls over 3 frames, all 64 words, through the real source-derived transition/collision operators. The certified pair has equal safe languages and byte-identical endpoints for every safe word. The live-variable counterexample has different safe languages.
5. A complete tiny declared action domain has two historical prefixes that merge before an unavoidable barrier. Actual exhausted-search memo counts and expansions fall from (5,5) to (4,4), while the result remains exhausted in that declared domain. This is actual search work reduction, not counting hypothetical keys.
6. Other tests retain inequality for different ticks and all relevant player-state fields, retain each binding's actual evidence history, reject a surviving target-dependent object or arena, and demonstrate a valid merge before a future GetHeartPos has been bound.

The 15 restricted-quotient tests pass, including conservative refusal of unmodeled resize callbacks. They prove these cases and the implemented restricted contract; they do not establish full original-game completion or an end-to-end millisecond bound.

A second opt-in experiment captures the complete committed VM state and compares its structural typed bytes, preserving all variables instead of projecting dead ones. This gives a generic sufficient-state key within the currently modeled source semantics without requiring a BlackScreen certificate. It is used only for future false memoization and retains independent history evidence. Pending rows, bindings with prebound future samples, and foreign template bases fall back to exact history. The independently implemented resumable VM now advances from actual suspended source states, eliminating repeated prefix execution while leaving quotient options off by default. Its contract, differential tests, work measurements and current copying overhead are recorded in docs/resumable-environment-state-contract-20261006.md.

## Original RealHELL and complete segment composition

The untouched score has 25 BlackScreen(1) instructions and 13 teleports. The last clear is source line 2589; 341 target observations remain afterward. The compiler agent's separate CFG/taint analysis reports empty variable liveness at all 25 cuts, including all bounded random jump alternatives; its supporting artifact is scratch/realhell-state-quotient-evidence.md. That is useful static evidence, but is not an integrated runtime snapshot/phase certificate in the current production solver.

After line 2589, explicit source-variable backward liveness is empty at the cut and no further RNG or jump occurs. Old samples can potentially be forgotten after that clear while retaining the player, arena and clock state. The later 341 observations still require causal memory: an old sample may be dropped only after all entities and live values depending on it have ceased influencing the future. A fixed number of seconds is not a proof of that condition.

At boundaries c_i define the complete safe segment relation

\[
R_i(q,q') \iff \exists \text{ legal no-hit controls taking }q
 \text{ at }c_i\text{ to }q'\text{ at }c_{i+1}.
\]

Composition is Boolean relational composition:

\[
(R_i\circ R_{i+1})(q,q'')=
 \bigvee_{q'}R_i(q,q')\land R_{i+1}(q',q'').
\]

Keep every inequivalent reachable exit q'. Choosing the locally highest-ranked exit can lose the only global solution: the minimal counterexample has S→A and S→B, A dead, and B→G. It is valid to merge A and B only after proving their future languages equal; here they plainly are not.

This quotient removes unnecessary historical dimension. It does not bound the number of distinct positions, velocities, live target-dependent entities or future branches. Exact reachability can remain large after a correct mathematical reduction.
