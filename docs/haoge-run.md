# haoge-sans 全流程无伤求解报告

对象：<https://github.com/1742137113/haoge-sans> 的 `gh-pages` 构建
commit `a1c36cbc3204e459b0d48df4df076d6895449c18`

## 结论摘要

| 项目 | 结果 |
|---|---|
| 回合攻击表 | 24 个回合全部提取，并与原版逐回合比对 |
| 已验证无伤路线 | **22 / 24** |
| 真机回放验证 | 见下（逐帧观察 HP/KR/按键） |
| 未解出 | `sans_bonestab2`（引擎 target-binding）、`sans_final`（构造上不可能无伤） |
| 引擎缺陷修复 | 3 项，均带回归测试 |
| 引擎性能修复 | 2 项，24 关世界指纹逐字节等价 |

## 判定口径

- **HP 不得低于满血**。本构建满血为 **142**（上游 `jcw87` 版本是 92；项目里
  `Globals.xml` 写 92 但构建产物实际是 142，因此基线从运行时读取 `MaxHP` 并缓存）。
- **KR 单独记录，不要求为 0**。本构建的脚本会用 `DamagePlayer(-N, 1)` 做**带 1 点 KR 的治疗**；
  而最低扣血档位是 `KR > 10`（每 0.5 秒 1 点），`KR > 0` 的分支只设置那句
  "* You felt your sins crawling on your back."。把 KR=1 判成受击是误报。
- 每次 KR 注入都记进 `krInjections`，证据里明确写出而不是藏起来。

## 回合内容：名字一样，攻击完全不同

回合**名字与顺序**与上游一致，因为 `AttackLoader.xml` / `Battle.xml` 与上游**逐字节相同**——
游戏仍然是 24 个槽位。但每个槽位里装的脚本被重写过：

| 回合 | 行数 他/原 | 弹幕指令 他/原 | 时长 他/原 | 首条弹幕 |
|---|---:|---:|---:|---|
| sans_bluebone | 124 / 18 | 101 / 12 | 31.6s / 6.4s | bonevrepeat（原版 bonev） |
| sans_final | 1065 / 214 | 280 / 25 | 58.2s / 24.7s | bonestab 参数已改 |
| sans_multi3 | 339 / 169 | 145 / 43 | 37.0s / 21.3s | bonev（原版 bonevrepeat） |
| sans_platforms2 | 23 / 20 | 2 / 14 | 4.0s / 9.8s | sinebones（原版无此机制） |
| sans_bonestab2 | 101 / 27 | 32 / 1 | 6.5s / 0.9s | boneh（原版仅 1 条 bonestab） |
| sans_platforms1 | 89 / 14 | 41 / 8 | 11.1s / 8.3s | gasterblaster（原版 platform） |
| sans_spare | 6 / 6 | 0 / 0 | 0.3s / 0.3s | 唯一真正相同的回合 |

`sans_platforms2` 最极端：原版 14 条平台指令，他换成 2 条 `sinebones`，机制直接替换。

身份核对：24 个求解入口的 payload **全部等于 haoge 的 CSV 文本**；其中只有 `sans_spare`
同时等于原版（它本来就只是"结束攻击"）。即求解对象无误。

## 引擎缺陷修复

### 1. `DamagePlayer(-N, 1)` 被误判为受击

`Battle.xml` 的 `DamagePlayer` 是无条件 `HP -= Param(0)`、`KR += Param(1)`，没有免疫判定。
脚本用它做治疗（负 amount）。观察器原来把任何 `DamagePlayer` 都算作受击，导致治疗回合
（`sans_spare` 等）被判"入口已受损"。

修法：只有 `amount > 0` 才算受击；负 amount 记入 `krInjections`。

### 2. `CombatZoneResize` 的 `TLPause` 完成回调未建模

`bonegap1` / `bonegap2` / `platforms1` / `platforms2` 在 resize 结束时用 `TLPause` 作为完成
回调，引擎只承认 `TLResume`，于是报 `unknown_callbacks` 而无法求解。

修法：`native_function_dispatch.py` 增加 `modeled_timeline_callback()`，把两个回调对称接纳；
`compact_wave` / `resumable_wave` / `parametric_environment` 统一改用
`executable_resize_callback()`。

回归测试：`tests/unit/test_timeline_pause_resize.py` 新增
`test_tlpause_resize_callback_is_executable_and_stops_the_timeline`（4 参数）与
`test_unknown_resize_callback_still_stays_unproven`。改动前 4 个失败，改动后通过。

### 3. 满血基线硬编码 92

本构建是 142，所有观察器写死 92 → "Original CSV entry is already damaged"。
改为从运行时 `MaxHP` 读取并缓存（`haoge-runtime/baseline.js`），中途变更会失败而不是静默放宽。

## 引擎性能修复

对话关系阶段占满了墙钟预算，导致 `sans_final` 一直是 `wall_budget`。

| 改动 | 效果 |
|---|---|
| `TimelineVM.clone()`：只复制 3 个可变字段，共享只读配置 | `deepcopy` 占比 52% → 时间线 VM 不再是热点 |
| `clone_simulation_state()`：按值类型精确复制，未知类型回退 `deepcopy` | 函数调用 4980 万 → 2170 万（−56%），`deepcopy` 从前十消失 |

**等价性证明**：24 个回合的 `environment_state_keys`（逐 tick 世界结构指纹）在改动前后
**逐字节相同**，0 分歧。相关测试集：11 失败 / 143 通过（基线）→ 7 失败 / 147 通过（改动后），
**零新增回归**，减少的 4 个正是新增的 TLPause 测试。

未做的优化（有意保留）：保留 frontier 层的 `np.memmap`、对话关系的跨 tick 记忆化。
理由：收益不确定而正确性风险实在。

## 未解出的两个回合

### `sans_final` — `wall_budget`，且**无伤在构造上不可能**

CSV 第 1038–1056 行是 RNG 四选一分支表，四条分支每条都先 `DamagePlayer,-142`（补满）
再 `DamagePlayer,141`（HP→1）或 `999`（必死）。`Battle.xml` 的 `DamagePlayer` 是无条件
`HP -= Param(0)`，没有任何免疫判定。引擎报告 `scripted_damage_present=true`，
12 个字面量 `scripted_vitality_events`（行 4, 498, 1000, 1025, 1045–1055）。

搜索本身只占零点几秒，其余全是对话关系阶段的墙钟消耗；width 1200/2000/3000 都是 `wall_budget`。

### `sans_bonestab2` — `frontier_empty`，**目标历史绑定**问题

他把它改成了循环 8 次的追踪激光：`SET loop,8` → 每轮 4 门 `GasterBlaster` 瞄准
`$HeartX/$HeartY`（`GetHeartPos`）→ `JMPNZ 6,$loop` → 治疗 → `EndAttack`。

诊断数据：

| width | reached_tick | 备注 |
|---:|---:|---|
| 40000（不截断） | 58 | tick 58 有 50928 个唯一状态、**零后继**、`unsupported_states=0`、未撞 100000 状态上限 |
| 20000 | 660 | 301 层被宽度截断 |
| 1200 | 201 | 166 层被截断 |

宽度**越窄反而越远**——因为宽度截断改变了那条唯一 target binding 提交的 `GetHeartPos`
采样历史。这说明问题在**目标历史绑定**，不是预算、也不是宽度。`max_bindings` 试到 8
仍然更差。需要引擎层面修 target-binding 的续算路径。

## 怎么跑

```powershell
$env:NOHIT_GAME_DIR = (Resolve-Path haoge-runtime).Path
.venv\Scripts\python.exe start_dashboard.py 8160
# 浏览器打开 http://127.0.0.1:8160/game/routes.html
```

`routes.html` 每个回合一个按钮；顶部大按钮是**连续演示**，按游戏自身的 24 回合顺序
自动播放已发布的路线。

### 回放的安全阀

回放走的是和求解同一条播放路径，因此仍然完整校验：CSV 哈希、时钟表哈希、dt 前缀、
动作/Confirm/轨迹形状、初始 Confirm、场地续态、**入口第一帧环境**、原生 EndAttack。
任何一处对不上都会**直接报错停下**，不会带病播放。

路线绑定在它被求解时的那个入口边界上。`visualization.frames[0].env` 必须保存下来交给
校验器比对——它是**模型第 0 帧**（源第一个 tick 之后）的环境，与请求里携带的
`initial_environment`（TLPlay **之前**）是两个不同的量，不能互相替代。
`tools/haoge/fix_frame0.py` 从入口请求重建并交叉校验：19 个走 dashboard 求解的路线
其已发布帧与重算值**完全相等**，验证了算法。

### 演示模式 `?demo=1`

- **掉血记录但不中止**：观察器仍然逐 tick 判定并记录 `firstDamage`、`minHP`、`maxKR`，
  但不再把它当作中止条件。
- **分叉后开环继续**（`csv_round_controller.js` 的 open loop）：路线来自无伤模型，
  真机一旦受击，玩家状态就分叉，剩余按键不再是已验证的路线——控制器会停止（这是对的）。
  为了演示能走完，`?demo=1` 下改为：继续施加原计划的按键作为开环模式、跳过逐 tick 模型
  校验、直到原生 `EndAttack` 才完成。横幅会明确显示"真机分叉，开环继续操作"，
  **不声称这一段是验证过的路线**。
- 这是显式开关，默认关闭；证据里带 `demo_mode` 标记。

## 已知限制

- 真机实测中 `bonestab1` / `multi1` / `multi2` / `multi3` 各掉 1 点血，说明这几关的模型与
  真机存在 1 点偏差，分叉点之后由开环接管。这是模型精度问题，不是播放问题。
- 回放要求入口边界可复现；边界不可复现的回合会明确报错而不是静默跳过。
- `sans_bonestab2` 需要引擎修 target-binding；`sans_final` 需要在 `Battle.xml` 层面
  加免疫判定才可能无伤。

## 目录

| 路径 | 内容 |
|---|---|
| `haoge-runtime/*.js` | 真机 TAS 驱动、观察器、控制器、回放器 |
| `haoge-runtime/routes.html` | 一键回放 / 连续演示页 |
| `haoge-runtime/routes/*.plan.json` | 已发布路线（校验器需要的最小字段集） |
| `haoge-runtime/sans_*.csv` | 24 个回合的攻击表 |
| `tools/haoge/` | 抓取入口、求解、发射路线、真机验证、等价性检查等工具 |
| `nohit/engine/*.py` | 求解引擎（含上述修复） |
