# SansText / RPGText 单阶段算子契约

实现位于 `nohit/engine/dialogue_operator.py`，对应原版 `RPGText.xml` 的事件顺序。现已通过显式逐 tick 输入接口耦合到 resumable Timeline/世界算子，并提供 opt-in ParametricEnvironment continuation；默认主搜索仍不枚举 Confirm。接口细节见 `docs/dialogue-controlled-environment-20261006.md`。尚未完成这一对话接口的原生差分验收。

## 状态与输入

`DialogueState` 保存文本原文、CurrentChar、文本自己的 T、Interactive、Timeout、EndFunc 和 alive。文本长度和截断使用 UTF-16 code unit，与 JavaScript 的 len/left 一致；空格也占字符。Real HELL 的两条文本长度分别为 9 和 46。文本 T 不能与 Timeline T 混为一谈。

`step_dialogue` 单独接收 Confirm、LastConfirm、Cancel、LastCancel。Confirm 来自 Z/Enter，是 VPad 的独立字段，当前 LRUD/Cancel 的 5 bit mask 没有包含它。MODE_SINGLE 的 Cancel 会退出关卡，外层必须继续限制其合法性；不能因为文本算子支持 Cancel 跳字，就把它加入单关合法搜索输入。

每阶段首先 `T += dt`。若尚有字符且 `T >= 1/30`，只递增一个字符并减去 `1/30`，不是 while，也不是直接计算显示字符总数。然后先检查 Confirm 上升沿和文本已全部显示，再检查 Cancel 上升沿。于是最后一个字符本阶段出现时可以由 Confirm 结束；未显示完时同时 Confirm+Cancel 只能显示全文。非交互文本在字符全部显示且 Timeout>0 时按 `min(dt,Timeout)` 递减，达到零才销毁。

销毁输出 opaque callback；纯算子不执行这个字符串。默认 EndSansText 的原版效果是销毁 SpeechBubble 并 TLResume。重复处理已销毁实例不重复产生回调。

## 调用阶段和后续耦合义务

Battle 事件 include 顺序是 InputManagement、Timeline、RPGText，然后后续玩家运动/攻击/场地事件；CustomMovement 行为阶段更早。Timeline 创建文本并 TLPause 之后，后续 RPGText 阶段仍运行，原生创建队列在事件边界刷入。因此新增文本在本 tick 的 RPGText 阶段就应累加文本 T。

原生销毁请求同步触发 OnDestroyed/EndFunc。RPGText 阶段中默认 EndSansText 恢复 Running 后，本 tick 的 Timeline 阶段已经过去，下一条 CSV 指令最早下一 tick 执行。Real HELL 的连续两行零延迟 SansText 因第一行的 TLPause 而顺序显示，不应在同一 Timeline 阶段合并。

NeedDialogue 接入必须保留：已消费/已加载的 Timeline 指令位置和残余 T、文本状态、Confirm/Cancel 上一状态、完整玩家状态、控制格点相位、精确 dt 时钟、所有仍活跃环境对象与计时器。暂停只影响 Timeline 指令推进，不影响重力、玩家位移、平台、骨头、激光、骨刺或场地 resize。不能以文本等待时长跳过整个物理世界，也不能在未知输入下直接假设对话立即完成。

本算子针对一个实例的 RPGText 阶段。耦合接口支持连续但不重叠的 SansText，已知 EndSansText/TLResume 回调；重叠实例显式拒绝，未知回调在当前 RPGText 相位停止，不发布假定其没有效果的后续世界帧。11 项单元测试覆盖纯算子；新增耦合及受控环境测试覆盖连续文本、真实输入边沿、目标采样、活跃物理世界和小图完整搜索。仍需原生时相差分验证。
