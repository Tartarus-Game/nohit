# 第六轮：精确空间索引、受限几何、因果预测与 Haoge 验收

## 已达到和未达到的目标

当前源码：原版 Normal 60 Hz 连续 24/24 轮通过原版 C2 无伤回放；Haoge 23/24 个攻击通过原版 C2 无伤回放。原版事件运行时、弹幕数据、攻击 CSV 均未修改。Haoge Final 仍未找到可验收路线。整关普遍再快 20 倍、所有任务毫秒级、所有关卡含冷启动低于 10 秒，均未实现。

## 同入口实测

BlueBone 使用此前捕获的同一原生入口、同一 CSV、8 个工作线程，在两个新进程中对照上一轮动态搜索实现与当前实现。只预加载编译代码，未缓存路线或世界。包含完整求解及独立源模型验证；不包含随后原版游戏验收。每个版本各测一次，不能当成跨任务统计。

| 指标 | 第五轮结构 | 第六轮 | 比例 |
| --- | ---: | ---: | ---: |
| 完整求解和独立验证 | 8.9205 s | 1.1819 s | 7.55× 加速 |
| 原生搜索 | 4.4325 s | 0.2600 s | 17.05× 加速 |
| 临时世界生成 | 1.8898 s | 0.4107 s | 4.60× 加速 |
| 独立验证 | 2.5535 s | 0.4631 s | 5.51× 加速 |
| 求解进程峰值 RSS | 326.22 MiB | 97.32 MiB | 3.35× 缩小 |
| 前沿工作空间 | 140,800,000 B | 6,809,144 B | 20.68× 缩小 |
| 提议世界共享张量 | 96,804,496 B | 12,048,912 B | 8.03× 缩小 |

独立碰撞内核对照：100,000 个状态、4,096 个白色矩形、混合蓝色矩形及四边形，含大量远离玩家的实体。两版各重复三次，中位数 262.115 ms → 1.446 ms，181.23×；全部碰撞布尔输出一致，另用独立标量公式抽查 128 项。这是固定密集几何内核基准，不能冒充整关 181×。

当前 BlueBone 两次空代码缓存、新 Python 进程的外部墙钟时间：4.0644 s、4.1700 s，包含首次 C++ 编译、导入、完整求解与独立模型验证。输出指纹一致；未导入 Numba/LLVM，未缓存路线或环境。求解进程峰值 RSS 约 97.4 MiB，编译器子进程约 165 MiB，分别记录，不能把求解进程 RSS 当作整个进程树峰值。代码缓存为空不代表操作系统文件缓存为空。

## 实现

- C++ 碰撞使用 16 像素格子的稀疏成员索引。空格子跳过检测；混合格子仅测试覆盖该格子的实体，仍用原闭区间矩形和 SAT 方程。蓝色实体只在玩家移动时生效。网格外回退原全扫描，边缘、NaN、无限边界均做差分测试。
- 私有独占的骨头续跑状态改为连续数组，减少对象遍历、逐字段调用和复制。保留浮点表达式次序、相等时原值、带符号零和 NaN 语义；公开纯环境 API 保留原身份。
- 密集提议世界只保留玩家窗口附近的矩形，并加上禁止越界的人工外墙。窗口之外的实体仍保留在真实源环境；候选经全实体独立源回放和原版游戏回放。此方法可能剪掉可行的远处路线，只是搜索限制，不构成无解证明。验证前释放临时张量。
- 搜索加入通用目标引导和 27 种接触跳跃/转向策略。工作线程并行跑不同前沿方案，不再只是加宽单一前沿。冷启动样本的有效搜索核数约 3.1–4.9，未达到所有时段满核。
- GetHeartPos 分段加入未来 60/240 tick 的因果预测和方向多样性。只提交真实读取之前的输入，预测的玩家位置不会写入最终目标历史。所有失败预测的搜索时间和工作量进入审计。
- 修正原 Timeline 度转弧度的运算次序：angle / (180 / π)。201° 的一 ULP 误差会令随机 Blaster 角度取整为 20 而非 21，此前导致模型安全但原版受伤。Python libm 与 V8 的 sin/cos 在其他角度仍可能有末位差异；当前成功以实际原生逐 tick 验收为准。
- 正数脚本 DamagePlayer 增加独立显式诊断开关；默认严格拒绝。即使允许物理投影，也要原版回放核对脚本伤害的 tick、数值、KR、存活和物理状态，才有资格报告该不同合同的成功。

## 当前原生验收

所有当前成功记录绑定实际发布的 engine 源码哈希。目录 `round6/normal-final`、`round6/haoge-final` 是当前证据；其他轮次为历史记录。

原版 Normal：24 轮连续完成，17,804 原生 tick，14,016 个匹配输入，153,912 个非终止状态分量一致，HP92、KR0、零 DamagePlayer、Win2。独立验证器判定 passed=true。Final 成功尝试求解 15.51 s；此前 8 秒首次尝试失败，重试另耗时间，记录均保留，不能将成功尝试耗时当作整场总耗时。

Haoge 以下 23 个攻击全部通过：

sans_intro, sans_bonegap1, sans_bonegap2, sans_bluebone, sans_platforms2,
sans_platforms4, sans_platformblaster, sans_platforms4hard, sans_spare,
sans_multi1, sans_multi2, sans_bonestab1, sans_boneslidev, sans_bonestab3,
sans_platformblasterfast, sans_randomblaster1, sans_boneslideh, sans_multi3,
sans_bonegap1fast, sans_bonestab2, sans_platforms1, sans_platforms3,
sans_randomblaster2。

Haoge 验收允许原脚本字面量负数治疗，要求存活、零非负 DamagePlayer 调用、物理状态与原版逐 tick 一致及 EndAttack。没有启用正数脚本伤害豁免。新增五关为 BoneGap1Fast、BoneStab2、Platforms1、Platforms3、RandomBlaster2。

Final 的最新 90 秒搜索仍为 unknown/native_search_limited，最深诊断前沿 tick11744；没有完整路线，不能称为已解出或证明无解。原脚本四个结尾分支均调用正数 DamagePlayer（141 或 999），因此“所有正数 DamagePlayer 都禁止”的严格零伤害合同与该结尾不相容；这不证明其弹幕物理躲避无解。允许脚本效果的诊断合同也尚未通过。原版 240 Hz Final 尚未解决。

## 测试边界

本轮涉及的回归共 132 项通过（9.41 s），覆盖精确空间索引、密集骨头差分、201° 表达式次序、因果预测、脚本效果合同及独立验证。

扩大旧源测试集：当前 276 passed、40 failed、24 errors。对上一轮交付源码使用同一组测试同样为 276 passed、40 failed、24 errors。除两个互换的 50 ms 性能阈值失败外，其余失败标识一致。旧失败包括上游缺失 Real HELL 文件、旧静态编译测试未提供真实目标/对话历史等。完整日志和比较 JSON 已保留；不能声称整个仓库测试全绿。

## 复现

安装 requirements-native.txt、C++17 编译器和 Node。以下在源码根目录运行：

```bash
python -m tools.benchmark_spatial_collision --out collision.json
python -m tools.benchmark_round6_request haogesans-export/sans_bluebone.csv \
  --entry tools/optimization-results/round5/haoge-current/sans_bluebone-entry.json \
  --healing --baseline --out blue-old.json
python -m tools.benchmark_round6_request haogesans-export/sans_bluebone.csv \
  --entry tools/optimization-results/round5/haoge-current/sans_bluebone-entry.json \
  --healing --out blue-new.json
python -m tools.benchmark_solver_request haogesans-export/sans_bluebone.csv \
  --entry tools/optimization-results/round5/haoge-current/sans_bluebone-entry.json \
  --healing --repeats 2 --out blue-cold.json

NOHIT_FPS=60 NOHIT_RETRY=1 NOHIT_BENCH_OUT=normal-new \
node tools/solve_normal_native.mjs
python -m tools.verify_normal_native normal-new/campaign.json --out normal-new/verdict.json

NOHIT_GAME_DIR=haogesans-export NOHIT_SCRIPTED_HEALING=1 \
NOHIT_FPS=60 NOHIT_SEARCH_STRATEGY=native NOHIT_SECONDS=45 \
NOHIT_WIDTH=8192 NOHIT_MEMORY_MB=256 NOHIT_BENCH_OUT=haoge-new \
node tools/native_optimized_replay.mjs sans_bonegap1fast sans_bonestab2 \
  sans_platforms1 sans_platforms3 sans_randomblaster2
```

基准旧版只替换上一轮动态规划与 C++ 内核，其余源解释与输入一致；不是整个旧仓库的绝对性能统计。验收使用本次新捕获的入口，固定入口对照使用此前捕获的入口，因原生时钟与浮点对话阈值，两者可能有少量 tick 差异。工具、参考源码、输入、记录和完整原版素材均在源码包中。
