# 10 秒目标验收记录

- `benchmark.json`（完整逐窗统计保存在 `benchmark-full.json.gz`）：最终源码，三次新进程＋空运行时编译缓存；已安装预编译代码，包含完整独立验证。中位数 8.406 秒，最大外部总耗时 8.625 秒。
- `native-summary.json`：原 C2 独立捕获新入口、重新求解和完整回放；求解 8.538 秒，外部 Python 进程 8.718 秒。HP 92、KR 0、无 DamagePlayer，25805 次输入、469 次观测及 283844 个非终点状态分量一致。
- `native-entry.json.gz`、`native-route.json.gz`、`native-replay.json.gz`：以上验收的完整入口、路线和原引擎回放。gzip 解压后保留原 JSON 字节；不得用已有路线代替从零计时。
- `scalar-build.json`、`native-build.json`：源派生数值模块、C++ 镜像及 CPU/编译选项绑定；安装构建耗时没有混入求解数字。
- `python-tests.log`、`node-tests.log`：1420 项通过、1 项预期失败；314 项通过。
- `earlier-warm-benchmark.json.gz`：此前显式分窗、热代码的三次测量，保留历史而不与最终组混算。
- `summary.json`：关键指标和证据文件 SHA256。

输入仍是仓库的 `artifacts/realhell-weakened-20261017/source.csv`，本轮没有再次改谱、改时钟、降低碰撞精度或跨请求缓存路线。详细复现与边界见 `docs/optimization-realhell-10s-20261018.md`。
