# 逐 tick 输入与四 tick 输入的搜索域

`ParametricRouteIterator(..., decision_ticks=1|4)` 默认仍为 4。一次边展开执行指定数量的原生离散物理步，每步检查碰撞，并在遇到 GetHeartPos 时绑定精确环境。返回的 `control_ticks`、`decision_ticks`、`control_hz` 明确描述动作时长。EOF 收敛段按同一控制格点决定是否补齐末块。

四 tick 控制路线集合是逐 tick 路线集合的子集：每个四 tick 输入可以重复四次表示为逐 tick 输入，反向不成立。因此四 tick 搜索穷尽只证明该受限输入域无解，不能证明原生逐 tick 输入无解。

## 真实离散动力学反例

测试 `test_parametric_decision_ticks.py` 使用原 CSV 编译器、离散动力学和 C-space，不替换图边或碰撞判定。红心初始 x=319.55、速度为零；tick 2 出现两根全高骨墙，其安全中心区间为 `(320,321)`。

逐 tick 先按右，再释放，可在 tick 2 到达 x=320.175 后停住。四 tick 持续向右则在 tick 4 到达 x=321.425 撞右墙；中立/向左不能进入安全区，Cancel 降速后的首次位移也不足以越过左边界，竖向操作无法绕过全高骨墙。实际搜索在 32 个允许 mask 下分别返回四 tick 穷尽、逐 tick 找到路线；测试逐物理步重放见证并核对所有状态与碰撞。

## 优化审计

- 逐 tick 模式停用旧四 tick `equivalent_controls`、垂直死亡剪枝和垂直首选跳跃缓存；不能把较粗动作域的失败拿来拒绝细动作域。
- 单步预测改为实际 `decision_ticks` 步。
- 保留与动作时长无关的精确状态去重及下一物理步跳跃锁存位规则；未绑定下一步观测时仍保留完整旧输入。
- 导航和恒定输入 coast 仅影响排序，始终不删除输入。恒定输入 coast 本身按每个物理 tick 调用同一转移算子；它在逐 tick 动作域内是合法候选策略。
- `coast_support` 的四 tick 反馈预测在逐 tick 模式关闭，只保留恒定输入预测及纯位置评分。其名称不会被当作更细控制的证明。
- lookahead 参数仍按原先 60 Hz 帧计，`lookahead_microticks=4*lookahead`，与决策粒度分开。

本次扩展的是声明的固定 240 Hz 物理输入域，不包括尚未接入的 Confirm 对话控制，也不构成原版完整战斗已回放的证明。

后续接口更新：`/api/tas?decision_ticks=1` 已转交同一 solver，响应保留
240 Hz 控制元数据，播放器和 campaign 安装入口按逻辑 tick 逐项消费。
URL 参数可由 campaign 转交。四 tick 默认行为保持原状；逐 tick 路径不因
elapsed-time 跳变而跳过输入，但仍要求外部保证模型 dt 协议，不能据此宣称
任意自然帧卡顿下物理轨迹一致。播放器和 campaign 的8项集成测试通过，
API 调度29项通过。这些更新尚未做新一轮原版实机验收。

EOF 的 `terminal_tail` 现在由 `execution_schedule` 合成为逐 tick 执行序列：
原有限计划只展开到 `start_tick`，随后接桥接动作；桥中已经包含的末次持键
剩余 tick 不会执行两遍。API 区分 `solver_control_ticks` 和执行用
`control_ticks`，并标记 `execution_includes_terminal_tail`。有限计划和尾段
不能错位或缺少已证明尾段。执行合成、真实 EOF 候选和 API 调度一组合计44项
通过（早于新增长时间线参数的第29项API测试，计数有重叠）。

## Real HELL 有界对照

使用完整未改动原谱、已记录原生初态与时钟、16 个 single 合法 mask、coast60、max_ticks=18845。一次编译后以 5000 节点搜索，再保留同一搜索树提高到 20000 节点。结果位于 `scratch/realhell-microtick-opening-result.json`。

| 决策粒度与节点预算 | 最深物理 tick | 状态 |
| --- | ---: | --- |
| 4 tick，5000（此前同排序试验） | 1496 | resource_limit |
| 1 tick，5000 | 827 | resource_limit |
| 1 tick，20000 | 827 | resource_limit |

逐 tick 试验环境编译 128.694 秒；第一次有界搜索 12.084 秒，继续至 20000 节点追加 5.582 秒。首次搜索含初次 C-space/运行加载工作，不作为纯热搜索耗时。只有一个环境 binding，因此此处瓶颈不是 GetHeartPos 历史分支爆炸。

细粒度扩大了可达路线集合，但现有排序下也扩大了局部回溯，不是直接的性能优化。上述三次结果均未得到完整候选，也未证明无解；反例证明的是更细输入域的必要性，与这次原谱的成功率和速度是不同结论。
