# nohit 新计算模式交接 — 2026-10-05

## 接手目标与当前结论

用户要求根据报告实现新的计算模式、优化冷处理/预烘焙、覆盖原版回合，并由正常速度的原版游戏验证。用户最后明确要求先 handoff 给他人；本次只整理交接，不继续实施或新开任务。

当前只有 Platforms4Hard 的纯计算切片。已有完整候选路线和固定步长原版回放成功记录，但最新正常时钟验收失败；还没有稳定连续三轮无伤，也没有全流程1秒/毫秒级，更没有所有原版回合的新内核覆盖。请直接继续实现，不把此状态包装成完成。

工作目录：<repo>；PowerShell；运行器 .venv/Scripts/python.exe。
原始报告：<user>/.codex/attachments/dc2d99b1-9893-4609-baaa-45f02538e998/已粘贴的文本.txt。

用户核心约束：所有回合都按有解处理，算不出意味着模型/算法/资源问题。新核求解不能重新退回 C2 快照分支搜索或读取已有路线当答案。原版只能用于校准、差分、回放、实机验收。不要修改 HP/KR、位置或正常游戏 dt 来取得通过。冷首次求解、机器码加载/编译、环境预处理、搜索、回放必须分开计时。

## 先读这些现有产物

以下相对路径均相对于上述工作目录，文档已有的细节不在这里重复：

- docs/new-compute-implementation.md：新模式设计和验证要求。
- docs/new-compute-platforms4hard.md：切片实施记录。注意它的三初态/15字段、200万死状态和4.2秒默认计时已经落后于当前工作树，不能当最新事实。
- README.md 与能力 manifest：当前入口与范围声明；新核稳定验收列表应保持空，直到真实通过。
- nohit/engine/compact_platform.py：纯 Python 微步参考。
- nohit/engine/compact_wave.py：审核 CSV 编译和 Python/Numba 碰撞位掩码两版。
- nohit/engine/compact_lattice.py：Numba 精确状态搜索与乘积微步。
- nohit/engine/compact_solver.py：新核 API/阶段计时。
- tools/solve_compact_platforms.py：可独立运行的 CLI。
- nohit/dashboard/server.py：compute=compact 显式新核接口；不支持的机制返回 unsupported_mechanism。
- tests/fixtures/platforms4hard-clock.json：仅时钟和初态，无路线；完整差分测试另用 platforms4hard-microsteps.json。
- tools/real-game/platforms4hard-environment-capture.json：原版环境捕获，用于差分。
- tools/operator-results/compact-collision-ab.json：Python vs native 掩码约332ms vs6–7ms，逐位相同，不能冒称全求解计时。

## Git 与尚未提交的工作

main，无远端。最近提交：a7c67ec（规范），d185dc4（纯核第一版及诚实验收边界），969fc47（新文件 LF）。

当前工作树修改但未提交：

- c2-sans-fight/index.html
- c2-sans-fight/tas_runner.js
- docs/new-compute-platforms4hard.md
- nohit/engine/compact_lattice.py
- nohit/engine/compact_solver.py
- tests/unit/test_compact_platform.py
- tools/operator-results/compact-platforms4hard.json
- tools/solve_compact_platforms.py

另有许多实验路线、候选和实机 traces 未跟踪；不要 git clean 或批量删除。特别保留本次开始之前用户已存在的这三项：

- tools/oracle-plans/sans_boneslidev-42-candidate-4a4067bbbd9a41efc013da5501b904b31899b485ca362554c2bbbe74401421bb.json
- tools/real-game/bonesgap1-20261005-022456-549786.json
- tools/real-game/bonesgap1-20261005-022526-142229.json

pytest-of-lf/ 是测试临时目录，之前自动审批拒绝删除，只给出 blocked by policy；已告知用户并保留，勿重复绕过。tools/test-temp-compact-final/ 是最后单元测试临时目录。

## 当前实现与上一提交之间的重要变化

1. 搜索状态由单初态5字段扩大为9个样本的45字段乘积：三个初速58.5/0.75/0 × 三种平衡微步时钟。每个候选按键同时推进全部成员，任一成员碰撞即拒绝；哈希碰撞比较全部字段和层数。不是连续时间/连续初态区间保证。
2. product_micro_into 按 (member//15)%3 选择时钟，后两种 profile 使用4.1/4.2ms组合并平衡四步总时长。环境仍使用共同名义时钟表，因此这只是样本实验，并未严格覆盖实际环境时钟扰动。
3. 完整六动作 DFS，没有 beam、速度分箱或取整。只把全部后继失败的状态记失败；默认1000万展开、400万失败状态。内存需求显著增加（400万×45×8约1.44GB虚拟存储，另有哈希表等）。未实现续算/落盘/资源恢复；资源耗尽不是无解。
4. TAS 对 compact planner 使用严格原按键，取消原来 P 横向补偿。固定每个控制帧4个原版 tick，取消对脚本 T 的3/4/5步补偿。此处没有改游戏 dt，故真实 dt 扰动仍可导致路线偏差。
5. 路线获取完成前等待，再创建原版 runtime；candidate URL 同样等待，避免准备动画开始时路线尚未到。
6. **已定位并修复提前开始**：TLPlay 同时用于准备动画，直接 arm 会让正式回合开始时 planned=10。当前 flag 等待 post-tick 的真实心脏 x175/y327、Timeline.Running 后才 arm（此门禁只针对当前审核的 Platforms4Hard 切片）。最新记录正式回合 planned=0，说明这次修复有效。务必继续审计所有轮次的 reset/end 分支。
7. 最近尝试的中心追踪预测/全成员最大位置评分导致默认与大余量均资源耗尽，已经撤销。当前恢复第一成员平台距离评分与中性预测，但预测本身推进并检查全部乘积成员。当前生成的最新路线与之前 fa2 候选未必相同。

## 最新实机反例：接手应优先分析

最新实机完整记录：tools/real-game/bonesgap1-20261005-162944-887427.json。
结果 passed=false，complete_rounds=3，三次均观察到原版 EndAttack；HP92→81→75→75，hits分别11/6/0。第三轮无新增受击不等于连续三轮无伤。

此记录用的是**较早9成员路线** tools/operator-results/compact-product-clock.json，其候选：
fa2d81679b9884c1e053c82f9269b858a0ccad1aff684e4f91d7248b7d1dc2fa。
固定步长原版回放成功证据：tools/real-game/platforms4hard-compact-clock-replay.json。

最新记录首轮最早受击 tick350，T1.2417，planned73，x281.6200，y322.741883，dy-3.342，碰到 x283 的纵骨头。模型名义轨迹 frame73 x275.5/y322.7391；大约6–8px横向偏差，纵向几乎一致。planned是执行后加一，比较时要精确对齐前/后状态。
首轮 teleport 后 dy60.048，模型初态58.5。后两轮 teleport 后 dy约0.738、0.774。由 landing/support 与浮点分段边界产生的微小时间差可能累积成横向偏差；这仍是待进一步差分的解释，不是已证明根因。
第一轮第30帧附近实际 x219.019，对应名义 x211.25；后续维持约8px偏差。支持行为/携带速度应在真实逐 tick dt 下重演，而不是靠增加若干经验 profile 宣称保证。
第二轮首次受击 planned37，x220.324/y327.95。查看该轮 rows 与 hazards。

此前失败记录：162057-407686 和161045-672167（都是相同前缀 tools/real-game/bonesgap1-20261005-），正式 T0 时planned10，不能用于判定新相位修复后模型性能。
早期低余量曾有三轮通过，但用了旧控制器补偿/时钟且后续产生反例，不是当前严格控制器的稳定证明。旧默认参照路线已经恢复，不要以早期自动晋升的缓存结果冒充新核。

## 最后完成的求解与测试（在用户中断后只检查结果，未继续实现）

独立 CLI 最后一次已正常结束，不再占用后台计算：
.venv/Scripts/python.exe tools/solve_compact_platforms.py --output tools/operator-results/compact-platforms4hard.json

最新输出 candidate_found，438动作，1,499,040展开；总 first_route_wall=88,909.37ms，其中search_including_load=87,753.93ms、CSV13.26ms、掩码101.68ms、重建1040.49ms；search/reconstruction=compiled，掩码=disk_build_cache。这是函数内首次路线时间，含 JIT、不是纯热搜索，也不含 Python 导入或游戏加载。**这条新路线尚未原版回放、尚未实机验证。** 当前默认已明显超过1秒，不要用旧单状态4.2秒替代。

tools/operator-results/compact-product-clock.json（旧预测排序）：9成员完整候选约16.94秒搜索/17.81秒函数总时长，2202477展开；只对应当时模型/顺序。
tools/operator-results/compact-robust-phase.json：margin_x10/margin_y3、中心预测试验，约47.70秒 resource_limit（4000116展开），没有动作。扩大余量并未解决。

最后单元测试命令：
.venv/Scripts/python.exe -m pytest tests/unit/test_compact_platform.py -q --basetemp tools/test-temp-compact-final
结果11 passed in15.17s；发生在撤销中心预测、恢复全乘积预测之前，之后未重跑。此前新核API测试通过的是较早版本，目前45字段最新版本未重跑集成。
接手应跑 tests/unit/test_dashboard_server.py::test_new_compact_full_wave_and_capability_gate，可能耗时较长。
旧仪表盘4项失败是旧英文标题/布尔死局断言与当前语义不符；不要为新核测试随意改掉原版无解语义。

## 运行中的服务与浏览器

- 8102：原服务保持运行，旧 unified exec session13531。不要随意杀掉用户原服务。
- 8103：最后已重启以加载当前 Python 工作树，session2517；命令 .venv/Scripts/python.exe start_dashboard.py 8103，ready608.7ms（这是服务器启动，不是新核首次解算）。
- 旧8103 session61172已 Ctrl-C。CLI72612已结束；unit51333也已结束。
- 浏览器仅使用 mcp__cua_repl 支持的接口/CDP，不用shell/Playwright独立程序做浏览器操作。
- IAB browser id2；tab13是 fa2 实机失败画面、自动暂停，tab12是8102 oracle校准页面，tab14是8103 compute=compact 冷入口旧实验画面。三页已 markHandoff，下一轮仍需标记要保留的页。勿关闭用户原有其他标签页。
- 实机URL：http://127.0.0.1:8103/game/index.html?mode=single&attack=sans_platforms4hard&seed=42&acceptance=1&continuous=1&candidate=fa2d81679b9884c1e053c82f9269b858a0ccad1aff684e4f91d7248b7d1dc2fa
- 冷新核入口：http://127.0.0.1:8103/game/index.html?mode=single&attack=sans_platforms4hard&seed=42&compute=compact&acceptance=1&continuous=1
冷入口会真实解算最新内核，无路线/环境命中；当前可能需要几十秒。不要与正常验收同时跑重CPU工作。

新会话先 await cua.rewriteDocumentation()，再按所需tab绑定。旧 REPL 名称可参考 compactLiveTab、compactCalibrationTab、compactFreshTab、compactProductLiveCdp，但新会话不要假设句柄存在。

原版接口为 window.EngineOracle（不是 __engineOracle）。校准页URL有 oracle=1，可 observe/initial/restore/replay。replay(actions)是原版固定时间戳240Hz验证，不能用于新核分支搜索。保存候选走 /api/oracle-plan，必须提供动作数+1的真实轨迹以及 ended/nohit等，不能伪造。正常页 __LIVE_ACC 保存 rows/hits/runs/result/saved，验收标准连续三次原版EndAttack且HP92/KR0/nohits；自动暂停结果。

## 建议接手顺序

1. 读规范、代码和当前 diff，确认45字段模型的样本范围与所有状态依赖。保留用户原文件，不先清理工作树。
2. 把最新实机162944的每tick按键、dt、平台几何送入纯微步做差分，先定位最早 dx/support/position 分歧；不要再拿平均60Hz轨迹直接猜。
3. 用真实起点/真实微步时钟校准输入相位、平台携带与边沿。选择可解释的时间误差/初态鲁棒建模，不盲目堆profile或删动作。
4. 最新compact-platforms4hard候选先做原版fixed-step验算，再在正常游戏单独跑三轮；失败保留反例，成功也重测新的冷入口。不要改HP/KR、原版正常dt或直接喂旧路线来通过。
5. 解算性能瓶颈现在是乘积搜索/预测，不是6ms位掩码。分开 JIT首编译、磁盘载入、预处理、热搜索。优化要有同一模型/资源/碰撞条件的对比，避免用缩小模型偷换速度。
6. 更新实施文档、manifest和证据摘要，恰当测试后显式提交相关文件。再扩展其它回合；当前没有全回合完成依据。

## Suggested skills

- diagnosing-bugs：定位实际tick模型分歧和性能回归。<user>/.agents/skills/diagnosing-bugs/SKILL.md
- computer-use:computer-use：原版浏览器实机验证，按会话实际技能目录读取（这轮路径 <user>/.codex/plugins/cache/openai-bundled/computer-use/26.930.31730/skills/computer-use/SKILL.md）。
- handoff：继续交接时使用。<user>/.agents/skills/handoff/SKILL.md
- code-review：仅用户要求review时再用，不要凭本交接自动开启额外分工。

用户希望自主推进、少问确认。此次仅明确授权handoff，未指定接收方或要求新建聊天；因此没有替用户发送消息或创建新任务。把本文件交给接手者即可。
