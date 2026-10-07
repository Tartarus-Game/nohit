# 对话与完整世界的受控状态转移

这一接口已实现，但明确 opt-in：默认 `ParametricEnvironment.bind/extend` 与默认 DAG 搜索仍保留原行为，在 SansText 停于 `NeedDialogue`，不会默默加入 Confirm 或跳过文字。

## 控制域

统一控制码取整数 0..63。原有 bit0..4 保持 Left/Right/Up/Down/Cancel；新增 bit5=Confirm。

`dialogue_operator.split_control(u)` 返回 `(u & 31, Confirm, Cancel)`。
**只能把 `u & 31` 传给旧物理算子/32动作表**。例如 u=32 只按 Confirm，绝不能当成运动动作编号32。Cancel 是否合法由外层游戏模式决定；受控环境接口默认拒绝 Cancel，显式 `allow_cancel=True` 才接受。

## 低层纯算子

`advance_with_dialogue_input(prior, confirm=..., cancel=..., previous_confirm=..., previous_cancel=...)`

首次接入必须提供此前真实 VPad 状态，防止已经按住的 Confirm 被误认为新边沿。此后 previous 输入由状态保存，调用者只提供本 tick 的输入。算子先 clone，保留父分支不变；每次推进一个真实物理 tick，或者在该 tick 的 GetHeartPos 采样点暂停。

没有输入时，已耦合的 `advance_one_tick` 返回 `NeedDialogue(kind='input_required')`，不推进时钟，也不猜测输入。GetHeartPos 暂停期间，本 tick 的 Confirm/Cancel 被固定，供给目标后不得替换。

EnvState 新增并保留：`dialogue`、`dialogue_coupled`、`dialogue_last_input`、`dialogue_current_input`、`dialogue_blocked_callback`。DialogueState 不可变，包含原文、CurrentChar、文本T、交互/存活标志、Timeout、EndFunc。对话状态与上个输入进入 committed exact environment key；未完成 tick 的输入与相位保留在 continuation 中。

## 原版相位闭环

1. Timeline 消费 SansText 指令，只消费一次；创建文本并 Running=False。
2. 当 tick 的 Timeline 尾部 T 累加条件在 RPGText 之前确定。对话结束不能使此前未执行的 Timeline 时间累加发生。
3. RPGText 在创建当 tick 就累加 dt；每 tick 最多显示一个 UTF-16 单元。Confirm 新边沿且文字完整才销毁；Cancel 的跳字不能让同时按下的 Confirm 提前关闭文字。
4. EndSansText/TLResume 立即恢复 Running，但 Timeline 阶段已过去；下条 CSV 最早下 tick 执行。
5. 同 tick 的玩家物理、骨头、平台、骨刺、龙骨、场地 resize 均照常推进。环境 Frame 不等于无伤证书；调用者仍要执行玩家算子并检查矩形/四边形碰撞。
6. 文件 EOF 遇到仍存活文本时不能结束。连续 SansText 分别等待真实输入边沿。

未知 EndFunc 在销毁时返回 `ResourceLimit(reason='unsupported_dialogue_callback:...')`，这里表示未建模/unknown，不表示无解或节点预算耗尽。它停在 RPGText 相位，**不发布**假定未知回调没有副作用的后半 tick Frame。多个重叠 SansText 也明确报 unsupported；当前没有把多实例选择集语义冒充成单实例循环。

## ParametricEnvironment 的 opt-in 接口

- `begin_controlled(binding, previous_input_code=...)`：从已烘焙边界建立独立 continuation，保留原 parent。
- `step_controlled(binding, input_code, allow_cancel=False)`：提供本 tick 的完整控制码，返回局部 Frame 或 NeedTarget。
- `supply_controlled_target(binding,x,y)`：在原采样相位供给目标，用已经选择的本 tick 输入继续执行，不重放此前指令。

返回 `ControlledEnvironmentBinding`，含 `state,parent,frame,status,request,input_code,reason`。
status 为 ready/terminal/need_target/need_input/unknown。缓存 key 用完整 base binding 的长度及身份、初始上一控制码、逐 tick 控制码、目标采样值构成，不能仅使用旧 target history 键。缓存命中仍验证 Cancel 输入域。

每条边只新增局部 Frame，parent 共享已经执行的前缀；不会为每个 Confirm 分支重新编译整个 CSV。未改默认搜索，也未把输入依赖的对话状态放进静态空间场后当成控制无关数据。

主 DAG 后续接入的完整状态至少是：物理 player11、精确源环境状态、文本状态、lastConfirm、当前物理 tick/控制格点相位及未完成事务输入。Cancel 的旧值必须与 player11.keymask 的 bit4 一致；现接口不知道外部 player11，**该一致性必须由联合转移调用方检查**。Confirm 是独立位，不能与跳跃 latch 或方向键别名合并。

## 已执行验证及限制

65 项纯对话、受控环境、resumable、旧 parametric 环境测试通过。包括：

- 两条连续文本各自需要新 Confirm 边沿；父分支和保留帧不变。
- 暂停 Timeline 时骨头和玩家继续运动。
- 缺少输入不推进时钟；跨 GetHeartPos 的输入不能更换。
- 文本进度与 lastConfirm 差异产生不同 exact key。
- 未知回调不发布伪造的完整 tick。
- 一个真实小图 BFS 在控制域 `{0,32}` 找到两条文字到 EndAttack 的17-tick路径，并逐个重放全部17帧；没有文字等待宏跳转。

另一次包含终端完成接口的扩展测试为67项通过（该集合与65项有重叠，不能相加宣称132项）。这些是数学/源事件顺序测试，尚未作为原版新对话段的实机验收。Real HELL 的完整求解也尚未由这些测试证明。
