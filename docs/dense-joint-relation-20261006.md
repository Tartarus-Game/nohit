# Dense exact joint reachability

`red_dense_frontier.py` represents the finite reachable relation by exact-bit
axis tables and a single occupancy bit per possible axis-ID pair. It never
replaces the relation with its marginal Cartesian product. Each output bit is
set only after a reachable predecessor's entire discrete trajectory passes
every microtick C-space collision test.

This changes witness representation, not the admissible relation. Eager
per-node parents, input masks and key lists are omitted. Every complete layer
is retained. Given a reached terminal class, the inverse finite axis maps
enumerate all possible predecessor pairs; the occupied-pair test and the full
discrete operator identify an actual safe incoming edge. Repeating this
recovers a witness. `terminal_mask` optionally requires a specific allowed
final input alias. Internal classes omit the irrelevant previous red-input
mask; all other target fields are compared bitwise. The representation is
limited to certified red windows and rejects unresolved observations/dialogue.

Unused marginal IDs are removed only after completing the entire union. The
occupancy bits are then relabeled injectively. This operation cannot invent or
remove a reachable pair. Resource exhaustion returns the untouched previous
complete relation; it is never an empty-set certificate.

Frozen original-source 636→640 differential validation retained all 1,145,772
classes with bit-identical axis tables. Sixteen inverse witnesses passed.
The output occupies 235,600 bytes, versus 19,570,500 bytes for the previous
resident representation. This is a representation reduction, not a promise of
millisecond end-to-end solving. Measured expansion took 0.351 seconds.

The new earlier-entry frontier at624 is propagated independently in
`scratch/dense-earlier-624-propagation/`. Each complete snapshot is first
written to a temporary NPZ and atomically renamed; only then is the report
atomically updated to reference that layer. Thus the report identifies a
complete usable layer even if a later operation is interrupted. The script
`scratch/propagate_dense_earlier.py` owns this run. Its latest report, rather
than this document, is authoritative for status.

Independent tests additionally cover joint correlation, many-to-one inverses,
nonconstant dt, all32 final-mask aliases, persistent-state perturbations,
unsafe-before-safe incoming edges, empty-set observation boundaries, and
snapshot bit popcount equality. No native branching or original-source edits
are involved. Real HELL completion remains unproven.

## Collision observation quotient and persisted model identity

The optional `red_collision_observation_cache.py` accelerator shares collision
results by `(tick, exact x bits, exact y bits, moving)`. It does not merge
dynamic states. This is valid only for the certified zero-slam-damage domain,
fixed geometry and margin zero: those are exactly the fields read by
`collision_query`. Distinct tick offsets and moving predicates have separate
cache entries; neighboring floating-point coordinates receive distinct IDs.
Unsupported states are rejected before caching. A cache-memory limit falls
back to ordinary exact propagation rather than trimming the relation.

The full frozen 704→708 relation, including all79,415,230 occupied classes,
axis values and persistent template, matched bitwise. That expansion measured
15.38 seconds versus the prior36.58 seconds, with a33.26 MB cache. The original
proof JSON is immutable; `scratch/collision-cache-equivalence.json` binds its
SHA256 to the exact tested kernel SHA256.

The propagation directory now has immutable `provenance.json`: original CSV,
phase data, explicit initial environment and clock, all13 recursively imported
model-input files, compiled environment arrays, Python/NumPy/Numba versions,
and the initial source/frontier hashes. The live legacy run was sealed only
after confirming every model file predated its verified process creation.
Resume recompiles and compares this problem identity before accepting any old
layer. Acceleration upgrades retain the parent identity and separately bind
their tested kernel and differential evidence.

After authorization for one reversible scheduling upgrade, PID19712 was
stopped only after verifying a committed checkpoint. The final committed old
layer was1020 with44,044,619 classes; its identity, SHA256 and popcount were
checked again after stopping. PID7164 resumed from that exact layer with the
cached kernel. Later status remains in the live report; these PIDs describe
that upgrade, not a promise they remain running indefinitely.
