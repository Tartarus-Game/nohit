# Real HELL：续算与原生开场验证

2026-10-06。本轮是进展，不是 Real HELL 完成验收。原版 Normal seed42 完整无伤证据保持独立。

## 已实现的数学执行改进

`resumable_wave.py` 提供真正可恢复的逐 tick 环境算子。目标采样在扣除指令延迟及提交副作用前暂停；供给目标后完成同一 tick。它保留加载参数、时钟、RNG、场地、活跃对象和本 tick 事务状态，不调用旧 `TimelineVM.run`，也不调用原生引擎搜索。

参数环境与参数 DAG 已默认使用 resumable；reference 编译器保留作显式差分对照。116 项相关测试通过，包括逐位环境对照、暂停分叉、多个同 tick 目标、目标目的键、回调、时钟及完整微型路线回放。公开结果的 `environment_backend` 和 `environment_work` 可核查实际使用的路径。

32 次目标采样基准中，环境执行从 2049 tick /1122 条指令减少到 145 tick /66 条指令，结果数组与历史完全一致。145 包括113个提交tick及32个未提交采样预览。小案例墙钟约35.9ms→42.3ms，尚无整体提速：兼容收集器仍复制完整前缀矩阵，逐步克隆也有成本。见 `../scratch/resume-benchmark-results.json`。

独立 `dialogue_operator.py` 已实现并通过11项测试：UTF-16字符数，每tick最多一字，Confirm/Cancel边沿及源码顺序。它还没有耦合进环境和搜索；Real HELL 的中途对话仍返回未知边界，不能忽略或直接跳过。

## 原版 Custom attack 入口验证

必须从原版主菜单 Custom attack→Load file→Run attack 载入文件。`mode=single&attack=sans_realhell_extreme` 不在原版字典中，会回退普通流程，不能作 Real HELL 起点。

原CSV字节SHA256为 `3b6252bc2d97a6ae5f82d63b8c8e82175cf1d819e85728e2f1fe9b1001106299`。原生AJAX读取会将CRLF规范化成LF，传入TLPlay的302906字节文本SHA256为 `2e095125881c1af9ba1cfc37c94c44b5527bd7243217f1284061cf9a1132045f`，与原文件仅换行规范化后的内容一致。原生Array宽度为7366（包含末尾空行），不是修改了7365条源行。

发现实际浏览器兼容问题：源第3行Sound要求音频20倍速，Chromium的HTMLMediaElement拒绝该值并中断原生tick。新增 `audio_compat.js` 仅在custom_acceptance=1或audio_compat=1时处理原生NotSupportedError，并记录请求20、实际16。原事件表没有音频完成/进度驱动攻击或Timeline的逻辑，此变更只影响声音表现；CSV、runtime、data没有修改。5项音频及4项观察器测试通过。异常中断的旧运行已丢弃，未恢复为成功证据。

新运行使用原版文件入口，成功暂停在真实custom开场。它没有指定seed，因此不能当作seed42整局；已核查本次前160tick尚无RND，足以独立验证初始化与开场几何。

## 开场相位证据

原生TLPlay入口前arena为 `[32,240,608,384]`，第一条指令设目标 `[241,226,406,391]`，HeartTeleport把323.5/308.5按原版int变为323/308。首次完整tick后arena已经移动2px。

因此数学初始化需要入口前环境，以及首tick后的角色初态；不能把已缩过一次的arena再当作执行源第0tick之前的环境。采用这一相位约定后，采集的82个原生快照中，完整玩家状态、arena、dt和白色矩形集合全部逐位相等。矩形集合比较保留重数，只排序消除原生按水平/竖直类型分组的观察顺序差异；没有容差或坐标舍入。

证据：

- `../tools/real-game/bonesgap1-20261006-142340-668370.json`：初始状态、tick80状态和tick81–160的80个连续原生记录，线性输入，无分支/恢复。最初1–79tick没有逐tick保存，不能据此主张完整逐tick验收。
- `../scratch/validate_realhell_initial_phase.py`：独立复算脚本。
- `../scratch/realhell-initial-phase-verdict.json`：82快照比较结果，passed=true，full_wave_no_hit=false。
- `../tools/real-game/bonesgap1-20261006-143745-044914.png`：诊断截图，非通关画面。

## 原谱搜索压力测试与下一步

从已验证相位构造seed42数学初态，在原谱上设置18845物理tick编译预算及20000搜索状态预算，未修改攻击脚本。实际使用resumable；首次目标在约78.48秒，根环境提交18835tick、预览1tick。

结果为resource_limit：20000个状态、19999次展开，只到最深tick1496（约6.23秒），总墙钟约123秒。未证明无解，也没有得到整段可回放候选。结果保存在 `../scratch/realhell-opening-probe-result.json`。

这表明当前瓶颈还包括已知静态环境中的搜索，而不是仅有历史重复编译。下一步应针对这个可复现案例分析时间展开DAG的状态增长、搜索排序和控制时间分辨率；当前每4个物理tick才换键，尚未覆盖240Hz的全部合法输入时刻。不能通过增大碰撞容差、丢弃候选或修改原攻击来掩盖困难。

同时仍需消除前缀矩阵复制、耦合对话与Confirm、让播放器消费EOF尾部证据，最后进行明确seed42的新原版完整运行。旧Normal通关页仍保留，custom诊断页暂停在前160tick。

8103服务已重启以加载默认resumable；当前PID14376，日志 `../scratch/resumable-server.log` / `.err`。
