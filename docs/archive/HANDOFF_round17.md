# 高难回合解算与正常速度验收（2026-10-05）

本轮固定 seed=42，使用原版 Construct 2 引擎全状态分支搜索。独立加速回放通过后，再打开独立页面，以正常游戏速度连续执行三回合。实时观察器只记录状态与原版 EndAttack；未修改 HP、碰撞、位置或物理参数。

| 回合 | 解算参数 beam/segment/marginPx | 解算耗时 | 完整动作帧 | 实机结果 |
|---|---|---:|---:|---|
| PlatformBlasterFast | 24 / 8 / 1 | 66.263 秒（超时后续算） | 504 | 三回合全部无伤，HP92，KR0，零受击，三次原版 EndAttack |
| Multi3 | 24 / 8 / 1 | 45.607 秒 | 498 | 三回合全部无伤，HP92，KR0，零受击，三次原版 EndAttack |
| Platforms4Hard | 48 / 4 / 1 | 102.569 秒（超时后续算） | 安全前缀240 | no_candidate，未找到完整路线，未实机验收 |
| Platforms4Hard | 24 / 8 / 0 | 42.520 秒 | 安全前缀264 | no_candidate，未找到完整路线，未实机验收 |

`no_candidate` 仅表示保留的有限搜索分支耗尽，不能证明回合死局。零额外余量依然使用原版碰撞判定。

两个通过的候选已由服务器核验轨迹、动作序列和原版 CSV/runtime/data 哈希并提升为默认路线；覆盖矩阵也已更新。结果索引、完整实时轨迹、未完成搜索前缀和验收截图位于 `tools/real-game/`。机器可读索引为 `high-difficulty-20261005.json`，候选及默认计划位于 `tools/oracle-plans/`。

本轮本地服务端口8102。直接打开如下地址，页面会自动加载已保存路线并启动 TAS，连续三回合后自动暂停：

- `http://127.0.0.1:8102/game/index.html?mode=single&attack=sans_platformblasterfast&seed=42&acceptance=1&continuous=1&candidate=25732de4f2fd1c6c2bd3413c28701985e76f8729e5fdab12ac62c27000550dad`
- `http://127.0.0.1:8102/game/index.html?mode=single&attack=sans_multi3&seed=42&acceptance=1&continuous=1&candidate=dad97feb02f587401d19c78023b6701252f644226cf7956cf375da1178dd1a1b`

重新启动服务使用 `.venv/Scripts/python.exe start_dashboard.py 8102`。本轮服务器在 exec 会话13531中运行。

解算耗时仍为几十秒；本轮结果证明路线实机有效，并未证明原版全状态冷解算已经达到毫秒级。
