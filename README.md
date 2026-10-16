# nohit

保留两条主线：**CSV 原游戏求解与验收**、**Godot / GameMaker 通用 Live SDK**。
旧算法、旧页面和研究原型保存在分支 `codex/history-before-cleanup-20261017`；当前分支为 `codex/latest-only`。

## CSV 真机流程

Python 3.10+，以及支持 C++17 / OpenMP 的 `g++` 或 `clang++`。Windows 可安装 MSYS2 UCRT64 GCC；启动入口会自动识别标准安装目录。

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

命令行可复用已捕获的完整入口与时钟：

```powershell
.venv/Scripts/python.exe -m tools.solve_csv attack.csv --entry entry.json --seconds 30 --workers 8 --out build/route.json
.venv/Scripts/python.exe -m tools.verify_csv_native_acceptance evidence.json --output build/verdict.json
```

当前只有 C++ 原生前沿搜索；代码首次使用时编译。长谱可用 `--observation-chunk-ticks 480 --observation-preview-ticks 480 --observation-goal-retries` 分窗搜索；其他参数见 `--help`。
求解、原游戏执行与独立验收的具体接口见 [CSV 说明](docs/csv-runtime.md)。

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
