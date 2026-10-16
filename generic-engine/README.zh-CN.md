# NoHit 通用游戏接入

这里保留可独立分发的 Live SDK、三个上游项目适配器及其保留的验收记录。游戏自己的心魂、弹幕、碰撞和伤害逻辑由原生引擎执行；Python 工具尝试有限输入策略，并以新进程回放候选。

## Live SDK

先读 [接入说明](portable/QUICKSTART.zh-CN.md)。Godot 3/4 项目可连接已有信号的 JSON 配置，或在一份 `nohit_adapter.gd` 中实现攻击入口、输入映射、伤害审计与逐帧观察。

以下命令从 `generic-engine` 目录运行：

```bash
python tools/nohit.py install /path/to/game
python tools/nohit.py doctor /path/to/game
python tools/nohit.py solve /path/to/game --godot /path/to/godot --output ../build/live-sdk/first --workers 4
```

要求 Python 3.10+，无需第三方 Python 包；Godot 版本及扩展必须与游戏匹配。`doctor` 只检查静态接线文件，原生执行进一步检查伤害审计、输入与观察。`solve` 的策略耗尽时返回 `unknown`，不能据此判断无解。GameMaker 保留同协议脚本模板，尚无原生编译运行验收，Python 安装器和进程运行器目前只支持 Godot。

[协议](portable/protocol.md) 定义输入、攻击结束和伤害审计。候选升级为 `native_nohit_fresh_process_observed` 需要原攻击完成、无累计伤害、独立进程逐帧观察精确一致及有效受伤反例；结论仅覆盖该场景、引擎、种子、路线和适配器审计范围。

## 三个项目适配器

| 接入 | 当前保留内容 | 验证范围 |
| --- | --- | --- |
| [meowjade](integrations/meowjade/README.zh-CN.md) | 固定提交准备器、原生场景 driver、几何观察器、验收测试 | 四组孤立圆环组件有保存的独立回放；完整 `default_attack` 未解出 |
| [Megalo](integrations/megalo/README.zh-CN.md) | 专用 driver 和公共 Live SDK 适配器 | 公共 SDK 的原版 bonegap 保存了候选、独立回放与受伤反例；不覆盖完整游戏 |
| [UNDOTALE](integrations/undotale/README.zh-CN.md) | 固定提交准备器、原生场景 driver | 历史三骨组件记录已归档；完整 RevengePapyrus 未解出 |

上游游戏源码和素材通过各接入说明中的固定提交获取。

## 保存的验证与本地检查

`validation/live-sdk/acceptance.json` 保存 Godot 3.5.3 / 4.6.1 共 24 项接入与故障拒绝结果；`validation/meowjade/` 保留圆环组件证据；`validation/megalo-live/` 保留公共 SDK bonegap 证据。这些是已有原生运行记录，静态测试不会重新执行 Godot。

从仓库根目录检查已保存的 meowjade 证据和解包器：

```bash
python -m pytest generic-engine/integrations/meowjade/test_validation.py -q
python generic-engine/tools/test_unpack_sample.py
```

有匹配的 Godot 二进制时，可按各接入说明重跑，或从本目录运行 `python tools/test_portable.py --godot3 ... --godot4 ... --output ../build/live-sdk/acceptance-new`。每次使用新的输出目录。

## 分发与包体检查

从 `generic-engine` 目录生成独立 SDK：

```bash
python tools/package_portable.py --output ../build/nohit-integration-sdk.zip
```

包内包含 SDK、示例、CLI、保留的 SDK 验收摘要及逐文件 SHA-256 清单。工具写出后重新打开 ZIP，核对每个文件的字节。

`tools/unpack_sample.py` 支持未加密 Godot PCK v1/v2/v3、ZIP 提取及 GameMaker FORM chunk 目录检查，校验包内 MD5/CRC 并拒绝不安全路径。FORM 检查不包含 GML 反编译；加密包与 EXE 内嵌 PCK 不在当前支持范围。

已移除的快照原型、样本扫描及旧研究材料保存在历史分支 `codex/history-before-cleanup-20261017`。Live SDK 的 MIT 许可见 [LICENSE.txt](portable/LICENSE.txt)，上游项目遵循各自许可。
