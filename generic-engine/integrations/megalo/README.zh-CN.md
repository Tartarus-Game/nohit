# Megalo 原生 Godot 3 接入

固定提交 `b449c9c05f8af91b8e015d490ff9fdcb8913ed1e`。使用官方 Godot 3.5.3 headless；3.3 不识别该项目的 gdshader 资源，最初尝试无法载入战斗，日志保留。

```bash
git clone https://github.com/Oplexitie/Megalo-Framework upstream-megalo
git -C upstream-megalo checkout b449c9c05f8af91b8e015d490ff9fdcb8913ed1e
python generic-engine/integrations/megalo/prepare.py upstream-megalo native-megalo
```

用 Godot 3.5.3 完成资源导入，等待扫描结束；随后：

```bash
python generic-engine/tools/run_upstream_native.py --adapter megalo \
  --godot /path/to/Godot_v3.5.3-stable_linux_headless.64 \
  --project native-megalo --out megalo-results --workers 6
```

运行原 Viewport、Battle、Border、PlayerHeart、Attacks、Bullets、Timer 与伤害逻辑。方向输入使用原生 InputEventAction，让原 `_input` 代码收到事件。关闭菜单操作只是攻击入口状态，不禁用心魂、Area 或物理碰撞。观察子类统计 takeDamage 后调用原实现。

六种完整攻击各试五种输入，共 30 次。bonegap 通过完整 421 帧，生成 32 根原生骨头，HP=92、KR=0、伤害调用=0；独立进程逐帧回放完全一致。其余 intro、platformtest、randomblaster、bonestabtest、platformblaster 均受伤，尚未找到无伤路线。

同一 bonegap 的伤害反例：仅在对照运行的第 90 帧，把心魂放到真实骨头形状中心，原伤害在第 92 帧触发，HP=91、KR=6。成功候选和回放没有该位移。该对照检查了实际骨头与原伤害入口，不是只手动调用伤害函数。

证据：`../../research/megalo-353/certificate.json`、`../../research/megalo-suite/suite.json`。通过单次 bonegap 不代表六种攻击组成的完整游戏通过。头部／底部骨头、颜色、形状共享方式和原版脚本行为保持原样。
# 使用公共 Live SDK

`prepare_live.py` 保留原主场景，仅绑定 `live_adapter.gd` 和原伤害观察子类。
使用公共安装器/运行器，不需要复制 Megalo 专用搜索 driver：

```bash
python generic-engine/integrations/megalo/prepare_live.py /path/to/pinned-megalo /path/to/live-fixture
# 先用 Godot 3.5.3 编辑器导入原资源。
python generic-engine/tools/nohit.py solve /path/to/live-fixture --godot /path/to/godot3 --output results/megalo --max-ticks 700 --control-mask 4
```

本轮公共协议结果在 `research/portable-v1/megalo-common/summary.json`：
原版完整 bonegap 422 帧，32 个骨头，HP92/KR0，独立进程观察精确回放。
上/跳输入反例在第 85 帧触发原伤害和 KR。未移动玩家位置、未修改伤害或无敌值。
该适配器只是真实接线示范；其他游戏只需要自己的配置或适配器，不依赖这里的节点路径。

