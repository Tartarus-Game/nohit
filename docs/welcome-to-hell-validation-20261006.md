# welcome_to_hell.csv 验证记录

**2026-10-07 当前结论：用户指定的已知有解样本已在原版完整无伤通过。**
从新 Custom attack 入口执行 1464 个物理 tick（48.8 游戏秒），实际触发原版 `EndAttack`，
全过程 HP92、KR0、无正伤害事件；再执行 12 个中立输入 tick，障碍为空、场地缩放完成，
原版正常返回 FIGHT 菜单。CSV、伤害规则和游戏状态没有修改，没有恢复存档或拼接原生片段。

## 当前权威证据

- 完整输入：`scratch/welcome-30-continuation/all0-beam3000-seed42-dialogue.json`，
  包含等长的移动 `actions` 和确认 `confirm`；主路线从初态新生成，尾段显式求解对话。
- 独立原版逐帧证据：`scratch/native-slow-input/fps30-all0-dialogue-complete.json`，
  SHA256 `76b3e615193f725218f100d3489a354eb1a9d9b77c0658e6b5aaf8b3b67aca08`。
- 检验报告：`scratch/native-slow-input/complete-verdict.json`。
- 原版完成截图：`scratch/native-slow-input/all0-dialogue-complete.png`。

正式 `solve_csv` 入口的新输出还完成了第二次独立原版验证：

- 输入候选：`scratch/welcome-30-continuation/csv-entry-result.json`，SHA256
  `aeb7ec6ab083d5a75bd4a6d328e68c77e78ad17abd64d19a6b18ed5516cfccaa`。
- 原版逐帧证据：`scratch/native-slow-input/fps30-csv-entry-complete.json`，SHA256
  `5df4d648f0f60009ec06ccf441d817aaf0feaa5506ae32e85e082a629b300409`。
- 报告和截图：`scratch/native-slow-input/csv-entry-verdict.json`、同目录
  `csv-entry-complete.png`。这次从另一个新入口开始，没有借用第一次原生现场。

复核：

```powershell
tools/uv_py.bat scratch/native-slow-input/verify_complete.py
tools/uv_py.bat scratch/native-slow-input/verify_complete.py fps30-csv-entry-complete.json csv-entry-verdict.json
```

这次采用固定 **30 Hz 物理协议**，每个完整原版 tick 收到
`last_tick_time + 1000/30 + 1e-6` 毫秒的时间戳，由原版自身夹值为精确 `dt=1/30`。
没有直接写入 dt。入场后的首次完整帧是 model tick0，下一帧才应用 `actions[0]`；
Confirm 通过正常键盘 Z 状态单独注入，不能遗漏或混入旧移动 mask 接口。
该证据验证声明的物理时间步下连续执行的整关解，不是任意变帧率或实时调度的鲁棒性证明。

所有物理 tick 连续、输入逐帧匹配、HP/KR 无变化。从初态到 tick1463 的 1464 个
11 维状态与模型逐字节一致，包含 GetHeartPos 及结尾对话。tick1464 的唯一状态区别是
原版 `EndAttack` 把心移回菜单并重置最大落速，攻击对象同时清空，属于真实结束副作用。

| 原版事件 | 物理 tick |
| --- | ---: |
| 第一句 SansText 暂停 Timeline | 1444 |
| Confirm 后恢复 | 1447 |
| 第二句 SansText 暂停 Timeline | 1448 |
| Confirm 后恢复 | 1463 |
| 真实 EndAttack | 1464 |

## 纠正 1444 tick 提前终止

旧 1444 tick / 48.133 秒候选的模型 `EndAttack` 标签不成立。原版结尾 `SansText`
暂停时间轴时，骨头和玩家运动仍继续。旧 start720 候选前 1444 tick 确实原版无伤，
但其下一 tick 试图停下并确认时，先前速度仍让 x350→345，撞骨头变成 HP91/KR6；
原版根本尚未执行 EndAttack。该反例保留为
`scratch/native-slow-input/fps30-start720-tail-failure.json`。

默认编译路径漏处理对话暂停已修正，新路线显式递推对话状态、移动和确认，继续避开
仍活跃的障碍，最终才获得上述 1464 tick 原版成功。历史 JSON 内旧 `complete` 或
`termination_reason=endattack` 不可继续当作原版完整通关证据。

成功路线使用的两段历史暖测是：从初态生成旧主候选 **16.2647274 秒**，显式对话尾段
**0.2420634 秒**，合计约 **16.51 秒**。它们不包含导入、强制冷编译、调试和原版验证，
也不是当前生产入口一次端到端计时。主候选使用不完备的 beam3000 及观察分支选择，
因此能验证找到的解，不能由它的搜索失败推出无解。

另一次新 `solve_csv` 入口从初态独立求解用时 **19.2864613 秒**，输出同为 1464 tick，
见 `scratch/welcome-30-continuation/csv-entry-result.json`，约为 48.8 游戏秒的 0.395 倍。
其中保留 3000 入口状态的对话关系求解 1.1387023 秒、尾段重放 0.0103417 秒、
主前缀验证 0.1382924 秒。这不同于上面的历史分段计时。该新输出已由第二份原生证据
独立验证完整通过；原求解 JSON 的原版标志仍为 false，以保留“求解器只验证模型”的边界，
外部原版结论在绑定该候选哈希的 `csv-entry-verdict.json` 中。

## 240 Hz 失败有具体证书，不能泛化为 CSV 无解

旧捕获时钟模型在 tick2204 的四束激光将安全中心夹在
`287.25<x<350.75`、`274.25<y<337.75`，左向重摔设置 dx=-750。在没有平台、
传送、缩框或可触墙面的 23 tick 内，即使逐 tick 任意选方向，tick2227 仍必须
`x<278.875`；避开 x259 竖束却要求 `x>280.860573789118`，矛盾约 1.98557 像素。
这是冻结捕获时钟模型的连续区域证书，独立于 DP 数量；旧四 tick 完整前沿和末段
逐 tick 枚举的清空结果也已记录。它不是原版所有运行协议无解的证明。

具体时序差别是该束在捕获 240 Hz 模型中 tick2154 开始伤害、2204 重摔、2233 才取消
伤害；恒定 30 Hz 下为 267 开始伤害、276 重摔且同 tick 取消伤害。原版 ENTER 的逐帧
插值及倒计时使事件相位改变；30 Hz 完整原生路线已通过此窗口。证书和边界见
`scratch/bottleneck2227-audit/corridor-certificate.json`、同目录 `clock-comparison.json`。
性能、多核和状态分布的完整记录见[性能与原版语义诊断](welcome-solver-performance-20261007.md)。

## 以下为初次 240 Hz 验证的历史记录

当时没有获得完整路线，也没有证明文件无解。后述 11 个激光数量差异随后定位为原版
透明度比较的六位小数舍入遗漏，修复后全部消失；完整原版结论以上面的新证据为准。

### 初次输入与运行条件

- 源文件：`<user>/Downloads/welcome_to_hell.csv`，未修改。
- SHA256：`ffad127627d5b098a91d8c4657ee9b733d740b3d5c54f2c4cdede104a827fcb0`。
- 206 行，71 条 GasterBlaster，1 条 GetHeartPos，包含 EndAttack。
- 延迟列直接相加为 48.1166366 秒；这不包含对话等造成的运行时等待，不能当作已经验证的总时长。
- seed42，项目现有固定 240 Hz 时间戳协议，每四个物理 tick 选择一次方向输入，Cancel 禁用。
- 使用 `ParametricRouteIterator`，即生产参数环境 DAG 解算核心；从源文件路径直接读取 CSV。
- 原版 Custom attack 入口已加载同一 SHA256 的 7012 字节文件，采集初态后仅执行一次向前的前缀验证，没有进行原版分支搜索。

## 有限预算搜索结果

| 排序策略 | lookahead（控制帧） | 状态预算 | 最深物理 tick | 结果 | 墙钟秒 |
| --- | ---: | ---: | ---: | --- | ---: |
| coast | 60 | 20,000 | 2212 | resource_limit | 21.46 |
| navigation | 60 | 100,000 | 2216 | resource_limit | 22.96 |
| coast | 240 | 100,000 | 2220 | resource_limit | 44.17 |

这些是独立的有界试验，不是完整穷举。首次运行包含首次代码加载/编译成本，不能直接用上述墙钟值比较算法吞吐。

最深位置约 9.22–9.25 秒；附近第 2204 tick 执行 SansSlam(2)，玩家被向左重摔，当时左侧竖直激光仍有效。结果提示需要检查更早站位和后续可达性；尚不能确定最终根因。首次 GetHeartPos 在第 4100 tick，当前瓶颈发生在到达它之前。

结果文件：

- `scratch/welcome-to-hell-result.json`
- `scratch/welcome-to-hell-navigation.json`
- `scratch/welcome-to-hell-coast240.json`

复现：

```powershell
tools/uv_py.bat scratch/verify_welcome_to_hell.py --policy coast --lookahead 240 --nodes 100000 --out scratch/welcome-to-hell-coast240.json
```

## 原版前缀验证

第一轮的 553 个控制动作在原版运行时连续向前执行 2212 个物理 tick：全程 HP92、KR0，无受伤；包含起点的 2213 个玩家状态与数学模型完全一致，dt、白骨和蓝骨记录也一致。第 352 tick 的脚本瞬时缩框后，场地边界一致。

证据：`tools/real-game/bonesgap1-20261006-222946-532585.json`。
独立比较：`scratch/welcome-to-hell-prefix-verdict.json`。

初次运行当时尚未闭合的对应关系（保留历史）：

1. 原版开场有尚未完成的菜单缩框目标；当前 env22 初始化没有编码该目标。本次前缀在这段保持静止，玩家状态一致，且第 352 tick 的瞬时缩框/传送重新同步场地。不能将这一结果扩展到任意开场输入。
2. 11 个边界 tick 的原版 tick 结束后伤害激光数量少于模型。数量相同的 tick 中，忽略四边形顶点起点/方向差异后，坐标最大误差为 2.274e-13 像素。对象销毁和伤害检测的相位仍需核对，不能声称全部几何已验证一致。
3. 没有执行到 GetHeartPos、结尾对话或真实 EndAttack，没有完整无伤或实时验收证据。

初次结论是“已知有解样本暴露了现有解算器的搜索/模型验证缺口”，并未宣称新样本无解。
后续已完成具体障碍证书、原版语义修复及 1464 tick 整关原版验证，见本文开头。
