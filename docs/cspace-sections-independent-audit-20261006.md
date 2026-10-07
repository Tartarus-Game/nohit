# Independent C-space section audit

## Monotonicity and floating-point operations

For fixed finite `x`, an SAT projection is evaluated as `fl(fl(ax*x)+fl(ay*y))` in the same operation order as `quad_intersects_box`. With finite intermediate values, binary64 multiplication and addition under the existing non-fastmath execution are monotone. Positive `ay` gives a nondecreasing projection and negative `ay` a nonincreasing one. Each strict separation predicate therefore has a prefix or suffix of true indices over numerically sorted `ys`. Its complement is an index interval; intersecting all SAT and bounding-box intervals gives exactly the indices accepted by the scalar predicate.

The section implementation does not divide by slopes, derive rounded geometric intersection coordinates, or merge nearby coordinates. Duplicate numeric coordinates and distinct signed-zero/one-ULP bit patterns retain distinct observation IDs. The inequalities preserve the original closed-edge collision semantics.

The direct primitive's contract requires sorted finite y coordinates. The integrated `red_section_frontier` builds them by bit-exact interning followed by stable numeric sorting. The actual dynamics and joint reachable relation are unchanged.

## Two discovered domain gaps

Equivalence to the full `collision_query` additionally requires respecting its existing grid acceleration contract, not only matching `_rect_hit` and scalar SAT.

1. An inverted rectangle `[319,305,321,303]` overlaps the radius-two heart at `(320,304)` under `_rect_hit`, but the existing grid bake skips inverted rectangles. Hence the existing `collision_query` returned false while the direct section returned true.
2. An ordered finite rectangle `[-1e30,-1e30,1e30,1e30]` caused existing grid index conversion to overflow its integer domain. Again the existing query returned false while the section returned true. A `1e100` SAT-overflow bound alone did not exclude this case.

Both were independently reproduced. The module owner added `section_domain` and an unchanged-query fallback. It requires ordered finite rectangle rows, except all-NaN padding; active quads with all finite coordinates; finite trace values; magnitudes at most `1e9`; finite grid origin and positive finite cell size; and a conservative grid-index bound below `2**62`. Inactive quads retain the original nonfinite-first-coordinate sentinel semantics. The magnitude limit also bounds SAT products and sums far below binary64 overflow. Unknown/invalid geometry is not discarded: the section accelerator falls back to `advance_dense`.

This proof assumes the supplied C-space bake belongs to the same wave geometry, as required by the existing solver interface. It does not bless malformed or stale external C-space objects.

## Collision observation decomposition

For a certified red edge, no damaging slam transition can occur, and the damage-this-tick field stays zero. The full collision observation is therefore

`unconditional_hit(x,y,t) OR (moving(dx,dy) AND blue_hit(x,y,t))`.

The two planes store unconditional and **blue-only** bits, not separate complete stationary/moving outcomes. The new joint kernel uses the OR expression correctly. Separate offset ranges retain the microtick identity. Coordinates are interned exactly; velocities remain in the transition state even when collision observation needs only their zero/nonzero predicate. The existing destination short-circuit still requires a previously verified safe incoming edge.

## Tests and scope

Independent tests add 120 finite random SAT cases over scales `1e-100`, `1`, `1e12`, and `1e100`, including arbitrary/degenerate vertices, signed zeros, and one-ULP neighbors. They compare every resulting bit against the unchanged scalar predicate. Integration regressions cover both geometry counterexamples and invalid/tiny grid-index parameters, requiring fallback rather than altered reachability.

Command:

```powershell
.\tools\uv_py.bat -m pytest tests/unit/test_cspace_slice.py tests/unit/test_cspace_slice_audit.py tests/unit/test_red_section_frontier.py -q
```

Result: **21 passed in 0.83 seconds**. Root separately supplied full frozen-frontier differentials and sampled source-frame evidence in `scratch/cspace-section-differential.json`; these are complementary empirical checks, not replacements for the domain argument above.

This audit did not edit the section implementation or running propagation. It establishes the optimization's finite-domain contract and regression coverage, not completion of the original-game no-hit objective.
