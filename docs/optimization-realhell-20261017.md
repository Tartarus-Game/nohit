# Real HELL 性能优化与复现（2026-10-17）

本地改动基于 `codex/latest-only` 的 `a78727741ba0c054b0d4d5de5f115a3b450d0c87`。
测试源使用仓库已有的 `artifacts/realhell-weakened-20261017/source.csv`，SHA256 为
`6fae36d1bdef87a5f9605080da045ed8121e7c867113bef5fc9c38f102775075`。
本次没有改变攻击几何、时钟、玩家速度或危险物行为。

## 改动

1. 分窗求解只为初始化玩家取得第 0 帧；不再预先烘焙至首个观测，再从头生成同一段世界。
2. 原生状态表在取槽位前一次性混合完整浮点位哈希，避免整数/半整数坐标先形成长冲突链再重建。状态仍按完整 binary64 位比较，控制锁存商保持原有定义，未启用 fast-math 或状态量化。
3. 独立 `TimelineVM.run` 增加内部逐帧观察口。完整源方程、物理和碰撞检查仍实际执行；验证后立即释放该帧危险物，不再物化长谱的矩形填充历史。
4. 已独立验证的源前缀只保留 `EnvironmentContinuation`，包含精确身份、首帧环境、实际继续状态和回调清单。它不是搜索用的 `EnvironmentBinding`，不会被发布到分支绑定缓存，也不伪装成空危险物世界。
5. 已知历史的重建使用现有等价骨骼数组路径；验证不生成展示用的组合几何副本。活跃危险物计数的临时掩码限制为 256 帧。
6. 编译超时从 8 秒改为 120 秒，避免较慢机器在正常编译完成前被中止。这是可用性修复，不是编译加速。
7. 对空骨骼直接返回；原生库已载入时，小批量骨骼也复用已有 C++ 算子，避免每 tick 多组 NumPy 临时数组。原生库尚未载入时，小场景保留免编译路径。
8. 分窗遇到后续死路时，最多保留 8 个精确源事务检查点、尝试 16 次局部回退。按键、物理轨迹、Confirm、目标历史与世界继续状态一起撤回，固定前缀不能撤回。回退使用原请求预算，改变排序种子后重搜；所有实际观测仍从已提交输入重新取得，最终完整独立复验。
9. 基准绑定整个引擎源码，在测量期间源码变化时拒绝结果。新增两个 checkout 的交替、独立进程基准；原事件引擎复跑支持分窗参数，并独立比较 GetHeartPos 清单。

## 性能对照

见 `artifacts/performance-realhell-20261017/revision-pair.json` 的逐次原始记录。
使用同一 CSV、历史入口完整时钟、4 workers、width 8192、512 MiB 搜索预算、480 tick 提交及前视，180 秒搜索预算；从零求解，无固定前缀，不跨请求复用路线或世界。仅跨请求复用已编译代码；局部回退只使用本次请求内的检查点。
每个请求均为新 Python 进程，包含世界构造、搜索和强制复验；编译器子进程内存不计入 Python 峰值 RSS。

| 指标 | 基线 | 优化版 |
| --- | ---: | ---: |
| 三次求解中位数 | 49.57 s | 41.87 s |
| 最大进程峰值 RSS | 4.184 GiB | 226.8 MiB |
| 完成且独立复验通过 | 3 / 3 | 3 / 3 |

中位加速 1.184 倍，耗时下降 15.5%，最大峰值内存下降 94.7%。

逐次结果：

| 顺序 | 版本 | 求解耗时 (s) | 峰值 RSS (MiB) | 局部回退次数 |
| --- | --- | ---: | ---: | ---: |
| 1 | baseline | 49.261 | 4254.3 | 0 |
| 2 | optimized | 41.868 | 226.8 | 0 |
| 3 | optimized | 41.705 | 223.3 | 0 |
| 4 | baseline | 49.574 | 4284.5 | 0 |
| 5 | baseline | 52.836 | 4257.5 | 0 |
| 6 | optimized | 53.667 | 221.3 | 11 |

优化版第三次运行实际回退 11 次后成功，耗时 53.67 秒，超过该轮基线；这是有限搜索的实际波动。没有丢弃该样本，也不按最好成绩承诺固定延迟。计时组按 baseline / optimized、optimized / baseline、baseline / optimized 顺序执行，运行期间未并行执行其他求解或测试。

环境：Python 3.12.14，NumPy 2.3.5，Linux x86_64；进程可用 CPU 配额为 8，本组仅请求 4 workers。

不要把 cProfile 诊断运行、有安全前缀的历史续跑、不同入口的原事件引擎运行和本表混作同一基准。
`memory_mb` 不是进程 RSS 上限；它约束的是搜索工作空间。

## 正确性与原事件引擎证据

- 完整 Python 回归 1,401 项通过、1 项预期失败；Node 314 项通过。新增测试覆盖流式几何差分、真实碰撞拒绝、0/1/8/32/64/256 骨骼的非有限数与有符号零、完整继续状态与身份一致性，以及故意注入一次分窗失败后的观测回退和固定前缀保留。
- 原 Construct 2 事件引擎（DOM、音频和渲染 stub）完整执行新起点下的 25,805 次输入；HP 始终 92，KR 始终 0，DamagePlayer 事件 0。
- 469 次 GetHeartPos 清单与模型一致；283,844 个非终点状态分量精确匹配，无状态差异。
- 最终源码在该独立原生入口下的求解与模型复验耗时 37.68 秒，此值不与历史入口的交替基准混算。正常触发原生 EndAttack；菜单转换后的最终实际与模型状态单独保留。此事件引擎证据不冒充新的浏览器截图验收。
- 为通过原游戏已有的单回合菜单入口，测试隔离副本将同一 Real HELL CSV 放在 `sans_bonegap1.csv` 名下。游戏事件、运行时和数据 JS 保持原样，报告同时绑定实际 CSV 与 JS 哈希。
- 本次原事件引擎独立捕获自己的起点与完整 60 Hz 时钟；本次与历史入口对照均为 25,805 tick，但不能据 tick 数相同交换入口或路线。

[原生汇总](../artifacts/performance-realhell-20261017/native-summary.json)、完整压缩原生轨迹、对应路线与入口均保存在同目录。`.gz` 解压后的 JSON 是原始文件字节，汇总绑定压缩件及原路线哈希。

## 复现

准备两个 checkout：基线固定在上述提交，优化版使用优化源码包。安装 `requirements-native.txt` 与 pytest。

```bash
python -m tools.benchmark_revision_pair \
  --baseline ../nohit-baseline --optimized . \
  --csv artifacts/realhell-weakened-20261017/source.csv \
  --entry artifacts/realhell-weakened-20261017/entry.json \
  --workers 4 --repeats 3 --out build/performance/revision-pair.json
python -m pytest tests -q
node --test tools/*_test.mjs tests/unit/*_test.mjs
```

交替基准共享优化 checkout 的编译缓存。原基线有 8 秒编译超时，因此先在两个 checkout 预热原生库；如果基线编译超时，可手动按基线 `_FLAGS` 构建其内容哈希命名的库。不要为完成基线预热而改变引擎源码。

原事件引擎复现：复制 `c2-sans-fight/` 到隔离测试目录，把同源 CSV 复制到该目录的 `sans_bonegap1.csv`，然后：

```bash
NOHIT_GAME_DIR=/absolute/path/to/test-game \
NOHIT_BENCH_OUT=/absolute/path/to/evidence \
NOHIT_FPS=60 NOHIT_SECONDS=180 NOHIT_WIDTH=8192 \
NOHIT_MEMORY_MB=512 NOHIT_WORKERS=4 \
NOHIT_OBSERVATION_CHUNK_TICKS=480 NOHIT_OBSERVATION_PREVIEW_TICKS=480 \
node tools/native_optimized_replay.mjs sans_bonegap1
```

## 剩余边界

没有证明达到绝对理论极限。搜索仍有宽度与时间预算，失败仍返回 `unknown`；这次优化不构成完备性、最优性或无解证明。
输入依赖观测的重叠前视仍会重复生成未来世界，Python 源解释和原生前沿扩展仍有成本。进一步消除它们需要设计可验证的观测依赖复用或改变搜索架构，不能靠缩减复验或套用已知路线宣称完成。
首次编译与导入仍有开销，本报告不承诺冷启动 10 秒或整谱毫秒级求解。有限搜索的计时预算会影响被选中的路线，因此固定 seed 不保证负载不同的机器产生同一输入串；所有被接受路线仍须独立完整复验。
