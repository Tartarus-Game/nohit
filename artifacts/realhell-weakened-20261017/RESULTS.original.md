# Real HELL 削弱版：原游戏全谱无伤通过

2026-10-17，本地原版 Construct 2 游戏浏览器运行，seed 42、60 Hz 原生时间戳序列，加速逐帧正向执行。未恢复游戏检查点，未修改 HP、KR、碰撞或无敌状态。

结果：全部阶段执行至原生 Timeline 的 EndAttack，25,805 次输入、430.083333 秒游戏时间。原最后攻击在 415.083333 秒结束，之后继续安全执行测试副本补充的 15 秒等待。

| 核验项 | 结果 |
| --- | --- |
| 每一帧 HP / KR | 92 / 0 |
| DamagePlayer 调用 | 0 |
| 游戏连续快照 | 25,806 个；tick、dt 均连续且精确匹配请求 |
| 战斗状态 | 终点前 25,805 个快照的 11 个状态分量逐 bit 一致 |
| GetHeartPos | 469 次，原生采样与模型历史全部精确一致 |
| 独立观察器错误 | 0 |
| 结束事件 | 原生 Timeline，第 8033 行 `0,EndAttack,,,,,,,,` |
| 末尾 SlamDamage | 开启的 1,029 帧同样零伤害 |

终点后原游戏会清除 SlamDamage，并将玩家传送到菜单位置。最终 posttick 快照的 x、y、SlamDamage 因此与“仍处于战斗”的模型值不同。原始三项差异及 EndAttack 前、后、PlayerMovement 前快照均保留在证据中；验收使用仓库控制器既有的 EndAttack 规则：最后一次输入触发原生结束事件且无伤即完成，不要求菜单状态等于战斗轨迹。终点前无状态差异。

## 文件与证据

- 完整输入、Confirm、轨迹、目标历史：[completed-route.json](./completed-route.json)
- 独立源脚本 / 标量物理与碰撞复验：[longest-p480-gNone-w8192-verification.json](./longest-p480-gNone-w8192-verification.json)
- 原游戏完整记录：[bonesgap1-20261017-014253-858339.json](../../tools/real-game/bonesgap1-20261017-014253-858339.json)
- 原游戏截图：[actual-completed.jpg](./actual-completed.jpg)；图中文字为测试进度 HUD。
- 阶段表与尾声机制分析：[late-audit/RESULTS.md](../realhell-weakened-late-audit/RESULTS.md)
- 加速方法记录：[OPTIMIZATION-NOTES.md](../realhell-weakened-local340-20261017/OPTIMIZATION-NOTES.md)

路线 SHA256：`a6b31e5af71ff6b7c19280174209bcc878dad230f39a1631102b5219c6401314`。

## 测试源的范围

原下载文件未改动：`C:/Users/lf/Downloads/Real HELL 困难模式削弱版 - 副本.csv`。

原文件 SHA256：`fd494d9e8d9b7ae1c27bccd7088f6d8ce100054e635be020d3af5c23702c7799`。

使用单独测试副本，攻击坐标、速度、时长和顺序均保留：

- 第 5、6、153 行是当前原版导出没有处理器的 `setmaxhp`、`damafeeplayer`、`NoTooth`，替换为保留延时的空行。
- 第 163 行 `DamagePlayer,-10000` 缺少 KR 参数；移除该异常回血行，防止回血掩盖受伤或产生 NaN。
- 文件末尾补 15 秒等待和 EndAttack，作为明确结束条件。

修改清单：[source-changes.json](../realhell-weakened-20261017/source-changes.json)。测试副本原始字节 SHA256：`6fae36d1bdef87a5f9605080da045ed8121e7c867113bef5fc9c38f102775075`；浏览器 AJAX 换行规范化后 SHA256：`9225db26f1ae39dc9a1a4fe83e6d18dd342a84cfc7192e643a125eebc69b59ff`。

## 算法与困难原版状态

复用最新 Round 8 C++ 原生核心，以 480 帧窗口、前视、必要的数学路线回退来求解。成功后段从固定的 16,129 帧前缀续算，使用 480 帧前视并将前视目标读取上限从 8 提高到 128，34.90 秒到达 EndAttack；另有前段搜索与独立复验时间。所有实验改动隔离在 scratch 和测试浏览器文件，生产引擎未改。

另一个文件“Real HELL 困难模式 (最终补全版)”仍为 **unknown**：已尝试完整源求解和真实浏览器前缀，但没有整谱路线，因此未完成其后续阶段的实机无伤验收。有限宽度搜索失败、某条路线受伤均不能证明“有无缝”。削弱版的通过也不能替代困难原版的验证。困难版已有记录见 [RESULTS.md](../realhell-final-20261017-native/RESULTS.md)。
