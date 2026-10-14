# 全样本尝试结果（2026-10-09）

恢复并核对 23 个固定提交仓库：14 个 Godot、8 个 GameMaker、1 个资源工具。另检查用户指定 UDTale 页面。该数量是仓库数，不是独立引擎家族数，也不是通过无伤的游戏数。

**实际通过：3 个项目、6 项原生测试。** 通过项都有新进程逐帧回放和会真实扣血的对照。全部项目已经尝试到当前可达到的层次；GameMaker 缺少编译运行时，若干 Godot/C# 项目也存在阻塞，不能把失败或仅运行场景容器标为无伤。

| 项目 | 本轮结果 |
| --- | --- |
| [Animeliqite/understudio](https://github.com/Animeliqite/understudio) | 源码入口已恢复、检查 YYP 与攻击/伤害候选；环境中未发现 Igor/GameMaker/Wine，未编译或运行 GML。 |
| [CoalitionEngine/Coalition-Engine](https://github.com/CoalitionEngine/Coalition-Engine) | 源码入口已恢复、检查 YYP 与攻击/伤害候选；环境中未发现 Igor/GameMaker/Wine，未编译或运行 GML。 |
| [KoitoLov/UT-BattleEngine](https://github.com/KoitoLov/UT-BattleEngine) | 600 帧场景启动；源码包含心魂移动/菜单，未发现可验收的完整弹幕伤害链。 |
| [Maks7594/LVENGINE](https://github.com/Maks7594/LVENGINE) | 场景启动与战斗管理脚本检查完成；当前只进入菜单，未完成有效攻击及伤害入口接入。 |
| [NsCrosu/Undertale-Fight-Engine](https://github.com/NsCrosu/Undertale-Fight-Engine) | 源码入口已恢复、检查 YYP 与攻击/伤害候选；环境中未发现 Igor/GameMaker/Wine，未编译或运行 GML。 |
| [Oplexitie/Megalo-Framework](https://github.com/Oplexitie/Megalo-Framework) | Godot 3.5.3 下六种原攻击各试五种输入；完整 bonegap 421 帧、32 根骨头无伤回放通过，另外五种均受伤。 |
| [SagaPDev/Undertale-battle-system-prototipe](https://github.com/SagaPDev/Undertale-battle-system-prototipe) | 600 帧场景启动；有射弹移动样本，缺少完整伤害/攻击结束验收链。 |
| [SamuelWolfang/UNDOTALE](https://github.com/SamuelWolfang/UNDOTALE) | 三发骨头组件通过 400 帧原生无伤与新进程回放；完整 RevengePapyrus 36 次尝试均受伤，最长 564 帧。 |
| [Stoxis/Godette-Tale](https://github.com/Stoxis/Godette-Tale) | 启动重试后仍有错误；主要为探索/对话，战斗未完成，无弹幕无伤验收。 |
| [TML233/UndertaleEngine](https://github.com/TML233/UndertaleEngine) | 源码入口已恢复、检查 YYP 与攻击/伤害候选；环境中未发现 Igor/GameMaker/Wine，未编译或运行 GML。 |
| [WDUT-Dev/UT-Godot-Engine](https://github.com/WDUT-Dev/UT-Godot-Engine) | 补齐 godot-cpp、修复缺失 cstdio 后 C++ 扩展编译成功；C++ 与 GDScript Sans 攻击均启动，未完成伤害审计和无伤验收。 |
| [Yanxiyimengya/UndertaleMakerX](https://github.com/Yanxiyimengya/UndertaleMakerX) | 原 C# 项目编译成功；SansFight 挂载尝试受主循环类注册/文件名大小写阻塞，修复后的重编译又遭 MSBuild Process 异常，未运行通过。 |
| [etherealxx/undotale-godot4](https://github.com/etherealxx/undotale-godot4) | 战斗场景能载入，但仍保留 Godot 3 Tween 节点/调用，原生报错；不计无伤通过。 |
| [meowjade/Godot-Undertale-Engine](https://github.com/meowjade/Godot-Undertale-Engine) | 四组圆环组件通过原生无伤与新进程回放；完整 default_attack 本轮 28 次尝试均受伤。 |
| [mouse114514/End-Of-Truth](https://github.com/mouse114514/End-Of-Truth) | 进入真实战斗并调用原 circle/spiral 发射方法，原生弹幕实际击中玩家；桌面 au_timelines.json 依赖缺失，尚无无伤证明。 |
| [neon-gr33n/underengine](https://github.com/neon-gr33n/underengine) | 源码入口已恢复、检查 YYP 与攻击/伤害候选；环境中未发现 Igor/GameMaker/Wine，未编译或运行 GML。 |
| [onezhazha233/Undertale-Engine-modded-by-Zhazha](https://github.com/onezhazha233/Undertale-Engine-modded-by-Zhazha) | 源码入口已恢复、检查 YYP 与攻击/伤害候选；环境中未发现 Igor/GameMaker/Wine，未编译或运行 GML。 |
| [rarespawns/UndertaleFangameFramework](https://github.com/rarespawns/UndertaleFangameFramework) | 尝试 C# 编译/启动；battle.cs 明确注明战斗尚未开发，不将场景容器运行当作战斗通过。 |
| [sultansagitov/UndertaleBattle](https://github.com/sultansagitov/UndertaleBattle) | 尝试 C# 构建与场景启动；MSBuild Process 异常，场景容器帧数不能当作 C# 战斗代码已运行。 |
| [techoskiller/AT-Engine](https://github.com/techoskiller/AT-Engine) | 源码入口已恢复、检查 YYP 与攻击/伤害候选；环境中未发现 Igor/GameMaker/Wine，未编译或运行 GML。 |
| [ws3917/psoutertale-gms](https://github.com/ws3917/psoutertale-gms) | 资源/翻译相关工具，不是可执行弹幕引擎。 |
| [znm2500/Undertale-Engine-Ultra](https://github.com/znm2500/Undertale-Engine-Ultra) | 源码入口已恢复、检查 YYP 与攻击/伤害候选；环境中未发现 Igor/GameMaker/Wine，未编译或运行 GML。 |
| [Tartarus-Game/UndertaleEngine](https://github.com/Tartarus-Game/UndertaleEngine) | 启动存在 UID 场景问题；BattleSoulRed 仅类声明，尚无完整弹幕/蓝心算子。 |

UDTale：发行包尚未获得，不能运行或解包。本轮只获得不可访问的网页检索结果；未绕过此前浏览器的下载限制。

## 实际无伤证据

| 项目/样本 | 完整原生帧 | 生成弹幕 | HP / KR | 回放 |
| --- | ---: | ---: | --- | --- |
| meowjade 白弹/红心 | 300 | 6 | 20 / 0 | 新进程逐帧一致 |
| meowjade 白弹/蓝心 | 300 | 6 | 20 / 0 | 新进程逐帧一致 |
| meowjade 蓝弹/红心 | 300 | 30 | 20 / 0 | 新进程逐帧一致 |
| meowjade 橙弹/红心 | 300 | 30 | 20 / 0 | 新进程逐帧一致 |
| UNDOTALE 首段三骨头组件 | 400 | 3 | 48 / 不适用 | 新进程逐帧一致 |
| Megalo 完整 bonegap | 421 | 32 | 92 / 0 | 新进程逐帧一致 |

以上是单次攻击或隔离波次；不代表三个项目的全部关卡通过。蓝心/红心、原生移动和原伤害逻辑未近似重写。UNDOTALE 的组件只包含原第一段三个骨头，完整攻击的移动场地/缩框/后续骨头尚未解出。Megalo 的 bonegap 为原完整攻击结束信号验收，其他五种攻击均受伤。

证据：`meow-all-round/suite.json`、`undotale-native/certificate.json`、`undotale-suite/suite.json`、`megalo-353/certificate.json`、`megalo-suite/suite.json`（路径相对于 research）。其中包括输入、位置、速度、模式、HP/KR、伤害计数、原生生成数量、回放与反例。Megalo 伤害对照在第 90 帧把玩家放到真正的骨头碰撞形状中心，92 帧原伤害触发；成功路线不做该位移。

## 运行与阻塞说明

- Godot 3.3、3.5.3、4.6.1 标准版和 4.6.1 Mono 均实际使用。资源导入与运行分开；3.x 编辑器必须等待扫描完成，立即 --quit 会使导入不足。
- C# 初次通过独立 MSBuild 入口成功构建 UTMX 原运行时；后续环境中 Process/StartTime 相关异常使重新构建失败。另发现 UTMXMainLoop.cs 与 UtmxMainLoop 类名大小写不符，已尝试两处同类文件重命名，但未完成重新构建运行。不得声称 C# 原攻击已验证。
- WDUT 补入 godot-cpp 固定提交并进行 -j8 原生编译；唯一游戏源码修复是补 cstdio 头文件。C++ 与 GDScript 攻击探测都输出原生启动记录，但伤害审计/结束条件仍未接入，无无伤证书。编译身份在 all-samples/wdut-build-identity.json。
- End-Of-Truth 原波次确实生成弹幕并击中玩家；完整时间线读取 Windows 桌面文件，样本缺少该运行位置的数据，记录为未完成。
- 八个 GameMaker 仓库只能检查工程和原 GML 接入点。本机无编译器/运行时；不会用自写近似模拟替代原生结算。[官方 Igor 构建文档](https://manual.gamemaker.io/lts/en/Settings/Building_via_Command_Line.htm)。
- startup_600_frames 只表示探测节点执行了 600 帧；C# 脚本、GDExtension 或场景脚本仍可能报错。最终结果以上表人工核对和独立验收为准，不能仅凭帧数通过。
- 日志未过滤退出时的资源引用/泄漏警告；不据此承诺长期运行零泄漏或所有项目冷启动十秒以内。

## 复现入口

`tools/restore_samples.py` 恢复全部固定提交；`tools/probe_samples.py` 尝试原生启动并记录编译错误；`tools/run_upstream_native.py` 搜索、回放和验收新增 Godot 3 适配器。

已验证适配器：`integrations/meowjade`、`integrations/undotale`、`integrations/megalo`。`integrations/probes` 的 WDUT/End-Of-Truth/UTMX 仅是探测脚本，没有无伤认证。各适配器 README 含运行命令。
