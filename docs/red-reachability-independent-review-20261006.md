# Red reachable-box certificate: independent review

Scope: `red_reachability_bounds.py` and its call in `ParametricRouteIterator`.
This review validates a sufficient dead-state certificate, not a complete
feasibility decision procedure or original-game completion.

Let B_k be the maintained closed center-coordinate rectangle. The invariant is
that every surviving concrete input continuation lies in B_k. With native
CustomMovement count equal to one, each axis either keeps its old coordinate or
accepts its displaced coordinate. Including zero in each displacement interval
therefore encloses both outcomes even when the horizontal position changes the
vertical solid predicate. No assumption of independent axis feasibility is made.

The first displacement is computed from the actual incoming velocity; all
subsequent velocities in the accepted red domain are within [-150,150]. Each
arithmetic bound is widened by nextafter. Monotonic rounded floating arithmetic
then preserves enclosure inductively. The explicit native sqrt(delta*delta)+0.5
test rejects count transitions, including the rounding-sensitive threshold.

The first-step tightening is sound: its four strict inequalities exclude all
border contacts for the entire old-to-proposed box, including the intermediate
horizontal/vertical test positions. Active and pre-movement-active platforms
are excluded. Thus neither axis can stop at that step. Later steps retain the
zero-displacement alternative. The clamp guard rejects any box for which a
native conditional clamp could execute; it does not assume mathematical clipping.

If the original x+2/x-2 and y+2/y-2 predicates hold at the appropriate extreme
endpoints for one white rectangle, their monotonicity implies every point of B_k
collides. Earlier-collided continuations are already dead. Therefore a True
result proves no surviving word through that tick. False remains unknown.

Integration stops no later than pending_target.tick-1, so the proof does not
consume the unresolved observation frame. Other incomplete bindings are stopped
by the existing resolvability guard. Initial player state and environment arrays
must satisfy their declared full11/env22 contracts.

Validation: existing 15 unit cases pass. Independent
`scratch/review_red_bounds.py` enumerates closed-border and adjacent nextafter
positions, incoming velocities -150/0/150, normal and near-threshold dt. All
33,280 concrete words in 110 supported prefixes lie in their certified boxes.
This is adversarial evidence in addition to the inductive argument, not a proof
for unsupported dynamics.

Minor robustness observation: state[0] and state[1] are read before the length
guard. Malformed short arrays should be rejected before those reads if the
function becomes a public untrusted-input API. Current full11 calls are unaffected.
