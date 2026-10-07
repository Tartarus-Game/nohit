# FRS-DP 续作与内置浏览器验收 — 2026-10-05

本轮保持单一时间分层 FRS-DP 内核、预烘焙碰撞位掩码及 9 成员 / 45 字段微步模型。新生成路线已在 Codex 内置浏览器中通过原版离线回放和正常时钟连续三轮实机验收。范围为 Platforms4Hard、seed 42；不推广到其他回合或任意 dt。

## 修复与实际边界

- 构造了一个两帧反例：穷举六种动作能找到路线，旧 4px 分桶却返回无解。回归测试位于 `tests/unit/test_frs_completeness.py`。
- 默认折叠改为比较全部动力学状态的 float64 位和前一横向动作，保留 dx、各扰动成员、跳跃边沿及影响后续平滑度代价的输入历史。哈希冲突执行完整比较，累计代价保持 float64。
- `max_beam=0` 表示不做数量剪枝；每层状态或总展开达到预算返回 `resource_limit`。有限 beam / 显式旧分桶若丢失状态后未找到路线，返回 `search_limited`，禁止将它标记为完整穷尽。
- 当前纯函数默认无分桶、无 beam。仪表盘的实用候选入口使用精确折叠、beam 1000，并如实输出限制；`beam=0` 可请求全展开。
- 按键评分现在同时惩罚跳跃的按下和松开，而不是每一帧长按都计费。危险邻近代价继续参与分层成本计算。
- 全展开在第 8 个决策帧就超过 30,000 状态容量。精确折叠、beam 100 在第 90 帧搜索受限；精确折叠、beam 1000 找到 438 帧完整路线。旧“每层只有几十个无损等价类”的假设不成立。
- 当前找到的是保留状态图内的最小声明代价路线；没有全图最优性或不漏解声明。未重新引入原版 C2 快照分支求解，也未读取旧路线作为求解答案。

## 本轮验收

候选 ID：`8f6adba922a08012c706c83286a9e518ac1504e4826715f77eb7d185904d484f`。

动作 SHA256：`abc93f77ec83d39156bda10d796797d5298824e02ce531a064992290009feaa6`。重新生成后的动作与原版离线、实机记录逐项一致。

| 检查 | 结果 |
|---|---|
| 原版固定 240Hz 回放 | 438 决策帧 / 1752 微步，HP 92、KR 0、EndAttack |
| 正常时钟第 1 轮 | 1755 记录 tick，HP 92、KR 0、0 hits、EndAttack |
| 正常时钟第 2 轮 | 1754 记录 tick，HP 92、KR 0、0 hits、EndAttack |
| 正常时钟第 3 轮 | 1755 记录 tick，HP 92、KR 0、0 hits、EndAttack |
| 实际 dt 范围 | 约 3.2–4.9ms |
| 横向 / 跳跃动作切换 | 32 / 9 次 |
| 决策帧边界原版净空 | 最小约 4.625px；这是帧边界指标，不代表每个微步的最小值 |
| 测试 | 66 项内核、差分、挑战测试通过；2 项新核 HTTP 集成测试通过 |

正常时钟页面没有 `oracle` 参数，确认 `window.EngineOracle` 不存在。正常验收只按求解动作驱动键盘，并观察原版 HP/KR、真实 dt 和 EndAttack；未写入 HP/KR、位置或强制正常时钟 dt。原有 8102/8103 服务保留。

证据：

- `tools/operator-results/frs-verified-20261005.json`：新求解结果、模型参数、源码哈希及已核实验收标志；同一内容同步到 `compact-platforms4hard.json`、`frs-dp-latest.json`。
- `tools/real-game/bonesgap1-20261005-201735-661147.json`：独立原版固定步长回放，含逐微步观察。
- `tools/real-game/bonesgap1-20261005-201810-041300.json`：内置浏览器正常速度三轮原始遥测。
- `tools/real-game/bonesgap1-20261005-201831-003550.png`：内置浏览器成功页面截图。
- `tools/real-game/frs-iab-acceptance-20261005.json`：同一动作、候选、源文件哈希及两种时钟证据的关联记录。
- `tools/finalize_frs_acceptance.py`：校验以上证据后才写入验收标志，不用模型预测 HP 冒充原版验收。

## 分段性能

每次求解重新解析 CSV、生成碰撞掩码和搜索；机器码缓存与路线缓存分别记录。

| 阶段 | 独立编译缓存中的首次运行 | 已有磁盘机器码缓存 |
|---|---:|---:|
| Python 导入 | 502ms | 466ms |
| CSV 展开 | 12ms | 12ms |
| 碰撞内核编译 / 加载 | 423ms | 85ms |
| 实际碰撞预处理（已加载） | 6.0ms | 5.2ms |
| 搜索内核编译 / 加载 | 8179ms | 11.6ms |
| 热搜索 | 2411ms | 2478ms |
| 重建内核编译 / 加载 | 3014ms | 8.1ms |
| 热重建 | 0.05ms | 0.03ms |

记录见 `frs-cold-phase-timing-20261005.json`、`frs-disk-phase-timing-20261005.json`。首次测量使用新建 `NUMBA_CACHE_DIR`，三类内核都报告 `compiled`；预热只使用当前场景的一帧，不读取答案。以上不含操作系统进程启动和浏览器加载，不能表述为整个系统冷启动。

最后一次带磁盘缓存的常规入口总墙钟约 2.58 秒，其中搜索含加载约 2.46 秒。旧约 246ms 是有损分桶、beam 100 的不同配置，不能视作此次精确折叠的性能。

## 复现入口

```powershell
.\tools\uv_py.bat tools/solve_compact_platforms.py --states 30000 --beam 1000 --output tools/operator-results/frs-fresh.json
.\tools\uv_py.bat tools/benchmark_frs.py
.\tools\uv_py.bat -m pytest tests/unit/test_frs_completeness.py tests/unit/test_compact_platform.py tests/unit/test_challenger_m1_product_fidelity.py tests/unit/test_challenger_m1_dag_dp.py -q
.\tools\uv_py.bat -m pytest tests/unit/test_dashboard_server.py -k 'compact or uncapped' -q
```

受保护的在跑服务不重启；修改后的 HTTP 默认求解配置在集成测试的新服务中验证。后续启动新版服务时使用空闲端口，例如 `.\tools\uv_py.bat -m nohit.dashboard.server 8104`。

可见验收页面：`http://127.0.0.1:8103/game/index.html?mode=single&attack=sans_platforms4hard&seed=42&acceptance=1&continuous=1&candidate=8f6adba922a08012c706c83286a9e518ac1504e4826715f77eb7d185904d484f`。本轮保留了已经完成且暂停的内置浏览器页面。

下一步是寻找有证明的无损压缩或保留备用状态的调度，解决全展开的状态增长与性能；再检查更多初态 / 时钟反例及其他回合。当前没有“毫秒级完备全展开”或“全回合完成”的证据。
