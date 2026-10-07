# Independent audit of resident joint reachability

Audited `nohit/engine/red_joint_frontier.py` and its axis-table operator on 2026-10-06. This is a reachability audit, not a claim that Real HELL has been solved or that a preferred witness is globally reward-optimal.

## Mathematical contract

Within a certified fixed-red, strict-interior window without platforms, slam, teleport, target observation, or dialogue boundary, write the state as `(X,Y,m,p)` with `X=(x,dx)`, `Y=(y,dy)`, previous input `m`, and persistent fields `p`. The source-derived one-tick operator has the form

`F_t(X,Y,m,p;a) = (f_t(X;a), g_t(Y;a), a, p_t)`.

The old mask does not enter either movement or red input assignment. Each actual source `dt_t` is consumed by the axis operator; no fixed clock substitution is needed for this equality. The joint safe successor relation is

`R_{t+h} = union_{(X,Y) in R_t, a in A} {(f_{t:t+h}(X;a),g_{t:t+h}(Y;a)) : all microticks pass C-space}`.

It is not the Cartesian product of reachable marginals. Axis IDs intern exact binary64 pairs. The bitset stores precisely the predecessor-generated joint pairs; unused axis IDs may then be compacted without changing that relation.

For the sixteen arrow masks, equal resulting control velocity gives nine equivalence classes. Cancel expands the velocity set and must not be silently removed in a context where it is legal. The first microtick moves using incoming velocity; subsequent microticks use the new control velocity. Therefore equal-velocity masks have identical geometry and safety throughout the held edge. The chosen parent remains a valid witness when its final action is replaced with any allowed alias. `terminal_states()` expands those masks before a caller enters a boundary where the old mask becomes observable.

Strict-interior and one-substep certification matter: border contact may couple horizontal and vertical motion. An unsupported axis is **unknown**, not an empty reachable set. The implementation currently declines the whole resident step in that case.

## Found and repaired contract gap

The resident entry point originally accepted windows across pending target, already bound `GetHeartPos`, and dialogue boundaries. A previously bound target is still an observation of this candidate's earlier position: merging histories across it against one fixed environment is not justified. The propagation script independently excluded targets, so its current target-free prefix was protected, but the reusable module was not.

Three new regressions demonstrated the gap: the old module returned `complete` in all three cases. The module owner added explicit `unsupported` reasons matching the full local relation's boundary contract, as well as tick-range validation. No native game source or physics was changed.

## Independent tests

`tests/unit/test_red_joint_frontier_audit.py` covers:

- Full terminal sets against the unfactored operator for one- and four-tick holds, sixteen/thirty-two controls, alias-only subsets, and correlated diagonal controls.
- Nonuniform source dt values `0.0031, 0.0042, 0.0067, 0.0048`, including one-ULP distinct input positions and nonzero incoming velocities.
- Every emitted terminal alias recovered through all parent layers, replayed with the full operator, checked for C-space safety at every microtick, and compared byte-for-byte at the endpoint.
- A correlated diagonal example with two reachable joint pairs despite two IDs on each axis; a Cartesian relaxation would incorrectly produce four.
- Explicit unknown at top/right contact and a multi-substep dt; input frontier remains intact.
- The three observation-boundary regressions.

Validation command:

```powershell
.\tools\uv_py.bat -m pytest tests/unit/test_red_joint_frontier_audit.py tests/unit/test_red_joint_frontier.py tests/unit/test_red_axis_expansion.py -q
```

Result after repair: **22 passed in 1.15 seconds**. Before repair the new audit had **12 passed, 3 failed**, with all failures being the boundary contract gap above.

## Limits

These tests compare the accelerated relation with the source-derived full operator, not with an independent full native Real HELL run. Previously established native/operator correspondence remains a separate obligation. They establish neither whole-source reachability nor exhaustive one-tick control search when a caller chooses four-tick holds.

One arbitrary witness per identical reachable state suffices for existence. It does not by itself minimize a path-dependent reward (for example switch count or timing robustness): that requires storing the relevant objective state and an appropriate DP value or Pareto set. This experiment must remain described as exact existential reachability within its certified domain.

## Follow-up: idempotent union and test isolation

The later optimization checks the destination bit before evaluating another incoming path. This is valid for Boolean reachability because a set bit is published **only after** a complete safe witness has been checked. Two direct kernel regressions use converging paths where exactly one collides: unsafe-first must retain the second parent, and safe-first must retain the first parent even though the later path is unsafe. Both pass. This shortcut still does not implement weighted path optimality.

An unrelated existing environment-state-quotient test was reproduced failing with dead-state counts `5/4` but expansions `3/3`, rather than its original `5/4` expansions. Default red-box pruning now proves those dead continuations earlier. The test now explicitly disables only that independent pruning mechanism, restoring its original `[(5,5),(4,4)]` assertion and preserving its intended isolation of the environment-state quotient. Production defaults and expected numbers are unchanged.

Follow-up combined validation of `test_environment_state_key.py`, `test_joint_transition.py`, `test_red_joint_frontier.py`, `test_red_joint_frontier_audit.py`, and `test_red_axis_expansion.py`: **41 passed in 1.32 seconds**. No additional failure was observed in the coupled transition tests; those finite cases do not prove whole-source native compatibility.
