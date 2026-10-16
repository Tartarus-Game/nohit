# 当前项目与历史恢复

当前分支 `codex/latest-only` 保留 CSV 真机链路和最新通用 Live SDK。

## 两条运行链路

CSV：`start_dashboard.py` → Dashboard CSV API → 源时间线与 C++ 原生前沿 → 模型及独立标量复验 → Construct 2 原游戏逐 tick 执行 → 独立证据验收。Normal 使用同一求解核心连续推进原游戏回合。

通用 SDK：`generic-engine/tools/nohit.py` → Godot 3/4 Live adapter → 原引擎真实帧 → 新进程回放与伤害反例。它保留原游戏输入、心魂、物理、伤害与结束信号；不要求完整世界快照。GameMaker 保留协议模板，尚未通过原生运行验收。

求解器只缓存编译代码，不缓存可冒充新求解的路线。运行证据、编译缓存和临时目录统一放在 `build/`。

## 本次移除

- 第一代 baker / common / verifier、旧 DP / bitmap / calibration / fallback 求解分支及其专用测试。
- 旧 Dashboard 页面、旧求解与 benchmark / TAS / coverage API、旧浏览器 planner。
- 重复游戏导出、临时 Real HELL 页面、研究探针、历史算法副本和一次性脚本。
- 通用引擎的旧 snapshot demo、独立 GameMaker 原型、样本批量扫描与研究输出。
- 大量阶段报告、历史日志、浏览器资料和运行中间产物。

保留源碰撞和时钟审计、当前 CSV 使用文档、精选 Real HELL 验收证据，以及通用 SDK 当前适配器需要的原生几何辅助代码。

## 恢复历史

历史快照分支：`codex/history-before-cleanup-20261017`，提交 `4a5609d`。
它保存精简前的源文件、必要的游戏素材、攻击包与 Real HELL 证据。

查看某个历史文件：

```powershell
git show codex/history-before-cleanup-20261017:path/to/file
```

需要运行旧版时，可为该分支另建 checkout，避免把旧文件混回当前分支。

未提交的大体积本机缓存、历史实验和重复资料移到仓库外：
`C:/Users/lf/Documents/Workspace/nohit-history-20261017/`。
移动清单位于其中的 `moved-manifest.json`、`retired-source/moved-root-manifest.json` 和 `cleanup-final-manifest.json`。这些本机文件不属于可移植源码，恢复旧分支不会自动恢复它们。

## 结果范围

模型候选、独立模型复验与真机通过分别报告。有限搜索失败只能报告 `unknown`。
EOF 也必须满足完成证明，不能以任意一段无伤存活代替攻击结束。
Real HELL 削弱版通过的是记录修改项的测试副本；困难最终版仍无整谱通过结论。

已知基线差异：`test_native_platformblaster_regression.py` 的失败路线在原游戏 tick 1151 受伤，模型碰撞回放尚未复现。该差异在历史提交 `4a5609d` 已存在，保留为 strict xfail；同一记录的 73 个运动采样仍逐 bit 通过。原游戏伤害验收继续严格拒绝受伤路线。

本机没有 Godot 可执行文件，本次验证覆盖 SDK 安装、静态契约、历史证据故障注入和独立打包；原生 Godot 验收记录保留原版本身份，未声称本次重新运行。

## 精简后验证（2026-10-17）

全部 Python 测试 1306 通过、上述 1 项 strict xfail；JS 契约及原游戏启动检查 245 通过。通用 SDK 的证据故障注入 / 解包器共 13 项通过，另完成 8 组安装检查与独立 ZIP 清单校验。

最终代码在浏览器中自动求解并执行 BoneGap1：206 次输入、207 个连续原生 HP/KR 观察，HP 92 / KR 0，战斗状态精确一致，原生 EndAttack 完成，独立验收通过。本机记录位于 `build/cleanup-smoke/`。

精简前后源码及精选资料由 2511 个文件、约 128 MB，降至约 514 个文件、22 MB；不含 `.git`、虚拟环境和生成目录。2159 个历史路径从当前分支移除，约 8.5 GB 本机历史资料移到仓库外归档。
