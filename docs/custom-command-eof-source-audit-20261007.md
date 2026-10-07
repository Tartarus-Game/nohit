# Custom 未匹配函数与 EOF 原版语义审计（2026-10-07）

本次仅核对原版源文件、已有观察器与终止证书实现，没有启动求解、修改 CSV、加入命令白名单或改变原版完成行为。结论是：套餐内的 `Score` 与命令列里的 `mus_zz_megalovania` 在本次审计的原版中没有对应函数动作；而 Custom 的 CSV 读完不会自动触发 `EndAttack`。这两类入口问题均不构成无解证据。

## 未匹配函数

逐个解析 `repo_jcw87/Event sheets` 下全部 **10** 个事件表，共找到 **116** 个 `Function: On function` 条件、**113** 个不重复的字面函数名，没有动态名称条件。大小写归一化后既没有 `score`，也没有 `mus_zz_megalovania`。事件表与运行时的 SHA256、计数结果保存在 [源审计 JSON](../scratch/custom-command-eof-source-audit-20261007.json)。

`jcw87-c2-sans-fight/c2runtime.js:373–374` 的 Function 插件调用路径先将名字转为小写，建立返回值为 0 的调用帧，复制参数，再触发对应名字的条件并弹出调用帧。无匹配函数时没有事件动作，也没有异常或隐式音频/闪光动作。`Battle.xml:113、127、356、1274` 中的 `mus_zz_megalovania` 是 Audio 动作使用的音频资源名，不是函数注册名。

套餐中的准确位置见 [12 处命令记录](../scratch/custom-unknown-command-sites-20261007.json)：Part1、Part2 首行各一条 `mus_zz_megalovania`；特殊分支①在 1221、1223、1236、1238、1244、1246、1279、1281、1369、1371 行各有一条 `Score,Flash`。

这些行的函数动作为空，但行本身仍须执行原版时序：`Timeline.xml:329–331` 发起函数调用，随后 `340–350` 扣除本行延迟、递增 `Line` 并调用 `TLLoadLine`。不能为了支持它们而把整个 CSV 行连同延迟删除；也不能把 `Score,Flash` 改写成 `Flash` 或把音频资源名改写成播放音乐指令。

这支持将上述两个名字作为**绑定当前原版身份的已审计无动作调用**接入模型。它不支持对任意版本、任意未知命令一概放行。当前共享入口仍会报告未支持命令，本审计没有改变这一实现状态。

## Custom EOF

原版导入路径完整保留 CSV：`MainMenu.xml:455–462` 把 `AJAX.LastData` 放入 `AttackList["custom"]`；`428–438` 的 `MenuCustomRun` 设置 `SingleAttack="custom"` 并进入 BattleScreen；`Battle.xml:1128` 起的 MODE_SINGLE 分支调用 `RunAttack(SingleAttack)`；`513–514` 再调用 `TLPlay(AttackList.Get(...))`。此路径不追加 `EndAttack`。

`Timeline.xml:294–315` 的逐行循环要求 `Running>0`、`Line>0`、`Line<=TLActionList.Width` 且本行延迟到期。执行最后一行后，`340–350` 仍递增行号；超过宽度后不再执行新指令。这个边界不会自动调用 `EndAttack`、`TLStop`、`ResetVars`，也不会销毁残余攻击对象。`Running` 可以继续为 1，`379–390` 仍累加 `T`。`Battle.xml:8880` 的 `TLIsRunning` 使用点属于 `PracticeMode` 事件组，不是 Custom EOF 完成回调。

因此 EOF 只证明主时间线已没有下一行；后续实体生命周期、对话回调、重力和场地调整仍需分别处理。`c2-sans-fight/custom_wave_acceptance.js:112–121` 当前对此处理正确：记录 EOF，统计全部待处理攻击实体、速度与场地是否稳定，但即使连续空场仍保留 `status="incomplete_eof"`、`terminalCertified=false`。观察器明确尚未证明未来回调全部耗尽。

## 可复用的证书与尚缺的连接

`nohit/engine/terminal_invariant.py` 已有一个充分条件证书：主时间线耗尽、待处理回调为空、没有对话、骨头/刺/炮/平台均为 0，场地固定，玩家与环境状态完整且有限，没有伤害状态或一次性脉冲。在速度为零、释放输入且夹取不改变位置的条件下，红心可形成固定点；蓝心还必须证明重力被静止的实体边界支撑。有限释放过渡由 `settle_release_to_invariant` 逐 tick 检验，最终仍必须得到解析固定点证书。有限时间“看起来没动”不会替代无限尾段证明。

`nohit/engine/terminal_completion.py:9–74` 还处理当前控制块剩余物理 tick 与精确时钟，再释放输入并调用上述证书；其结果明确只覆盖声明的编译器环境和时钟，`original_replay_passed` 仍为 false。低层 `eof_hazards_drained` 可以在仍有被动平台时结束环境构造，但当前固定点证书要求平台也为 0，故这类情况应返回 unknown，或另行提供包含平台动力学的证明。

当前共享入口 `nohit/engine/csv_solver.py:80–83` 固定使用 `endattack`；不能因为低层已有证书，就宣称共享 API、控制器和原版独立验收已经支持 EOF。

后续应增加独立的 **EOF 耗尽且释放输入后持续安全** 完成类型，保留与 `EndAttack`/Win 不同的事件语义。一次有效验收应保存：

1. CSV、原版与模型源身份、真实初态和时钟，以及从开始到证书位置的完整无伤执行证据。
2. 原生行号越过 EOF，且所有可能产生未来攻击或改变场地/玩家模式的回调、对话及实体生命周期均已耗尽的来源证明。空画面或当前碰撞栅格为空不满足这一项。
3. 证书边界处的原生完整玩家状态、场地状态与模型精确对齐；当前未释放控制块的尾部仍按原输入执行，然后才开始合法的释放输入过渡。
4. 对实际原版转移规则成立的安全不变式证书。蓝心的重力支撑、遗留平台和一次性脉冲均不得省略；不能只凭模型证书或若干静止 tick 提升为原版通过。

如果这些义务中任一项未证明，报告具体 unknown/unsupported 原因。不得给源 CSV 补 `EndAttack`、调用清场或把 EOF 记成原版胜利来获得通过结果。
