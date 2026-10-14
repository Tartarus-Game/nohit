# Generic engine source import — 2026-10-15

## Source and comparison

- Base: local `haoge`, commit `654ff77`.
- Branch: `codex/import-generic-engine-source`.
- Input: `nohit-generic-engine-source.zip`, SHA-256 `bf88c5eb006806d8aeddc66d565dd78b08a4771fef5b9e27cd6b14665507bbad`.
- Delivery format: `nohit-source-v11-portable-live-sdk`; delivery instructions dated 2026-10-09.
- All 4,307 files listed in the delivery manifest passed byte-size and SHA-256 checks. The archive also contains the manifest itself.
- Against the pre-import working directory: 2,354 new files, 7 byte-different files, 1,947 identical files. Some byte differences include line endings. The archive omits 97 tracked local files, mostly the Haoge runtime and tools; these are retained.

## Changes imported

The new `generic-engine/` tree contains the Godot snapshot search prototype, Godot 3/4 live SDK, declarative configuration and single-file adapters, a GameMaker source template, native integrations for meowjade/UNDOTALE/Megalo, installation and packaging tools, and sample research and acceptance records. GameMaker has no native runtime acceptance; the delivery does not claim every upstream level is solved.

The import also brings delivery instructions, historical integration patches, the original delivery manifest, the updated source packager, and the Round 8 reference implementation. Existing local Haoge files remain available.

The archive is extracted locally in full, except for the three intentionally preserved files below. New historical C2 optimization run evidence (approximately 1.6 GB for the complete optimization-results tree), upstream `haogesans-export/` assets, and a temporary coverage file are not added to Git. Already tracked evidence stays tracked. Generic-engine research and acceptance evidence is committed with the source.

## Algorithm review

The archive's `nohit/engine/` code matches the pre-import local engine. In particular, the three added reference files are byte-identical to the current implementation:

| Delivered reference | Current implementation |
| --- | --- |
| `tools/reference/round8_native_backend.py` | `nohit/engine/native_backend.py` |
| `tools/reference/round8_native_candidate.py` | `nohit/engine/native_candidate.py` |
| `tools/reference/round8_native_frontier.cpp` | `nohit/engine/native_frontier.cpp` |

Thus the existing Round 8 C++ algorithm tuning is already present locally and is not overwritten with a different search implementation.

New algorithm paths imported intact:

- `generic-engine/godot/addons/nohit/solver.gd`: bounded frontier search, exact serialized full-state deduplication (including hidden state/RNG supplied by the host), host-provided ranking, width truncation, and parent-linked route reconstruction. Each returned route is replayed with per-tick state digests and damage checks. Budget, horizon, or frontier exhaustion returns `unknown`.
- `generic-engine/tools/nohit.py`: 12 finite input strategies (9 constant masks and 3 alternating held/released strategies), tested in separate native Godot processes through a Python thread pool. It waits for the submitted attempts and verifies the first successful candidate in submission order. This is a finite strategy portfolio, not exhaustive state search or a guarantee of an optimal route.
- `generic-engine/integrations/meowjade/run_suite.py` and `generic-engine/tools/run_upstream_native.py`: native parallel strategy/seed trials with fresh-process replay. The meowjade runner tries batches and stops searching after a successful batch.
- Live certification requires exact exposed-observation replay, an actually damaging control run, and unchanged integration fingerprints. Observations are not full world snapshots; this evidence has a narrower scope than the snapshot prototype's state digest.

## Local fixes preserved

- `.gitignore`: retain local Haoge runtime/reference exclusions and credential-material exclusions. The delivery copy predates these additions.
- `nohit/dashboard/server.py`: retain `NOHIT_GAME_DIR` and the served build's declared HP/KR acceptance policy from `fe73646`.
- `tools/benchmark_round8_request.py`: retain the Windows-compatible RSS implementation from `654ff77`; the delivered copy unconditionally imports Unix-only `resource`.

`DELIVERY_MANIFEST.json` remains an unchanged description of the original archive. Its hashes are not a manifest of this integrated branch; the preserved files above intentionally differ.

## Validation

- Archive integrity: all 4,307 manifest entries passed.
- PCK/ZIP extraction suite: 7 tests passed.
- Full-game acceptance, acceptance evidence and transport: 70 tests passed.
- Godot 3 and 4 fixture installation, repeated installation, project/adapter preservation, declarative installation, and static doctor checks passed using disposable local copies.
- CLI help worked for both the new SDK and the preserved Windows benchmark entry point.
- Dashboard suite: 21 passed, 1 failed. The failure expects the obsolete `SANS TAS ROUTE SYSTEM` heading on `/`; neither the test nor the current homepage changed in this import. Execution used the installed UCRT compiler, a writable local native cache/temp directory, and `os.add_dll_directory` for compiler runtime DLLs.
- No Godot binary was found on PATH or in the checked Downloads entries. Native Godot acceptance was not rerun; the delivered acceptance records are historical evidence, not results generated on this machine.
