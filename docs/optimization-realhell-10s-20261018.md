# Real HELL：10 秒内求解与独立验收

本次固定测试达到 10 秒目标。最新三次均为独立 Python 进程、空运行时 C++ 编译缓存，从零构造世界、搜索并完成独立源模型验证。没有读入历史路线、固定前缀或跨请求世界缓存，也没有再次削弱谱面、更改时钟、速度或碰撞规则。

## 输入和构建条件

- 基线：`codex/latest-only` 的 `a78727741ba0c054b0d4d5de5f115a3b450d0c87`；任务开始时远端没有名为 `latest` 的分支。优化保存在本地 `codex/performance-realhell`，未推送远端。
- CSV：`artifacts/realhell-weakened-20261017/source.csv`，SHA256 `6fae36d1bdef87a5f9605080da045ed8121e7c867113bef5fc9c38f102775075`。原测试副本的弱化及补充终点见同目录 README，本轮没有修改它。
- 固定入口：同目录 `entry.json`，SHA256 `912d8eb5d389f9329649913627d44fa0fd4ab3f915dd8e16c4ba7b217e04c56e`；使用其中 40000 项精确 binary64 dt，不改成理想化的 1/60。
- Linux x86_64，Intel Xeon Platinum 8370C，Python 3.12.14、NumPy 2.3.5；CPU 配额 8，搜索请求 4 workers、width 1024、512 MiB 工作空间预算。
- **先安装预编译代码，再测冷进程启动。** 三个 Cython 数值模块及 C++ 镜像在安装阶段构建；求解期间无需 JIT。镜像仅在源文件、编译选项、平台、CPU 特征和二进制 SHA256 全部匹配时载入。空运行时缓存不包含路线或世界；安装阶段编译耗时不算入求解。
- 未安装匹配镜像的纯源码第一次运行会回退现场 C++ 编译，不能把它也说成已经证明小于 10 秒。性能数字只适用于本报告的输入、构建和机器条件。

## 三次最终结果

记录位于 `artifacts/performance-realhell-10s-20261018/benchmark.json`；每行都绑定全部引擎源码、数值模块二进制、C++ 镜像及结果指纹。

| 独立进程 | 构造＋搜索＋完整验证 | 外部总耗时 | 验证 |
| --- | ---: | ---: | --- |
| 1 | 8.406 s | 8.617 s | 通过 |
| 2 | 8.327 s | 8.504 s | 通过 |
| 3 | 8.426 s | 8.625 s | 通过 |

中位数 8.406 秒，最大峰值 RSS 247.96 MiB。相对上一轮 41.87 秒的中位数约快 4.98 倍；相对最初 49.57 秒基线约快 5.90 倍。上一轮使用不同搜索配置，此处比较的是同一输入的完整求解结果，不是同配置微基准。

先前热代码、显式 240/240 配置的三次结果为 8.079 / 8.180 / 7.856 秒，也保留了原始记录；最终交付以本节冷进程结果为准。没有宣称 200 倍、300 倍、毫秒级整谱求解或达到绝对理论极限。

## 实现

- 观测源默认走 240/240 滚动分窗；在公开入口就跳过不适用的整世界求解器，避免先烘焙到第一个 GetHeartPos，再把这个前缀丢弃。
- 控制宏每个物理 tick 都执行原运动及碰撞。保持按键的决策粒度和接触触发跳跃只用于搜索，不跳过物理帧；保留原始浮点状态，并逐位差分。
- 对平台建立二维有序区间索引，以原顺序的端点加法作保守筛选。承载更新可能连锁改变后续接触，因此每次重新查询并保留原平台行顺序，不能简单丢掉最初包围盒之外的平台。
- 密集线性平台、骨骼及激光以私有数组推进；出生帧、旧活动标记、方向的原始数值类型、反向及清除行为均保留。反向平台回到原标量路径，已发布帧独立持有其数据。
- 空间分布、粗控制和多种候选方式并发寻找可行路径。错误预测的未来 GetHeartPos 只作低预算指导；真实回退重试仍保留完整预算。观测来自本次输入的实际采样点。
- 仅在本次请求内延续已算出的按键，并在新世界中重放检查；没有磁盘路线、历史前缀或跨请求环境缓存。
- 验证器独立执行源时间线、实体生命周期、玩家运动与全部实际观测。逐帧的心形包围盒只筛选碰撞查询几何；实体仍全部推进。独立算出的完整状态必须与候选逐位一致，篡改候选位置不能绕过检查。
- 数值加速器从原 Python 方程生成，使用 `-ffp-contract=off -fno-fast-math`；普通物化编译器保留原标量实体路径作差分对照。原生镜像可随安装部署，冷进程无需调用编译器。

## 正确性

最终 Python 回归 **1420 通过、1 项预期失败**；Node **314 通过**。覆盖源帧及身份差分、真实碰撞拒绝、浮点边界和有符号零、密集平台连锁承载、出生/反向/清除、真实观测继续状态、回退、候选延续、二进制及源绑定、无编译器冷启动等。

原 Construct 2 回放独立捕获新入口并重新求解，使用同一 CSV 的隔离副本 `sans_bonegap1.csv`。游戏的 `c2runtime.js`、`data.js` 和事件方程保持原样，仅有 DOM、音频、渲染 stub；这不是新的 GUI 浏览器录像。

最终新入口求解及完整验证耗时 **8.538 秒**，外部 Python 进程耗时 **8.718 秒**，原 C2 回放全部通过。最终验收汇总及完整压缩轨迹见同一证据目录。逐帧验收 25805 次输入，检查 469 次 GetHeartPos 和 283844 个非终点状态分量；EndAttack 后的菜单重置状态单独记录，不与战斗终点混为一谈。HP 始终 92，KR 始终 0，DamagePlayer 事件 0，无状态或观测差异。两种入口虽都为 25805 tick，也没有交换入口或借用已有路线。

## 复现

在对应平台安装并构建一次：

```bash
python -m pip install -r requirements-accelerated.txt
python -m tools.build_accelerators --native
```

固定测试，默认观测求解配置：

```bash
python -m tools.benchmark_round8_request \
  artifacts/realhell-weakened-20261017/source.csv \
  --entry artifacts/realhell-weakened-20261017/entry.json \
  --out build/performance/repeated.json --workers 4 --width 1024 \
  --memory-mb 512 --seconds 18 --repeats 3 --empty-code-cache
```

实际输出路线：

```bash
python -m tools.solve_csv artifacts/realhell-weakened-20261017/source.csv \
  --entry artifacts/realhell-weakened-20261017/entry.json \
  --out build/route.json --workers 4 --width 1024 --memory-mb 512 --seconds 18
python -m pytest tests -q
node --test tools/*_test.mjs tests/unit/*_test.mjs
```

原事件引擎验收：复制 `c2-sans-fight` 到隔离目录，把同源 CSV 放到其中 `sans_bonegap1.csv`，再执行：

```bash
NOHIT_GAME_DIR=/absolute/path/to/test-game \
NOHIT_BENCH_OUT=/absolute/path/to/evidence \
NOHIT_FPS=60 NOHIT_SECONDS=30 NOHIT_WIDTH=1024 \
NOHIT_MEMORY_MB=512 NOHIT_WORKERS=4 \
node tools/native_optimized_replay.mjs sans_bonegap1
```

搜索仍有宽度和时间限制，失败返回 `unknown`，不作无解或最优性证明。安装镜像不能替代目标平台的正确性与性能复测。
