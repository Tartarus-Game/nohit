"""Create a pinned real-game fixture using the COMMON live SDK/runner."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("upstream", type=Path)
p.add_argument("destination", type=Path)
a = p.parse_args()
here = Path(__file__).resolve().parent
subprocess.run([sys.executable, str(here / "prepare.py"), str(a.upstream), str(a.destination)], check=True)
# Use original main scene. The previous test-specific driver is unused.
project = a.destination / "project.godot"
project.write_text(project.read_text().replace('run/main_scene="res://nohit_driver.tscn"',
                                             'run/main_scene="res://Scenes/gameview.tscn"'))
spec = importlib.util.spec_from_file_location("nohit_cli", here.parents[1] / "tools/nohit.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.install(a.destination.resolve(), "3")
(a.destination / "nohit_adapter.gd").write_bytes((here / "live_adapter.gd").read_bytes())
manifest = a.destination / "nohit-upstream.json"
identity = json.loads(manifest.read_text())
identity["live_sdk"] = "nohit.live.v1"
identity["changes"] = ["Observer soul subclass delegates original takeDamage", "Separate adapter binds original startup, damage and EOT", "Original main scene preserved"]
manifest.write_text(json.dumps(identity, indent=2))
print(a.destination.resolve())
