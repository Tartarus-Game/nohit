# CSV EOF 原版验收与当前性能（2026-10-07）

当前共享 CSV 链路已在原版完成 `welcome_to_hell.csv` 无伤运行，并独立验收三种 EOF 充分条件案例。所有原版状态只向前执行；没有恢复存档、改写 CSV、清除实体、修改伤害或补发 EndAttack。

## 当前 welcome 完整运行

- 原始证据：`tools/real-game/bonesgap1-20261007-115817-087944.json`。
- 判定：`scratch/custom-eof-execution-20261007/current-welcome-verdict.json`，`passed=true`。
- 30 Hz 原版时间戳协议，1464 次输入、1465 个连续 HP92/KR0 观察帧，16104 个非末端状态分量精确一致，1 次真实目标采样一致。
- 实际观察到 EndAttack；菜单位置和最大落速变化由原版 ResetVars/菜单事件链单独验证。
- 求解及强制验证 9.673519 秒；包含可视化和请求处理的 API 总时间 **9.910592 秒**；游戏时间 **48.8 秒**。
- 截图：`scratch/custom-eof-execution-20261007/current-welcome.png`。

## EOF 与 EndAttack 分开处理

Custom 请求允许 `termination_policy=eof_hazards_drained`；Normal 默认仍要求 EndAttack。后端公开的动作、Confirm、轨迹和时钟已含全部释放尾段，前端不再拼一次。

| 原版案例 | 输入数 | E / D / N | 实际中性尾段 | 独立原生记录 |
| --- | ---: | --- | ---: | --- |
| 延迟后红心 EOF | 5 | 3 / 3 / 5 | 2 | `bonesgap1-20261007-120836-667583.json` |
| 蓝心落地 EOF | 19 | 3 / 3 / 19 | 16 | `bonesgap1-20261007-120836-690097.json` |
| 起点即 EOF | 2 | 0 / 0 / 2 | 2 | `bonesgap1-20261007-120836-715448.json` |

E 是主时间线耗尽，D 是环境义务消失，N 是实际释放后固定点。三份记录均在 `tools/real-game/`，对应 `scratch/custom-eof-execution-20261007/{minimal-red,minimal-blue,zero-red}-verdict.json` 均通过。全部最终状态也精确一致。

独立检查包括：实际 Line > TLActionList 原生宽度、全部攻击类型和 family 成员清空、原版 Wait 队列为空、无待切换布局、BattleScreen/Custom/menu 状态、场地及 EndResize、两次真实中性输入、14 个 VPad 字段，以及原版有限边框和玩家固定点。原版时间 T 仍可增长。

常驻 HP、PlayerName、QuitMessage 三个 BattleFont 必须保留完整证据并满足严格字段守卫；不能要求整个 RPGText family 为空，也不能忽略这一 family。字段/UID/名字在 D 与 N 之间除 T 外保持不变，其他文本对象均拒绝。依据见 `scratch/eof-resident-rpgtext-source-audit-20261007.md`。

原版 Sprite 碰撞多边形字段是 `ga.hr`，旧适配器的 `collision_poly→Ua` 不能作为证据。实际 SID 也必须按 JavaScript 数值读取；两个超安全整数已按原始 JSON 往返锁定。依据见 `scratch/eof-native-polygon-field-audit-20261007.md`。

EOF 判定是 `safe_forever_under_release=true`，同时 **`nativeEndAttack=false`、`complete_in_original_game=false`**。这不是原版胜利。蓝心当前原生充分条件仅覆盖向下重力和静止底边支撑；其他方向、残留平台、未处理回调仍不能宣称通过。

## 保留失败与测试

`114708-960190` 的实际执行因错误要求常驻文本消失而停止；`115816-971376` 的红心运行完整，但缺少实际多边形字段，独立验收拒绝。两份原始 JSON 均未修写，随后从新入口重新运行。

后端 EOF 及相邻门禁 161 passed；独立 EOF/EndAttack verifier 224 passed。前端新增控制器/观察器回归含少于两次释放、错误输入、最终细微漂移、缺失/非空回调、常驻 UI 篡改、错误多边形字段。真实记录与合成回归严格区分。

`scratch/custom-eof-execution-20261007/accepted-8146-source/` 保存 80 个源码文件：模型和原版字节已对证据哈希核验；其他观察器/测试文件是当前源码快照，不声称加载字节码认证。快照说明记录了最终边框字段断言比原生三案例晚加入。

## 性能与未完成覆盖

真实 RandomBlaster2 的 width300 失败尝试与 width1000 成功尝试累计，原 NumPy 分桶构建 **8.230229 秒**，融合构建 **7.724337 秒**，减少 **6.15%**，小于关卡 **8.5875 秒**。两个宽度各自的完整非计时语义、binary64 轨迹和源码身份相同。仅一组串行 A/B，不能当作所有机器实时延迟保证。证据见 `scratch/select-builder-prototype-20261007/actual-api/summary.json`。

本次不等于套餐 17 个 CSV 已全部验收。对话后的目标读取、残余平台的终止证明、minimum-damage 完整优化仍有工作；有限宽度或时间搜索失败始终是 unknown，不能推导 CSV 无解。
