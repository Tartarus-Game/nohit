# CSV 求解与原版执行接口

当前 CSV 链路使用 Round 8 C++ 原生前沿搜索。给定源文件、原版入口和逐 tick 时钟，求解器返回经过模型及独立源算子复验的候选，或带具体原因的 `unknown`。有限宽度、时间或观察预算耗尽均不证明无解；模型的 `verified` 也不等于原版运行通过。

## 入口与时钟

Dashboard 的 CSV 页面可以选择或导入文件，打开原版 Custom 模式，捕获真实入口后求解并执行。捕获字段包括完整玩家 `initial`、TLPlay 前的 `initial_environment` 和 `initial_arena`、独立的 `initial_confirm` / `previous_confirm`，以及同一首帧真实发生的 `initial_target_history`。

玩家状态来自源首帧提交后的边界，环境和场地参数保留其各自的原版相位，不能用当前可见边框替代完整场地状态。目标读取发生在函数触发时；其后的传送或 clamp 后坐标不能替代该读取。

原版使用时间戳差并将 dt 钳制到 `1/30`。较高名义帧率的 binary64 时间戳差并非恒等的 `1/fps`。真实入口保存的 `dt_schedule` 必须原样复用；每个输入只推进一个相同时间戳协议下的原生 tick。

从仓库根目录运行已捕获入口：

```powershell
.venv/Scripts/python.exe -m tools.solve_csv attack.csv --entry entry.json --search-strategy native --seconds 30 --workers 8 --out build/route.json
```

`actions` 是方向键 / Cancel 掩码，Confirm 单独保存在 `confirm_sequence`，二者长度必须一致。Custom 模式中 Cancel 会退出关卡，不能作为无伤路线的有效控制。脚本伤害和治疗仅在显式允许时建模；仍须在原版逐次核对，不能用回血掩盖碰撞伤害。

长谱可通过 `--observation-chunk-ticks 480 --observation-preview-ticks 480` 使用当前分段观察与前视方案；前视目标读取预算默认为 128。每段继续保留真实前缀、源时序与目标历史，并在返回候选前独立复验。`--fixed-prefix` 可保留同源、同入口与时钟下已验证的前缀，不能把另一份谱的路线直接拼入。

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

Custom CSV 读完不会自动触发 EndAttack，也不会自动清除遗留实体或回调。支持的 EOF 完成证据必须证明时间线耗尽、所有相关未来回调耗尽、场地与攻击实体满足终止前提，并在释放输入后进入持续安全的不变状态。有限时间空场或静止不足以证明完成。

需要补充明确终点时，应建立独立测试副本，记录原文件与副本身份以及修改项；副本的通过仅适用于该副本。原文件和其他版本的求解结论分别保留。

物理判定与时钟依据见 [碰撞源审计](original-hitbox-source-audit-20261006.md) 和 [时间域源审计](original-runtime-time-domain-audit-20261006.md)。
