# 当前 CSV 原生核心与性能复现

当前保留 Round 8 C++17 核心及其 Python 环境构造、动态目标 / 对话衔接和独立源复验。搜索仍为有限宽度前沿，完整玩家状态使用 binary64 精确比较，不量化状态，不启用 fast-math。未找到候选返回 `unknown`。

核心实现包括按实际前沿规模清理哈希表、分片精确去重、连续数组排名、按需分配的父指针历史、共享输入分支运动结果，以及保守扫掠检查后的空白位移快速路径。发生旧墙、移动平台或任何不确定接触时，继续使用原版逐像素扫描。排名仅决定截宽保留顺序，不构成安全证明。

`memory_mb` 约束内部搜索工作空间；源世界数组、Python 对象和编译器内存另计，因此它不是整个进程 RSS 上限。`seconds` 约束候选搜索，编译、世界构造和强制复验另有开销。

## 当前基准入口

`tools.benchmark_round8_request` 只测当前实现。每次启动独立 Python 进程并重新构造世界、搜索和复验；仅允许复用已编译代码。入口由实际原版捕获得到，不能用其他时钟或初态的结果替代。

```powershell
.venv/Scripts/python.exe -m tools.benchmark_round8_request attack.csv --entry entry.json --repeats 3 --workers 8 --out build/benchmark.json
.venv/Scripts/python.exe -m tools.benchmark_round8_request attack.csv --entry entry.json --empty-code-cache --repeats 3 --out build/benchmark-cold.json
```

`solve_seconds` 包含当前请求的模型求解及复验；`external_wall_seconds` 另外包含子进程启动、导入与序列化。空代码缓存会将首次编译计入请求。`peak_rss_bytes` 是解算进程的峰值，不含编译器子进程。结果同时绑定 CSV、入口、C++ 源码和候选指纹；`original_replay_passed` 单独报告，基准本身不执行原版游戏。

## 历史测量范围

2026-10-08 冻结版在同一入口、交替新进程对照中，Final 模型求解中位数由第七轮 10.6519 秒降为第八轮 9.2734 秒，约 1.15 倍；峰值 RSS 由 237.48 MiB 降为 209.82 MiB。两个空代码缓存 Final 进程耗时 13.2789、14.2761 秒，仍超过 10 秒。上述测量不保证当前机器、不同源谱或不同入口的延迟。

历史冻结版另有 Normal 60 Hz 连续 24 轮原版事件引擎通过记录；Haoge 的 23 个非 Final 攻击为独立进程通过，Haoge Final 仍为 `unknown`。这些记录只适用于各自绑定的源实现、输入与时钟，不能直接作为清理后代码的新验收。

完整旧基准、Round 7 对照源码、计时插桩、逐轮报告及原始验收证据保存在 `codex/history-before-cleanup-20261017` 分支和本地历史归档。当前分支移除了旧对照及插桩选项。重新执行当前原版验收的方法见 [CSV 接口说明](csv-runtime.md)。
