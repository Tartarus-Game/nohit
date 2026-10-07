# nohit

Compute a verified **no-hit route** for an Undertale Sans fight from a CSV attack
description, then execute it in the original game and check it independently.

The solver is a bounded, width-limited frontier search over the game's own
discrete operator. It never claims global optimality: a route that comes back is
a route that was *verified frame by frame*; a route that does not come back is
reported as `unknown`, which is not the same as "impossible".

## Quick start

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-native.txt   # Windows; see tools/uv_py.bat
.venv/Scripts/python start_dashboard.py 8080
```

Then open <http://127.0.0.1:8080/>.

| Page | What it is |
| --- | --- |
| `/` | The single entry point: pick one of the bundled attacks or your own CSV, choose the engine, watch live solve telemetry, then run it in the original game |
| `/old.html` | The retired first-generation engine (raster `bake_cspace` + 5-D lattice DP). Kept for comparison only |

## Layout

| Path | Contents |
| --- | --- |
| `nohit/engine/` | The current solver: exact C-space, bounded frontier, dialogue and target frontiers, completion certificates |
| `nohit/dashboard/` | HTTP API and the static pages (single entry + retired engine page) |
| `nohit/baker/` | The first-generation hazard rasteriser, used by the retired engine |
| `hrzq/` | The self-made attack pack (17 CSVs), ASCII-named; original paths and sha256 are recorded in `data/samples.json` |
| `data/samples.json` | The sample list. Ids only, no display names: `can/<wave>` for the campaign waves, `hrzq/<slug>` for the pack, `user/<slug>` for imported files. An id gets a `-nohit` suffix once a native no-hit run is confirmed |
| `c2-sans-fight/` | The game runtime this project drives (vendored from the original Bad Time Simulator project) |
| `tools/` | Every research, benchmark, verification and migration script used to build the claims above |
| `docs/` | Design notes, source audits, validation reports. `docs/archive/` holds process records that are historical, not current state |
| `tests/` | Unit, contract and acceptance tests |

## What the numbers mean

Progress telemetry (`GET /api/progress/<id>`) reports the live frontier: tick
reached, retained and expanded state counts, states per second, and a fraction
that is only honest against the horizon the search will actually end on. A
`fraction` of `unknown` means there is no defensible denominator, and the reader
should show elapsed time instead of a percentage.

Solve quality is ranked by an explicit input cost: every tick that presses
anything costs 1, every change of the pressed set costs 12. That ranking only
decides which equally-safe candidates survive the width cut, so routes come out
calm rather than twitchy, and reported `input_cost` uses the same weights.

## Verification discipline

A route is accepted only when it survives, in order:

1. the model's own per-tick replay of the retained witness;
2. an independent scalar replay at the same clock;
3. the original game, which hooks `DamagePlayer` and compares `HP`/`KR` every
   single tick and refuses to continue on any mismatch.

Evidence bound to an implementation hash does **not** carry over to later
source changes: the dashboard refuses to solve when `nohit/engine/*.py` changed
since import, and tells you which file changed. Restart it after editing.

## Not published

Working evidence, browser profiles, upstream reference copies, the agent
dispatch archive and heavyweight recordings stay local. Some research scripts
contain a `<repo>` placeholder where an absolute checkout path used to be; the
packaged entry points (`start_dashboard.py`, `nohit/`, `tests/`, `tools/solve_csv.py`)
do not depend on it.

## Third-party content

`c2-sans-fight/` is vendored from the original Bad Time Simulator project and
keeps its own authorship. The solver code in `nohit/`, the tooling in `tools/`
and the attack pack in `hrzq/` are this project's own work.
