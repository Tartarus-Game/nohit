# Optimized nohit source delivery

Full source and original assets, with per-file hashes in DELIVERY_MANIFEST.json.
New generic-engine/ contains the Godot native collision prototype, GameMaker
bridge draft, pinned GitHub sample audit and two real PCK extraction manifests.
It also includes the meowjade native integration, pinned installer, black-box
parallel search, fresh-process replay and four verified circular-wave tests.
Start that work with generic-engine/README.zh-CN.md. Four isolated wave tests passed; the complete upstream default_attack remains
unsolved. See generic-engine/integrations/meowjade/README.zh-CN.md. The C2
engine below is unchanged.
Start with docs/optimization-round8-20261008.md for measured results and limits.
OPTIMIZATION.patch contains all source changes relative to the manifest base commit.

## Run

Install Python dependencies from requirements-native.txt, plus a C++17 compiler
(g++ or clang++). Node is required for original-game acceptance replay.
The normal native CSV path does not load Numba/LLVM.

```bash
python start_dashboard.py 8080
python -m tools.solve_csv c2-sans-fight/sans_final.csv \
  --entry tools/optimization-results/round8/normal-delivery/23-sans_final-entry.json \
  --search-strategy native --seconds 45 --width 8192 --workers 8 --memory-mb 256 --out result.json
```

The entry supplies the captured original clock and initial state; omitting it
can select a different clock. In particular 240 Hz Final remains unknown.
Bundled proof routes are audit records, not a solver route cache.

Haoge export reproduction (literal script healing allowed; positive scripted
damage is rejected, and the result requires native replay):

```bash
NOHIT_GAME_DIR=haogesans-export NOHIT_SCRIPTED_HEALING=1 \
NOHIT_SEARCH_STRATEGY=native NOHIT_FPS=60 \
node tools/native_optimized_replay.mjs sans_intro
```

The Haoge health contract is alive with no nonnegative DamagePlayer call;
literal negative scripted healing may run, so HP need not stay constant.
Current campaign and 23 Haoge proofs are under round8/normal-delivery and
round8/haoge-delivery. Haoge Final remains unknown; all ending branches contain
positive scripted damage. A physical projection is only a diagnostic opt-in. Other folders contain historical or diagnostic records
with their own source hashes. See the round8 report for current cold compilation costs.

Rebuild this archive from the git checkout after adding new source files with
git add -N, using python -m tools.package_optimized_source --output /path/source.zip.
