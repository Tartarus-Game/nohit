# Exact internal-layer input-latch quotient

`full_local_relation(..., input_latch_quotient=True)` optionally compresses
internal layers. It never quantizes position/velocity, changes controls, or
projects the requested terminal layer. The default remains false. Real state
representatives and their original predecessor/control witnesses are retained.

For a fixed known next environment row e, define J(e)=0 in red mode and the
gravity-direction jump bit in blue mode. A slam pulse forces blue even when
e.mode is zero. The projected key is the full binary64 state with its previous
input mask replaced by previous_mask & J(e).

The source CustomMovement phase does not read the previous input mask. After
movement, PlayerMovement overwrites mode and gravity from e (including slam),
then reads only the previous jump bit in its jump-press/release predicates.
Finally it writes the selected current control as the output mask. Therefore,
for any two states with equal projected keys and for every legal current mask
u, F_e(s,u) and F_e(s',u) are bit-identical full states. Damage and velocity
used by collision checking are included. The next collision decision is thus
also identical. Induction gives equality of all safe future control languages,
not merely equality of one preferred rollout.

This proves Boolean safety reachability, not preservation of every reward
objective. For example, a switch penalty `mask != previous_mask` can differ
between two representatives even when their next states coincide. A weighted
Bellman optimizer must additionally prove reward compatibility, retain separate
cost labels, or enlarge its key with the reward-relevant previous-mask data.
The current `full_local_relation` is a pure reachability relation and returns
one witness per state, without claiming a minimum-switch or optimal-weight route.

Keeping one actual representative per internal equivalence class therefore
preserves every reachable final full state. The terminal layer uses the full
88-byte state key, so even different final physical masks remain distinct.
If a resource limit is reached at an internal layer, its frontier represents
all completed equivalence classes at that layer; it is not advertised as an
enumeration of every raw mask variant at that intermediate tick. Its status
remains resource_limit, never exhausted or globally infeasible.

No observation may occur within this fixed-environment relation. Existing
checks reject unbound targets, bound GetHeartPos events, and dialogue boundaries
inside the requested window. The projection consults the next environment row,
not the current player's mode or old gravity direction. This distinction is
necessary at a red-to-blue or slam boundary.

## Audit of other persistent fields

| State field | Source read before overwrite | Consequence |
| --- | --- | --- |
| x, y | Both CustomMovement axes and collision | Always retain exact bits |
| dx, dy | First next-tick displacement and contacts | Always retain exact bits |
| previous mask | Only next-mode gravity jump bit | Implemented projection |
| slammed | Wall contact, damage, and persistence | Retain |
| old mode | Copied to local, then overwritten by env[4] before use | Transition-redundant for full env rows, but not projected here |
| old gravity direction | Old-phase one-way platform predicate | Retain; platform-free proof would be required to discard |
| old max-fall | Copied to local, then overwritten by env[8] | Transition-redundant for full env rows, but not projected here |
| old slam damage | Can create damage during old-phase wall contact | Retain; absence of a pending damaging slam would need proof |
| damage-this-tick | Current safety filter; next operator regenerates it | Safe frontier already has zero; retain |

Mode/max-fall are already the same in normal reachable states of a fixed
environment layer, so deleting them promises little or no practical reduction.
Direction and slam damage must not be casually removed because the late
environment overwrite happens after CustomMovement reads their old values.

## Verification and measurements

`test_local_relation_latch_quotient.py` checks all physical current masks for
each projected previous-mask class across red, blue, all gravity directions,
and forced slam rows, including contact-adjacent states. It separately checks
the next-direction/slam negative case. One- and four-tick relations retain
exactly the unquotiented terminal state sets across red/blue/slam changes; each
returned witness independently replays to its exact stored terminal state.
Together with the pre-existing local relation and closure tests, 21 tests pass.

`scratch/benchmark_local_latch_quotient.py` compares the corrected original
RealHELL source in the same process. For tick 500→612, both versions return all
44,676 exact terminal states. Internal expanded-layer states fall from 309,979
to 115,976; measured time falls from 4.491 to 1.722 seconds. This is a local
constant-factor improvement, not a whole-game solution or a millisecond claim.
The raw report records source/helper/module hashes, counts, timings, and the
complete terminal-set equality check in `local-latch-quotient-benchmark.json`.

For tick 612→1528, both versions completely exhaust at tick 1512 with no
terminal states in the declared 16-control, four-tick domain. Expanded-layer
states fall from 5,184,970 to 2,906,632, peak frontier from 158,209 to 88,843,
and measured time from 74.043 to 40.600 seconds (about 1.82 times faster).
This remains a result for that particular starting state and control domain;
it does not discard other tick-612 entry states or establish original-game
infeasibility. The original source/helper hashes are recorded in the report.
