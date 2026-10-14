"""Build the standalone integration SDK, without historical solver/assets."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
root = Path(__file__).resolve().parents[1]
files = {}
for source in (root / "portable").rglob("*"):
    if not source.is_file() or source.is_symlink(): continue
    rel = source.relative_to(root)
    if any(part in [".godot", ".import", "__pycache__", "addons"] for part in rel.parts): continue
    files[rel.as_posix()] = source.read_bytes()
for name in ["nohit.py", "test_portable.py", "package_portable.py"]:
    files["tools/" + name] = (root / "tools" / name).read_bytes()
files["README.zh-CN.md"] = '''# NoHit 通用接入 SDK

优先阅读 portable/QUICKSTART.zh-CN.md。
已有信号的 Godot 游戏只填配置；复杂游戏集中编辑一份适配器。
保留原心魂、弹幕、碰撞与伤害，不要求完整世界快照。

python tools/nohit.py install /path/to/game
python tools/nohit.py doctor /path/to/game
python tools/nohit.py solve /path/to/game --godot /path/to/godot --output results/first

要求 Python 3.10+，不依赖第三方 Python 包；使用与原游戏匹配的 Godot。
Godot 3.5.3 / 4.6.1 已执行验证。GameMaker 脚本模板尚未原生运行验收。
有限策略搜索可能返回 unknown，不保证解出任意弹幕。
本包不含历史 nohit 求解器、他人游戏素材或引擎二进制。
新 Live SDK、模板与工具采用 MIT，见 portable/LICENSE.txt。
'''.encode()
acceptance = root / "research/portable-v1/acceptance-v2/acceptance.json"
if acceptance.exists(): files["validation/acceptance.json"] = acceptance.read_bytes()
manifest = {"format": "nohit-integration-sdk-v1", "files": {
    name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in sorted(files.items())}}
files["MANIFEST.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
a.output.parent.mkdir(parents=True, exist_ok=True)
temporary = a.output.with_suffix(".building")
with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for name, data in sorted(files.items()):
        archive.writestr("nohit-integration-sdk/" + name, data)
with zipfile.ZipFile(temporary) as archive:
    assert archive.testzip() is None
    for name, data in files.items(): assert archive.read("nohit-integration-sdk/" + name) == data
temporary.replace(a.output)
print(json.dumps({"path": str(a.output.resolve()), "files": len(files), "bytes": a.output.stat().st_size,
                  "sha256": hashlib.sha256(a.output.read_bytes()).hexdigest(), "all_file_bytes_verified": True}))
