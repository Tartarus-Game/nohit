# 自制 CSV 清单与后续验证队列（2026-10-07）

`自制sans战套餐v2.0[已完结}` 下共有 **17 个非空、可由当前原版式 tokenizer 读取的 CSV**：13 个章节关卡、4 个辅助草稿。原始字节去重和原版 token 序列去重均为 17；没有需要合并的重复文件。此处“可读取”不代表命令语义已验证，更不代表存在无伤解。

本轮仅读取文件、已有报告、原生证据和执行静态入口审计，没有运行求解、游戏或编译完整弹幕。完整路径、字节数、两种哈希、各命令计数和逐行静态问题保存在 [清单 JSON](../scratch/custom-csv-inventory-20261007.json)，其 SHA256 为 `9d272bea1cee771579b4ccd6d698b7edf2033384275cf9b938c1429eaaa10a0b`。

## 数量与去重口径

| 口径 | 数量 |
| --- | ---: |
| 非空 `.csv` 文件 | 17 |
| 章节关卡 / 辅助测试草稿 | 13 / 4 |
| 原始文件 SHA256 唯一值 | 17 |
| 原版 token 序列 SHA256 唯一值 | 17 |
| 含 SansText 的文件 | 11 |
| 含 GetHeartPos 的文件 | 8 |
| 有显式 EndAttack 的文件 | 2 |
| 当前 `solve_csv` 默认静态审计无问题 | 1 |
| 仅切换静态检查为 EOF 策略后无问题 | 14 |

主去重键为原文件字节 SHA256。辅助 token 键严格使用 `read_timeline_rows`：UTF-8 BOM 解码、CRLF 转 LF、按换行再按逗号切分；序列化全部行/单元格后哈希。没有按标准 RFC CSV 处理引号，没有折叠大小写、删除空参数或排序指令。两种键在本目录都没有重复组，也未与 `welcome_to_hell.csv`、`Real HELL 困难模式(1).csv` 或 `repo_jcw87/Files` 的原版 CSV 发生原始字节重复。

## 当前静态入口的四类队列

`solve_csv` 当前调用 `model_issues(..., allow_player_history=True)`，默认要求显式 `EndAttack`。15 个文件缺少该命令，其中 2 个还有其他命令审查问题。低层虽然存在 `eof_hazards_drained` 路径，当前共享 CSV 入口并未暴露该终止策略；把静态检查切成 EOF 后没有问题，也不等于已证明尾段安全或原版完成。

| 队列 | 数量 | 所需下一步 |
| --- | ---: | --- |
| 可直接进入当前入口的新求解 | 1 | Part4：捕获真实初态/时钟，fresh solve，标量重放，再原版完整验收 |
| 仅缺 EOF 完成协议 | 13 | 明确原版 Custom EOF 的完成标准，再接入/验证终止链；不直接给 CSV 补 EndAttack |
| 命令审查与 EOF 协议 | 2 | Part1、Part2 首行 `mus_zz_megalovania` 位于命令列，当前未验证；同时没有 EndAttack |
| 命令审查 | 1 | 特殊分支①的 10 处 `Score` 当前未验证；文件已有 EndAttack |

未验证命令不应直接叫作语法错误。后续[原版源审计](custom-command-eof-source-audit-20261007.md)已确认 `Score` 与 `mus_zz_megalovania` 在此次原版中没有匹配函数，因此函数调用没有事件动作，行延迟与行号推进仍照常执行。尚未修改共享入口支持，所以本表仍保留原静态队列；不能把审计结论当作已完成求解或验收。

以下均相对套餐根目录；完整绝对路径见清单 JSON。`D/T` 分别为 SansText / GetHeartPos 指令数，只表示结构复杂度，不是执行次数或难度证明。

| 文件 | D/T | 当前队列 | 原始 SHA256 前12位 |
| --- | ---: | --- | --- |
| 第一章——相遇/特殊的Sans战 Part1.csv | 11/0 | 命令 + EOF | `9ecb8be1d430` |
| 第一章——相遇/特殊的sans战 Part2.csv | 8/0 | 命令 + EOF | `f415587c000b` |
| 第一章——相遇/特殊的sans战 Part3.csv | 9/0 | EOF | `9541459028bd` |
| 第二章——坚持/特殊的sans战 Part4.csv | 4/1 | 可进入当前入口 | `5ff983750eac` |
| 第二章——坚持/特殊的sans战 Part5.csv | 6/1 | EOF | `c1b4838f66cb` |
| 第三章——勇气/特殊的sans战 特殊分支①.csv | 2/0 | Score 命令 | `211be9878e22` |
| 第三章——勇气/特殊的sans战 特殊分支②.csv | 6/0 | EOF | `af745d4f922a` |
| 第三章——勇气/特殊的sans战 特殊分支③.csv | 7/41 | EOF | `fcccaf46fb01` |
| 第四章——回忆/特殊的sans战 THE RUINS.csv | 0/0 | EOF | `ff3c5a785f7b` |
| 第四章——回忆/特殊的sans战 THE SNOWDIN.csv | 0/11 | EOF | `bdae958ac138` |
| 第四章——回忆/特殊的sans战 THE WATERFALL.csv | 0/81 | EOF | `65faa2dfc440` |
| 第四章——回忆/特殊的sans战 THE HOT.csv | 0/8 | EOF | `9bbae16d26a0` |
| 第五章——再见/特殊的sans战 h e l l.csv | 7/179 | EOF | `fa221a137659` |
| 一些UP需要用的东西/测试.csv | 1/0 | EOF 辅助草稿 | `1a4406db2312` |
| 一些UP需要用的东西/新新测试（研究官方攻击专用）.csv | 0/0 | EOF 辅助草稿 | `810bbd0647c5` |
| 一些UP需要用的东西/测测测！试.csv | 0/0 | EOF 辅助草稿 | `9a0c94b547cc` |
| 一些UP需要用的东西/新测试.csv | 4/47 | EOF 辅助草稿 | `37c0b7fa7704` |

检索现有 docs、scratch 报告/摘要/验收结果以及 tools 记录后，**未找到这 17 个文件的完整源模型候选或完整原版无伤验收报告**。这是一项“尚未找到可信记录”的清单状态，不是对可解性的判断。辅助文件不会被悄悄排除出 17 个文件总数；章节覆盖的分母另外记为 13。

## 可复用的既有证据

- [原版24 CSV历史30 Hz批量报告](../scratch/original-csv-corpus-20261007/REPORT.md)：22/24 个源模型候选，全部原版通过标志仍为 false。两个 unknown 是当时的 Intro 对话边界与 BoneStab3 限宽前沿。这是旧实现的探索性结果，不能代表本套餐或当前实现已完成批量验收。
- [welcome_to_hell 完整验证记录](welcome-solver-performance-20261007.md)：已有两次独立新 Custom 入口、30 Hz 原版完整无伤证据，包括真实对话与 EndAttack。它不在本套餐中，字节哈希也不相同。
- [Normal 旧版完整战役记录](full-game-progress-20261006.md)：2026-10-06 的固定240 Hz原版 Normal 已有24回合完整通过。该文已标注历史版本，不替代后续共享 CSV 链路或本次新代码的验收。
- [共享 CSV 链路的历史前缀](normal-csv-native-20261007.md)：早期运行独立确认23轮、55306连续原生tick无伤，Final当时未决；随后8143新 Normal在Final frame5950受伤，见 [负角度取整差异审计](final-native-geometry-audit-20261007.md)。修正原版整数语义后，8144的[新完整 Normal 记录](../tools/real-game/bonesgap1-20261007-091242-917789.json)已完成24轮、68243连续原生tick无伤并到达Win2，清单 `result.passed=true`，主任务独立校验通过；同tick终局事件归属见[审计](campaign-terminal-event-audit-20261007.md)。这是共享 CSV 链路的新完整证据，不是本套餐17个文件的覆盖率。本套餐仍无新的完整验收记录。

这些记录应继续保留各自的 CSV hash、初态、时钟、实现版本和证据等级，不能只按文件名把历史通过迁移给新候选。

## Normal 之外的 PlatformBlasterFast

最有力的现有单关原版记录是 [bonesgap1-20261006-043823-339916.json](../tools/real-game/bonesgap1-20261006-043823-339916.json)，文件 SHA256 为 `9fae1d2f961a56425b23693f4fc325fea365d23a430cc9cf80b6b275dcfd8a8f`。本轮只读重查了其原始行：

- seed42；`original-runtime-fixed-240hz`；504 个控制输入，每个保持4个微 tick。
- 2016 行连续原生记录，tick75..2090，全部 HP92/KR0；每行输入都等于对应计划，全部为 Single 允许的 0..15，未使用 Cancel。
- 从捕获起始时间戳逐次加 `1000/240`，2016个记录时间戳全部精确相同。
- 原版 `EndAttack` 事件在 tick2089，最后提交行 `ended=true`；记录 `status=end_attack`、`total_hits=0`。
- 记录中的 CSV hash 与当前源文件一致：`0312ef3aec4f170844e72a7cef4cf8b30f41a6c1703489cb8dcf64506f10e35a`。

这是可信的**历史单次原版无伤执行证据**；记录自身 `realtime_accepted=false`，不能称实时连续三回合通过，也不是当前共享 CSV/API 驱动的新鲜验收。候选 [platformblasterfast-native-single-candidate.json](../scratch/platformblasterfast-native-single-candidate.json) 为旧 `canonical-dag-dp` 生成，候选自身的原版标志为 false；外部原生记录才是上述通过证据。

另有 [30 Hz源模型候选](../scratch/original-csv-corpus-20261007/results/sans_platformblasterfast.json)：252个输入、8.4模型秒、约1.105秒历史总耗时，`verified=true`，但 `original_replay_passed=false`。不要把240 Hz旧原版结果当作这条30 Hz候选的原版验收。

后续具体执行顺序：先在当前共享 CSV入口重新验收 PlatformBlasterFast，再做唯一静态就绪的 Part4；按已完成的源审计接入两个已知无动作函数。EOF 完成标准及现有证书边界见[源审计](custom-command-eof-source-audit-20261007.md)；补齐共享入口与原版证书协议后，先用辅助 `测试.csv` 和无目标读取的 THE RUINS 分别覆盖对话/平台尾段，再推进其余 EOF 关卡；每个结果分别保存模型候选、原版完整通过或明确 unknown/unsupported，不把静态入口通过记为解算完成。
