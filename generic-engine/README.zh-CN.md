# 通用弹幕测试引擎：源码样本与可运行原型

## 快速接入自己的游戏（新入口）

优先使用 [Live SDK 快速接入说明](portable/QUICKSTART.zh-CN.md)。已有原生信号的
Godot 3/4 项目可只填一份 JSON 配置；复杂项目集中编辑一份 `nohit_adapter.gd`。
原心魂代码不需要搬进求解器，普通接入不要求世界快照；测试由原引擎真实推进。

```bash
python tools/nohit.py install /path/to/game
python tools/nohit.py doctor /path/to/game
python tools/nohit.py solve /path/to/game --godot /path/to/godot --output results/first --workers 4
```

命令从本目录运行。配置式安装使用 `install /path/to/game --config my-config.json`。
普通运行游戏时不会启动测试。新 API 与之前的快照桥并存，不依赖任何样本节点结构。
Godot 3.5.3 / 4.6.1 均通过原生接入、配置式接入和故障拒绝验收；
Megalo 原版 bonegap 也已使用这套公共运行器完成无伤路线、独立回放与受伤反例。
GameMaker 同协议模板仍未通过原生运行验收。

本轮从专用 C2/CSV 算子切换到“游戏侧原生执行 + 外部可替换搜索”。旧 nohit 求解器仍可独立运行；这里是新后端原型，没有把其他游戏的逻辑强行翻译成旧 CSV。

目前完成：23 个固定提交的 GitHub 仓库扫描，两个真实 PCK 解包，Godot 原生碰撞采样器、可替换心魂控制槽、场景测试节点、保存完整状态的有界搜索与确定性回放。GameMaker 提供碰撞烘焙、输入与伤害审计脚本草案。另已接入 meowjade 的真实 Godot 战斗场景：四组圆环组件测试通过原生执行与新进程逐帧回放，三个伤害反例正常扣血。

**尚未完成：全部 23 个项目的完整运行接入、各项目全部攻击／关卡无伤验收、GameMaker 编译运行、UndertaleMakerX 的 C#/JS 运行时快照、自动编辑任意发布包。** 协议示例与真实接入的证据分别保存；组件通过不代表这些上游游戏的完整关卡已被求解。

## 全样本尝试

本轮已检查全部 23 个固定仓库，新增 UNDOTALE 和 Megalo 原生接入，总计三个项目、六项无伤测试通过独立进程回放；八个 GameMaker 缺少运行时，其他项目的启动/伤害/编译阻塞逐一记录。见 [完整结果表](research/all-samples-report.zh-CN.md)。

## 实际上游弹幕接入

见 [meowjade 接入说明](integrations/meowjade/README.zh-CN.md)、[UNDOTALE](integrations/undotale/README.zh-CN.md) 和 [Megalo](integrations/megalo/README.zh-CN.md)。提供固定提交安装器、输入搜索、独立回放、逐帧 HP/KR 与伤害审计及受伤反例。完整 meowjade `default_attack` 共 28 次尝试均受伤，尚未解出；其他项目的实际运行接入结果见全样本报告。

## 直接运行

使用官方 Godot 4.3 或 4.6.1，导入 `godot/project.godot`，运行场景可看求解后的原生碰撞回放。

```bash
godot --path generic-engine/godot
godot --path generic-engine/godot -- --blue
godot --headless --path generic-engine/godot --script res://demo/test.gd
python generic-engine/tools/test_unpack_sample.py
```

只需复制 `godot/addons/nohit` 到自己的 Godot 项目，不依赖 Python、Numba 或原来的 C2 游戏。原型搜索使用 GDScript；没有把它宣传成最终的高性能搜索器。旧 C++ 搜索目前还不能直接吃任意引擎的状态。

## 两个接入位置

1. **心魂槽**：`demo/soul_controller.gd`。把自己的红心／蓝心原始推进代码放入 `step(state, mask, delta)`；保存速度、重力方向、平台 ID、跳跃阶段、按键上一帧等全部状态。示例位移代码仅供测试，不是任何上游项目的等价实现。
2. **游戏侧桥接脚本**：参考 `demo/host.gd`。场景放入 `NoHitBridge` 和 `NoHitTester` 节点，配置心魂脚本与 host。不同游戏的具体绑定集中在这一份 host 脚本。

| Host 方法 | 必须提供的行为 |
| --- | --- |
| `capture()` | 所有影响未来的玩家、弹幕、计时器、RNG、平台、HP/KR、输入锁存和伤害计数；值类型，不能共享可变 Node/Resource |
| `restore(snapshot)` | 完整恢复一条分支，包含弹幕生成／删除、随机状态及事件队列 |
| `advance(mask, delta, controller)` | 按原游戏顺序完成一帧：弹幕、心魂、碰撞与伤害；不可另增一次正常 `_physics_process` |
| `damage_count()` | 审计区间内累计伤害／KR 接触事件；累计值不能靠回血清零 |
| `finished()` | 原攻击确实结束；存活达到任意帧数不能替代攻击结束 |
| `actions()` | 游戏实际允许的输入集合，包含慢速、按下／释放锁存等 |
| `rank()` | 只用于预算内保留候选路线，不参与无伤判定 |

普通游戏通常没有完整 `restore`。这需要接入工作，不能靠粘贴一句脚本自动解决。Godot 的 `await`、Tween、Area 重叠列表和物理体内部状态也不是一个属性字典能全部恢复的。没有快照能力时，下一层应采用独立世界重启／真实物理帧回放，不能用手工调用 `_physics_process` 冒充整个引擎推进。

## 原生碰撞烘焙的边界

`native_baker.gd` 从 `CollisionObject2D` 的 shape owners 获取当前有效形状、完整世界变换与多形状，复制形状资源以冻结动画帧，调用 Godot 的 `Shape2D.collide`。不重写 SAT、多边形或像素碰撞算法。

这只是**几何层**。所属碰撞层、是否监测、碰撞例外、单向平台、伤害颜色、输入／速度判断、无敌与 KR、事件顺序都由原游戏 host 保留。实际游戏若使用 Area 缓存或自定义函数，最终验证必须使用同一物理帧和原伤害入口。不能把几何重叠直接当作所有项目的伤害结果。

`bake_samples` 输出每个采样点的原生重叠位图；它不是采样点之间区域的安全证明。当前原型搜索仍在每个候选上精确调用 host，不用粗网格排除路线。独立于玩家的弹幕才可共享按帧烘焙；追踪弹／脚本读取心魂的关卡要保留每条分支的世界状态。

## 结果级别

- `native_nohit`：当前仅 meowjade 适配器的孤立圆环波次，原生帧内无伤且攻击组件确实终结；`run_suite.py` 另以新进程精确核对整条路线，输出 `native_nohit_fresh_process`。此级别不外推到未接入项目。

- `verified_adapter_route`：候选路径在同一个 host 上重新执行，通过每帧完整状态 SHA-256 与累计伤害核对。仍需未改伤害规则的真实游戏独立回放。
- `replay_failed`：漏存状态／随机状态／执行顺序等造成回放不一致，拒绝通过。
- `unknown`：预算、宽度或时域不足，或候选耗尽；不宣称无解。
- `invalid_adapter`：接入点不完整。

`seconds` 目前限制搜索，初始化、烘焙与最终回放不包含在预算内。原型没有“任意游戏冷启动十秒”保证，也没有多核优化声明。

## 发布包检查与解包

```bash
python generic-engine/tools/unpack_sample.py game.pck --extract extracted --manifest unpack.json
python generic-engine/tools/unpack_sample.py game.zip --extract extracted
python generic-engine/tools/unpack_sample.py data.win --manifest chunks.json
```

支持未加密 Godot PCK v1/v2/v3、ZIP 提取及 GameMaker FORM chunk 目录。核对 PCK 自带 MD5／ZIP CRC，限制包体积与条目数，拒绝路径穿越、符号链接、重复文件及加密／未知标志。只检查字节，不执行下载的游戏。FORM 检查不等于 GML 反编译；EXE 内嵌 PCK、加密包、YYC 恢复尚未实现。

真实解包记录：`research/utmx-pack.json`（110 文件，4.6.1 PCK v3）；`research/undotale-pack.json`（263 文件，3.3.0 PCK v1）。旧包含 `.gdc`，本轮未反编译；新包包含可读 JS 心魂／攻击脚本。没有把他人完整素材复制到本交付包。

UDTale：已查看用户指定 GameJolt 页，确认存在 1.0.0／112 MB 的公开下载按钮。点击后，当前浏览器因不允许的 URL 协议阻止下载，未获得发行包，因此未识别它的引擎、未解包、未求解。不能用其他样本冒充 UDTale。

完整样本列表与接入优先级见 `research/sample-matrix.md`；源码定位及提交号见 `research/source-audit.json`。
