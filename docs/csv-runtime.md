# CSV 求解与原版执行接口

当前 CSV 链路使用 Round 8 C++ 原生前沿搜索。给定源文件、原版入口和逐 tick 时钟，求解器返回经过模型及独立源算子复验的候选，或带具体原因的 `unknown`。有限宽度、时间或观察预算耗尽均不证明无解；模型的 `verified` 也不等于原版运行通过。

## 入口与时钟

Dashboard 的 CSV 页面可以选择或导入文件，在页面内独立解算并查看模型轨迹，或另开静音原版 Custom 页面捕获真实入口后求解并执行。打开游戏不会离开 Dashboard；两页通过同一 `progress_id` 读取后端进度，游戏向原 Dashboard 回传本次求解结果和执行状态。捕获字段包括完整玩家 `initial`、TLPlay 前的 `initial_environment` 和 `initial_arena`、独立的 `initial_confirm` / `previous_confirm`，以及同一首帧真实发生的 `initial_target_history`。

`GET /api/progress/<id>` 提供最近的真实阶段与计数；运行时的耗时即使暂时没有计数事件也会持续更新。搜索、源准备、逐 tick 复验与完成证书分别显示，分窗和重试可以重新经过这些阶段。搜索 tick 上限与预算消耗都不能解释为整项任务的完成率或可靠 ETA。游戏 HUD 的进度链接可另开只读 Dashboard 监控；该链接仅恢复进度，不恢复已关闭页面的完整结果。

页面和游戏 HUD 的 ETA 使用 `eta_seconds` / `eta_basis`，明确标为当前阶段的估算。源搜索按谱面字面时长、真实时钟和已提交 tick 的速度估算，前视探索不算已提交；逐帧复验按当前复验速度估算。没有足够数据、动态延时无法估计、重试或阶段切换时会重新估算，不用剩余预算冒充预计完成时间。游戏面板可折叠，进入执行后自动收起，只保留一行状态；警告、进度计数和链接仍可展开查看。

Windows 的线程 CPU 时钟可能不足以测量极短的单线程预检。原始值超过实际墙钟时间时，CPU 耗时改报墙钟上界估计，并在 `native_code` 中保留原始值、`cpu_measurement_resolution_limited` 与 `search_cpu_seconds_kind` 标记。

导入预检和求解结果将已审计的原版空调用放入 `warnings`，保留行号、名称、源文本与延时，并继续执行。名单为 `Score`、`mus_zz_megalovania`、`setmaxhp`、`damafeeplayer`、`NoTooth`（忽略大小写），仅在原版 `data.js` / `c2runtime.js` 身份匹配时有效。这些名称没有处理器，不会自动修正为近似名称；其他未建模机制仍列入阻断的 `issues`。能继续执行不代表已得到无伤路线，仍需完成求解和原版验收。

Dashboard 导入与直接求解 API 默认清空 CSV 中显式 `DamagePlayer` 的命令单元格，保留原延时和行号，并报告 `scripted_damage_disabled` 警告。原始文件不变，原始字节和可执行字节分别绑定 SHA256；有清理的导入通过 `import_id`、`preparation` 和 `original_url` 保留追溯。模型、逐帧几何和原游戏均使用清理后的执行源；原游戏的碰撞伤害函数保持有效。

页面默认使用自动预算，不要求用户填写初态、宽度或秒数。API 的 `budget_mode="auto"` 根据时长、指令数和目标读取数选择现有求解参数；长目标脚本自动分窗与前视。有限失败最多自动加宽一次，搜索预算合计上限 180 秒，准备和复验另外计时。结果的 `budget_selection` 记录实际参数和尝试。`budget_mode="manual"` 或旧 API 的显式预算参数保留手动行为；页面手动项位于高级设置。

真机执行与 Dashboard 默认请求使用 `visualization_mode="entry"`，只重建用于核对原版入口的第 0 帧，避免为长谱额外分配整段预览几何。Dashboard 仍可播放完整玩家轨迹与输入，后续帧明确标注未生成危险几何；高级设置可选择完整逐帧几何。完整路线仍经过求解器的独立源算子复验，原游戏执行后仍须逐 tick 独立验收。

玩家状态来自源首帧提交后的边界，环境和场地参数保留其各自的原版相位，不能用当前可见边框替代完整场地状态。目标读取发生在函数触发时；其后的传送或 clamp 后坐标不能替代该读取。

原版使用时间戳差并将 dt 钳制到 `1/30`。较高名义帧率的 binary64 时间戳差并非恒等的 `1/fps`。真实入口保存的 `dt_schedule` 必须原样复用；每个输入只推进一个相同时间戳协议下的原生 tick。

从仓库根目录运行已捕获入口：

```powershell
.venv/Scripts/python.exe -m tools.solve_csv attack.csv --entry entry.json --search-strategy native --seconds 30 --workers 8 --out build/route.json
```

`actions` 是方向键 / Cancel 掩码，Confirm 单独保存在 `confirm_sequence`，二者长度必须一致。Custom 模式中 Cancel 会退出关卡，不能作为无伤路线的有效控制。脚本伤害和治疗仅在显式允许时建模；仍须在原版逐次核对，不能用回血掩盖碰撞伤害。

长谱可通过 `--observation-chunk-ticks 480 --observation-preview-ticks 480` 使用当前分段观察与前视方案；前视目标读取预算默认为 128。每段继续保留真实前缀、源时序与目标历史，并在返回候选前独立复验。`--fixed-prefix` 可保留同源、同入口与时钟下已验证的前缀，不能把另一份谱的路线直接拼入。

## 失败位置与少操作目标

失败结果的 `failure_diagnostics` 包含最后安全 `last_safe_tick` / `last_safe_seconds`、首个未解决转移的 `failure.tick` / `failure.seconds`，以及 `failure.csv` 的行、列、原始单元格和最近实际执行指令。秒数按本次精确 dt 累加，首帧为 tick 0、时间 0。资源边界无法取得下一帧时，`seconds_exact=false`，时间只代表已累计的边界时间。CSV 行是实际解释器游标，造成碰撞的物体可能在更早的指令生成；不把游标冒充致伤物的来源。

`failure_diagnostics.routes` 保留独立复验后的安全输入、Confirm、轨迹、dt、目标读取和源哈希，始终标记 `complete=false`。失败的顶层 `actions` 仍为空，原版自动执行器只接收完整候选。Dashboard 会弹出位置、提供前缀选择和 JSON 导出。静态搜索导出最深保留前沿；观测搜索也保留回退前的不同分支，再按各分支自己的真实目标读取重新执行，截掉碰撞后的部分。默认上限 32 条，可用 API `diagnostic_routes` / CLI `--diagnostic-routes` 改为 1–256；诊断复验另有 200,000 个转移预算。达到上限会设置 `routes_truncated=true`，结果始终 `exhaustive=false`，不能证明全局无解。

API `objective="fewest_operations"` / CLI `--objective fewest_operations` 按方向键组合的变化次数优先排序，长按计一次、释放或换方向再计一次。默认权重为换键 1000、持键帧 0；`balanced` 保留 12 / 1。可分别通过 `operation_weight` / `held_weight`（CLI `--operation-weight` / `--held-weight`）调整，范围 0–1000，不能同时为零。奖励为 `-(换键次数 × 换键权重 + 非零按键帧数 × 持键权重)`，初始按键锁存也计入。Confirm 的既定对话策略不属于这个方向键目标。少操作模式跳过提前返回的快速控制策略，保留完整上一帧掩码作为代价状态；有限宽度仍可能丢弃更优或可行路线，`optimality_proven=false`。

少操作模式会继续运行预算内的其他 native 探针，在同一已解析搜索窗口内比较所有找到的完整路线，返回实际加权操作代价最低的一条。观测搜索仍按窗口提交，因此这也不是对整份 CSV 的全局最优证明。

## 独立原版复验

浏览器执行保留完整输入、连续原生快照、函数事件、目标读取和源身份。保存后使用独立验收器：

```powershell
.venv/Scripts/python.exe -m tools.verify_csv_native_acceptance evidence.json --output build/verdict.json
```

保存格式和判据见 [验收器说明](../tools/verify_csv_native_acceptance.md)。通过须有逐 tick 无伤、输入一致、非终态状态一致和合法结束证据。EndAttack 后原版会进入菜单，因此菜单状态按审计过的结束事件链核对，不能强行当成仍在战斗的模型状态。

开发用的无界面复验直接启动原版 Construct 2 事件引擎，只替换 DOM、音频和渲染接口；它与浏览器画面验收分别报告：

```powershell
$env:NOHIT_PYTHON = (Resolve-Path .venv/Scripts/python.exe).Path
$env:NOHIT_SEARCH_STRATEGY = 'native'
node tools/native_optimized_replay.mjs sans_bonegap1
```

默认产物放在 `build/native-replay/`，可用 `NOHIT_BENCH_OUT` 指定输出目录。`native_replay_batch.py` 为独立攻击分配进程和搜索线程；连续 Normal 战役使用 `solve_normal_native.mjs`，并由 `verify_normal_native.py` 复验，不把独立攻击拼成连续战役。

完整战役浏览器记录使用 `tools.verify_full_game_acceptance` 验收；默认按 `tools/original_c2_sha256.json` 固定的原版运行时和攻击源身份比较，也可以显式提供 `--original-dir`。服务器保存的记录位于 `build/evidence/`，分块记录须保留完整 `campaign-evidence/` 相对路径，验收器会检查每块字节数与 SHA256 后重建。

## EOF 与结束

兼容接口仍沿用 `eof_hazards_drained` 策略名。除空场证明外，原始模型和原版观察器现在可确认「只剩速度严格为零的蓝骨」的源准备边界，记录实际数量与几何；随后逐 tick 检查释放按键的桥段，再要求玩家速度为零、没有未来回调的固定点。该证书明确命名为 `static-blue-release-fixed-point-v1`，不会把蓝骨数量改成零；白骨、橙骨、运动蓝骨、平台和未耗尽的炮头等均不适用此证明。CSV 明确把红心传送到场外时，还可用原版有限场地 clamp 的不相交条件证明停住持续安全。

BlackScreen 的同帧新建对象遵循实测 C2 选择语义：销毁本 tick 前已登记的攻击对象，保留本 tick 的待登记新对象。原版回放必须覆盖这类情况；只让两套模型共享错误生命周期不能完成验收。

Custom CSV 读完不会自动触发 EndAttack，也不会自动清除遗留实体或回调。支持的 EOF 完成证据必须证明时间线耗尽、所有相关未来回调耗尽、场地与攻击实体满足终止前提，并在释放输入后进入持续安全的不变状态。有限时间空场或静止不足以证明完成。

需要补充明确终点时，应建立独立测试副本，记录原文件与副本身份以及修改项；副本的通过仅适用于该副本。原文件和其他版本的求解结论分别保留。

物理判定与时钟依据见 [碰撞源审计](original-hitbox-source-audit-20261006.md) 和 [时间域源审计](original-runtime-time-domain-audit-20261006.md)。
