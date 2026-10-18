# nohit

保留两条主线：**CSV 原游戏求解与验收**、**Godot / GameMaker 通用 Live SDK**。
旧算法、旧页面和研究原型保存在分支 `codex/history-before-cleanup-20261017`；清理基线为 `codex/latest-only`。

## 免编译 Windows / Linux 下载

每次提交自动构建两个平台的独立运行包，内含 Python 与预编译 C++，用户设备无需配置编译环境。
前往 [Actions 下载成功构建的 Artifact](https://github.com/Tartarus-Game/nohit/actions/workflows/build.yml)。
Windows 运行自解压 EXE 后启动解压目录的 `nohit.exe`；Linux 解开 `.tar.xz` 后运行 `nohit`，浏览器打开 `http://127.0.0.1:8080`。
每个平台压缩包设有 20 MB 硬上限，详情见 [自动构建说明](docs/portable-builds.md)。

## CSV 真机流程

Python 3.10+。从源码构建原生核心需要 C++17 编译器、xmake 和 vcpkg；第三方依赖由根目录 `vcpkg.json` 固定。多线程使用 `std::thread`，不依赖 OpenMP。详见 [原生构建说明](docs/native-build.md)。已有匹配源码及 CPU 的预编译镜像时，运行不需要这些构建工具。

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-native.txt
.venv/Scripts/python.exe start_dashboard.py 8080
```

打开 <http://127.0.0.1:8080/>，导入 CSV 后选择：

- 「在 Dashboard 解算」：直接查看源模型的搜索进度、结果和轨迹。默认轻量预览；高级设置可启用完整危险几何。
- 「原游戏解算并执行」：另开静音游戏页，捕获真实起点后求解并执行。Dashboard 保留进度，并接收本次求解结果与游戏执行状态。

两种入口均按脚本规模自动选择预算与分窗配置，必要时自动加宽重试一次。进度显示真实阶段、持续耗时和已上报的搜索计数；tick 表示当前搜索或复验的位置，不是整项任务的完成率。手动参数放在高级设置中；Normal 模式使用同一 CSV 求解核心连续运行各回合。

导入时默认禁用 CSV 中直接调用的 `DamagePlayer`（包括回血），显示警告并保留延时；碰撞伤害仍照常验收。已核实没有处理器的 `setmaxhp`、`damafeeplayer`、`NoTooth` 等调用仅警告并继续。原文件、清理后的执行源和修改记录分别保留，求解器与原游戏使用同一份执行源。其他未支持的机制仍按行显示。

自动 CSV 和战役测试默认静音，只关闭音频输出，保留播放时钟和回调。

Real HELL 削弱版历史通过记录使用 `artifacts/realhell-weakened-20261017/source.csv`，另补有终点；该记录只适用于对应测试副本，见[具体差异](artifacts/realhell-weakened-20261017/README.md)。

Real HELL 固定测试从零求解并完整验证已达到 **10 秒内**；默认观测求解使用 240/240 分窗。安装源哈希与 CPU 匹配的预编译算子后，新进程及空运行时编译缓存的三次结果为 **8.33 / 8.41 / 8.43 秒**。详见[10 秒优化与复现报告](docs/optimization-realhell-10s-20261018.md)，以及[上一轮历史对照](docs/optimization-realhell-20261017.md)。

命令行可复用已捕获的完整入口与时钟：

```powershell
.venv/Scripts/python.exe -m tools.solve_csv attack.csv --entry entry.json --seconds 30 --workers 8 --out build/route.json
.venv/Scripts/python.exe -m tools.verify_csv_native_acceptance evidence.json --output build/verdict.json
```

当前使用 C++ 原生搜索。先执行 `vcpkg install --triplet x64-linux`（Windows 根据工具链选择 triplet），再执行 `python -m tools.build_native --install`，通过 xmake 安装原生镜像。安装 `requirements-accelerated.txt` 后执行 `python -m tools.build_accelerators --native`，可同时预编译 Python 数值算子；求解时无需 JIT。未安装匹配原生镜像时使用 xmake 现场编译，编译计入该次冷启动耗时，运行时不会自动下载依赖。推荐 `--workers 4 --width 1024 --memory-mb 512`；含 GetHeartPos 的源默认分窗求解并自适应移动。其他参数见 `--help`。
求解、原游戏执行与独立验收的具体接口见 [CSV 说明](docs/csv-runtime.md)。

失败会显示最后安全 tick、累计游戏秒数和实际 CSV 执行游标，并可选择回放、导出当前保留的安全前缀。高级设置的「尽量少操作」会让搜索优先减少方向键组合的切换；命令行对应 `--objective fewest_operations`。有限搜索和有上限的前缀导出均不宣称穷举或全局最优。

新增「人类友好」模式（`--objective human_friendly`）：分档优先搜索更大余量，再减少换键，避免相反方向同按，仅在对话可确认时按 Confirm；自动生成空间余量、局部时序扰动、重点 tick／秒／CSV 游标和路线难度报告。该报告不是人类成功率或弹幕无解证明，详见 [人类友好搜索与难度报告](docs/human-friendly-20261018.md)。

上传的 Real HELL 最终补全版修复记录见 [失败诊断、少操作目标与完整回放报告](docs/realhell-final-and-diagnostics-20261018.md)。已修正 BlackScreen 同帧新建对象的销毁选择，并加入静止蓝骨／场外红心的释放输入尾部证明。

vcpkg / xmake 构建、Highway 与 pdqsort 的逐项对照见 [库加速实验报告](docs/library-acceleration-20261018.md)。该报告保留失败试跑及耗时波动，不宣称所有样本都能在 1 秒内完成。

连续 tick 的 C++ 批量推进及最新完整回放见 [批量推进实验](docs/idle-batching-20261018.md)：本轮原游戏验收解算 6.783 秒，仍未达到 1 秒目标；同参数开关对照未测出明确的整体提速。

全部内置 CSV 的批量测试入口为 `python -m tools.benchmark_samples --out build/samples --seconds 8`。
每项使用原 C2 捕获的入口和精确时钟，独立进程从零求解并完整复验；缺失文件、unknown 和错误都会保留。
单个 GetHeartPos 行的源默认使用 240/720 分窗，其他观测源继续使用 240/240。基准包含独立验证，不包含安装时编译；原引擎回放另列。结果及限制见[全样本优化报告](docs/optimization-samples-20261018.md)。

## 通用 Live SDK

见 [接入说明](generic-engine/README.zh-CN.md) 和 [快速开始](generic-engine/portable/QUICKSTART.zh-CN.md)。SDK 的 Python 工具只用标准库，独立于 CSV 求解器；Godot 必须使用与游戏匹配的版本。

```powershell
python generic-engine/tools/nohit.py install C:/path/to/game
python generic-engine/tools/nohit.py doctor C:/path/to/game
python generic-engine/tools/nohit.py solve C:/path/to/game --godot C:/path/to/godot.exe --output build/sdk-first
```

保留 Godot 3/4 Live SDK、三个已接入项目和少量验收记录。GameMaker 为尚未完成原生运行验收的协议模板。

## 目录

| 目录 | 当前职责 |
| --- | --- |
| `nohit/engine/` | CSV 源算子、C++ 搜索、独立复验及完成证明 |
| `nohit/dashboard/` | 单一 Web 入口、CSV API、进度与证据存储 |
| `c2-sans-fight/` | 原 Construct 2 游戏、CSV 控制与伤害观察 |
| `generic-engine/` | 通用 SDK、现有适配器和打包工具 |
| `hrzq/`、`data/` | 内置攻击包与样本索引；用户导入留在 `data/user/` |
| `tools/`、`tests/` | 当前命令行、基准、契约与回归测试 |
| `artifacts/` | 精选验收证据；[Real HELL 削弱版记录](artifacts/realhell-weakened-20261017/README.md) |
| `build/` | 可再生成的本机编译缓存、运行证据和测试输出，不提交 |

## 验证

```powershell
.venv/Scripts/python.exe -m pip install pytest
.venv/Scripts/python.exe -m pytest tests -q
node --test tools/*_test.mjs tests/unit/*_test.mjs
python generic-engine/tools/test_unpack_sample.py
```

模型候选必须经过逐 tick 复验；只有原游戏实际运行并核对输入、HP/KR、伤害、观察与合法结束事件后，才能报告真机通过。
`unknown` 表示预算或模型能力内尚未求得路线，不能据此断言无解或“有无缝”。真实游戏修改后应重新生成证据；历史记录只适用于记录中的源身份。

架构与历史恢复方式见 [项目说明](docs/architecture.md)。`c2-sans-fight/` 保留原 Bad Time Simulator 项目的作者与许可信息；Live SDK 的许可位于 `generic-engine/portable/LICENSE.txt`。
