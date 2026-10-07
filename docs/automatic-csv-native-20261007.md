# CSV 自动原版入口验收（2026-10-07）

`welcome_to_hell.csv`、Intro 和 BoneStab3 已通过自动加载、真实入口捕获、重新求解、同运行时输入执行与独立原版验收的完整流程。三份独立验收结果均为 `passed: true`，`scope: saved_native_csv_run`，无错误；前两条记录使用 30 Hz，BoneStab3 使用 60 Hz 原生时间戳序列。使用方式见 [CSV 入口文档](csv-solver-entry-20261007.md)。

## welcome 证据身份

| 对象 | 文件或字段 | SHA256 |
|---|---|---|
| 原始运行记录 | [welcome.json](../scratch/automatic-csv-native-20261007/welcome.json) | `e4d0cc80b2142be2951ea6ba99e89f868d748e54c1b0b7a3d079d23eb936feec` |
| 独立验收结果（新增时钟核验字段后的重验） | [welcome-verdict.json](../scratch/automatic-csv-native-20261007/welcome-verdict.json) | `9e8266ec7831d9c8cb74da6f3515c790d5c996c1341a6de72ab698352ed03dc0` |
| CSV 原字节，7012 字节 | `source.raw_sha256` / `source.id` | `ffad127627d5b098a91d8c4657ee9b733d740b3d5c54f2c4cdede104a827fcb0` |
| 原版 AJAX 文本 | `source.sha256` / `plan.csv_sha256` | `ffad127627d5b098a91d8c4657ee9b733d740b3d5c54f2c4cdede104a827fcb0` |

本次 CSV 原字节与原版文本的哈希相同。一般情况下，UTF-8 BOM 和 CRLF 会使二者不同：下载接口返回保存的原字节；文本身份按原版 UTF-8 解码、去 BOM、CRLF → LF 后的文本计算。运行记录的哈希是另一种身份，不能混作 CSV 哈希。

## welcome 实测结果

| 判据 | 结果 |
|---|---|
| 新搜索用时 `plan.wall_seconds` | 20.029973099997733 秒 |
| API 请求用时 `plan.request_seconds` | 20.25270350003848 秒 |
| 游戏推进时间 | 48.8 秒 |
| 物理与控制频率 | 固定 30 Hz，`control_ticks=1` |
| 种子 | 42 |
| 完整动作数 | 1464，均独立核对方向键及 Confirm |
| 原生观测区间 | tick 7 至 1471，含首尾共 1465 tick |
| 全程无伤 | 1465 个独立观测均为 HP 92、KR 0，无漏 tick |
| 非终态状态比对 | 16104 个分量，非零差异 0，最大绝对误差 0 |
| 原生 GetHeartPos | 1 次触发位置与候选目标历史一致 |
| 结束 | 原版真实 EndAttack；驱动 `completed`；独立验收 `passed` |

游戏时间与求解时间之比约为 2.44；这是一条实际测量，不是吞吐量、CPU 利用率或所有关卡的性能保证。

## Intro 独立验收通过

原始记录：[intro.json](../scratch/automatic-csv-native-20261007/intro.json)，SHA256 `dce85d0ac12fbba54fc48e110083d5dcaeb747674695b7e75a1639819def7797`；独立结果：[intro-verdict.json](../scratch/automatic-csv-native-20261007/intro-verdict.json)，`passed: true`。

| 判据 | 结果 |
|---|---|
| 新搜索用时 | 1.544696400000248 秒 |
| 游戏推进时间 | 9.566666666666666 秒 |
| 时钟 | 30 Hz 原生钳制 |
| 输入与独立观测 | 287 个输入，tick 6 至 293，共 288 个观测 |
| 无伤与状态比对 | 全程 HP 92、KR 0；3157 个非终态分量零差异 |
| 结束 | 真实 EndAttack 与原版 Custom 菜单重置均通过独立验收 |

Intro CSV 原字节哈希为 `d3e7e6a448e358a6f9eb70621c8dcea84a6b39b9506916fbec2ee5a0bb193620`，原生文本哈希为 `84a56e9ff0eddc73f117d1a71b1757eca5fb2df9af9067e437b8f0110dc91cfd`。本次原字节与规范化文本身份不同，二者均保留在源描述中。

## BoneStab3 独立验收通过

原始记录：[bonestab3-60.json](../scratch/automatic-csv-native-20261007/bonestab3-60.json)，SHA256 `6004283625d8475ebf689b394fe696a9125450dd8a7ef6c94539ff56915fc596`。独立结果：[bonestab3-60-verdict.json](../scratch/automatic-csv-native-20261007/bonestab3-60-verdict.json)，`passed: true`，SHA256 `9f428c4be2faae5c5fa255de5f8aa7775e55463b49db6e6cc07a1a9d5c669909`。

| 已观察项目 | 结果 |
|---|---|
| 驱动状态 | `completed`，405 个输入 |
| 独立原生观测 | tick 7 至 412，共 406 个时间戳 |
| 时钟 | 名义 60 Hz，原生时间戳差分，7 种实际 `dt` |
| 新搜索用时 | 1.7948825999628752 秒 |
| 游戏推进时间 | 6.7500000000000355 秒（约 6.75 秒） |
| 无伤与非终态比对 | 全程 HP 92、KR 0；4455 个非终态分量零差异 |
| 完整独立验收 | `passed: true`，无错误；终态速度由原版规则推导后核验 |

终态速度使用 `original_blue_menu_clear_sweep` 受限规则核对。原版 ResetVars 保留蓝魂模式，将重力方向改为 Down；菜单位置更新后，本 tick 继续执行 PlayerMovement。左右键同时按下使 `dx=0`，本次未发生松开 Up 的跳跃截断，原有 `dy=150` 加上重力 `540 × 0.01666666666666697`，得到 `159.00000000000017`。报告中的推导值与实际值均为 `[0,159.00000000000017]`，严格相等。

这项规则对原版结束链和菜单状态有明确前提，核验速度变化的具体结果，没有将 `dx` / `dy` 排除在检查之外。终态相对于战斗模型仍有位置、速度、方向共 5 个分量变化，全部在报告中保留；4455 个非终态分量实际零差异。

旧 30 Hz 区间审计限定于旧模型、入口和时钟；此次实际 `TLPause` 语义修正后，旧区间结论不能直接复用为新模型或原版游戏的全局无解结论。

## 可选原生时钟

自动入口目前支持 30、60、120、240 Hz。30 Hz 通过时间戳小偏移触达原版 `1/30` 上限；较高频率采用 `fixed-native-timestamps`，每步只给原版下一个时间戳，不把一个理想 `dt` 写入运行时。实际步长为 `min((next_timestamp - timestamp) / 1000, 1/30)`。

binary64 逐次累加与相减会产生多种实际 `dt`。驱动从帧 0 的实际 `clock_start_ms` 和 `dt` 生成显式序列交给求解器，暂停求解期间保持时间戳相位，候选与每个实际执行 tick 都严格逐项核对。`max_ticks` 默认 40000，计数包含帧 0，因而完整候选的动作数加 1 必须不超过它。名义 60 Hz 不是精确常量 `1/60`，非均匀候选可用 `physics_hz=null` 表示没有单一精确频率。

四文件 Node 门禁 79 项通过，其中 60 Hz 用例覆盖暂停后的时间戳连续性、非均匀序列以及错误统一为 `1/60` 时拒绝回放。新时钟能力与驱动字段不会改变上述 welcome 和 Intro 保存记录各自的实际时钟范围。

## Timeline 暂停修复

原版 `TLPause` 会停止 Timeline 累时与后续 CSV 行执行，同时让场地和世界继续逐 tick 更新。此前忽略这个命令会提前执行缩放后的攻击；现已按原版恢复暂停与回调阶段。即使 `TLResume` 在本 tick 的场地更新阶段触发，也不能追溯执行已经过去的 Timeline 阶段。

[native_bonestab3_resize_pause_prefix.json](../tests/fixtures/native_bonestab3_resize_pause_prefix.json) 保存了真实 60 Hz 入口的 17 个 tick（7 至 23），[正式测试](../tests/unit/test_timeline_pause_resize.py) 同时检查 reference / resumable 后端的暂停、状态、场地缩放与恢复阶段。此次修复的关联门禁 220 项通过；这是有真实原生前缀依据的模型回归，完整路线仍需另行原版验收。

## welcome 自动入口的状态边界

Dashboard 的“在原版中自动解算并执行”先注册路径或粘贴的 CSV，然后打开携带源身份的原版 Custom 页面。源桥等待原版 AJAX 的成功完成事件，再执行 `MenuCustomRun`。旧响应文本、HTTP 错误、源身份不匹配均不能代替本次加载成功。

驱动在匹配的源 TLPlay 前保存环境，并在源首个完整 tick 后暂停原版。此次实际读数如下：

```json
{
  "pre_source_bounds": [32, 240, 608, 384],
  "initial_arena": {
    "target": [33, 251, 608, 391],
    "size": [576, 144],
    "speed": 480,
    "callback": ""
  },
  "post_source_bounds": [33, 251, 608, 391],
  "initial": [320, 320, 0, 0, 0, 0, 0, 1, 750, 0, 0],
  "initial_confirm": false,
  "previous_confirm": true,
  "initial_target_history": [],
  "boundary_tick": 7
}
```

`initial_environment` 来自前侧的完整 22 分量环境，`initial_arena` 保留原版对象的目标、实际宽高、速度、回调；`initial` 来自后侧玩家观测。求解器重建已观察的源首帧世界，避免再移动一次玩家。只用后侧环境重建，会重复推进场地收缩；只用当前边框，又会丢失仍有效的目标和速度。实际宽高必须保留原始浮点值，不能由边框相减或取整代替。

`initial_confirm` / `previous_confirm` 保存已提交的 VPad 按键边沿。GetHeartPos 则在原版函数触发时直接读取位置，后续传送或钳制后的玩家坐标不能替代它。本次首帧目标历史为空，完整路线中另有 1 次目标读取，由独立观察器与完整 `plan.target_history` 比对。

候选返回后，驱动核对源文本哈希、时钟、后侧玩家、重建首帧环境、前侧场地状态及首帧目标历史，再继续原运行时。每个后续输入只推进一个实际原生 tick；`unknown`、输入偏差、损伤或提前结束均停止执行。

## welcome 独立结束判据

原版 EndAttack 在 native tick 1470 内触发，结束后快照为 tick 1471。此时 Custom 模式执行正常菜单重置，玩家位置等数据已经不是源模型 EndAttack 前的端点。验收器分别检查终点事件与菜单重置，不将重置后的状态强行当成模型战斗状态。

本次报告保留了 3 个终态差异：`x` 从模型 368 变为原版 47.99999949336052，`y` 从 310 变为 453，`max_fall` 从 330 变为 750。它们通过 `native_endattack_and_original_single_custom_menu_reset` 判据核验。该例外只适用于已核对的原版菜单变化；16104 个非终态分量没有使用这项例外，实际零差异。

原始观察器仍将状态标为 `incomplete_eof`，驱动仍未自行把 `original_replay_passed` 设为真。最终通过来自独立验收器对完整事件、无伤序列、输入、目标采样和菜单结束状态的交叉核对，不是单独采信上述任何标记。

在仓库根目录可重新检查已保存记录：

```powershell
.\tools\uv_py.bat tools/verify_csv_native_acceptance.py scratch/automatic-csv-native-20261007/welcome.json
```

保存格式与判据说明见 [验收器文档](../tools/verify_csv_native_acceptance.md)。

## 结论范围

welcome 与 Intro 的独立通过记录分别证明对应 CSV 在各自此次原版 Custom 入口、seed 42、30 Hz 原生钳制协议下存在完整无伤输入；BoneStab3 的记录证明其在此次入口、seed 42、60 Hz 原生时间戳序列下存在完整无伤输入。它们没有证明解最优、搜索完备、全部样本可解、任意初态可解或其他帧率下鲁棒。有限搜索耗尽仍只能返回 `unknown`。

Normal campaign 已接入共享 CSV 回合驱动，进度见 [Normal 原版验证](normal-csv-native-20261007.md)。本次 Custom 入口通过不能代替完整战役验收；原版 CSV 模型的其他命令与回调也不能只凭这些样本宣称全面等价。
