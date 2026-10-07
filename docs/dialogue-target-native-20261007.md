# 对话后目标读取与原生 EndAttack 边界验收

## 最新：Part4 完整原版无伤通过

BoneStab 到点判据修正后，8150 新服务从全新 Custom 入口自动求解并执行 Part4，
独立验收通过。3121 个输入、3122 个连续原生帧均为 HP92/KR0；34331 个非终帧
玩家状态分量逐字节相同。CSV 第448行真实调用 EndAttack，触发 tick3126，
post-tick3127 已进入原版菜单。末帧位置、max_fall 的变化由原生三阶段快照及
原版菜单/ResetVars规则解释，末帧速度[-150,-150]独立推导一致。

- 原始记录：`tools/real-game/bonesgap1-20261007-143822-383254.json`。
- 7 个分片、13061168 字节均验证SHA256，总哈希为
  `c76ee0fd76adeaf82856f597944a0d3ea509d0e5ac13e70785c9f7553267c8a6`。
- 原始展开字节、正式验收和独立Node审计分别为同scratch目录的
  `part4-corrected-native.expanded.json`、`part4-corrected-native-verdict.json`、
  `part4-corrected-independent-audit.json`；截图 `part4-corrected-native.png`。
- 对应实现及正式回归保存在 `accepted-8150-source/`；64个请求实现哈希均匹配。

本次完整API耗时62.7770918秒，搜索/模型主体58.7067967秒，可视化2.8235494秒，
对应104.0333333秒游戏（约1.657倍）。这些分项不额外相加到API总时间。
此处API计时止于Python返回结果对象，HTTP序列化、传输及浏览器解析尚未包含，
不能用它单独证明完整用户等待时间。
独立记录服务冷启动61.323秒，其中通用内核准备60.0947秒；它不是热请求计时。
前五次调试的已知成本下界101.6876328秒，再加旧原版失败请求56.0410943秒、
本次成功62.7770918秒，累计已知下界220.5058189秒，尚有一次精确成本缺失。
因此仅本次热请求满足1倍以上；不能声称累计重试预算或所有CSV的性能目标完成。

旧8149原版记录仍然是失败。其1824个玩家状态虽全部与模型相同，但原生骨刺
仍在y319，模型已退到y334，导致漏判碰撞。根因是模型用`dot >= 0`近似替换了
原版0.5度到点角度判据；浮点横向残差让精确到达纵坐标时两者不同，模型提前
一帧反转。现在按原版运算顺序、三角函数判据、相同坐标跳过赋值规则实现。
60项新增正式回归及12个相关文件共293项测试通过，旧实现的原生首伤断言会失败。
详见 `scratch/dialogue-target-continuation-20261007/BONESTAB-ARRIVAL.md`。
实际hazard快照为稀疏采样，独立审计对未采样的1829帧明确标为原规则重建，
没有把推算当作每帧原生物体记录。

下文保留此前阶段记录，其中“Part4仍未完成验收”描述的是本次修正前状态。

2026-10-07。本轮在新的原版 Custom 入口完成两条独立无伤验收。结果绑定于
`scratch/dialogue-target-continuation-20261007/accepted-8148-source/`，其中64个模型文件
逐一匹配请求中的SHA256，另保留原版runtime/data及观测、验收、测试代码，共83个文件。
观测代码的文件保存不等于浏览器已加载字节的远程认证。

| 实际原版案例 | 完整API耗时 | 执行时长 | 输入/连续HP92、KR0帧 | 精确匹配非终帧分量 |
| --- | ---: | ---: | ---: | ---: |
| PlatformBlasterFast | 0.2959763秒 | 8.633333秒 | 259 / 260 | 2849 |
| 对话前后取目标 + BoneStab缺省参数 | 0.0588221秒 | 1.1秒 | 33 / 34 | 363 |

API时间包含必须的模型验证和可视化重建。这是两次实际请求的测量，不能外推为所有CSV
的性能保证。二者均执行了真实EndAttack并到达原版菜单，独立验收没有忽略末帧速度差异。

平台记录为 `tools/real-game/bonesgap1-20261007-134327-163160.json`，验收结果为
`scratch/custom-eof-execution-20261007/platformblasterfast-three-phase-verdict.json`。
新增三次只读观测：EndAttack进入、返回、PlayerMovement事件组进入。实际平台数量依次
为32、32、0。原版销毁队列在事件边界清理，不能把函数返回时的平台列表伪造成空。
玩家速度在三个边界均为[150,111]，最后按原版输入/重力得到[150,129]。

EndAttack调用来源由原生当前事件/动作对象、已求值参数、加载行和源行共同约束：
Timeline事件441595194418922、原生动作9188948149072352；第三个边界读取原生Battle
事件组6451037740410459、名称playermovement。缺失或损坏的三阶段证据不会回退到宽松
规则。旧失败记录继续保留失败结论。

小样本源文件为 `scratch/dialogue-target-continuation-20261007/native-target-missing-stab.csv`，
原版记录为 `tools/real-game/bonesgap1-20261007-134551-793673.json`，验收结果为同目录的
`native-target-missing-stab-verdict.json`。真实目标历史恰为
`[[1,2,320,320],[3,4,320,325]]`，包含同一物理tick内先GetHeartPos后SansText的边界。
原生BoneStab第四参数及警告对象StayTime均为0。源码中的缺列通过Timeline固定九参数
调度补为数值0；不能替换为裸Function调用的缺参规则，也不能把已有空字符串全部改写。

`dialogue_target_frontier.py`现在扩展已烘焙的对话前缀，在需要目标时按每个实际玩家状态
解析世界，再按完整动态世界和当前帧数组精确分组，批量扩展箭头。不同目标产生的世界
不会因为玩家后来位于同一点而合并。最终父链用step_joint重新执行，恢复完整目标历史、
受控世界身份和真实源终点。资源或宽度限制依然报告unknown。

可视化从明确的base_target_history出发，以实际玩家和控制逐帧重放受控世界，检查完整
目标历史的类型/字节、最终受控身份及source_terminal，保留原有EOF中性尾段验证。
首次受控帧中已属于基础历史的目标读数，只在前缀精确相等后跳过一次，不做全局去重。

正式门禁包括176项模型/缺参/对话邻接测试、28项可视化测试、262项原生验收测试、21项
JS观测测试；此外不导入solver或验收器的独立Node脚本复核了两条完整记录。各门禁范围
有交叉，不将相加结果当作独立用例总数。独立审计见
`scratch/custom-eof-execution-20261007/platformblasterfast-three-phase-independent-audit.md`。

Part4仍未完成验收。宽度300在第839帧前沿变空，宽度1000到842帧；宽度3000能穿过该段。
它首先暴露第258行BoneStab缺StayTime的模型异常；修复后一次完整记录的尝试耗时
39.4933574秒、CPU50.4375秒，到2785帧后在第369行BoneV缺Direction/Speed处再次异常。
3000次目标事务、72766个世界/当前帧组是该次真实搜索统计。不能据此前沿失败或异常
宣称无伤无解。全部已知失败成本和旧异常未能恢复的精确计时，保存在
`scratch/dialogue-target-continuation-20261007/part4-attempts.json`；缺失计时明确为null。
