# Normal 使用 CSV 求解链路的原版验证

## 最新状态：24 轮连续无伤到 Win2，独立验收通过

以下历史分节记录各自版本。服务器 **8144** 的全新 Normal 游戏已经完成，未继续
或恢复此前受伤的 8143 runtime。完整记录为
`tools/real-game/bonesgap1-20261007-091242-917789.json`；独立验收
`scratch/campaign-csv-native-20261007/typed-fixed-whole-game-verdict.json` 返回
`passed=true, errors=[]`。

- 原版 24 次 EndAttack 后依次触发 Win1、Win2，完成 23 次 FIGHT。
- tick 29..68271，共 68,243 个连续原生 tick，全部 HP92/KR0；时钟逐 tick 检验通过。
- 55,957 个计划输入与原版一致，615,527 个非终态玩家分量零差。
- 28 次目标读取、27 份完整请求时钟和全部源/实现哈希通过。
- 包括三个失败搜索尝试的总 API 时间 116.9267 s。Final 两次尝试合计
  46.4926 s < 52.5708 s；Platforms2 为 8.5106 s < 10.0167 s。
- 22/24 轮累计 API 时间低于攻击时长。Intro 为 11.2080 s > 9.5125 s，
  其中首次 kernel materialization 7.3277 s；RandomBlaster2 包括失败重试为
  9.4495 s > 8.5875 s。每轮 1× 目标尚未全部达到。

![24轮原版无伤结果](../scratch/campaign-csv-native-20261007/typed-fixed-normal-win2.png)

首轮离线验收暴露了 verifier 的事件归属错误：Final EndAttack 同 tick 内同步
调用 SansText → TLPause。控制器仍拥有本物理 tick；独立观察器已在 EndAttack
清除 active，因此把嵌套 TLPause 标为下一轮。验收现按匹配的 TLPlay 事件序号
至 EndAttack 物理 tick（包含尾部嵌套事件）逐项比较，稍后 Win1 的 TLPause
仍排除在该控制器区间之外。原始记录没有修改。新增测试先红后绿，并证明旧版
会错误地接受“删掉该末尾 TLPause”；完整验收器测试 56 passed。全局伤害扫描、
逐 tick HP/KR、完整输入/时钟/状态约束保持不变。

125 份已验收源码已按 manifest 哈希核对后保存于
`scratch/campaign-csv-native-20261007/accepted-8144-source/`，含引擎、Dashboard、
游戏脚本、原版副本及本次 verifier。后续优化不能把该记录冒充另一个实现的
全新原版执行；可向 `verify_record` 显式传该快照的 `implementation_dir`、
`game_dir` 和 `original_dir` 重查历史证据。

8143 连续完成 23 轮后，在 Final 模型帧 5950 受伤。玩家的 65,461 个状态分量
仍逐位匹配；实际差异来自弹幕几何：CSV 算术生成的负小数角度，原版按 floor
取整，旧模型按向零截断。类型敏感修复同时区分 literal/SET 字符串与算术数字，
保留原版 parseInt 和坐标 SetX/SetY 的正负零语义。原始失败输入现在在两个后端
都首次碰撞于 5950；相关近邻测试 198 passed。独立审查见
[typed-integer-independent-audit-20261007.md](typed-integer-independent-audit-20261007.md)。

对该次真实 Final 入场请求重算，得到 12617 步完整模型候选，并经 reference
标量重放通过。严格等价的 selection bucket 优化已经接入；43 个真实选择批次
的下标和完整 RNG 状态相同，正式及近邻门禁 114 passed。完整 API 单变量对照
保持其他代码、请求和 OMP_WAIT_POLICY=PASSIVE 一致：

| 本次真实 Final 请求 | 原 NumPy 选择 | 新选择 |
| --- | ---: | ---: |
| width 300，unknown | 8.8595 s | 7.6614 s |
| width 1000，完整模型候选 | 45.1933 s | 36.6686 s |
| 包括失败重试的总耗时 | 54.0528 s | 44.3299 s |

攻击时长为 52.5708 s。两组完整语义、二进制 float64 轨迹和磁盘实现哈希全部
一致；原选择通过诊断脚本的显式 monkeypatch 提供，不伪称该对照为原版验收。
首次新选择测量 44.5556 s 另存，含 `_held_trace` 首次物化约 7.61 s，不用于
热性能结论。证据在 `scratch/campaign-csv-native-20261007/final-frontier-audit/`
的 `typed-int-selection-api-comparison.json`、`typed-int-width300-selection-comparison.json`
及其引用的完整请求/结果。当前结论仅针对这些真实请求，不代表每轮已满足 1×。

下文的“尚未接入并行”和“Final 未找到候选”等描述属于早期阶段，已被本节及
`scratch/campaign-csv-native-20261007/NEXT.md` 的最新记录更新。

本次将 Normal 驱动从旧 `/api/tas` 接到 `/api/solve-csv`，与 Custom 共用 `csv_round_controller.js`。每回合保存原版 TLPlay 前环境、首个源 tick 后的玩家、场地续态、Confirm 前态和实际目标采样，按同一原生时间戳序列求解与执行。每个动作都包含方向与 Confirm；只有最后一个输入实际触发 EndAttack 后，下一 tick 才交还菜单控制。

原版 `c2runtime.js`、`data.js` 与原始 jcw 副本保持相同。没有恢复游戏存档、修改伤害或纠正玩家状态。失败时的只读原生快照仅用于诊断。

## 修复后的新运行：23 轮连续无伤，Final 未决

在全新原版 Normal runtime 中重跑，已连续完成前 23 轮（至 BoneStab3），包括此前发生伤害的 RandomBlaster2。独立诊断 [fixed-23-round-prefix-verdict.json](../scratch/campaign-csv-native-20261007/fixed-23-round-prefix-verdict.json) 返回 `completed_rounds_valid=true`、`errors=[]`，顶层 `passed=false` 保留整局尚未完成的事实。

- 原生 tick 22..55327 共 55,306 步连续 HP92/KR0。
- 43,339 个执行输入匹配，476,729 个非终态状态分量零差。
- 27 次 GetHeartPos 与 24 份完整请求时钟序列精确匹配。
- 证据为 `tools/real-game/bonesgap1-20261007-064255-876353.json`：56 个无损分块、110,657,513 字节，全部哈希通过。后续仍处于同一无伤暂停边界的尝试另存于 `bonesgap1-20261007-064902-685578.json`。

Final 没有被判为无解。真实边界下，宽度 300、500、750、1000 分别在 1159、4896、7642、7642 帧耗尽保留前沿；其中 1000 的 50 秒预算尝试实际耗时 36.980 秒，失败原因为 `frontier_empty`，不是预算耗尽。较早的宽度 1000/3000、30 秒预算尝试则确实超时。Final 尚未执行任何候选，原版保持暂停。全部失败尝试均有独立 request UUID、完整时钟与明确 unknown。

已定位具体剪枝反例：真实第 7600 层的第 103 个状态，按右＋下产生的转移通过碰撞检查和精确去重，却在第 7601 层限宽筛选中被丢弃，且没有留下同余代表。沿该分支持续按右＋下，可在第 7634 帧通过低速触底解除 Slammed，安全越过失败点直到第 7680 帧。复现脚本和真实层数据见 `scratch/campaign-csv-native-20261007/final-frontier-audit/reproduce_pruning_counterexample.py` 及 `minimal-pruning-counterexample.json/.npz`。这证明当前保留策略会丢掉已有可行延续；该局部前缀还不是 Final 完整解。

已进一步恢复该分支的全部真实祖先：同目录 `recovered-safe-prefix-7680.json` 包含 7680 动作、7681 个状态，并由 reference backend 从原始帧 0 逐帧复核通过。它没有在原版运行时执行，也没有到达 Final EndAttack，不能冒充完整原版解。

回合核心支持在不变边界重试搜索参数。Normal 可配置 `width=300&retry_widths=1000,3000`，只对 `unknown + verified=false` 自动重试；下一轮恢复初始宽度，失败/伤害/取消不会触发重试。这是有限候选搜索调度，不改变动作和碰撞语义。

当前可用服务器为 8142，验证入口：`/game/index.html?campaign=1&mode=normal&compensate=1&seed=42&seconds=30&width=300&retry_widths=1000,3000&max_ticks=40000`。本次已运行的页面保留在 Final 的原始暂停边界。

## 首次连续运行：19 轮通过，第 20 轮发现真实反例

完整记录为 `tools/real-game/bonesgap1-20261007-060615-744782.json`，格式为带 SHA256 的无损分块 manifest；用 `tools.verify_full_game_acceptance.load_record` 读取。记录包含全部菜单、对话和战斗 tick，没有为了 8 MB 上传限制删除观测。

- seed 42，Normal 原生 240 Hz 时间戳协议；所有实际 dt 均保存。
- 46,615 个连续原生 tick；前 19 轮实际 EndAttack 且无伤。
- 第 20 轮 `sans_randomblaster2.csv` 的动作 790 发生真实 DamagePlayer：原生 trigger tick 46636，提交后 tick 46637，HP 91、KR 10。整局验收失败，驱动停止。
- 前 19 轮 396,308 个非终态玩家分量与模型逐位一致；失败帧的全部 11 个玩家分量也一致。因此轨迹一致不能替代碰撞验证。

失败现场：`scratch/campaign-csv-native-20261007/randomblaster2-failure-native.json`、`randomblaster2-failure.png`。逐回合耗时见同目录 `failed-run-summary.json`。此前保存的 12 轮健康前缀独立诊断见 `prefix-verdict.json`；该诊断明确不是整局通过。

## 反例根因：ANGLE 的符号影响入场插值

原版 System.angle 直接将 atan2 的有符号结果转成角度。模型此前额外 `% 360`，把该炮的原始 `-141°` 改成 `219°`。两者最终朝向相同，但原版入场动画对原始 Ang/EndAng 做普通线性插值，二者并非相同的运动过程。

这使旧模型提前 10 帧开火并提前收束：伤害帧原版 beam timer 为 0.1791666666662495、基础宽度为 70，模型为 0.22083333333281915、59.21279075269468。碰撞宽度分别为 52.5 与约 44.40959，模型因此漏判。

仅移除 ANGLE 的归一化，保留相同 CSV、seed、全部目标采样、实际 dt 和完整玩家轨迹，模型首次碰撞就变成与原版一致的 frame 790。生产修复与正式回归针对这一规则，而非修改某关的弹幕或路线。

## 性能结论与边界

同一真实 Intro 请求，宽度 100、300、500 都找到 2283 输入的模型候选，游戏时长 9.5125 秒，完整 API 含可视化分别耗时 2.553、5.066、7.017 秒。平均仅使用约 1 个 CPU 核。详见 `scratch/campaign-csv-native-20261007/intro-width-benchmark.md`。

串行使用有明确实现原因：有界搜索调用串行 `_expand`；对话搜索要求至少 131072 条边才并行，而宽度 3000 的 16 种控制最多只有 48000 条边，且并行路径最多使用 2 个线程。后续应对同一层内的独立转移测试并行交叉点，再处理去重、筛选与内存分配，不能把占满 CPU 当作加速证据。

随后完成了真实层的独立进程内核基准：9000 条边，原串行为 1658.45 微秒，并行内核的 1/2/4/8 线程分别为 892.56/500.21/402.01/280.13 微秒，所有输出逐字节一致；8 线程 CPU/墙钟约 7.98。729 条边以上已有明确并行收益，9 条边的小批次反而变慢。详细结果见 `scratch/expansion-crossover-intro-minimal-20261007/RESULTS.md`。尚未将新调度接入生产或验证端到端加速，不能将 5.92 倍内核加速当作整局加速。

本次仍未满足每回合快于游戏时长的目标。例如宽度 1000 的 RandomBlaster1 完整请求为 11.873 秒，对应游戏 8.6875 秒；多个平台回合也略慢于 1×。缩窄候选宽度属于搜索预算调整，不是多核优化，也不提供完备性证明。

有限宽度、目标分支和 Confirm 策略下的失败仍为 `unknown`。本次记录不证明全局最优、任意初态或任意时钟相位可解；完整 Normal、其他有效自制 CSV 和无法证明无伤时的最小伤害路线仍需继续完成。
