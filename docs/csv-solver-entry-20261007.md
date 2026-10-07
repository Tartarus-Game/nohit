# CSV 自动原版入口与精确轨迹页面

`welcome_to_hell.csv` 已通过新的自动原版入口完整无伤验收：原版加载 CSV、自动捕获实际起点、重新搜索并在同一个运行时执行。此次求解用时 **20.029973099997733 秒**，1464 个输入覆盖 **48.8 秒**游戏时间；独立观察器记录的 1465 个连续 tick 均为 HP 92、KR 0，16104 个非终态状态分量与候选逐项零差异，1 次 GetHeartPos 目标读取独立比对一致，并实际触发 EndAttack。

最新证据为 [welcome.json](../scratch/automatic-csv-native-20261007/welcome.json) 和 [welcome-verdict.json](../scratch/automatic-csv-native-20261007/welcome-verdict.json)（`passed: true`）。**原始记录文件** SHA256 为 `E4D0CC80B2142BE2951EA6BA99E89F868D748E54C1B0B7A3D079D23EB936FEEC`；它不是 CSV 内容哈希。入口快照、源身份和终态菜单重置的详细判据见 [自动原版验收记录](automatic-csv-native-20261007.md)。该证据只绑定这次源文件、入口、种子、时钟和候选。

Intro 也已通过独立原版验收：[intro.json](../scratch/automatic-csv-native-20261007/intro.json) / [intro-verdict.json](../scratch/automatic-csv-native-20261007/intro-verdict.json)。30 Hz 下重新求解用时 1.544696400000248 秒，287 个输入覆盖 9.566666666666666 秒游戏时间；288 个独立 tick 全程无伤，3157 个非终态分量零差异。

BoneStab3 在 60 Hz 原生时间戳协议下也已通过[独立原版验收](../scratch/automatic-csv-native-20261007/bonestab3-60-verdict.json)：405 个输入、406 个时间戳、7 种实际 `dt`，求解 1.7948825999628752 秒，游戏约 6.75 秒，全程无伤且 4455 个非终态分量零差异。终态速度按原版 ResetVars 和后续 PlayerMovement 的受限规则精确推导，与实际 `dx=0`、`dy=159.00000000000017` 一致；验收没有豁免速度检查。

## 使用入口

启动项目 Dashboard 后打开 `/csv.html`（首页已有入口）。

页面可直接读取本机 CSV 路径或接收粘贴内容。点击 **“在原版中自动解算并执行”**，页面通过 `POST /api/csv-source` 注册不可变源文件，再进入 `/game/index.html?csvtas=1&csv_source=<id>&attack=custom&custom_acceptance=1&seed=42&fps=<所选频率>`，同时传递当前搜索预算。原版 AJAX 插件下载注册后的原字节，完成成功后才调用 `MenuCustomRun`；驱动从原版实际状态建立求解请求，无需手工填写初态或提前加载动作。

自动入口支持 **30、60、120、240 Hz**。30 Hz 通过原版钳制得到 `dt=1/30`；较高频率按原生 binary64 时间戳逐次相减生成实际 `dt_schedule`，不能把 60 Hz 描述成精确常量 `1/60`。求解请求和回放严格使用同一显式序列，暂停求解保留时间戳的浮点相位。`max_ticks` 包含帧 0，默认 40000；`dt_schedule` 长度与之相同。非均匀序列的候选可正确报告 `physics_hz=null`，名义频率由驱动时钟另行记录。

驱动在源 Timeline 首个完整 tick 后暂停运行时，调用 `POST /api/solve-csv`；候选通过源、时钟和入口校验后，才在同一运行时逐 tick 输入方向键与 Confirm。`unknown` 或验证失败保持暂停，不执行未验证路线。完整无伤结论由独立原版证据验收器给出，驱动的 `completed` 标记本身不充当证明。

页面另有 **“开始解算”** 按钮：使用填写的初态、环境和帧率生成源模型候选及可视化。画布采用原生 640×480 坐标，显示轨迹、白骨和蓝骨矩形、激光四边形、活动平台及每帧输入；受伤判定框为 4×4。帧 0 是起点观测，输入 0 推进到帧 1。这条可视化路径仅显示源模型验证。

注册源保留原字节，`id` / `raw_sha256` 对原字节求哈希；`sha256` 对原版 AJAX 解码后的文本求哈希，包括去除 UTF-8 BOM 和将 CRLF 转为 LF。桥接器、求解器和原版观察器按文本身份互相核对，下载原字节不因此改变。当前 welcome 文件两种哈希恰好相同；带 BOM 或 CRLF 的文件可以不同。

命令行同样直接接收文件，不需要浏览器选取文件：

```powershell
tools/uv_py.bat tools/solve_csv.py <user>/Downloads/welcome_to_hell.csv --entry scratch/welcome-30-continuation/entry.json --fps 30 --max-ticks 3000 --out scratch/welcome-new.json
```

Python 入口为 `nohit.engine.csv_solver.solve_csv`。输出包括 `actions`、`confirm_sequence`、`unified_controls`（Confirm 位为 32）、完整轨迹、实际 `dt_sequence`、目标观察历史及环境绑定身份。需要同时执行移动和 Confirm，不能直接塞给只支持方向键的旧 TAS 消费端。

自动入口分别保存两侧状态：`initial_environment` 是源 TLPlay 执行前的环境；`initial_arena` 额外保留原版场地目标、对象实际宽高、缩放速度和结束回调；`initial` 是首个完整源 tick 后的玩家观测。目标边界不一定等于当时边框，实际宽高也不能靠边框相减或取整代替。原版可自动启动 RunAttack，等待场地稳定不能替代保存这些状态。

同时捕获真实 `initial_confirm` / `previous_confirm`（VPad Confirm / LastConfirm），并在 GetHeartPos 触发时读取玩家位置，形成 `initial_target_history`；随后 HeartTeleport 或场地钳制产生的后帧位置不能替代该采样。TLPlay 之后可以先有未执行源行的 tick，帧 0 必须对齐首个已提交的源 tick。

若首个 CSV tick 就执行 SansText，求解器只重建一次已观察的第 0 步世界和文字状态，不再次移动角色；`actions[0]` 从第 1 步开始。结果以 `primed_initial_frame`、`initial_frame_control` 标记这一协议。不能把已经等待多步、甚至已经结束首段文字的旧初态冒充第 0 步。CLI 或直接 API 调用者同样需要提供与对应入口一致的状态。

## 正确性与范围

- 正式 `solve_csv` 的普通和对话阶段均采用有限宽度候选搜索。对话阶段固定 Confirm 策略，在精确状态去重后沿用同一多样性筛选，并在 `dialogue_stats.motion_states_discarded_by_width` 中记录丢弃数。父状态、输入和初始来源同步保留；每个候选仍须通过独立标量重放与受控世界重放，终点必须是真实模型 EndAttack。底层 `solve_dialogue_frontier(width=None)` 保留完整运动关系的默认语义。
- `dialogue_max_ticks=None` 默认继承全局剩余步数，不再隐含截断在256步；显式提供较小值时仍尊重该限制。对话后的整个余下世界都会推进，场地与障碍不会因文字暂停而冻结。每层去重状态先检查 `dialogue_max_states` 资源上限，再进行宽度筛选。
- 已修复实际 `TLPause` 被忽略的问题：Timeline 暂停时，世界仍推进；场地缩放结束触发 `TLResume` 也不能追溯执行本 tick 已经过的 Timeline 阶段。[17 tick 原生前缀](../tests/fixtures/native_bonestab3_resize_pause_prefix.json) 已固化为[正式回归](../tests/unit/test_timeline_pause_resize.py)，关联门禁 220 项通过。
- 预算、状态数量或观察分支限制耗尽都返回 unknown，不构成无解证明。未证明全局最优、任意帧率鲁棒性或所有 CSV 都可解。welcome 和 Intro 的已通过记录各自限于本次 30 Hz 协议，BoneStab3 限于本次 60 Hz 原生时间戳序列；支持其他频率不等于那些频率已对全部样本验收。
- 首步对话通过上述显式输入初始化处理；初态不匹配不能通过删除一个输入或重复第0步来修补。对话后的新目标观察和未验证回调仍保留 unknown。
- 同 tick 的 GetHeartPos → SansText 会保存已解析环境及其本层父状态，拼接与可视化都从该真实父状态验证目标，不消耗额外输入。
- 可视化重新校验 CSV、完整时钟、绑定、状态和碰撞；页面仅显示源模型验证。原版验收证据单独保存，页面不会据此宣称任意新路线已经原版通过。
- Normal campaign 现已复用共享 CSV 回合驱动，并保留独立整局验收。首次新链路连续通过 19 轮后，在 RandomBlaster2 暴露 ANGLE 有符号角度的碰撞漏判，已修复并加入原生首伤回归；完整状态见 [Normal 原版验证](normal-csv-native-20261007.md)，不能将单关或健康前缀当作整局通过。

自动入口、原生 AJAX 桥、Dashboard 按钮及可视化契约的 4 个 Node 测试文件共 **79 项通过**；其中驱动 41 项，覆盖入口时间边界、完整场地状态、目标采样、30/60 Hz 输入时钟和失效停止。60 Hz 回归明确拒绝把非均匀 `dt` 改成统一 `1/60`，原有 30 Hz 检查保持通过。此前源传输、CSV API、可视化及 hold 回归的 5 个 Python 文件一次检查共 **54 项通过**，其中正式 hold 回归 12 项。后续时钟字段与测试的扩展没有改写既有 welcome 原版证据；回归测试与实际逐帧验收互为补充，不能互相替代。

历史手工入口证据保留于 `scratch/native-slow-input/csv-entry-verdict.json` 和 `scratch/welcome-30-continuation/`，仅绑定各自记录中的候选与协议；本文最新结论以上述自动入口记录为准。

旧 BoneStab3 30 Hz 区间审计也只适用于其固定的旧模型、入口和时钟。此次发现并修复了 Timeline 暂停语义后，不能将旧审计直接复用为新模型或原版游戏的全局无解结论。
