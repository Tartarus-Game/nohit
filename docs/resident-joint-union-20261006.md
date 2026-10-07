# Exact resident joint reachability and idempotent union

The certified fixed-red operator factors its kinematics into exact-bit axis
tables. A joint key is a pair of axis IDs; only pairs reached by an actual safe
edge are retained. Marginal axis sets are never treated as an independent
Cartesian reachable set. Each retained pair stores a real predecessor and mask.

For a fixed next layer, let `v = F(u,a)` denote its exact internal equivalence
class. Boolean DAG reachability obeys `R(v) = OR safe(u,a)` over reachable
predecessors. Once one safe edge makes `R(v)` true, further incoming edges to
the same class cannot alter this relation. Thus checking the reached bit before
performing that edge's microtick collision checks is exact. The first safe
witness remains unchanged. An unset bit still requires every relevant
microtick collision check. This optimization concerns existential safety, not
weighted optimal-path values; it must not be transplanted into a weighted
relaxation without comparing objective values.

On the original Real HELL frozen 636 frontier, full-state baseline parent
reconstruction and resident 640 outputs have all 1,145,772 internal classes
bit-identical except the provably irrelevant old input latch. Evidence is
`scratch/resident-frozen-differential.json`; the independent full operator
reconstructs every baseline output from saved parents and actual controls.

Moving the reached-bit check before collision changed observed 636→640 runtime
from 1.988 seconds to 0.426 seconds. All six saved arrays (axis values, joint
keys, input masks, persistent template, parents) were byte-identical to the
pre-optimization frozen resident output. Timing is a local observation, not an
end-to-end or millisecond campaign claim. Evidence:
`scratch/resident-union-shortcircuit-differential.json` and
`scratch/resident-joint-frontier-benchmark.json`.

Continuation was resumed from the complete 752 frontier with a 12-million
class budget. It preserves all descendants of all 500→612 entry classes, not
only the previously selected 612 state. Resource exhaustion retains the last
complete frontier and means unknown. `scratch/resident-500-entry-propagation/`
contains complete layer parent chains; its report is the authoritative latest
status. The running continuation imported the prior collision-before-bit
kernel; the next launch will use the proven short circuit.

At checkpoint 1000, 16 evenly spaced retained classes were reconstructed back
through resident and full-state layers to the original tick500 state. All
sampled witnesses were microtick-safe and ended at bit-identical full11 states.
`scratch/resident-witness-verdict.json` records the result and one full opening
prefix. Sampling is witness validation, not exhaustive proof of each edge.
Real HELL remains incomplete.
