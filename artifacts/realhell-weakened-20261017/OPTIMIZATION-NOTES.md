# Real HELL 削弱版：原生求解加速记录（2026-10-17）

同一 60 Hz 浏览器入口最终走到 EndAttack：25805 次按键 / 25806 个状态，约430.08秒游戏时间。成功续跑使用已有安全前缀至16129 tick，耗34.90秒墙钟；独立原始 scalar 世界、物理、碰撞复验耗2.66秒，469次目标读取一致、0状态差异、0碰撞，并保留已真实执行的前4736次按键。此速度是有前缀的续跑，不是从零的冷启动测速。随后真实浏览器整谱无伤完成，见 [验收记录](README.md)。

可复现证据：

- [完整路线](route.json)、[独立复验](scalar-verification.json)、[原游戏记录](native-evidence.json)。
- 当时的局部续跑脚本和中间试验已移至仓库外归档的 `scratch/realhell-weakened-browser-continuation-20261017/`。

## 1. 先让最新 native 路径实际可用

原困难谱没有 EndAttack，原生调度直接拒绝 EOF hazard-drain 策略；末尾还有静止蓝骨，因此单纯等尾部不能保证drain。测试副本补15秒等待+EndAttack，原下载文件不改。缺KR的 DamagePlayer 会把KR变成NaN，须在已授权测试副本中明确处理并绑定同源hash。对削弱版去掉缺KR的回血行，严格要求全程HP/KR零损伤；原版无handler的三个拼写命令也换同delay空命令，记录精确diff。没有更改危险物参数或时间。

## 2. 静态长前缀一次生成，直接 C++ 搜索

首个GetHeartPos在约79秒，默认动态调度会多次从0生成这段世界。直接给ParametricEnvironment限定前缀tick，再把原样环境张量交给native_backend.search：8秒前缀仅0.482秒、20秒1.03秒、首个读取前4736tick只需4.56秒。前缀结果要明确标为诊断prefix，不能把截断边界当EndAttack。

## 3. 短段提交，保留前视与失败现场

使用已有 `_segmented_coupled` 的 `_chunk_ticks=480`，每段只提交实际安全、实际观测之前的部分；保留按键、trajectory、confirm、实际target_history与源行号。无前视的480tick贪心会在1920tick末态选进下一帧死路；preview120可推进到约340秒。宽度继续加大不如先改善边界选择。

已确认安全的旧前缀可以固定，先前向重建其世界，再从回退点搜索后缀。成功路线固定到16129tick；同时明确检查固定前4736动作和trace逐位不变，才能继续冻结的浏览器实例。回退能让新目标选择影响更早分支，避免从当前已陷死的末态重复搜索。

## 4. `preview_ticks` 并不是有效前视长度的唯一上限

原实现还有 `if preview_reads>8: break`。该谱八方向跟踪炮一组就连续执行8次GetHeartPos；因此preview120改preview480仍常在一组后停止，实际没有看到下一组。独立scratch将读取上限改128后能跨多组采样；局部试验从原20394推进到20452tick，证明此前340秒失败不是无解证据。

成功续跑设置是4 workers、width8192、chunk480、preview480、read上限128、默认无定向goal。脚本提供中心/四角共6种goal的短预算重试，但成功这次156个native调用全部第一次无goal就成功；不能把goal重试误写成已经验证的必要条件。

预览中的目标位置只是提案。每次真正GetHeartPos必须重新读取已提交物理状态，不能沿用前视猜测；最终仍需独立完整source replay和真实游戏前向验收。

## 5. 另一个待验证的短段边界问题

`_preview_ticks and committed_count>4` 会令1–4tick的短段完全跳过前视。在局部20448→20452的4tick提交中，该段被选为安全，下一段只有18个扩展就全死。值得进一步试验：短段也前视，或者合并相邻短段。此次成功路线保持生产条件不变，未验证这项改动的完整收益；`local_short_commit_unrun.py` 仅保留未运行提案，不能作为成功证据。

## 6. 必须保留的验收边界

源文件hash、精确dt序列、初态/arena、前置confirm、seed和按键都要绑定。CRLF原字节hash与浏览器规范化LF文本hash可以不同，必须记录对应关系。

独立目标记录器要在 `_supply_target_owned` 后记录 `state.supplied_target`：同tick先HeartTeleport再GetHeartPos时，实际采样会被前置传送坐标覆盖，记录原始sample_position会出现假的history不一致。独立验收也必须检查状态第10槽的slam碰撞伤害；成功路线该槽始终0，后段启用了slam damage，不能忽略它。

以上描述当时的实验版本。精简后的生产 CLI 已提供分窗、前视、读取上限、goal 重试与固定前缀参数，仍要求独立复验。本记录不构成普适完备性或最优性证明。
