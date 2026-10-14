# UNDOTALE 原生 Godot 3 接入

固定提交 `9dc511a5ec5225866ceaf86f1f44de8972429490`。使用官方 Godot 3.3 headless，保留原 Soul、Box、Bone、物理、碰撞、伤害与计时器。心魂观察子类统计 hit 调用后委托原方法。

从源码包根目录运行：

```bash
git clone https://github.com/SamuelWolfang/UNDOTALE upstream-undotale
git -C upstream-undotale checkout 9dc511a5ec5225866ceaf86f1f44de8972429490
python generic-engine/integrations/undotale/prepare.py upstream-undotale native-undotale
```

Godot 3 资源导入必须等待编辑器扫描完成，不能启动后立即 `--quit`。完成导入再运行：

```bash
python generic-engine/tools/run_upstream_native.py --adapter undotale \
  --godot /path/to/Godot_v3.3-stable_linux_headless.64 \
  --project native-undotale --out undotale-results --workers 6
```

完整 RevengePapyrus 攻击进行了固定、脉冲及两阶段输入搜索，36 次均受伤，最长 564 帧。另从原攻击第一段提取三发 Bone 波次：速度 (100,0)、底部高度 30、每秒一发。使用原始节点和原始心魂蓝心逻辑；400 帧无伤，HP=48、hit 调用=0，独立进程输入回放逐帧完全一致。原地不动反例在 102 帧受伤。

组件结束要求三发全部生成且所有剩余骨头中心越过场地右边界 30 像素；它们按原脚本持续向右移动，之后不会折返。结果不覆盖重定位、缩框和其余八发骨头。适配器只调整初始场地与入口绑定，不改速度、重力、伤害或碰撞体。

证据：`../../research/undotale-native/certificate.json`、`../../research/undotale-suite/suite.json`。完整攻击的失败尝试也保留。Godot 3 服务器版运行原生碰撞，不提供渲染截图。
