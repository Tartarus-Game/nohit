# 研究方案与当前生产调用链对照

> **历史快照说明：** 本文记录 2026-10-06 较早版本与研究方案的差距。下文“当前调用链”、五维状态、未接入 DAG-DP/C-Space 及机制尚未支持等结论只适用于当时版本。最新架构与已修复能力见 [DAG-DP 实现说明](dag-dp-implementation-20261006.md)，原版验收状态见 [整局无伤进度](full-game-progress-20261006.md)。保留本次历史审计与数学论证，以便核对后续修复。

本次核对来源为用户分享的研究文档本地提取版 `tools/gemini_chat_extracted.txt`，尤其是第 4.1 节（分层 DAG-DP）、第 8.2 节（双缓冲、位图与紧凑访问）、第 9.1 节（三层接口）。本文件描述现状，不声明以下缺口已经修复。

## 当前实际调用链

`/api/tas` 的新计算请求 → `canonical_solver.solve_attack` → `compile_wave` → `adaptive_dag.search` → `canonical_lattice.step_into / collision`。

候选回放走单独加载路径。旧 `compact_solver.solve_platforms4hard` 不是新计算请求的通用入口。

| 研究方案 | 当前主调用链 | 结论 |
| --- | --- | --- |
| 按时间层推进的 DAG-DP；同状态按需做 Bellman 代价松弛 | 边只向未来，所以图确实是 DAG；但节点由全局堆调度，命中已有状态直接跳过，没有累计路径代价与更优父链松弛 | 使用了时间 DAG 与可达状态去重，未采用文档规定的分层 Bellman DP 调度 |
| 将障碍与自机碰撞体做 C-Space 变换，预烘焙为位图供快速查表 | 预计算了骨头矩形；碰撞时仍遍历当前帧每个矩形，与角色中心 ±2 检查重叠 | 矩形检测与解析 C-Space 扩张等价，但没有接入所要求的预烘焙位图优化 |
| 独立、可替换的离散动力学转移算子；由原版规则提取并差分验证 | 有 `step_into(s, ux, up, env, platforms, out)` 纯函数和 Numba 编译；搜索直接导入该具体函数，状态固定为五维，转移仅覆盖有限机制 | 有算子雏形，未完成通用注入接口，也未实现所述 AST/PDG/SSA 提取流水线 |
| 连续内存、紧凑去重、双缓冲前沿 | 已有连续数组、开放寻址哈希、完整 float64 状态比较；主搜索保留全图并扩容 | 部分底层优化已用，双缓冲分层前沿未接入当前主链 |

## 代码证据

- `nohit/dashboard/server.py` 新 TAS 请求直接导入 `canonical_solver.solve_attack`。
- `nohit/engine/canonical_solver.py` 直接把 `geometry_white/blue` 传给 `search`，没有调用 `prepare_collision_dual_native`。
- `nohit/engine/adaptive_dag.py` 使用 `heap`，根据 `priority` 入堆、出堆；已有状态执行 `if existing: continue`。`priority` 是深度加局部偏好，不是累计路径成本。
- `nohit/engine/canonical_lattice.py::collision` 遍历 `white[tick]` 与 `blue[tick]`。一次碰撞检查随弹幕数量增长，不是单个位图探针。
- `adaptive_dag.landing_priority` 默认前瞻 60 个控制帧，即每个新增安全节点最多额外预测 240 个微步，每步再进行上述碰撞检查。
- 旧 `compact_lattice.search_frs_dp_bellman` 确实有双前沿、累计成本和同状态更优成本松弛；`compact_solver.solve_platforms4hard` 确实调用预烘焙位图，但限于该旧切片，不能当作当前完整游戏入口已经采用这些机制的证据。

## 偏离与修正方向

此前为取消 Beam 删除安全分支、保留窄路线并尽快输出可行见证，当前主入口转向了保留全图的堆式搜索，并改用浮点矩形直接检测。改动恢复了一些搜索覆盖与可核对的几何语义，但没有同步恢复研究方案的分层调度和 C-Space 查表，也没有清楚报告性能架构发生了变化。不能继续把主链描述为已经完成的研究方案。

应把当前经过差分确认的转移语义、无损去重和无伤硬约束，接回同一套分层 DAG 可达性/DP 核心；固定几何先烘焙，搜索通过明确的安全查询接口访问；运动、接触与重置事件通过统一转移接口执行。权重只改变偏好，低分安全分支仍须保留，不引入全局最优性证明作为执行前置条件。

接回位图前必须处理真实亚像素坐标的查询语义，不能直接对浮点状态取整后把窄路堵死或放过碰撞。旋转几何也必须使用正确形状，不能以大 AABB 充当最终危险区域。上述精确性要求需要在原架构中解决，不应成为长期绕开该架构的理由。

当前已测骨阵的毫秒级性能与回放结果仅覆盖那些测试场景；尚无完整原版战斗采用完整三层架构并无伤通过的证据。
