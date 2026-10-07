# Owned environment continuation

The public `advance_one_tick(s)` remains a pure value operator: it deep-copies
the complete mutable state and advances that independent copy. `supply_target`
also deep-copies its parent, and observation preview uses the public operator.
Sibling branches therefore retain independent entities, variables, RNG and
partially executed timeline state.

`ParametricEnvironment._bind_resumable` now uses `_advance_owned_tick` internally.
The loop starts with a fresh `initialize` state or the independent result of
`supply_target`. It retains frames, not intermediate mutable states. It can
therefore consume this exclusively owned continuation without copying every
tick. Once it publishes a binding, it never mutates that continuation again.
All frame arrays are newly materialized. No entity evolution equation, command
order, floating-point arithmetic, callback or target sampling phase changed.

This is the same transition function with ownership made explicit; it does not
merge search states, coarsen collision geometry or remove active entities.

## Evidence

The original profile (`scratch/profile-realhell-environment.txt`) measured
541.144 of 565.830 profiled seconds in `EnvState.clone`, including approximately
14.7 million object reconstructions. Active entity lists were copied every tick.
The new profile (`scratch/profile-realhell-owned-environment.txt`) takes 24.244
profiled seconds; cloning disappears from the top 30. Remaining work is mostly
per-tick entity bounds and array materialization. Profiled timings include
instrumentation overhead and must not be compared with ordinary wall times.

Ordinary wall timings on this workspace, original source SHA256
`3b6252bc2d97a6ae5f82d63b8c8e82175cf1d819e85728e2f1fe9b1001106299`, seed 42,
native-recorded initial environment and clock, `max_ticks=18845`:

| Backend | Initial 18836-frame binding | Extend to 18845 frames |
| --- | ---: | ---: |
| Reference | 13.330 s | 13.592 s |
| Owned resumable | 12.145 s | 1.618 s |

The prior unprofiled resumable opening run used 122.845 seconds for the same
initial configuration. The new initial binding is approximately 10.1 times
faster; these are separate wall-time runs, not a controlled CPU-isolated trial.

`scratch/benchmark_owned_environment.py` compared every byte of environment,
platforms, platform counts, white/blue/polygon geometry, initial state and
schedule arrays, plus source events, target history and boundary metadata.
Both the 18836-frame unresolved-target binding and the 18845-frame resource
boundary matched the unchanged reference compiler. The diagnostic target at
tick 18835, source line 451, was `(323, 308)`; this is a differential input, not
a solved player trajectory. Report: `scratch/realhell-owned-environment-result.json`.

Validation: 36 tests passed across the resumable operator, environment bindings
and new owned-continuation tests. They verify public prior states remain
byte-identical, retained frames remain unchanged, active-entity siblings match
reference, and cloning occurs only at branch/preview boundaries.

This is environment compilation validation only. It does not establish a Real
HELL solution or native no-hit acceptance, and the 18845-tick boundary is a
resource limit rather than source termination.
