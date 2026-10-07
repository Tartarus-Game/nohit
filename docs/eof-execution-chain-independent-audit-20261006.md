# EOF execution chain audit

The source-derived EOF witness now passes through a physical-tick schedule before execution. For a solver hold `h`, an environment ending at tick `b`, and carry `c=(-b) mod h`, the schedule is exactly:

`repeat_each(solver_actions,h)[:b] + certified_tail_actions`.

The tail's first `c` actions must equal the unfinished final solver action. Thus the last block completes once; it is neither truncated early nor repeated. All later release/settling actions are already certified by the EOF tail operator.

## Reproduced API inconsistency and fix

The server initially retained `result.actions` while overwriting `control_ticks` to one and publishing the expanded `action_sequence`. A real public EOF solve showed:

- One-tick solver: 5 finite solver actions, 163 executable physical inputs.
- Four-tick solver: 2 finite solver actions, the same 163 executable physical inputs.

The mismatch was reproduced by calling the real handler and real solver. The response now preserves the finite proof inputs as `solver_actions` alongside `solver_control_ticks`; both `actions` and `action_sequence` contain the execution schedule described by the public `control_ticks` and `control_hz`. Campaign playback already consumed `action_sequence`, but the response is now unambiguous for other consumers.

## Execution verification

`tests/unit/test_execution_chain_audit.py` exercises the real public solver and handler, then sends their response to `tools/tas_execution_probe.mjs`. The probe loads the production `tas_runner.js` in a stub runtime. The original tick body reads actual keyboard state, thereby checking that the hook injects before the engine tick consumes it. Installing a plan consumes no tick; the next tick consumes action zero. Every physical input is consumed once, even under artificial game-time jumps, and the following tick releases all keys.

Additional differing-direction sequences cover EOF boundaries 4, 5, 6, 7, and 8. These distinguish duplicated final holds, missing first inputs, reordered blocks, and incorrect carry release. The existing acceptance-verifier regression checks one-tick masks against each corresponding native raw-evidence row and rejects an altered input.

Validation: execution-chain, schedule, terminal-completion and full-game-verifier tests **39 passed in 87.33 seconds**. Production `tools/tas_clock_test.mjs`: **5 passed**.

This is integration evidence for schedule construction and input delivery. The runtime stub does not establish native collision safety or native dt equivalence. The full Real HELL witness and uninterrupted original-game acceptance remain separate required work. No original runtime, source CSV, HP, damage, or physics was modified by this audit.
