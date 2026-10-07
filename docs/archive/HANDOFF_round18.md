# Platforms4Hard 求解器修正与实机验收

所有原版回合按有无伤解的前提继续研发；有限搜索失败应记为求解器未解决。

## 复现与根因证据

固定 `sans_platforms4hard`、seed42，从此前保存的安全前缀160帧开始，原版全状态求解器 `beam24 / segment8 / margin0` 稳定在剩余104帧（总帧264）耗尽分支，局部复现约15秒。

三种假设为历史最小余量排序、平台后续落脚位置、固定控制步长。仅把历史最小余量换为当前余量，仍失败在同一点；只把平台水平距离加入排序优先级，即找到完整剩余278帧，约40秒。保持原版碰撞与完整状态恢复，未修改游戏难度。

## 改动

`engine_oracle.js` 的新默认 `policy='support'` 在蓝色灵魂且有平台时优先保留与平台水平间距更小的状态，再比较原有安全余量和输入成本。原有运动阶段、接触高度及空间分组仍然保留。`policy='clearance'` 用于原策略对照；续算记录并恢复 policy。

这是一项启发式改进，不是可达性证明；仍不能把搜索耗尽当作关卡无解，也不保证其他所有回合立即可解。

## 回归检查

fixture 为 `tools/platforms4hard-regression.json`，浏览器检查函数为 `tools/oracle-regression.js`。在 seed42、对应原版 oracle 页面通过 CUA CDP 载入脚本，执行 `runOracleRegression(fixture, 'clearance')` 会报 `Original-engine regression: {"policy":"clearance","status":"no_candidate","frame":104}`；执行 `runOracleRegression(fixture, 'support')` 找到278帧剩余路线，并独立回放完整438帧无伤。

机器可读回归证据：`tools/real-game/platforms4hard-regression-20261005.json`。`git diff --check` 已通过。

## 从零解算与正常速度验收

正式新策略从第0帧重新搜索，未预置安全前缀：beam24、segment8、margin0，438帧，累计66641.4ms（60秒预算后续算）。独立原版加速回放无伤。

候选ID：`68f2729cbbd0f351ec9eb592f203a1d3c40b3303689c0487d87a43434a56f7b7`。

独立正常速度页面已连续完成三回合：每回合HP92不变、KR0、零受击、原版EndAttack，服务器成功校验并提升为默认路线、更新覆盖矩阵。完整实时轨迹为 `tools/real-game/bonesgap1-20261005-134500-678140.json`；截图为 `tools/real-game/platforms4hard-20261005.png`。

直接打开会自动触发TAS，连续三回合后暂停：

`http://127.0.0.1:8102/game/index.html?mode=single&attack=sans_platforms4hard&seed=42&acceptance=1&continuous=1`

服务端口8102，重启命令 `.venv/Scripts/python.exe start_dashboard.py 8102`。目前原版完整冷解算仍需几十秒，不能宣称达到毫秒级。
