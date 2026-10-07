# Exact finite-window transition relation

**Model provenance correction:** the experiments below originally used a
centered Fire-sprite hotspot. Native replay found this wrong; the helper was
corrected on 2026-10-06. These original numbers are old-model diagnostics,
not proofs about the original game. Corrected-model results are recorded
separately after rerunning the entire prefix and relation.

`nohit.engine.local_relation.full_local_relation` computes the complete safe
endpoint set for a fixed environment window and explicitly declared control
hold. It calls the original-derived full discrete operator, so closed border
contacts, cross-axis solid coupling, platforms and changing arenas require no
separability approximation. Unresolved targets and dialogue preview rows cannot
be crossed. Already bound target observations inside the window are rejected
too, since alternative player states could change their values.

For frontier S_k and admitted masks U, the update is exactly

    S_(k+1) = { F_hold(s,u) : s in S_k, u in U,
                every intermediate microtick has zero damage/collision }.

All 11 float64 state fields, including the input latch, are interned by their
88 raw bytes. Two equal keys at the same time in the same fixed environment
have identical future transitions, so one predecessor witness per exact state
preserves every possible suffix. Different endpoint states are never ranked
away. `states[index]` and `witness(index)` provide each retained exit and its
complete control word. A macro edge may represent this whole relation, but
selecting one endpoint and discarding the rest does not preserve completeness.

Status `complete` means the requested endpoint set was completely computed;
`exhausted` means no safe states remain in this declared hold/mask domain;
`resource_limit` leaves the last complete frontier and is unknown for the
requested window. A caller must fall back or retain the unresolved computation,
not memoize it false. Four-tick exhaustion says nothing about omitted one-tick
input switches.

Real HELL source environment, seed 42, actual initial-phase metadata and the
existing diagnostic prefix were used, without native checkpoint branching.
The 1,600-row environment is explicitly incomplete for the full battle.

| Prefix state tick | Window end | Result | Endpoint count |
|---|---|---|---|
| 612 | 676 | complete | 7,812 |
| 1200 | 1264 | complete | 3,040 |
| 1460 | 1504 | exhausted at 1500 | 0 |
| 1440 | 1504 | exhausted at 1500 | 0 |
| 1400 | 1504 | complete | 1 |
| 1400 | 1528 | exhausted at 1508 | 0 |
| 1200 | 1504 | complete; same single endpoint | 1 |

These rows use all 16 arrow masks and four-tick holds. The 1400→1504
computation took about 1.2 seconds after JIT warmup; 1200→1504 took 3.75 seconds.
Crossing 1500 is not escaping the whole trap: its sole endpoint dies by 1508.
The script supports different starts, window ends, holds, masks and budgets;
there are no attack-specific tick constants in the engine interface.

Tests exhaustively compare all short control words at a closed border, verify
the witness for every retained exit, and verify unknown resource handling.

Additional microtick test: 1400→1528 with all 16 arrow masks and hold=1 fully
exhausts at tick 1509. Peak frontier 209,328 states; wall time 48.6 seconds.
Thus this particular prefix state is dead even in that finer input domain.
Cancel masks remain a different declared domain; earlier prefixes remain open.

With a 300,000-state budget, the actual prefix state at tick 612 also fully
exhausts by tick 1512 under 16 masks/hold=4. Peak frontier is 158,209 states;
69.7 seconds. This result contains every intermediate endpoint and is not a
budget failure. It does not establish whole-game infeasibility: earlier entry
states, different control domains, and source-model accuracy remain separate
questions. Detailed counts are in
`scratch/realhell-local-612-1528-hold4-controls16.json`.

## Corrected Fire-hotspot recheck

Helper SHA256 `b31e257c22f7733adaf8faab84b7aaa1ec5384f7c746dfa6cbb28291ff63c2fe`
was independently confirmed by the dynamics agent against native samples through
tick 1328. With a fresh corrected environment, the old diagnostic prefix remains
safe through tick 1496. Recomputing its tick-612 complete relation still exhausts
at tick 1512 (16 masks, hold=4, budget 300,000, peak 158,209, 64.23 seconds).
Every layer cardinality equals the old-model run; this comparison alone does
not assert byte-equal frontier sets. The corrected report includes source and
helper hashes; the old report has a `before-hotspot-fix` filename suffix.

An independent collision-query comparison used 308 ticks whose beam polygons
changed, sampling every quarter pixel over the nominal playable center box.
All 95,556,692 old/new collision queries agreed. Environment rows and white
rectangles are byte-equal. This is meaningful arena-local evidence beyond a
vertex displacement, but a finite grid is not a proof that every continuous
collision-set boundary is identical. The hotspot correction is necessary for
source fidelity; it did not resolve this particular local trap.
