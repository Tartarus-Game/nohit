# Independent dense relation and reverse witness audit

The new `red_dense_frontier.py` replaces explicit reachable-key/parent arrays with a dense Boolean occupancy relation over exact axis IDs. This representation remains a **joint** relation: the bit for `(ix,iy)` must be present. Marginal membership alone cannot justify reachability.

For a certified red window, the predecessor of a desired endpoint is searched over the full inverse-image sets of each axis transition. The implementation tests each joint pair's occupancy, then replays its actual control using the full player operator and checks every microtick for collision. It does not assume axis maps are injective. Existing saved layers suffice for reverse witness recovery, so omitting eager parent storage does not discard an existential solution.

The internal class omits the previous mask only in the certified red domain. `predecessor(..., terminal_mask=...)` now supports an explicitly requested allowed physical mask, including a noncanonical equal-velocity alias. Default predecessor queries are explicitly internal-class queries; they ignore the target mask but compare all other target fields bit-for-bit. A class state with mask zero must not be mistaken for a verified physical endpoint outside this domain.

## Findings and repairs

Initially, an empty frontier returned `complete` before validating pending target, bound target-observation, or dialogue boundaries. Three independent regressions reproduced this contract discrepancy. The module owner moved validation before the empty return. The reverse query previously checked only the four kinematic fields; it now checks persistent fields and exposes the explicit terminal-mask option.

`tests/unit/test_red_dense_frontier_audit.py` includes:

- A missing cross-pair whose x and y marginal values both exist; inverse lookup correctly rejects it.
- Many-to-one x and y transitions with only two of four inverse pairs occupied; reverse recovery finds an actual predecessor.
- Full-operator endpoint-set comparisons with nonuniform source dt and one-ULP-separated initial coordinates, using one- and four-tick holds and all 32 masks.
- Converging safe/unsafe paths in both orders: the destination bit is published only after a safe path; only a previously safe destination permits collision-work short-circuiting.
- Empty/nonempty boundary validation, actual empty-output compaction, and subsequent empty propagation.
- All 32 requested terminal masks recovered and replayed to bit-identical full states; one-ULP changes to every persistent target field are rejected.

Validation:

```powershell
.\tools\uv_py.bat -m pytest tests/unit/test_red_dense_frontier_audit.py tests/unit/test_red_dense_frontier.py tests/unit/test_red_joint_frontier_audit.py -q
```

**34 passed in 6.58 seconds.** The initial new audit had 9 passing cases and the 3 empty-boundary failures before repair.

## Checkpoint publication

`scratch/propagate_dense_earlier.py` saves a layer to a temporary NPZ and replaces the final layer path before updating `reached_tick` in a separately replaced report. An interruption before report publication therefore leaves the preceding complete layer authoritative; a later orphan layer may be recomputed. This is process-interruption ordering, not a claim of filesystem durability across power loss.

A read-only independent check of the published tick-656 checkpoint found report count = stored count = bit population count = **49,505,673**. Bitset length matched the axis-product capacity, padding bits were zero, and arrays occupied **7,790,008 bytes**. This checks the consistency of a committed checkpoint; it does not independently prove all of those states reachable. The differential relation tests and previous operator/native correspondence are separate evidence.

At audit time resume checked the geometry-helper hash only. Expanding provenance checks to the source, initial phase, operator, C-space and dense implementation was recommended to the module owner before future cross-version reuse.

## Scope

This is exact Boolean reachability in the certified domain and selected input-hold protocol. It does not optimize path-dependent rewards, prove one-tick completeness when callers use four-tick holds, or establish a full native Real HELL no-hit run. New entry propagation is still ongoing.
