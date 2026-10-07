# Original Real HELL linear differential and Fire hotspot correction

Evidence consists of 14 original native trace shards, timestamps 154715 through
154718, covering consecutive ticks 293217–294544, plus their starting observation
at 293216. Each trace's SHA256 is recorded by
`scratch/verify_realhell_linear_native.py` in
`scratch/realhell-linear-native-independent-verdict.json`.
No checkpoint was restored in this linear run. All 1328 execution ticks retain
HP 92 and KR 0. This is a bounded prefix, not full Real HELL acceptance.

The verifier compiles the original unchanged source with the plan's recorded
source initial state, pre-TLPlay environment and clock. It applies zero input
through model tick 160 and then each of the 332 supplied masks for four physics
ticks, through tick 1488. Geometry comparison matches unordered object sets;
polygon matching allows cyclic vertex rotation and reversed winding, but no
coordinate deformation. Collision checks use an independent separating-axis
implementation on recorded native geometry and model geometry.

The native damage object is type 42, SID 165116925986465, the sole member of
family 71. Its `vars[0] > 0` gates damage. Its actual quad is used, rather than
the AABB of the rotated beam. The visible beam (type 31, SID 9836012384209519)
has animated width and exists while harmless, so comparing all visible sprites
to damaging polygons is not an equivalence requirement.

## Discovered discrepancy

Before correction, player state, arena, exact dt and white rectangle geometry
matched bit-for-bit for all 1329 observations. There were no blue rectangles in
this prefix. Damaging beam counts matched, but 236 observations had coordinate
errors above 1e-8; maximum error was 8.375 pixels. The first discrepancy was at
model tick 876.

At tick 875, native blaster UID 161 had position
`(658.3590635868175, -71.35906358681744)`, angle 135 degrees, size 114 by 88,
and actual bounding-box bottom `-0.6483875755051116`. It was already outside
the viewport, so native stopped its retreat at tick 876. The model assumed the
sprite hotspot was its centre and still considered part of it inside. It took
an extra step of `2070 * dt = 8.625` pixels, producing an axis error of
`8.625 / sqrt(2) = 6.098795987848` pixels.

The original data specifies all five Fire animation frames as 57 by 44 with
hotspot `(0.5087719559669495, 0.5)`. The Default animation's different hotspot,
`(0.4912280738353729, 0.5)`, cannot be used during Fire retreat.

For scaled width W, height H, angle unit vector u=(cos a,sin a), and Fire
hotspot hx, the sprite's geometric centre is

`c = (x,y) + (0.5-hx) W u`.

Its axis-aligned half extents are

`rx = (|cos a| W + |sin a| H)/2`,
`ry = (|sin a| W + |cos a| H)/2`.

The corrected common helper `_blaster_fire_bbox` computes these bounds for all
blaster sizes and directions. It changes no attack script and adds no attack
specific branch. Both reference and resumable compilers use the same entity
class. Old compiled environment caches must be invalidated by source hash.

## Verification after correction

- 1329 observations: player11, arena, dt and white rectangles bit-for-bit equal.
  Direction is derived from the recorded angle; the player's final per-tick
  damage field is inferred zero from unchanged native HP/KR, not directly logged.
- 3010 damaging beam quads over 512 observations: object counts identical;
  maximum coordinate error `2.2737367544323206e-13`. All observations meet the
  declared absolute tolerance 1e-8. Beam geometry is not claimed bit-identical
  across Python and JavaScript trigonometry/quad arithmetic.
- Native geometry and model geometry both report zero path collisions;
  native recorded HP/KR remain unchanged.
- 111 tests passed: original first-divergence regression, all Fire frame
  metadata, 33 angle/size corner comparisons, 32 rotated boundary cases,
  resumable/environment differential and exact C-space tests.

The visual sprite diagnostic still reports 879 count mismatches, as expected:
11181 visible beam instances include non-damaging beams; collision geometry
contains only the 3010 damaging instances. This is explicitly excluded from
required collision-geometry equivalence.
