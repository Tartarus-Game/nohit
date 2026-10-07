# Earlier entry sets, corrected source model

These experiments use original Real HELL source SHA256
`3b6252bc2d97a6ae5f82d63b8c8e82175cf1d819e85728e2f1fe9b1001106299`
and corrected helper SHA256
`b31e257c22f7733adaf8faab84b7aaa1ec5384f7c746dfa6cbb28291ff63c2fe`.
Starts are exact states on the previously verified diagnostic input prefix.
All 16 arrow masks are held for four physics ticks; no Cancel or one-tick
completeness claim is made. Maximum stored frontier size is 300,000 states.

| Start | Requested end | Status | Last complete tick | States there | Time |
|---|---|---|---|---|---|
| 300 | 612 | resource limit / unknown | 508 | 223,860 | 42.16 s |
| 400 | 612 | resource limit / unknown | 592 | 275,912 | 31.69 s |
| 500 | 612 | complete | 612 | 44,676 | 4.38 s |
| 500 | 1528 | resource limit / unknown | 616 | 140,059 | 6.05 s |

The 300-start run had an earlier peak of 264,914 states. The other displayed
frontiers are their respective peaks. NPZ files with matching names under
`scratch/realhell-local-<start>-<end>-hold4-controls16.npz` store every actual
frontier state plus `initial`, `parents_i`, and `masks_i`. They retain one
exact witness for each state; no favored endpoint was selected. JSON files
record the termination status, counts and hashes. Resource-limit frontiers
are not the requested endpoint sets.

The complete 500→612 entry set has 156 distinct bit-pattern x positions,
112 y positions, three values each for dx and dy, and all 16 input masks.
Only one entry is bit-identical to the old tick-612 state:

    [279.62499999910386, 311.12500000005826, 0, -150, 4,
     0, 0, 1, 750, 0, 0]

Two entries match all fields except the previous input mask. At the next
committed red tick without a slam, that previous mask is not read for any
movement/input update and is overwritten by the chosen input. Those two
entries therefore have identical same-mask successor states and safety
outcomes, so the existing old-612 dead proof applies to both. The remaining
44,674 entries have not been shown dead. This is a legal future-state quotient,
not a proximity or rounding merge.

There is no position synchronization event between ticks 300 and 612.
SansSlam at 300, 384 and 468 changes velocity/direction but does not erase
position differences. HeartMode(0) at 610 changes mode and allows the red
input update to replace velocity, but the movement phase already used the
incoming velocity, and x/y persist afterward. Thus neither these events nor
the later return to red permits merging distinct y or x values. The actual
frontier measurements independently show surviving coordinate diversity.

The 500→1528 experiment performs the same-layer union and exact deduplication
of every predecessor branch. Its budget limit at 616 is evidence of a larger
unresolved entry set, not evidence of an impossible battle. Further work can
use the proven previous-mask projection or a more compact exact relation;
discarding entries based on the old single-prefix death proof is invalid.
