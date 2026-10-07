# Exact axis tables with a coupled joint relation

Independent experimental module: `nohit.engine.red_axis_expansion`.
It does not replace the local Boolean reachability algorithm. It reduces
repeated work and temporary edge storage for supported fixed-red transitions.

## Why the tables are exact

The accepted environment window has fixed old/mid/final arena bounds, red
input updates, no slam/teleport, and no active or pre-active platforms. Each
axis trace is computed by the complete source-derived operator with the other
coordinate fixed at a strict interior center, its velocity zero, and its input
bits omitted. Both current and resulting coordinates must satisfy the original
strict +/-8 border comparisons at every microtick, and displacement must have
native CustomMovement count one. A trace failing any check is not certified.

If both actual joint axes have certified traces, every horizontal step sees
the actual y strictly clear of top/bottom borders; its remaining border tests
depend only on x. The resulting x is strictly interior, so the vertical step's
remaining border tests depend only on y. Induction gives exactly the two table
traces, including blocked attempts toward a border. In particular, this does
not assume a y touching a border cannot block horizontal movement. Such a case
fails certification and executes the full operator instead.

The old experimental `factored_red` was more conservative: its single-axis
simulation allowed the other coordinate to move under the same full mask.
That could reject a table because of unrelated other-axis motion. Fixing the
other axis and retaining an explicit joint certificate avoids that rejection
without claiming global axis independence.

## Why the relation is not a Cartesian approximation

Only states already present in the actual joint frontier are expanded, for
each actual allowed input. Tables provide their deterministic coordinates;
the original collision oracle still checks the combined state at every
microtick. No absent (x-axis state, y-axis state) pair is introduced.

Axis IDs intern raw binary64 pairs (position, incoming velocity), not rounded
coordinates. Terminal IDs similarly intern exact outgoing pairs. For nx and
ny endpoint IDs, the packed key

    ((x_id * ny) + y_id) * 32 + actual_mask

is injective over the represented joint states and input latch. The only old
non-kinematic field surviving this red update, `slammed`, must have identical
bits across the packed batch; all other final fields are explicitly assigned
by the common environment/input. Signed integer capacity is checked. Thus
deduplicating this key removes only identical full states. One actual parent
and actual control witness is retained. Requested terminal masks remain distinct.

`compact_red_axis_step` returns `(states, parents, masks, stats)`; states are
full 11-field exits. `None` means the environment is unsupported and requires
the full operator. If any individual axis trace fails certification, this
version falls back to the unpacked full-operator expansion and exact dedup.
The caller remains responsible for known-environment/observation boundaries,
as with the existing low-level `_expand` kernel.

## Differential evidence

Four tests compare all outgoing bytes and parent/control witnesses with the
complete operator: 1/4 tick holds, all 32 masks, closed border and nextafter
states, excessive incoming velocity, and unsupported blue mode. Packed keys
also preserve nextafter-distinct interior entries and every final input mask.

Corrected original Real HELL model, all 44,676 tick-612 entries from the
actual tick-500 prefix, all 16 arrow controls, four-tick holds:

| Window | Safe edges | Exact full exits | Full expansion + dedup | Packed axes + dedup |
|---|---:|---:|---:|---:|
| 612→616 | 707,808 | 140,059 | 0.637 s | 0.240 s |
| 616→620 | 2,226,416 | 431,225 | 2.007 s | 0.769 s |

Every exit set is byte-identical. The unpacked axis implementation additionally
matches every safe edge and parent/mask array in original order. At 616→620,
195.9 MB of repeated 88-byte edge states becomes 17.8 MB of 8-byte edge keys;
predecessor/mask arrays and the eventual unique full-state frontier are extra.
This reduces a constant factor, not the number of inequivalent reachable
states, and does not establish passage through the whole battle.
