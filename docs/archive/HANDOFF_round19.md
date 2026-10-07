# 其他高难回合：RandomBlaster1 与 BoneStab3

固定 seed42。两个回合都已通过独立原版回放和正常速度连续三回合无伤验收，均 HP92、KR0、零受击、三次原版 EndAttack。覆盖矩阵已更新，已通过路线提升为默认TAS。

| 回合 | 方法 | 候选生成耗时（引擎已加载） | 帧数 | 实时轨迹 |
|---|---|---:|---:|---|
| RandomBlaster1 | 原版全状态前向搜索，beam24/segment8/margin1 | 54161.3ms | 510 | bonesgap1-20261005-135711-483332.json |
| BoneStab3 | 原版事件控制策略，hold32/settleFrames2/margin1 | 510.7ms | 378 | bonesgap1-20261005-141947-642302.json |

## BoneStab3 诊断和修正

旧搜索在184帧分支耗尽。把安全前缀截到128帧后，局部复现约4.3秒失败于剩余56帧。去掉额外余量、改变重力分组、补全按键分组、4帧控制步长以及更大的当前安全距离排序，均未越过相同失败点。失败状态会在同向重力冲击时撞回仍有伤害的墙骨刺。

持续起跳事件策略解决了短跳分支的限制：原版落地状态触发朝重力反方向的按键，尝试多种持续时间，每一帧依然运行原版240Hz四微步并检查真实HP/KR与膨胀碰撞盒。未修改物理、碰撞、HP或重力。

最初hold28且无落地等待的候选可独立加速无伤，但实机第一回合通过、后两回合受击。完整失败证据保留在 `bonesgap1-20261005-141643-072292.json`，该候选未提升为默认。随机方向三次一致，首次受击发生在按键提前于真实接触而消耗了起跳的时刻。

加入落地后两帧中性输入，候选选择hold32，才通过实机三回合。候选ID为 `8e29b7faffb1d29ce48658f675544e09d4842274ba080af2e92cc9bc9895e83d`。保留的失败候选ID为 `9fd380322c3d7fe8321fbf6eac1e5bc93a63a24c818fe13fcd859f35a070522c`。

`engine_oracle.js` 新增 `solveEventPolicies`，求解按钮先尝试事件策略；未找到候选时再使用现有分支搜索。续算仍只续已有分支前沿，不重新执行预试探。新策略不是完备性证明。

## 验证和复用

`tools/oracle-event-regression.js` 可通过CUA CDP载入对应seed42 oracle页面，调用 `runOracleEventRegression()`。验证完整378帧、两帧落地等待、1px余量、独立原版回放无伤。本轮结果为458.5ms，证据 `tools/real-game/bonestab3-event-regression-20261005.json`。`git diff --check` 已通过。

结果索引 `tools/real-game/other-rounds-20261005.json`，截图分别为 `randomblaster1-20261005.png` 与 `bonestab3-20261005.png`。

直接打开会自动播放默认已验收路线，连续三回合后暂停：

- `http://127.0.0.1:8102/game/index.html?mode=single&attack=sans_randomblaster1&seed=42&acceptance=1&continuous=1`
- `http://127.0.0.1:8102/game/index.html?mode=single&attack=sans_bonestab3&seed=42&acceptance=1&continuous=1`

目前seed42下累计10个回合有实时三回合通过记录。仍有其他回合待解决；不得把有限搜索失败称作死局。510.7ms只覆盖本回合加载完成后的候选生成，不包括服务启动、页面加载或预烘焙，也不能推广到所有回合。
