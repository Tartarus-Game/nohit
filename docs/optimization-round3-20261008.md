# 第三轮优化与可复现测量（2026-10-08）

本轮修复了小宽度误入旧 JIT 后端、重复验证越来越长的观察前缀、
重复复制及哈希完整时钟序列、碰撞算子反复扫描补齐空槽等问题。
两项原版任务的整进程冷启动超过 300 倍；这不是所有任务均达到 300 倍的声明。
原版攻击 CSV、`c2runtime.js`、`data.js` 均未修改。

## 同条件冷启动对照

基线是原始提交 `479597f6faac3442d66238fd3fee296cbee7b2b8` 的独立检出。
同一台 AMD EPYC 9V74 主机，Python 3.12.14、NumPy 2.3.5、Numba 0.68.0、
LLVM 包 llvmlite 0.50.0、g++ 13.3。进程 CPU 配额为 8 核，亲和性可见 9 核，
容器内存限额 8 GiB。未在并行负载下测量这组结果。

使用同一原版入口、完整 30 Hz 时钟、宽度 3000、最大 40000 tick。
基线搜索预算 60 秒，新实现 8 秒；两者均实际完成，而非比较预算超时。
每次独立 Python 进程，Numba 缓存和本地 C++ 代码缓存均为空；没有路线缓存。
时间从父进程启动子进程前计至退出后，包含导入、编译（如需要）、搜索、
独立逐帧验证及 JSON 输出。文件系统和操作系统页缓存没有人为清空。
基线每项测一次；优化后每项测五次，以下使用中位数，原始记录全部附带。

| 原版任务 | 原版冷启动 | 优化后冷启动中位数 | 加速 | 原版进程峰值 RSS | 优化后峰值 RSS 中位数 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Spare | 46.1345 秒 | 0.1264 秒 | 364.91× | 627.05 MiB | 29.85 MiB |
| BoneStab2 | 46.8737 秒 | 0.1406 秒 | 333.27× | 628.05 MiB | 30.48 MiB |

这两项通过有严格时间和步数上限的通用落地跳跃预检找到完整路线，因此无需
启动 JIT 或 C++ 编译器。预检使用原标量运动和碰撞算子，成功后仍独立验证。
不按攻击名称分派，也不存储既有路线；预检失败即进入 C++ 搜索。

证据：`tools/optimization-results/round3-spare-baseline.json`、
`round3-bonestab2-baseline.json`、`round3-preflight-cold.json`。

## 全流程覆盖和限制

23 项原版攻击在实际捕获的 30 Hz 入口解算，BoneStab3 使用实际 60 Hz 入口。
每项新进程、空代码缓存，均返回经过独立验证的完整路线：
整进程耗时范围 **0.132–2.340 秒**，包含编译。
BoneStab3 另测三次，最慢 0.199 秒。
Dashboard 空缓存启动、首次 HTTP CSV 解算、场景回放、服务关闭共 **2.514 秒**。
常规解算进程峰值 RSS 为 29.85–119.14 MiB；编译器子进程最高 151.44 MiB。
不能把不同进程在不同时刻的峰值相加后当作实测同时峰值。

同一份最终引擎源码在未经修改的 C2 原版事件引擎中回放这 24 项攻击：
全程 HP=92、KR=0，没有 DamagePlayer 调用；非终止帧共比较 **79563** 个
玩家状态分量，全部精确一致。终止 tick 必须与原版 EndAttack 一致；
原版切换菜单时的最终状态重置另行记录。运行环境只替代 DOM、声音和渲染。
每份证据绑定 CSV、原版运行时、数据、解算方案及全部引擎源码的 SHA-256。
运行不是读取既有路线来代替搜索，附带路线仅供审计。

**固定 240 Hz 的 Final 仍返回 unknown，未找到完整无伤路线。**
这个诊断使用另一条时钟序列，不可用 30 Hz 的成功回放代替。
`round3-final240/` 保留本轮诊断（在最后两项性能记账/时钟共享变更之前生成）。
也没有证明所有攻击、所有初态、旧后端或自定义机制均在 10 秒内完成。

最新证据在 `round3-native30/`、`round3-native60/`、
`round3-original-summary.json`、`round3-cold-suite30.json`、
`round3-cold-bonestab3.json` 和 `cold-dashboard-http.json`。
上一轮报告的数据是历史数据，不能替代本轮绑定的验收。

## 异常慢路径为什么慢，如何修改

1. **小宽度误入旧后端。** 以前 auto 模式宽度小于 128 会直接走原 JIT，
   少量工作反而支付数十秒编译成本。现在宽度是搜索资源，不决定启动哪个编译器。
   用户显式指定旧后端或旧对话资源控制时仍保留原路径。
2. **观察验证的平方增长。** 原实现每次 GetHeartPos 都重新编译并重放整个
   已有前缀。新验证在实际原版观察点取样，线性编译、线性独立玩家重放，
   再用完整真实历史绑定并逐字节核对整个环境，避免缩减正确性检查。
   同时保持传送、平台移动、新建、销毁和立即缩放的原版阶段顺序。
3. **重复复制/哈希时钟。** 同一请求的已验证 dt 序列变为内部不可变对象；
   身份仍覆盖完整序列及未来后缀，后续环境绑定直接共享。外部传入数组仍先复制，
   不能通过修改调用方数组改变解算时钟。
4. **碰撞的补齐槽和重复 SAT 几何。** 每帧只扫有效范围，凸四边形的
   AABB、轴和投影只计算一次，共享给全部候选和线程。保留内部空洞、原始顺序、
   闭边界接触和浮点运算语义；不通过放宽碰撞来换速度。
5. **搜索分配、重复状态和多核。** 使用滚动状态数组、紧凑父索引/动作、
   复用哈希及扩展缓冲区；运动分支和碰撞结果复用。独立组合搜索和宽前沿扩展
   使用持久 C++ 工作线程，共享只读世界、各写独立输出，主线程确定性合并。
   精确状态去重不依赖坐标量化。短任务往往提前证明成功，不需等待全部工作线程。

64 MiB 参数限制搜索工作区，不是总进程 RSS 限制；共享环境和碰撞索引另有记账。
`shared_world_bytes` 是输入数组大小，额外索引大小见 `native_code.collision_index_bytes`。
NumPy/source VM 的世界数据仍有按帧矩形数组；本轮没有宣称彻底消除这部分内存。

## 观察验证单项算子测量

使用合成的 1600 次 GetHeartPos、1601 tick，旧验证与新验证共用当前 source VM
和同一组路线、入口、时钟。验证结果的历史与绑定身份完全一致。
旧验证 **19.9068 秒**，新验证 **0.0586 秒**，**339.51×**。
这是暖导入、仅验证算子的测量，不能混入整任务冷启动加速表。
800 次观察的另一记录为 4.6524→0.0272 秒，体现旧路径的平方增长。
旧实现源码保存在 `tools/reference/previous_observation_certifier.py`，可直接复测。

## 回归及复现

本轮集中回归 **207 项通过**，记录在 `round3-core-regression.txt`。
包括原标量/C++ 状态及碰撞一致性、原版数学、控制商、对话和目标历史、
源观察阶段、时钟身份、无 Numba 冷路径和小宽度请求。
这不是整个仓库所有测试的通过声明。
编译使用 `-ffp-contract=off -fno-fast-math`，不使用放宽浮点规则。
V8/fdlibm atan/atan2 的许可证和来源保存在对应实现中。

安装原有 Python 依赖及 g++/clang++。Node 用于原版运行时验收。
从项目根目录执行：

```bash
python -m tools.benchmark_cold_native --entry-dir tools/optimization-results/round3-native30 \
  --waves sans_spare sans_bonestab2 sans_final --repeats 5 --workers 8
python -m tools.benchmark_observation_verification --observations 1600 \
  --out tools/optimization-results/observation-recheck.json
python -m tools.benchmark_dashboard_cold
NOHIT_PYTHON=python NOHIT_SEARCH_STRATEGY=native NOHIT_SECONDS=8 \
  NOHIT_BENCH_OUT=tools/optimization-results/recheck \
  node tools/native_optimized_replay.mjs sans_spare sans_bonestab2 sans_final
NOHIT_PYTHON=python NOHIT_FPS=60 NOHIT_SEARCH_STRATEGY=native NOHIT_SECONDS=8 \
  NOHIT_BENCH_OUT=tools/optimization-results/recheck60 \
  node tools/native_optimized_replay.mjs sans_bonestab3
```

基线复测先单独检出上述原始提交，然后：

```bash
python -m tools.benchmark_baseline_cold --baseline /path/to/original-checkout \
  --wave sans_spare --entry tools/optimization-results/round3-native30/sans_spare-entry.json \
  --output tools/optimization-results/baseline-recheck.json
```

附带完整源码、原版资源、测试、基准程序、验收 JSON、变更补丁和文件哈希清单。
不附带编译后的二进制、Numba 缓存或 Python 虚拟环境。
