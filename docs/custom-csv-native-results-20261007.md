# 自制套餐当前原版验收结果

2026-10-07，原始17份CSV中已有4份获得本次完整原版无伤证据。结果绑定于
`scratch/dialogue-target-continuation-20261007/accepted-8150-source/`：每条请求的64个
实现文件SHA256均与保存版本一致。后续源码修改不能自动继承这些版本的验收结论。

| CSV | 输入 / 连续HP92、KR0帧 | 精确匹配状态分量 | API计算 / 游戏秒 | 原版终点 |
| --- | ---: | ---: | ---: | --- |
| 特殊的sans战 Part4 | 3121 / 3122 | 34331（非终帧） | 62.7771 / 104.0333 | 真实EndAttack及菜单 |
| 测测测！试 | 636 / 637 | 7007（含终帧） | 0.8969 / 21.2 | EOF释放按键永久安全 |
| 新新测试（研究官方攻击专用） | 3363 / 3364 | 37004（含终帧） | 3.5010 / 112.1 | EOF释放按键永久安全 |
| 特殊的sans战 THE HOT | 2786 / 2787 | 30657（含终帧） | 36.7040 / 92.8667 | EOF释放按键永久安全 |

三条EOF样本没有执行EndAttack，`complete_in_original_game=false`；验收证明的是
实际CSV执行后弹幕已消失、没有未处理的危险生命周期，继续释放按键永远安全。
没有合成终点、清除原生弹幕、恢复血量或纠正玩家状态。

THE HOT宽度300首轮在680帧前沿变空，返回unknown，API计算2.8654250秒。
从未改变的实际原生起点重试width1000，API计算36.7040443秒后获得已验收路线；
两次合计39.5694693秒。这个真实反例说明有限宽度前沿为空不等价于原问题无解。
Part4此前失败调试成本另见 `part4-attempts.json`，已知累计下界220.5058189秒，
超过本回合时长；不能把最近单次热请求的速度写成累计重试目标已达成。

这里的API计算包括模型构建、搜索、模型验证和可视化重建，但计时结束于返回Python
对象，**不包含HTTP JSON序列化、传输和浏览器JSON解析**。另存的THE HOT原生浏览器
ResourceTiming显示两次响应读取耗时2.8973和40.6692秒，合计43.5665秒；成功响应
187442140字节。ResourceTiming仍不包含随后JSON解析及候选安装的全部工作。下一步
需要完整记录请求准备到候选就绪的时长，避免把局部性能统计当成端到端保证。

机器可读索引：
`scratch/dialogue-target-continuation-20261007/corpus-native-results.json`。
每条记录均关联原始CSV哈希、请求ID、源快照、原版录制和正式独立验收结果。

| CSV | 原版证据（tools/real-game/） | 正式验收（scratch/dialogue-target-continuation-20261007/） |
| --- | --- | --- |
| Part4 | bonesgap1-20261007-143822-383254.json | part4-corrected-native-verdict.json |
| 测测测！试 | bonesgap1-20261007-144507-986330.json | corpus-short-eof-native-verdict.json |
| 新新测试 | bonesgap1-20261007-144931-583470.json | corpus-blue-eof-native-verdict.json |
| THE HOT | bonesgap1-20261007-145808-614516.json | corpus-hot-eof-native-verdict.json |

Part4及THE HOT原始录制分别以7和96个内容寻址分片保存，所有分片及总SHA256已校验；
展开后的原始字节保持不变。Part4另有不导入求解器/验收器的独立Node审计，3328项
检查通过。截图在同scratch目录的 `part4-corrected-native.png`、
`corpus-short-eof-native.png`、`corpus-blue-eof-native.png`、`corpus-hot-eof-native.png`。

其余13份套餐CSV尚未完成原版验收；任意CSV缺参调度、橙色骨头模型支持、残留平台的
EOF证明、最小实际扣血搜索以及全部回合累计计算快于游戏的目标仍未完成。
