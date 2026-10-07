# Automatic CSV native acceptance

Save this JSON after the controller has stopped and the observer's source hash has resolved:

```javascript
JSON.stringify({
  controller: window.__CSV_TAS,
  observer: window.__CUSTOM_WAVE,
  finalSnapshot: window.__CUSTOM_WAVE.capture(),
  source: window.__CSV_SOURCE,
  clock: window.__TAS_CLOCK
})
```

The first three fields are required. `source` and `clock` provide additional cross-checks when present. Function properties disappear during JSON serialization. This format expects the complete `__CUSTOM_WAVE` object, including `started`, rather than only its HTTP save response.

Run from the repository root:

```powershell
.\tools\uv_py.bat tools/verify_csv_native_acceptance.py evidence.json --output verdict.json
.\tools\uv_py.bat -m pytest tests/unit/test_csv_native_acceptance_verifier.py -q
```

Exit code 0 means the saved evidence passes; 1 means it is rejected. Neither the controller's `completed` status nor a caller-supplied success flag can replace the independent checks.

The verifier checks the exact UTF-8 source hash across source/observer/controller/plan; captured boundary and initial Confirm history; frame-by-frame arrows and Confirm; all independent native HP=92/KR=0 ticks without gaps; DamagePlayer arguments and event-chain agreement; and every recorded nonterminal state component against the model trajectory. Physical floating state components use absolute tolerance `1e-7`; discrete components require exact equality. Every nonzero difference includes its frame, native tick, component, actual value, expected value, and absolute error.

With the new driver, `controller.source_environment` is the environment observed immediately before the source TLPlay. It must match `plan.initial_environment`. The rebuilt `plan.visualization.frames[0].env` must separately match the committed post-source boundary's arena, mode, direction, dt, and max-fall speed. Older records without `source_environment` compare their plan environment against the recorded boundary.

When present, `controller.source_arena` must exactly match `plan.initial_arena`, retaining the pre-source arena target, size, speed and callback. Every independent GetHeartPos event needs `source_line` and `sampled_position`; its relative source tick is `event.tick - (boundary.tick - 1)`. The complete ordered `plan.target_history` must exactly match these trigger-phase observations. The tick-zero subset must additionally agree with both controller and plan `initial_target_history`. A posttick player position is not a substitute for an earlier GetHeartPos sample.

The original EndAttack runs inside native tick `t`, while its posttick capture is `t+1`. Both controller and observer must record exactly one EndAttack at `boundary.tick + actions.length - 1`, and the independent final snapshot must be exactly the final input's posttick. No extra neutral tick is accepted. A plan endpoint is a source-model state; EndAttack then moves the native heart to the original custom-mode menu. The verifier reports that final difference separately and checks the original menu resize event/target, callback, object cleanup, reset variables and menu position. Only the supported menu changes to position, gravity direction, max-fall and slam-damage settings are exempted from direct terminal model comparison; unexplained terminal changes fail closed.

This is a verifier for one saved native custom-mode trace. It does not authenticate the capturing process, certify all future callbacks, or prove solvability/unsolvability for other entries, clocks or seeds. A valid run may be rejected if it uses an original terminal-menu variant outside the explicitly supported policy; such a case needs source-based review rather than relaxing a check merely to obtain a green result.

The regression fixture is a real five-action native run captured on 2026-10-07. It includes a Confirm press, six continuous observer ticks, and a menu-reset endpoint. Tests corrupt actual evidence to ensure completion flags cannot conceal gaps, transient damage, missing/early EndAttack, wrong input edges, source mismatches, environment phase mismatches, trajectory errors or incomplete cleanup.
