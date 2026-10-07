# 连续正常模式验收独立审计

**最新状态：v2 已安装并完成整局自动无伤验收。** 24 回合、68242 个连续原生 tick 全部 HP92/KR0，独立验证通过。正式结果见文末及 [持久化验收结果](../tools/real-game/full-game-verdict-20261006.json)。下列“记录层缺口”和“下一次全新进程”保留的是 v1 审计与升级历史，其中逐 tick 证据、模式检查及完整胜利链检查已由本次 v2 运行落实。

本次只读审计 `full_game_acceptance.js`、`full_game_runner.js` 及其调用顺序，没有修改当前浏览器加载的 JavaScript。最终结论应以保存的原生记录通过 `tools/verify_full_game_acceptance.py` 为准。

## 已确认的正向行为

- 固定时钟在每个 240 Hz 逻辑步调用完整 wrapper 链；验收器在原生 tick 后检查 HP/KR，追帧批次不会只检查最后一帧。
- 首次 HP≠92 或 KR≠0 会永久设置 `failed_damage` 和 `done`、暂停原生引擎并保存。最小原文件运行测试中，随后恢复 HP 再触发 Win2 仍保持失败。
- runner 的重新求解受 `done` 约束，只有未结束的原暂停边界可以 retry；它没有清除首次伤害的代码。保存原生 checkpoint 用于诊断，runner 本身不恢复它。
- 计划播放完毕只显示 `PLAYBACK FINISHED (HP UNVERIFIED)`，不会自动当作胜利。真正通过来自 Win2 观察。
- 原版事件表的正常胜利链为 Final EndAttack、HitAttempts>22、Win1、Win2，Win2 请求返回 MainMenu。

## 记录层缺口和处理

1. 在线验收器只要求出现 Win2，没有独立要求 Intro 到 Final 的完整序列。隔离测试中，没有任何回合而直接触发 Win2 可以得到 `passed`。离线验证器补充 24 回合顺序、24 次 Start/Run/EndAttack、Win1/Win2 时序、首尾监测覆盖，不将这种零回合记录认作成功。本次正常进程没有人工调用 Win2。
2. `SimulatorMode===0` 只在启动监测时检查。之后切换模式仍可能通过在线布尔判定；现有行中的 `mode` 是灵魂颜色，不能当作 SimulatorMode。离线验证器检查完整正常流程；若未来记录添加 SimulatorMode，也会逐样本验证其为 0。本次从原版正常入口启动且未改模式。
3. `rows.keys` 的实际顺序是 Left/Up/Right/Down/Z，不含 X/Shift 的 Cancel。不能将该数组解释成 LRUD-Cancel 掩码。完整数学计划保存在 computedPlans，但当前稀疏输入字段不能单独证明每一个实际按键。
4. 源文件哈希在保存时由服务端计算，并非浏览器已加载代码的独立内存哈希。当前进程期间保持相关 JavaScript 文件不变；离线验证器检查保存哈希、当前文件以及 jcw 原版 runtime/data/攻击 CSV 一致。
5. 原始 HP/KR 行按每 16 tick 保存；逐 tick 检查来自已审计监测器与 checkedTicks/tickGaps，不能声称离线拥有每个 tick 的原始 HP 行。离线验证器核对 `checkedTicks == lastTick - firstTick + 1`，完整采样序列、每个样本 HP92/KR0，以及终行覆盖 Win2 执行 tick。
6. 当前记录没有 HitAttempts 计数。正常源码的胜利条件提供间接约束，但不把它写成“已直接观测 23 次成功 FIGHT”。若未来记录包含初始 0、最终 23 的单调计数，验证器才报告直接验证成功。

## 使用

```powershell
.\tools\uv_py.bat tools/verify_full_game_acceptance.py tools/real-game/RECORD.json --json-out scratch/full-game-verdict.json
```

退出码 0 仅表示该完整记录满足上述独立验收；退出码 1 表示拒绝。允许同一暂停边界留下 resource_limit 等失败求解记录，但要求每个实际回合恰有一份成功 fresh candidate，禁止把失败重试计作额外成功回合。

10 项最小回归覆盖完整证据、失败重试、缺回合、假 Win2、tick 覆盖缺失、已恢复血量但留下首次伤害、缓存路线、缺少候选、被改动的原版 runtime 和可选 FIGHT/SimulatorMode 计数。真实受伤记录 `bonesgap1-20261006-053236-657557.json` 已运行验证器并被正确拒绝。

该标准只验证一个 seed 的正常原版战役。固定 FIGHT 顺序共 24 回合、23 种攻击脚本，重复一次 BoneGap2；可选 PlatformBlasterFast 不在此序列内。

## 下一次全新进程的强化版本

`scratch/full_game_acceptance_next.js` 是待安装版本，当前已加载的观察器保持不变。该版本使用 evidenceVersion=2，每个原生 tick 记录 `[tick, HP, KR, HitAttempts, SimulatorMode, VPad按键掩码, Confirm]`；按键掩码明确为 Left=1、Right=2、Up=4、Down=8、Cancel=16。每 64 tick 另外保存坐标和速度诊断。

它逐 tick 检查正常模式、HP/KR、HitAttempts 单调逐次从 0 到 23，严格约束 24 回合顺序和最终 Win1→Win2。首个 StartAttack 的原生触发边界也记录 HP/KR/模式/计数；DamagePlayer 调用立即留存，不会因同 tick 恢复血量而消失。Win1 和 Win2 可以相隔多个对话 tick。若 Win2 立刻销毁战斗对象，终行的计数来自同一 tick 已记录的原生 Win2 快照，并显式标注来源。

离线验证器兼容 v1/v2。对于 v2，它直接核查每个原始 HP/KR/模式/计数行、与坐标采样交叉比对，并比较每份数学计划所覆盖物理步的实际 VPad 输入。160000 tick 的模拟记录小于 8,000,000 字节；严格的发送前字节检查会拒绝超限记录，保留内存中的全部原始证据，不发送超大 POST。

## 完整原版战役验收结果

上述 v2 观察器随后安装到正常入口，产生完整记录 `tools/real-game/bonesgap1-20261006-115516-273476.json`。独立执行验证器退出码为 0、`passed=true`、`errors=[]`，结果另存于 `scratch/full-game-final-independent-verdict.json`。

- seed=42，24 个原版正常回合全部结束，原生 Win1→Win2 胜利链成立。
- 24 次 fresh candidate，0 次失败求解重试。
- 原生 tick 11 至 68252 共 68242 步连续原始证据，全部 HP=92、KR=0、SimulatorMode=0；无 tick 缺口或时钟错误。
- 直接观测 HitAttempts 从 0 单调逐次增长至 23。
- 54413 个数学计划覆盖步的实际 VPad 输入与计划逐步一致。菜单和对话输入同样逐 tick 留存，但不属于攻击计划。Intro 在计划末尾另有 90 tick 自动等待，已由原生逐 tick 无伤证据覆盖；其他 23 回合计划覆盖至原生 EndAttack。
- 9 个源文件的保存哈希与当前文件相符；runtime、data 和 23 种正常战役攻击 CSV 与 jcw 原版导出一致。

这证明本次 seed=42 正常原版战役从 Intro 到胜利完整无伤，不将该实机结果外推为所有随机种子、可选 PlatformBlasterFast 攻击或搜索算法对无限状态空间的完备性证明。

Intro 尾段补充核对：原版 CSV 最后为 `SansText("here we go.") → EndAttack`，文字函数会暂停 Timeline，结束文字再恢复。模型不包含这段交互文字等待，计划覆盖原生观测 tick 61–2204，EndAttack 的完成观测为 2294。其间 90 tick 的方向键及 Cancel 全为 0、Confirm 交替；tick 2240 的原生 Timeline.Running=0。编译环境的最后伤害几何已在 local tick 1872 消失，文本在 2144 开始，因此这是攻击结束后的对话推进，未漏掉仍需躲避的攻击段。模型结束时刻不等同于包含对话等待的原生回合时长，也不能据此忽略任意中途尚有弹幕的文本暂停。
