# Exact C-space sections for the joint relation

This optimization changes how safety predicates are evaluated. It does not
change the reachable state set, action alphabet, or collision margin.

For a fixed horizontal coordinate x, a convex quadrilateral intersects the
player box exactly when its bounding-box tests and all separating-axis tests
hold. Each axis gives inequalities of the form

    fl(fl(ax*x + ay*y) + radius) >= polygon_min
    fl(fl(ax*x + ay*y) - radius) <= polygon_max.

For finite intermediates, each left side is monotone in y (increasing when
ay > 0, decreasing when ay < 0, constant when ay == 0). Consequently, on a
numerically sorted array of actual y coordinates, the accepted indices form
one interval. Binary search evaluates the original floating-point operations,
without dividing by slopes, computing rounded intersections, or moving a
boundary by epsilon. Intersecting these index intervals gives precisely the
original SAT result. Rectangles have the same interval property.

`cspace_slice.py` unions those intervals into two bit planes: unconditional
hazards and blue hazards. The final predicate is

    unconditional[x,y] OR (moving AND blue[x,y]).

`red_section_frontier.py` builds the observation coordinates from every
microtick of the certified axis traces. Numeric sorting applies only to
collision observation IDs. Exact-bit position/velocity axis IDs, correlated
joint occupancy, all intermediate collision checks and endpoint identities
remain unchanged. Even signed zero IDs are retained. After one safe incoming
edge proves an endpoint reachable, another incoming edge can be skipped for
Boolean reachability; this does not prove arbitrary reward optimality.

The safety-query cost changes from pointwise geometric predicates over the
coordinate product to interval queries per x and hazard, followed by bit-word
unions. The complete transition relation must still be propagated. Therefore,
sub-millisecond collision baking is not a claim of sub-millisecond complete
game solving.

## Checked domain

The existing red-axis specialization certifies fixed red dynamics, no relevant
platform/teleport/slam coupling, and strict interior single-step movement.
The section wrapper additionally requires finite bounded traces, valid ordered
rectangles, and finite active quadrilateral coordinates. Absolute magnitudes
at most 1e9 keep SAT intermediate products finite; a separate origin/cell-size
check keeps expanded grid indices below 2**62. All-NaN rectangle padding
and inactive polygons are allowed. Outside this domain it calls the original
dense operator without deleting any route.

The rectangle guard matters: the grid baker ignores inverted rectangles,
whereas direct box intersection can accept one narrower than the player box.
The independent audit supplied [319,305,321,303] at player (320,304) as a
counterexample. A regression test verifies fallback to the existing grid query.

## Evidence

- 12 unit checks cover original SAT tangencies, ULP neighbors, rotations,
  degenerate/absent shapes, rectangle inversion, bit padding, signed-zero
  observation IDs, both moving planes, complete small joint relations,
  predecessor recovery, and budget/domain fallback.
- `scratch/cspace-section-differential.json`: nine actual Real HELL source
  frames, roughly 750,000 coordinates, both moving states: every output bit
  agrees with the original collision query. Per-frame section bake measured
  0.10–0.18 ms versus 7.9–10.1 ms pointwise (warm kernels).
- `scratch/section-checkpoint-704.json`: all 79,415,230 output classes from
  tick704 to708 have identical axis, template and occupancy bits; 3.40 s in
  the first run and 3.47 s with the first domain guard, versus the prior
  observation cache's 15.38 s. The later 1488 evidence includes the final
  grid-index guard and records its module hashes.
- `scratch/section-checkpoint-1488.json`: current guarded module preserves all
  11,582,454 exits through tick1492, including real beam quadrilaterals, in
  1.96 s. Input and output snapshots are read-only in both benchmarks.

These are mathematical-model differential checks, not native game acceptance.
Normal seed42's historical acceptance remains separate; Real HELL is unfinished.
