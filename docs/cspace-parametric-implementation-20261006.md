# C-space 与玩家依赖环境的实现边界

当前生产接口使用 `compact_wave` 编译原版脚本，`discrete_operator` 执行离散角色转移，`cspace` 执行空间查询。固定环境交给需求驱动 Bellman 可达性递推；`GetHeartPos` 使用相同递推并将环境历史纳入状态。

## 精确空间判定

矩形障碍按 PlayerHitbox 的 ±2 像素扩张。斜激光保留原版四个世界坐标顶点，使用闭集 SAT 相交判定；不以 AABB 代替束体。粗空间单元分为全安全、全危险、边界三类；边界查询保留原始 float64 坐标，回到精确矩形/四边形判定。空间格大小只改变速度、内存，不改变可行性。

蓝骨使用独立图层，仅在原版判据 `dx != 0 or dy != 0` 成立时致伤。正接触视为碰撞。奖励距离场和时间导航代价只能用于排序，不可作为安全检查。

## 时间与源码顺序

原版 Timeline 在执行到期命令之后才增加 T。平台 CustomMovement 在角色 CustomMovement 前运行；新创建平台在该步的运动阶段尚不存在。角色运动、Timeline、PlayerMovement、弹幕更新、最终 CombatZoneTick 的环境阶段分别保存。

不能用数学常数 `1/240` 替代原版调用时钟。原版从两个 binary64 时间戳相减得到 dt，`.1` 倒计时有可能因此相差一微步。`compile_wave(clock_start_ms=...)` 统一生成后续每步的实际 dt；搜索和几何都读取同一张表。

`BlackScreen(1)` 并非只有显示效果：原版会销毁 AttackSprite 和 Attack9Patch 家族（包括骨头、骨刺、平台和激光容器）。`EndAttack` 执行相同家族清理。编译器在原命令微步清除对应几何；销毁的平台仍以 `active=0, preTimelineActive=1` 保留该微步的行为阶段支撑信息。

原版 `Platform` 对坐标、宽度、方向与速度分别执行向零整数截断。`PlatformRepeat` 先计算每个平台的浮点坐标，再逐个调用 `Platform`，因此 `346-sin(pi)*140*2` 会先得到 `345.99999999999994`，随后截为 `345`。忽略该转换会虚构一像素的着陆空间，已用真实 PlatformBlaster 失败轨迹定位并添加回归。

## 动态目标绑定

`ParametricEnvironment.bind()` 遇到尚无玩家观测的 GetHeartPos 时返回 `complete=False` 和明确的 `pending_target`。`extend(binding,x,y)` 绑定该原版采样点，继续编译；每份历史使用完整浮点位值区分。

`ParametricRouteIterator` 在同一输入转移中遇到目标事件时，先调用原版运动阶段取得坐标，再绑定环境，继续同一微步。父节点保留尚未尝试的输入游标。只有全部后继失败的状态才能缓存为失败；状态键包含环境历史，不能只按角色位置合并。找到候选后继续迭代仍可访问其他候选。资源限制不是无解证明。

Normal 模式包含 Cancel 慢移的 32 种按键组合；Single 模式 Cancel 会退出关卡，因此合法字母表仅 16 种，必须在搜索前指定 `allow_cancel=False`。

参数环境与固定环境入口共用 `lookahead_policy='coast'` 与 `lookahead` 参数。`lookahead=60` 表示 60 个控制帧，即 240 个物理微步；同一动力学算子沿当前输入计算该窗口内能存活多久，仅用于排序，遇到未绑定观测边界即停止。重力轴松弛递推也可提供可行首个跳跃位用于排序；只有严格满足其不变条件时的空可达集才能证明当前完整状态失败。

## 已验证证据

- Intro 原版线性诊断共 1745 个死亡前微步，其中 423 个微步存在致伤激光。使用录制 dt 后，全部骨头、骨刺、边框和各方向激光四边形最大坐标误差为 `2.2737367544323206e-13`。这是机制差分，不是这份有受伤诊断路线的无伤证明。
- RandomBlaster1 已通过真实原版 EndAttack：510 个控制帧、2040 个微步、HP92/KR0；证据为 `tools/real-game/bonesgap1-20261006-041558-*.json`。
- RandomBlaster2 已通过真实原版 EndAttack：504 个控制帧、2016 个微步、HP92/KR0；证据为 `tools/real-game/bonesgap1-20261006-042031-356839.json`。
- PlatformBlasterFast 已通过真实原版 EndAttack：504 个控制帧、2016 个微步、HP92/KR0；证据为 `tools/real-game/bonesgap1-20261006-043823-339916.json`。
- Final 已按实际起始时钟、Single 合法 16 输入求解并通过真实 EndAttack：3128 个控制帧、12512 个物理微步，全程 HP92/KR0。候选见 `scratch/final-native-single-coast60.json`，完整原版证据为 `tools/real-game/bonesgap1-20261006-053223-796600.json`。
- 本实现新增测试覆盖亚像素边界、斜束空隙、随机连续查询、时间戳倒计时边界、不同目标历史、跨目标回退、零权重出口、后续候选和资源限制。

当前完备性仅针对声明的每四个物理微步选一次输入的控制时序。未证明全局评分最优、未证明任意输入时序的完整可达集。整个连续战斗仍需完整原版验收；不能用以上独立关卡证据替代整局通过。
