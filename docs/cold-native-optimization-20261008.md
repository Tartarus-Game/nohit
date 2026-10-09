# 冷启动、CPU 与内存优化（2026-10-08）

基于原仓库提交 `479597f6faac3442d66238fd3fee296cbee7b2b8`。原版 CSV、
`c2runtime.js`、`data.js` 未修改。新增 C++17 搜索内核，CSV 默认优先使用它；
旧算子仍可通过 `--search-strategy fixed` 选择。

## 实测结果与口径

环境：Linux x86-64、AMD EPYC 9V74、9 个可用逻辑 CPU、Python 3.12.14、
NumPy 2.3.5、g++ 13.3.0。原版重放使用 Node 24.19.0。

| 测试 | 完整新进程耗时 | 解算进程峰值 RSS | 记录 |
| --- | ---: | ---: | --- |
| 原提交 BoneGap1，空 Numba 缓存 | 50.934 s | 626.72 MiB | `cold-baseline.json` |
| 5 个主要攻击，各 3 次空代码缓存 | 1.763–2.354 s | 32.31–37.61 MiB | `cold-native-empty-w8.json` |
| 全部 23 个 30 Hz 攻击，各 1 次空代码缓存 | 1.812–2.314 s | 30.97–87.86 MiB | `cold-suite30.json` |
| Final，30 Hz，3 次空代码缓存 | 2.325–2.514 s | 87.46–87.91 MiB | `cold-final.json` |
| BoneStab3，60 Hz，3 次空代码缓存 | 1.921–2.053 s | 32.23 MiB | `cold-bonestab3.json` |
| 5 个主要攻击，新进程、已有代码、重新搜索，各 3 次 | 0.178–0.260 s | 31.00–36.47 MiB | `cold-native-process-w8.json` |
| 空缓存 Dashboard 启动、真实 HTTP 解算、场景完整重放 | 2.681 s | 见记录 | `cold-dashboard-http.json` |

数据在 `tools/optimization-results/`。完整新进程计时从父进程启动 Python 到
子进程退出，包含解释器、导入、首次 C++ 编译、源环境构造、搜索、独立验证、
轨迹 JSON 序列化和结果输出。每次都重新计算路线和观察依赖的世界；空缓存
测试使用临时目录，确认 `compiled=true`，并断言未加载 Numba 或 LLVM。
该指标包含首次编译，并不是只测热内核。Dashboard 时间另含关闭服务的约半秒。

编译器自身峰值约 146.15 MiB，**不包含在解算进程 RSS 中**。
`recorded_rss_peaks_sum_bytes` 只是两个已记录峰值的和，不是同时发生的进程树
峰值。当前容器 PID 命名空间使 `/proc` 树采样不可靠，因此相关字段为 null，
没有把它当作可靠测量。`--memory-mb` 限制搜索工作区，不是整个进程 RSS；
Python、共享世界数组和编译器另计。

同一机器 BoneGap1 的完全冷启动约缩短 25 倍；已有代码的新进程约缩短
数百倍，但这两个缓存条件不同，**不能把后者称为 200 倍冷启动提升**。
原提交只对 BoneGap1 做了新测量，没有伪造其他攻击的旧版对照。

## 原版无伤验收

`original-engine-final-summary.json` 和 `final-native30/`、`final-native60/`
保留了全部 24 个原版攻击的初始状态、完整输入、模型轨迹、原版状态及事件。
23 个使用原版合法的 30 Hz dt 上限；BoneStab3 使用 60 Hz，传入逐帧真实 dt。
Final 在 30 Hz 下完整通过 1577 帧，代码缓存已有时模型解算约 0.54 s。

验收直接启动原版事件引擎，只替换 DOM、音频及渲染接口；不更改物理和伤害事件。
读取真实 TLPlay 入口状态，用新进程求解，再注入输入到同一原版引擎：每帧
HP=92、KR=0，没有正伤害，恰好最终帧 EndAttack；全部非终止帧逐位匹配
11 个玩家分量，共检查 79,563 个分量。EndAttack 会把原版玩家重置到菜单，
因此最终重置状态单独记录，不将其冒充活动战斗状态的一致性检查。

**时钟属于证据的一部分：30/60 Hz 的通过不能推广到 240 Hz。**
Final 在固定 240 Hz、64 MiB 工作区、8 秒搜索预算下仍返回 `unknown`，见
`final-240-native/`。搜索耗尽不证明无解。未声明任意自定义弹幕、任意时钟和
任意硬件都能在 10 秒内得到完整无伤解；测试机器上这 24 个已验收入口满足目标。
原版引擎验收和模型 `verified` 是不同层级，公共结果保持这种区分。

随机激光回归曾发现一个模型安全而原版受伤的候选。原因是平台 libm 的 atan2
给出 `102.99999999999999°`，V8 给出 `103°`，floor 后使碰撞激光方向相差 1°。
已在两个源环境执行器中使用保留运算顺序的 V8/fdlibm atan2；新增 3036 组
包含符号零、无穷及极端尺度的 JavaScript binary64 对照。修复后重新生成并
重放全部攻击。算法出处与授权说明保留在 `native_math.py` 中。

## 实现改变

- CSV 启动路径延迟旧 Numba 内核和重型旧模块的导入；默认预热只编译小型
  C++ 内核。严格 native 模式不会在预算用尽后悄悄启动旧 LLVM 编译。
- 搜索循环、连续碰撞和精确去重移到 C++；ctypes 调用释放 GIL。
  严格 float64，不启用 fast-math 或 FMA，不量化玩家物理状态。
- 对一个玩家的多个按键共享一次运动计算；蓝心只按跳跃分支计算，碰撞按
  分支和移动状态复用，之后按原版顺序输出边。
- 小宽度多种子探测并行运行；宽前沿用常驻线程划分父状态，共享只读环境，
  每个线程写不重叠的边槽，主线程固定顺序去重、排序和提交。真实线程 CPU
  时钟累计显示 Final 搜索平均使用 5.55–6.81 个核心；短任务未声称 8 线程
  一定更快，已有单线程对照。
- 只保留两层完整状态，父指针宽度允许时使用 uint16，输入使用 uint8；
  复用哈希、排序和边缓冲区，只回溯胜出路线。较宽探测保留有限滚动快照，
  用于恢复之前被宽度剪枝丢弃的路线，无需为每个失败重建整个前缀。
- NumPy 直接填充弹幕几何数组；私有环境构造器拥有状态后原地推进，公共
  resumable API 保留纯操作语义。GetHeartPos 使用当前候选自己的真实观察，
  对话按源事件推进，最后必须通过独立源算子完整重放。
- 不使用攻击名称特判、已保存输入路线或路线缓存。搜索仍是有限前沿启发式，
  不宣称最优或完备；预览只参与排序，不能成为无伤证明。

## 复现

安装 C++17 编译器和项目 Python 依赖。性能测试自动创建空代码缓存。

```bash
python -m pip install -r requirements-native.txt
python -m tools.benchmark_cold_native --workers 8 --repeats 3 \
  --entry-dir tools/optimization-results/final-native30
python -m tools.benchmark_cold_native --waves sans_final --workers 8 --repeats 3 \
  --entry-dir tools/optimization-results/final-native30 \
  --output tools/optimization-results/cold-final.json
python -m tools.benchmark_cold_native --waves sans_bonestab3 --repeats 3 \
  --entry-dir tools/optimization-results/final-native60 \
  --output tools/optimization-results/cold-bonestab3.json
python -m tools.benchmark_dashboard_cold

NOHIT_SECONDS=8 NOHIT_SEARCH_STRATEGY=native \
  NOHIT_BENCH_OUT=tools/optimization-results/replay-new \
  node tools/native_optimized_replay.mjs sans_final sans_randomblaster1
NOHIT_FPS=60 NOHIT_SECONDS=8 NOHIT_SEARCH_STRATEGY=native \
  NOHIT_BENCH_OUT=tools/optimization-results/replay-new60 \
  node tools/native_optimized_replay.mjs sans_bonestab3
```

常规调用应提供原版捕获的入口和相同逐帧时钟，而非只提供心的位置。

```bash
python -m tools.solve_csv c2-sans-fight/sans_final.csv \
  --entry tools/optimization-results/final-native30/sans_final-entry.json \
  --search-strategy native --seconds 8 --workers 8 --memory-mb 64 \
  --out final-new.json
```

`core-regression-final.txt`：171 项通过，覆盖 native/旧 JIT 字节一致性、
线程数不改变证据、剪枝快照恢复、输入依赖、场景验证及旧 CSV 接口。
没有声称整个仓库所有遗留测试通过。Linux/g++ 已实测；其他平台没有本次
性能保证，未安装编译器时可显式使用旧后端。
