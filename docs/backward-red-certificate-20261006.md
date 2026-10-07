# Independent backward certificate for the fixed Real HELL model

`scratch/certify_backward_red.py` certifies an empty relaxed position-viability set at tick **1264**, for surviving until tick **1528**, under the currently baked environment and timestamp protocol. It covers the complete closed position domain x `[254,393]`, y `[239,378]`, with incoming red velocities bounded by 150 on each axis. It does **not** claim that the original game is unsolvable.

This changes the next investigation: changing the earlier opening cannot repair this particular fixed model's obstruction if its states enter this domain. Source/native collision and clock correspondence must be audited at the obstruction. Arbitrary original-game behavior, a different dt protocol, or states outside the certified domain are not covered.

## Domain checks

The script verifies all environment rows from 1264 through 1528: fixed old/mid/current arena bounds, red mode, no slam or teleport, no active or pre-movement platforms, positive finite dt with at most one movement substep for every velocity in `[-150,150]`, and no unresolved or bound player-target observation or dialogue boundary. It also checks the geometry/SAT/index domain of the section operator.

Controls may change on every physical tick in this relaxation. Only every fourth tick's white/polygon collision is tested. Blue collisions, intervening collisions, control hold restrictions and velocity correlations are ignored. These omissions can only add paths; they cannot justify deleting a genuinely surviving path.

## Complete closed cells and transitions

There are 1112 × 1112 closed cells, each width at most 0.125. Adjacent cells share endpoints. The last cell contains the exact right/bottom boundary; lookup conservatively includes both owners of an interior endpoint.

To avoid treating the native clamp as an ideal real-number projection, the script finds exact binary64 thresholds of `q-8 >= L+5` and `q+8 <= R-5` by ordered-float bisection. It records both those thresholds and the actual assigned constants `(L+5)+8` and `(R-5)-8`. Their extrema give a closed domain invariant under the clamp.

For each source cell and each of the four future microticks, its successor interval includes all displacements in `[-150*dt,150*dt]`, with each product and addition expanded by `nextafter` in the outward direction. This includes both accepted movement and a wall-stopped zero displacement. The interval then follows the exact conditional clamp partition: all-true branches replace the interval with the assigned constant, and mixed branches union the constant with the retained-coordinate interval. An assertion establishes that the whole candidate box overlaps the arena, so the enclosing native clamp guard always executes. The resulting intervals remain in the recorded post-clamp domain.

An integral image answers whether each cell's conservative successor rectangle intersects any viable next cell. No empirical roundoff allowance or assumed velocity independence is used to narrow this rectangle.

## Whole-cell collision certificates

A cell is blocked only when **one same obstacle** collides at all four corners under the original scalar rectangle/SAT operations. Each SAT inequality is separately monotone in each coordinate under the finite-intermediate domain, so its extrema lie at corners. Passing the collision test at all four corners therefore implies every point in the cell collides with that obstacle. Taking the union of these individually certified whole-cell obstructions is safe. Testing corners against an arbitrary union of different obstacles would not suffice and is not used.

The implementation obtains these four-corner intersections efficiently using exact section index intervals; it does not use a shrunken hitbox or the earlier heuristic `0.001` margin.

## Backward induction

Let `V_T` contain every terminal cell not certified fully blocked. For each preceding sampled time, retain a cell iff it is not certified blocked and its conservative successor rectangle meets `V_next`. If a real surviving trajectory exists, its terminal position has a retained cell. Inductively, its prior position also has a retained cell because its actual successor belongs to the conservative rectangle. Therefore an empty `V_1264` excludes every trajectory in the declared model/domain, including all one-tick input choices allowed by the velocity bound.

The run retained 156,844 cells at tick 1268 and **zero** at tick 1264. The initial complete run took 4.90 seconds. The final artifact records source, phase, script, module and baked-window hashes in `scratch/backward-red-certificate.json`; `scratch/backward-red-certificate-grid.npz` stores the complete cell edges and empty resulting grid.

## Independent helper checks

`tests/unit/test_backward_red_certificate.py` checks 2,500 boundary/random four-tick transitions against the complete player operator, using arbitrary incoming velocities within the certified range and independently changing all 32 input masks. Every result remains inside its predicted successor intervals. It additionally verifies same-obstacle corner witnesses and interior sample collisions for every blocked cell of a synthetic scene. Both tests pass. These tests supplement the containment and induction arguments; sampling alone is not the certificate.

No live propagation, native runtime, original CSV, damage or physics was changed. This certificate is diagnostic evidence of a fixed-model inconsistency with the requested no-hit outcome, not permission to alter the original game or declare original-game UNSAT.

## Matched-window literal-clock comparison

The script also accepts `--literal-dt`, which compiles a separate hypothetical constant `1/240` environment without touching gameplay. For the **same** 1264→1528 interval, closed domain, 0.125 cells, and certificate algorithm, that alternative also yields an empty tick-1264 set (12,264 cells remain at 1268). Its output is `scratch/backward-red-certificate-literal.json`, with explicit clock protocol and separate environment/geometry hashes.

Thus the earlier nonempty coarse literal-clock diagnostic, which used a different terminal tick and looser discretization, does not establish a route or overturn this matched-window result. A nonempty conservative relaxation is unknown, not a feasible witness. Neither fixed-clock certificate is an original-game impossibility verdict.
