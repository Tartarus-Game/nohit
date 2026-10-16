# Real HELL 削弱版：原游戏完整无伤记录

2026-10-17，在原 Construct 2 游戏浏览器中以 seed 42、60 Hz 时间戳序列加速正向执行至原生 EndAttack：**25,805 次输入，430.083333 秒游戏时间，全程 HP 92 / KR 0，DamagePlayer 调用 0 次**。

终点前 25,805 个原生快照的 11 个状态分量精确匹配模型；469 次 GetHeartPos 读取一致。原生 EndAttack 触发后进入菜单，最后一个快照的 x、y、SlamDamage 因菜单切换而改变；原始差异与结束前后快照均保存在证据中。

| 文件 | 内容 |
| --- | --- |
| [route.json](route.json) | 完整输入、Confirm、轨迹与目标历史 |
| [entry.json](entry.json) | 原游戏初始入口及逐 tick 时钟 |
| [native-evidence.json](native-evidence.json) | 原游戏完整观察与结束事件链 |
| [scalar-verification.json](scalar-verification.json) | 独立源算子与标量复验 |
| [native-completed.jpg](native-completed.jpg) | 原游戏完成截图 |
| [source.csv](source.csv)、[source-changes.json](source-changes.json) | 测试副本及修改记录 |
| [OPTIMIZATION-NOTES.md](OPTIMIZATION-NOTES.md) | 当时成功搜索的参数与测量 |

原下载文件保持不变：`C:/Users/lf/Downloads/Real HELL 困难模式削弱版 - 副本.csv`。
测试副本保留攻击几何、速度、时长与顺序，仅把无处理器 / 拼写错误的命令置空并保留延时，移除缺 KR 参数的异常回血行，补充 15 秒等待和 EndAttack。通过结论仅适用于该副本。

- 原下载 SHA256：`fd494d9e8d9b7ae1c27bccd7088f6d8ce100054e635be020d3af5c23702c7799`
- 测试源原始字节 SHA256：`6fae36d1bdef87a5f9605080da045ed8121e7c867113bef5fc9c38f102775075`
- 浏览器规范换行后 SHA256：`9225db26f1ae39dc9a1a4fe83e6d18dd342a84cfc7192e643a125eebc69b59ff`
- 路线 SHA256：`a6b31e5af71ff6b7c19280174209bcc878dad230f39a1631102b5219c6401314`

这是精简前保留的实测记录，源身份绑定原记录版本。另一份“Real HELL 困难模式 (最终补全版)”仍为 `unknown`，没有整谱无伤或无解证明。
