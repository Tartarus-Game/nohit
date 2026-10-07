# 玩家、环境、对话的联合一步算子

实现位于 `nohit/engine/joint_transition.py`，保持 opt-in，未改默认 solver、server 或 TAS 播放入口。

联合状态为 `(player11, EnvState, previousInput)`。控制为 `u∈[0,63]`，物理控制只使用 `u & 31`，Confirm 独立占 bit5。`begin_joint` 的 player 必须是烘焙边界未执行当前物理 tick 的真实玩家状态，不能使用预览帧假定出的后继。旧 Cancel 与 player.keymask 的 bit4 必须一致；每个已提交节点也检查环境保存的旧 Confirm/Cancel 与控制码一致。

一步转换按以下相位执行：

1. `step_controlled` 消费当前输入推进源环境。如在 GetHeartPos 暂停，取只读 observation preview，以输入前 player 的速度执行 `sample_position`。此采样是 CustomMovement 后、Timeline 剩余命令前的位置，不是上一 tick 的位置，也不是当前方向键设置后的速度积分。
2. 向该暂停事务供给位置。此前 HeartTeleport 由源环境供给接口覆盖采样；同 tick 多个 GetHeartPos 分别处理，不能重放此前源命令或改变该 tick 的输入。
3. 只有完整 committed Frame 发布后，物理算子执行一次 `step_mask_into(player,u&31,frame)`。对每个真实 tick 检查白色矩形、运动条件蓝骨、激光四边形与 slam damage。对话等待不省略物理或碰撞。
4. 未建模回调、没有完整帧或输入缺失均为 unknown，不发布安全后继。

完整 key 保留 player 的全部 IEEE 位、原始程序与算子源字节、dt schedule、时钟累加值、资源与终止策略、输入、事务相位。已提交环境使用已有结构编码；bootstrap 暂停事务编码完整 data、VM 变量/RNG/HeartPos、目标请求、当前事务输入和对话状态。比较完整结构字节，不以摘要相等代替结构相等；不合并坐标或 Confirm latch。

数学上令 `F(s,u)` 为上述确定性后继，`H(F)` 为本 tick 的碰撞谓词，则安全边为 `s→F(s,u)` 当且仅当已建模且 `¬H(F)`。有限时域层的关系是

`R[t+1] = { F(s,u) | s∈R[t], u∈U, F 已定义且无碰撞 }`。

`joint_reachable` 的小型层状 DAG 枚举声明控制域的每条边，仅合并完整 key 相同的状态，保留一个真实见证。归纳上每个保留节点都有无伤输入前缀；完整展开的空层才表示该起点/控制域/模型下穷尽。状态或 tick 预算用尽、存在未知边都不能证明全域无解。返回 terminal 仅意味着**源环境终止且此前每 tick 安全**，不等价于原版游戏胜利，不替代 terminal tail、对话实机验收或 Real HELL 全程验收。

`verify_joint_witness` 逐 tick 重放同一转换，包括所有文字等待 tick。当前测试中两段连续文字到 EndAttack 的17 tick完整产品图见证可重放，Confirm 未污染物理控制码。另覆盖移动后采样、同 tick 两次 GetHeartPos 和中间 teleport、旧 Cancel 不一致、非法 Cancel 域、Confirm/速度/时钟 key 区分、逐 tick 白骨/蓝骨/激光/slam 碰撞与 unknown 回调、预算 unknown。

验证：联合模块8项通过；与受控环境、纯环境对话耦合集共26项通过。扩大至旧环境key套件时共34项通过、1项失败：旧 `test_exact_state_memo_reduces_actual_complete_small_search` 期待 expansions `(5,5)/(4,4)`，当前实际 `(5,3)/(4,3)`；该失败属于既有 DAG expansion 计数断言，本次未修改相关代码或断言。未作新对话段的原版实机验收。
