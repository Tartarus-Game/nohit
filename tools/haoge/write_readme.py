"""Write the route-package README from the emitted index and evidence files."""
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
data = json.loads((root / 'scratch/haoge-run/ROUTES.json').read_text(encoding='utf-8'))
real = {}
real_path = root / 'scratch/haoge-run/replay-verification.json'
if real_path.exists():
    for row in json.loads(real_path.read_text(encoding='utf-8')):
        real[row['round']] = row

lines = []
lines.append('# haoge-sans 无伤路线包\n')
lines.append(f'游戏：{data["game"]["repo"]}（`{data["game"]["branch"]}` 分支，commit '
             f'`{data["game"]["commit"][:12]}`）\n')
lines.append(f'已解出 **{data["solved"]}/{data["total"]}** 回合。\n')
lines.append('## 判定口径\n')
lines.append(f'{data["criterion"]}\n')
lines.append(f'{data["protocol"]}\n')
lines.append('## 怎么跑\n')
lines.append('启动 dashboard 指向 `haoge-runtime/`，然后打开 '
             '[routes.html](../haoge-runtime/routes.html)：每个回合一个按钮，'
             '点一下就把该回合的 CSV 注册进原版 Custom 入口，并用 `?route=<回合>` '
             '在真机里回放已求解并验证过的路线，不再重新求解。\n')
lines.append('回放走的是和求解同一条播放路径，因此仍然完整校验：CSV 哈希、时钟表哈希、'
             'dt 前缀、动作/Confirm/轨迹形状、初始 Confirm、场地续态、入口第一帧环境、'
             '原生 EndAttack。任何一处对不上都会直接报错停下。\n')
lines.append('\n```powershell\n'
             '$env:NOHIT_GAME_DIR = (Resolve-Path haoge-runtime).Path\n'
             '.venv\\Scripts\\python.exe start_dashboard.py 8160\n'
             '# 浏览器打开 http://127.0.0.1:8160/game/routes.html\n'
             '```\n')
lines.append('\n## 逐回合\n')
lines.append('| 回合 | 输入步数 | 游戏时长 | 求解耗时 | 真机回放 | 观察 tick | 最低 HP | 最高 KR |')
lines.append('|---|---:|---:|---:|---|---:|---:|---:|')
for row in data['rounds']:
    name = row['round']
    if not row['solved']:
        lines.append(f'| {name} | — | — | — | 未解出（{row["reason"]}） | — | — | — |')
        continue
    r = real.get(name, {})
    s = r.get('summary') or {}
    c = s.get('custom') or {}
    verdict = '通过' if r.get('passed') else ('—' if not r else '失败')
    lines.append(f'| {name} | {row["actions"]} | {row["game_seconds"]:.1f}s | '
                 f'{row.get("wall_seconds", 0):.0f}s | {verdict} | {c.get("ticks", "—")} | '
                 f'{c.get("minHP", "—")} | {c.get("maxKR", "—")} |')
lines.append('')
lines.append('## 未解出的回合\n')
blocked = [r for r in data['rounds'] if not r['solved']]
if not blocked:
    lines.append('无。\n')
for row in blocked:
    lines.append(f'### `{row["round"]}` — `{row["reason"]}`\n')
    if row['round'] == 'sans_final':
        lines.append('引擎在 width=1200/2000/3000、seconds=1200–1800 下均为 `wall_budget`。'
                     '这一关的对话/关系阶段占满了墙钟预算（搜索本身只占零点几秒）。\n')
        lines.append('\n**并且这一关无伤在数学上不可能**：CSV 第 1038–1056 行是 RNG 四选一分支表，'
                     '四条分支每条都先 `DamagePlayer,-142`（补满）再 `DamagePlayer,141`（HP→1）'
                     '或 `999`（必死）。原版 `Battle.xml` 的 `DamagePlayer` 是无条件 '
                     '`HP -= Function.Param(0)`，没有任何免疫判定。\n')
    if row['round'] == 'sans_bonestab2':
        lines.append('`frontier_empty`。宽 40000（不截断）时：tick 58 有 50928 个唯一状态、'
                     '零后继、`unsupported_states=0`、未撞 100000 的状态上限。'
                     '窄宽度反而能走更远（1200→201、20000→660），因为宽度截断改变了那条唯一 '
                     'target binding 提交的 GetHeartPos 采样历史。这说明问题在**目标历史绑定**，'
                     '不是预算、也不是宽度。\n')
lines.append('## 文件\n')
lines.append('| 路径 | 内容 |\n|---|---|')
lines.append('| `ROUTES.json` | 索引：每回合的步数、时长、状态与失败归类 |\n')
lines.append('| `replay/<回合>.json` | 单文件回放包：入口状态 + 时钟 + actions/confirm |\n')
lines.append('| `entries/<回合>.request.json` | 原版入口捕获的完整求解请求（初态/环境/时钟） |\n')
lines.append('| `routes/<回合>*.json` | 求解器完整响应（含 provenance 与轨迹） |\n')
lines.append('| `../../haoge-runtime/routes/<回合>.plan.json` | 浏览器回放用的精简 plan |\n')
lines.append('| `replay-verification.json` | 真机回放逐帧验收结果 |\n')
lines.append('| `real-evidence/<回合>.observer.json` | 真机观察器逐 tick 记录（HP/KR/按键） |\n')

out = root / 'scratch/haoge-run/README.md'
out.write_text('\n'.join(lines), encoding='utf-8')
print(f'wrote {out}')
print(f'solved {data["solved"]}/{data["total"]}, real-verified {sum(1 for r in real.values() if r.get("passed"))}')
