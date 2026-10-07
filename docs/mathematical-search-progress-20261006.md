# Mathematical search refinement, 2026-10-06

## Proven scope and unchanged acceptance

The existing Normal seed 42 uninterrupted original-game acceptance remains in
`full-game-progress-20261006.md`. These experiments do not replace it. Real HELL
has not been solved or accepted. Its unmodified source, captured opening state,
and clock are used for bounded mathematical probes; resource limits mean unknown.

## Input language

The public `solve_attack(..., decision_ticks=1)` now exposes a physical-tick
control graph through the same parametric DAG. Default remains four ticks and
the browser API/player has not been switched to one-tick plans.

For fixed environment semantics, four-tick control words embed in one-tick
words by repetition. The inclusion is strict: the actual CSV/operator/C-space
regression in `test_parametric_decision_ticks.py` has a one-tick no-hit witness
and no four-tick witness. Coarse-grid exhaustion cannot prove native infeasibility.
Old four-tick-specific pruning is disabled on the finer grid. This extends the
input language, not a claim that broader search is automatically faster.

The Real HELL one-tick probe reaches tick 827 at both 5,000 and 20,000 nodes;
the former four-tick probe reaches 1496. Both are resource limits. The existing
ordering does not exploit the larger input language efficiently.

## Sufficient dead-state certificate

Let B_t enclose every position reachable at tick t under all legal one-tick
inputs. Propagate an outward-rounded box using the incoming velocity on the
first tick and the red-heart velocity bound on subsequent ticks. Retaining both
the old and moved coordinates includes either outcome of the coupled solid
collision tests. If one white C-obstacle contains B_t, every control word is
unsafe by that time. This proves false in Boolean Bellman reachability.

`red_reachability_bounds.py` implements this only in its certified domain:
fixed red mode and arena, no teleport/slam/platform, one CustomMovement substep,
and no possible conditional clamp. It uses outward `nextafter` and the original
closed `position +/- 2` comparisons. Unsupported events or noncoverage mean
unknown. Search truncates before unresolved observations. The certificate is
valid for both one- and four-tick control graphs and independent of reward.

The parametric search now applies a 64-tick certificate window by default;
`red_box_pruning=False` supports controlled comparisons. On the old Real HELL
prefix, tick 1464 already certifies death by 1503, and 1484/1488 certify death by
1497. The original 1496 state is itself doomed on the next movement tick under
every mask; its old velocity acts before the next input.

Independent review enumerated 33,280 control words over 110 supported prefixes
and found all positions enclosed. Unit tests also cover actual deadline values,
unsupported transitions, target truncation and agreement with unpruned search.

## Exact product representation, experimental

`factored_red.py` factors suitable fixed-red kinematics into exact binary64
single-axis automata and a coupled Boolean reachable set. It preserves final
input masks and all reachable exits. It does not choose one segment exit as a
substitute for the others. It is not enabled in production.

The first proposed closed-interior proof failed review: touching a top border
can stop horizontal movement. The implementation now rejects border contact at
entry and along generated micro-trajectories. Outside this sufficient domain,
factorization is not certified. Unit tests compare full exit states against
unfactored operator enumeration for both 16 and 32 masks, including Cancel's
shared speed coupling.

## Cost measurements

The five-ordering experiment found genuinely different local dead states,
not observed floating near-duplicates or GetHeartPos history growth, before the
first target at tick 18835. See `scratch/realhell-opening-ranking-findings.md`.
Forecast time reductions were hoisted out of the per-mask loop without changing
floating reduction order: 3192 score tuples and the original bounded route
prefix/expansion count matched exactly.

Environment clone/deepcopy is a separately measured execution bottleneck. It is
not evidence that a different state can be merged, and fixing it alone does not
resolve the combinatorial dead region. No full-wave millisecond claim is made.

After integration, 118 relevant tests passed in one run (parametric search,
resumable environment, public entry point, candidate enumeration, timing grids,
terminal completion, interval certificates and factorization). This is a model
regression result, not native Real HELL acceptance.

## Original-source post-integration probe

`scratch/realhell-red-bound-opening-result.json` records a fresh four-tick,
coast60 run with the original captured state/environment/clock and unchanged
source. One retained search tree was extended from 5,000 to 20,000 states.
At 5,000 it reached tick 1488, with 804 certificate cuts and 4195 expansions.
At 20,000 it reached tick 1500, with 3260 certificate cuts and 16739 expansions.
Both statuses are resource_limit. The old 20,000-state probe reached 1496;
this is a small advance, not resolution of the bottleneck or evidence of an
overall speedup. Environment compilation took 122.845 seconds; initial search
took 14.562 seconds including load, continuation another 6.006 seconds.

Next mathematical work must address the larger reachable set and its ordering
around the intersecting laser/stab corridor, rather than simply increase the
budget or identify four-tick timing as the sole cause. Factorization remains
experimental; dialogue coupling and terminal-tail player integration remain
unfinished. The server process was not restarted by this work, so its loaded
solver still predates this turn's changes.
