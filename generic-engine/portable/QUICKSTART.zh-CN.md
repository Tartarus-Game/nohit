# 把原游戏接入 NoHit

已有原生信号的项目只填 **一份配置文件**；其他项目把不同之处集中到
**`nohit_adapter.gd` 一份文件**。
直接使用原红心／蓝心控制代码、弹幕更新、碰撞与伤害规则。
不需要把心魂算法搬过来，不需要实现完整世界快照，也不需要 Python 第三方包。

当前已执行验证：Godot 3.5.3 与 4.6.1 的最小接入示例。
GameMaker 2.3+ 提供同协议脚本模板，尚未通过原生编译运行验收。
Python CLI 要求 Python 3.10+；Godot 使用你游戏对应的原生引擎可执行文件。

## Godot：安装、接线、运行

如果游戏已有伤害与攻击结束信号，先复制 `portable/config.example.json`，
填写节点路径、信号名、原攻击方法和要观察的属性，然后执行：

```bash
python tools/nohit.py install /path/to/your-game --config my-config.json
```

以后只需编辑游戏里的 `nohit_config.json`，不需要编写 GDScript。
路径 `.` 代表原主场景；也可填相对子节点或 `/root/自己的自动加载`。
属性 `position:x` 表示 Vector2 的 x 分量。
配置中的 `"$seed"` 会替换成测试种子；无参数攻击方法填写 `"start_arguments": []`。
`has_kr=false` 必须由开发者明确声明该游戏没有 KR 路径。
带 0–4 个参数的信号由通用中转函数审计；其他信号或复杂菜单初始化用下方脚本接入。
子 Viewport 游戏可设置 `input_viewport_path` 为实际接受输入的 Viewport 路径。

需要编写游戏特有逻辑时，使用脚本接入：

在本源码包的 `generic-engine` 目录执行：

```bash
python tools/nohit.py install /path/to/your-game
```

安装器自动区分 Godot 3/4，只复制 `addons/nohit_live` 和初始适配模板。
不会修改主场景、自动加载或心魂代码；再次安装保留你已经编辑的适配器。
Godot 编辑器无需启用插件。普通运行游戏时，这些文件不会启动测试。
Windows 路径包含空格时用双引号，例如 `"C:\My Game"`。

打开游戏目录里的 `nohit_adapter.gd`，完成三个连接：

| 连接 | 做什么 |
| --- | --- |
| 开始攻击 | `nohit_begin(seed)` 找到自己的战斗/心魂节点、设置随机种子、调用原攻击入口 |
| 审计与结束 | 原伤害入口接 `record_damage`，KR 接 `record_kr`，原攻击结束事件接 `mark_finished`；全部接好后 `enable_damage_audit()` |
| 逐帧观察 | `nohit_observe()` 返回坐标、速度、HP/KR、心魂模式等非空 JSON 字典 |

Godot 4 的完整最小接线示例：

```gdscript
extends "res://addons/nohit_live/adapter_base.gd"
var soul

func nohit_begin(attack_seed):
    soul = game.get_node("Battle/Soul") # 换成你游戏的节点路径
    soul.damaged.connect(record_damage) # 换成原游戏信号
    soul.kr_contact.connect(record_kr)  # 没有 KR 的游戏不需要这一项
    game.attack_finished.connect(mark_finished)
    enable_damage_audit()
    game.start_attack(attack_seed)      # 换成原攻击入口

func nohit_observe():
    return {"x": soul.position.x, "y": soul.position.y,
        "vx": soul.velocity.x, "vy": soul.velocity.y,
        "hp": soul.hp, "kr": soul.kr, "mode": soul.mode}
```

Godot 3 使用 `soul.connect("damaged", self, "record_damage")` 一类连接语法。
如果信号带多个参数，写一个对应签名的中转方法再调用 `record_damage()`。
若原游戏没有信号，可在原伤害函数插入调用，或继承原心魂类并在调用原函数前记录。
不能用只比较最终 HP 的办法代替累计审计，回血会掩盖受伤。

默认输入位是 1左、2右、4上/跳、8下，绑定 `ui_left/right/up/down`。
自己的 InputMap 名字不同时，在 `nohit_begin` 设置：

```gdscript
action_names = ["move_left", "move_right", "jump", "move_down", "slow"]
```

这样慢速键是 16。适配器同时向原 Viewport 发送边沿 `InputEventAction` 并更新轮询状态，
在 headless 模式也验证了 `_input` 和 `Input.is_action_pressed`。
子 Viewport 游戏在适配器设置 `input_viewport = soul.get_viewport()`。
直接读键盘扫描码/自定义输入表的游戏，应覆盖 `nohit_apply_input(mask)`，
把掩码交给 **原输入抽象**；保留按住、刚按下、刚释放语义和原运动顺序。
不要再次手动调用心魂 `_physics_process`。

启动测试前，主场景须允许先挂审计钩子、再开始攻击。原游戏若一进入场景便自动开打，
建议增加独立测试入口场景，并用 `--scene res://my_attack_fixture.tscn` 指定。
异步加载可覆盖 `nohit_is_ready()`；超时会明确拒绝接入。

```bash
python tools/nohit.py doctor /path/to/your-game
python tools/nohit.py solve /path/to/your-game --godot /path/to/godot --output results/first --workers 4
```

`doctor` 检查安装与配置；第一次原生运行进一步检查伤害审计、观察值与 InputMap。
`solve` 先尝试有限输入策略，再新进程回放候选，并执行受伤反例。
它不是能解所有弹幕的通用完备搜索器，策略耗尽输出 `unknown`。
每次输出使用新目录，保留原生日志、请求、逐帧结果与总结。

保存或提供自己的输入路线：

```json
{"route":[4,4,4,0,1,1,0]}
```

```bash
python tools/nohit.py verify /path/to/your-game --godot /path/to/godot --route route.json --output results/replay --control-route hit-route.json
```

默认受伤反例是静止路线。静止也安全的攻击，需要自己提供 **确实会撞弹幕** 的路线；
反例未受伤时输出 `control_failed`，不会把候选直接升级为验证通过。
`--max-ticks` 包括结束后的审计帧；超时不是攻击完成。
验证比较的是适配器导出的逐帧观察，不能冒充完整世界快照。

## 先运行随包示例

```bash
python tools/nohit.py install portable/examples/godot4
python tools/nohit.py solve portable/examples/godot4 --godot /path/to/godot4 --max-ticks 70 --output results/demo4
python tools/nohit.py install portable/examples/godot3
python tools/nohit.py solve portable/examples/godot3 --godot /path/to/godot3 --max-ticks 70 --output results/demo3
```

示例原游戏与适配器是不同文件，伤害发生在原游戏内，碰撞调用 Godot `Shape2D.collide`。
这两份是接入范例，不是上游弹幕或 Undertale 原版控制实现。

仅安装 SDK 后，也能完全不用 Python 运行单条路线：

```bash
godot --headless --path /path/to/your-game --script res://addons/nohit_live/session.gd -- --nohit-request=/absolute/request.json --nohit-output=/absolute/result.json
```

请求参考 `portable/request.example.json`。自动搜索/独立回放的 Python 工具可按需使用。

## GameMaker：相同协议，脚本接入

导入 `portable/gamemaker/nohit_live.gml` 与 `nohit_adapter.gml` 为脚本。
填写 `MyNoHitAdapter` 的 `begin/observe`，在明确的测试构建里创建 `NoHitLive`，
原输入边界调用一次 `begin_step()`。将输入包装成 `NoHitHeld/Pressed/Released`；
原红心/蓝心移动代码继续调用这一层，测试以外返回正常键盘输入。
原伤害、KR、攻击结束入口记录到 session，原碰撞事件照常执行。

Begin Step 在 Step 之前，但同类事件之间的实例顺序不能作为通用保证。
若原心魂在 Begin Step 就移动，应把调用放在其原输入代码前，避免另一个对象的顺序依赖。
结果在下一输入边界采集上一完整 Step，保留 End Step 中的伤害。
读取请求 JSON、导出结果及原生进程启动，由自己的 GameMaker 测试构建处理。
目前 Python 安装器/进程运行器只支持 Godot，不声称 GameMaker 一键运行已完成。

## 接入范围与可选加速

| 接入方式 | 开发工作 | 适用情况 |
| --- | --- | --- |
| Live 接入（本页） | 一份适配器、输入映射、原伤害/结束钩子 | 普通已有游戏，Timer/Tween/Area/物理世界无需自行恢复 |
| Snapshot 接入（原 `godot/addons/nohit`） | 完整 capture/restore/advance | 需要高性能分支搜索且能精确恢复世界的游戏 |
| 原生烘焙（可选） | 导出原碰撞形状/掩码 | 几何诊断或搜索加速；最终仍使用原伤害规则回放 |

多核来自隔离原生进程并行，`--workers` 可控制。每个进程保留自己的 RNG/物理世界。
主场景导入、资源、攻击时长和冷启动仍会占时间；这条快速接入路径没有毫秒级执行保证。
Godot 3/4 的版本、Mono/C#、GDExtension 应与原游戏匹配；缺少依赖会保留失败日志。
所有联网、实时钟表、自定义 RNG 等影响轨迹的来源，都应由游戏测试入口固定。

接口细节和验收范围见 [protocol.md](protocol.md)。
只使用轻量接入包即可，不需要下载旧 nohit 优化器或研究素材。

## 依赖、许可证与接口依据

Live SDK 与随包接入模板按 MIT 发布，可用于自己的项目，见 LICENSE.txt。
此许可仅覆盖新 Live SDK、nohit.py 和 test_portable.py，不替代上游游戏、
旧求解器或研究样本自己的许可证。

实现参考原生接口文档：
- [Godot SceneTree 物理帧边界](https://docs.godotengine.org/en/stable/classes/class_scenetree.html)
- [Godot 3 Viewport 输入](https://docs.godotengine.org/en/3.5/classes/class_viewport.html)
- [Godot 4 Viewport 输入](https://docs.godotengine.org/en/4.5/classes/class_viewport.html)
- [GameMaker 原生事件顺序](https://manual.gamemaker.io/lts/en/The_Asset_Editors/Object_Properties/Object_Events.htm)
