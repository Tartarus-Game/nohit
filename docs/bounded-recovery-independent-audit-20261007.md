# 有限候选前沿恢复的独立审查（2026-10-07）

本轮未发现恢复路径、历史归属或微步碰撞验证的正确性阻塞。新增的独立边界测试全部通过。恢复仍是丢弃候选后的启发式尝试；恢复失败不证明无解，恢复成功也必须继续经过既有的完整标量重放后才能报告候选。

审查范围为 `nohit/engine/bounded_frontier.py` 的 `_recover_frontier`、`_held_trace` 和主循环接入点，没有修改该生产文件或重新运行旧持键行偏移测试。

## 实际检查的约束

- 从当前保留层中取真实祖先行，每一行继续使用其自身 binding。后续已解析的世界即使存在于全局 registry，也不能供尚未观察目标的祖先借用。
- 宏动作仅使用调用方允许的 controls。环境和平台按绝对 tick 读取，完整碰撞表也按绝对 tick 查询；每个微步都必须安全。
- `stop <= _last_motion_tick(binding)` 和 pending-target 检查阻止越过目标、对话预览行或缺失的时钟行。已知世界的合法结束 tick 可以到达，由外层既有终止验证处理。
- 按 binding 分组后的局部父索引通过 `rows[parents]` 映射回祖先层真实行。恢复第一层接该祖先行，其余层逐层衔接；没有补造初态或历史。
- `_held_trace` 重建所有中间微步，并把最后状态字节与已检查端点对比。只有完整 suffix 就绪且预算未耗尽，才整体替换旧 suffix。
- 每次成功把 `reached_tick` 从旧值推进到旧失败 tick，即严格增加 1。失败立即返回；祖先距离按几何增长且有有限 lookback，外层有 tick 和墙钟预算，不会在同一失败 tick 无限重试。
- 预算在 bounded 操作之间检查，不是可中断任意 Numba 调用的硬实时截止。扩展或重建完成后发现超时，均不会发布部分恢复层。

## 新增正式测试

文件：`tests/unit/test_bounded_recovery_boundaries.py`。

测试中的保留层由真实 CSV、真实初态、标量状态转移和实际 `GetHeartPos` 读数逐层构建，不依赖 scratch 文件或旧候选。覆盖：

1. 多个真实目标历史，祖先 binding 行交错为 `[0,2]` 与 `[1]`；恢复父链包含非零真实行。每条恢复 witness 使用 reference 环境从真实初态重新执行，逐 tick 比较状态字节、碰撞和最终 binding/history。
2. 不等长 dt 序列，恢复从非零 tick 开始，验证读取绝对时间表行。
3. 未解析目标、对话预览和时钟耗尽三类边界禁止调用扩展内核。
4. registry 已有后续完整 binding 时，旧的 pending-target 祖先仍不得借用它。
5. 一条宏动作终点安全、但中间 tick 撞骨头，恢复必须拒绝；原有保留路径在该中间 tick 仍安全。
6. 截止时间分别在调用前、扩展后、重建后耗尽，检查全部旧层、父链、输入及 dialogue entry 保持原样。
7. 有限 lookback 的尝试次数和范围、失败仍为 unknown、配置拒绝负数/布尔/非整数 lookback。

命令：

```powershell
.\tools\uv_py.bat -m pytest -q tests/unit/test_bounded_recovery_boundaries.py
```

结果：**13 passed in 0.72s**。未运行大型 Final 搜索或原版浏览器重放；这份报告不把小型边界测试称为 Final 通关证据。

## 审查时文件版本

| 文件 | SHA256 |
| --- | --- |
| `nohit/engine/bounded_frontier.py` | `8DF01449C1D7501973C01F30285A0C5107B5CDDB5760C8538CF6BB069E633839` |
| `nohit/engine/expansion_dispatch.py` | `885F7472FB8DFA0AFD6FC986A58F86D23D374094EA0467AE2FBB0FF707815EE9` |
| `tests/unit/test_bounded_recovery_boundaries.py` | `E9B95B2F6A4F5FBB8C50D0BD4CF4C8B4A4B8DB7C38E969CFAD7F812C071EE504` |

已向实现者反馈一个统计语义问题：恢复会替换真实层，而 `stats.layer_counts` 的旧条目保留了被替换的扩展工作。实现者随后补充 `layer_counts_scope='expansion_history'`，成功恢复追加 `kind='recovery'` 的终点条目。本审查者已读取并确认这项改动；该日志不再暗示与当前 `result.layers` 一一对应。

统计语义补充后的 `bounded_frontier.py` SHA256 为
`9BDC599A3A370ECA009C8DB58E29847EA3A3D070D4AC914090AC2B06FF0C21CB`。
实现者报告其将 bounded 主测试、真实 Final 保留层 fixture 和本文件的独立边界测试合并执行，结果为 **40 passed in 8.74s**；这项合并测试是实现者的执行记录，本审查者自己的直接执行记录仍是上述 13 项。
