# Real HELL: original geometry audit and complete local reachability

## Current state

Real HELL is unfinished. The existing Normal seed42 uninterrupted no-hit
acceptance remains unchanged. This work used only mathematical search and one
forward native diagnostic continuation, with no native checkpoint restoration.

The original runtime and data still match the jcw checkout byte-for-byte:
runtime SHA256 `664b5d93dbd5159976d490663ac64c49c8eb7dc68c9aac92fba940b6fa2a3de9`,
data SHA256 `9f70e7179fe4260002321a75e5170e96583439bb39988b92ed93da42a0a402c7`.
The Real HELL source SHA256 remains
`3b6252bc2d97a6ae5f82d63b8c8e82175cf1d819e85728e2f1fe9b1001106299`.

## Actual model error found and corrected

Starting at the already paused native tick293216/model160, a precomputed fixed
332-mask continuation was run once, forward only. Its 1328 physical ticks ended
at native294544/model1488, with HP92/KR0 throughout. Fourteen evidence shards
have names `bonesgap1-20261006-154715-*` through `154718-*`; the exact inventory
and hashes are in `scratch/realhell-linear-native-independent-verdict.json`.
The diagnostic browser is still paused there; it is not a victory screen.

The differential found an incorrect centred-sprite assumption in the model's
blaster retreat bounding box. Fire animation uses hotspotX .5087719559669495,
not .5 (nor Default animation's .4912280738353729). The old formula occasionally
allowed one extra retreat tick, shifting beam geometry by up to8.375pixels.
`compact_wave._blaster_fire_bbox` now uses the original Fire dimensions/hotspot
for all sizes and angles, without an attack-specific correction.

After correction, all1329 observations match player state, arena, dt and white
rectangles bit-for-bit; blue rectangles are absent in this prefix. Across3010
damaging beam quads, maximum error is2.274e-13pixels, within1e-8 but not claimed
bit-identical across JS/Python trigonometry. Both independent geometric checks
and recorded native HP/KR confirm this prefix is safe. See
`realhell-native-beam-hotspot-audit-20261006.md`. The111 related tests passed.

## Complete finite-window relation

`local_relation.full_local_relation` evaluates every legal control edge of the
full player operator and retains every bit-distinct11-field safe exit, including
the final input mask. One witness is retained for each identical exit state.
It refuses unresolved observation/dialogue crossings. Resource overflow returns
the last complete frontier with status `resource_limit`, not false.

Experiments on the old diagnostic prefix established:

* From1400, four-tick words have one exit at1504, then none by1508.
* From1400, one-tick words exhaust by1509 (peak209328states).
* From612, four-tick words exhaust by1512 (peak158209states).

The612 four-tick experiment was rerun after the hotspot correction: old prefix
replay remains safe, exhaustion is still1512, and every layer count is identical.
Thus the correction does not rescue that particular prefix/control domain.
It says nothing about other612 entry states or the full original input domain.
Additional quarter-pixel arena sampling found no collision changes for the
308changed geometry ticks; finite sampling does not prove continuous equality.

The main iterator now has optional `closure_window`, `closure_trigger`, and
`closure_max_states`. When DFS stalls, it can fully evaluate a window from an
earlier ancestor. Only `exhausted` permits marking that ancestor dead. Nonempty,
unsupported and truncated relations leave the existing DFS untouched. A bounded
subset of all intermediate Bellman false facts is retained for sibling reuse.
The default window is0: this remains experimental because the measured5000-node
probe still reached1488 and took104.7seconds, including4.45million additional
local states, even after retaining100000dead-state facts. These are extra work
budgets and must not be hidden in a same-node-count speed comparison.

## Compilation and ranking evidence

Public environment stepping remains pure. The collector now consumes privately
owned states between branching/preview boundaries, avoiding deep-copying every
entity each tick. The actual18836-frame binding observed12.145seconds versus
122.845seconds before; all arrays/events/history through18845 matched the
reference implementation.36 isolation/differential tests passed. Details:
`owned-environment-continuation-20261006.md`.

Removing navigation from coast ordering worsened progress. Replacing the coarse
navigation displacement with150pixels/second did not improve the bottleneck.
The corrected-hotspot fresh20k baseline still reaches1500, with16739expansions
and3260red-box cuts. Its prefix and terminal state match the prior baseline.
See `scratch/corrected-blaster-baseline.json`. No complete route exists in these
results, and no infeasibility of the original attack has been established.

## Continuation details

Server8103 was restarted after tests, now PID28216. Logs:
`scratch/owned-hotspot-server.log` and `.err`; startup47.245seconds, listening
127.0.0.1:8103. Verify PID/command before future restarts. Port8102 was untouched.
The browser retains the original Normal victory tab5 and diagnostic Real HELL
tab6. Tab6 is unseeded, though the tested prefix executes no RND; a final full
acceptance must start fresh with seed42. Its `__LINEAR_DIAGNOSTIC` object holds
only the fixed plan and evidence filenames, not a branch search.

Next work should investigate reachable entry states before612 and the actual
control/time domain, and continue source/native comparisons as needed. Confirm
dialogue coupling, terminal-tail playback and automatic full Real HELL execution
remain unfinished. All current physical proofs explicitly assume240Hz stepping;
frame-dependent source updates must not be silently assumed invariant under
different clock schedules.
