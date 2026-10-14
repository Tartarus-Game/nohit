# 实际项目接入：meowjade Godot Undertale Engine

已在官方 Godot 4.6.1 Linux headless 中运行真实上游战斗场景，搜索四组圆环测试，并以独立新进程回放。证据在 `../../research/native-meow-delivery/suite.json`，包含候选、逐帧回放、原生伤害反例和完整攻击的失败尝试。

## 复现

安装 Python 3.10+、Git、官方 Godot 4.6.1 标准版。该接入不需要 Mono、Numba 或编译旧 nohit 算子。以下命令从本源码包根目录执行；把 `/path/to/godot` 换成可执行文件路径。

```bash
git clone https://github.com/meowjade/Godot-Undertale-Engine upstream-meow
git -C upstream-meow checkout 729dfb7ef9ba41f8695724cb31e5cd360d49128d
python generic-engine/integrations/meowjade/prepare.py upstream-meow native-meow
python generic-engine/integrations/meowjade/run_suite.py \
  --godot /path/to/godot --project native-meow --out native-results --workers 6
python generic-engine/integrations/meowjade/test_validation.py
```

`prepare.py` 要求新目标目录，核对提交与游戏代码，创建独立项目副本。`run_suite.py` 先完成一次资源导入，再开最多六个原生进程并行试输入。每个候选都会从初始场景重新运行，没有假装能恢复 Godot 的协程、Tween、Area 缓存和内部物理状态。当前搜索是有限输入策略组合，不保证求出任意弹幕。

只回放一条已有路线（此示例使用随包证据）：

```bash
/path/to/godot --headless --path native-meow --fixed-fps 60 --quit-after 600 -- \
  --scenario=circle_white_blue --seed=1 \
  --replay="$PWD/generic-engine/research/native-meow-delivery/circle_white_blue-replay.json" \
  --out="$PWD/replayed.json"
```

## 真正运行的内容

加载上游 `scene_container.tscn` 和 `battle.tscn`，保留原生 `SoulBattle`、`CharacterBody2D.move_and_slide`、`BulletCircle`、`Bullet`、`BulletArea`、Timer/Tween 及原伤害实现。桥接器在每个正常物理帧开始前注入方向键；心魂的红／蓝移动代码继续由上游执行。没有把上游移动逻辑翻译成另一套近似公式。

`audited_soul.gd` 继承原心魂，统计 `hurt`／`heal` 后调用 `super`。场景只替换脚本引用，保留 `special_bullet_mode=2`，不会把颜色规则改成另一个设定。该子类退出时释放上游已实例化但未加入树的绿心／青心节点；此清理发生在验证结束后。

入口重置 HP=20、KR=0，放到 (320,350)，调用原 `enable()` 和 `set_mode()`；场地调用原 `change_size(140,140)` 后实际可移动边界为 (256,256) 到 (384,384)。心魂碰撞形状和弹幕参数保持原值。

| 场景 ID | 提取的弹幕参数 | 心魂 | 输入搜索 |
| --- | --- | --- | --- |
| `circle_white_red` | 白弹，速度 250，6 发，半径 80，生成时长 0.6 秒 | 红 | 固定方向／环行组合 |
| `circle_white_blue` | 同一白弹组件 | 蓝 | 短暂横移后起跳等两阶段组合 |
| `circle_blue_red` | 蓝弹，速度 100，30 发，半径 80，生成时长 0.5 秒 | 红 | 含静止策略 |
| `circle_orange_red` | 同一 30 发组件，橙色 | 红 | 含持续环行策略 |

参数来自上游 `Battle/Attacks/default_attack.gd` 的圆环阶段，直接调用原节点实现。这里只取出单个波次；白弹蓝心是测试该组件的另一心魂模式。没有同时复现完整攻击中的多波圆环、追踪炮和之前的骨头／平台。

白弹结束要求全部 6 发已生成且实际节点消失。30 发不以存活满 300 帧作为完成依据：要求全部已生成，剩余每发距离生成中心大于 250 像素、且原生线性速度向外，已离开当前场地，后续不会折返。headless 下屏幕可见性回调可能不清理这些节点，故这里只认证这一孤立线性波次离场；不冒称整个关卡结束。

## 无伤验收与烘焙

每组候选关闭无敌、保持身体碰撞及 Area 监测，在 300 个正常物理帧中 HP 保持 20、KR 保持 0、伤害／回血调用均为 0。新进程仅读取输入路线，逐帧精确比较位置、速度、模式、健康、检测开关以及原生重叠计数，无浮点容差。

三个反例分别为白弹静止、蓝弹移动、橙弹静止，原生伤害均正常触发。蓝／橙成功路线也有实际 Area 重叠，因此不是靠禁用碰撞通过。

候选每 15 帧抓取原节点形状和变换，调用 Godot `Shape2D.collide` 烘焙三种颜色的几何位图。颜色伤害判定继续使用原游戏。采样间隔为 10 像素；位图用于检查与后续优化，当前搜索没有用粗网格作为安全证明。独立回放关闭烘焙，状态仍完全一致。

## 上游修复与范围

安装器记录两处兼容修复：无关攻击 UI 的无效 `0b` 字面量改成 `0`；完整攻击的 `throw` 信号补入原接收函数默认力度 `10`，匹配原信号的两个参数。未更改伤害、速度、重力、弹幕尺寸或无敌时间。入口场景、GL 渲染设置及 Git 编辑器插件调整也记录在 `upstream.json`。

完整 `default_attack` 已尝试四种策略，均在前段受伤，尚未求出无伤路线。GameMaker 和 UndertaleMakerX 此轮没有编译运行。随包包括本项目的完整接入源码与验证记录；上游完整资源通过固定提交获取，遵守上游许可，不与新编写的接入代码混作同一许可。
