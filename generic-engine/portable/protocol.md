# Live protocol v1

Engine-specific bridges use the same input route and audit vocabulary. This
interface neither replaces soul physics nor assumes player-independent attacks.
Godot 3/4 execute fresh processes; the GameMaker bridge is an unvalidated source
template and requires a developer-provided native launch/export workflow.

Request:

```json
{"schema":"nohit.live.v1","seed":1,"route":[4,4,0,1],"max_ticks":600,
 "warmup_ticks":120,"settle_ticks":2,"repeat_last":false}
```

Bits 1/2/4/8 are left/right/up (or jump)/down. Godot adapters may extend
`action_names` with slow/jump/confirm bits 16/32/64/128, or override
`nohit_apply_input()` for the game's original input abstraction. An exhausted
route supplies zero input unless `repeat_last` is explicitly enabled. Seed
every game-owned RNG in `nohit_begin`; the global seed cannot reset custom RNGs,
wall clocks, network responses or autoloads that ran before the adapter.

The runner observes a completed native frame at the next input boundary. It
counts every original damage/KR contact and waits additional native frames
after the ORIGINAL completion signal. `max_ticks` is only a horizon; reaching
it produces `unknown`, never completion. The test scene must expose an attack
start hook so that audit installation precedes the attack's first frame.

`nohit_observe()` returns a nonempty dictionary of finite JSON values: coordinates,
velocity, HP/KR, mode, input/attack counters, etc. Convert Vector2 to x/y values.
Do not include process IDs, wall time or instance IDs in deterministic comparisons.
This is an observation projection, NOT a saved/restorable full world state.

Result statuses:

| Status | Meaning |
| --- | --- |
| `invalid_adapter` | Missing audit, inputs, readiness, or observations |
| `hit` | At least one original damage or KR event |
| `unknown` | Budget/horizon expired; no claim of impossibility |
| `native_route_candidate` | Completed native attack with zero audited damage |
| `replay_failed` | Fresh-process observations or integration files diverged |
| `control_failed` | Supplied damage control did not hit; certification withheld |
| `native_nohit_fresh_process_observed` | Candidate + exact fresh-process observed trace + native damage control passed |

The certificate applies only to its game scene, engine, seed, route and adapter's
audit coverage. A successful control demonstrates a functioning damage path;
it cannot prove all unobserved damage paths are hooked. Developers must connect
white/blue/orange/KR/environmental damage at their common original entry point(s).
For formal complete world equality, implement the existing snapshot bridge.

No collision baking is mandatory for live adoption: original physics remains
the verification authority. Godot 4 projects may optionally also copy
`godot/addons/nohit/native_baker.gd`; GameMaker may import
`gamemaker/nohit_bridge.gml`. Baking is a geometric observation, not a damage rule.
