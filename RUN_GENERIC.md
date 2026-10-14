# Generic engine source delivery, 2026-10-09

Start with generic-engine/portable/QUICKSTART.zh-CN.md.
The live SDK supports Godot 3/4 config-only or single-file adapters, without
world snapshots or replacement soul physics. Native fixtures and faults passed
24 acceptance checks, plus the original Megalo bonegap through the same SDK.
GameMaker remains a source template without native runtime acceptance.

This archive preserves all previous nohit source and all-sample evidence.
Three upstream projects / six native tests were verified; not all levels solved.
OPTIMIZATION.patch and NATIVE_INTEGRATION.patch are historical patches.
PORTABLE_INTEGRATION.patch describes live SDK changes since the previous v10
archive. Evidence is included directly. Upstream assets use pinned fetches.

Repackage without requiring a .git directory:
python generic-engine/tools/package_generic_snapshot.py --root . --output /path/source.zip
