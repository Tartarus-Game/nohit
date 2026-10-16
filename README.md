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

打开 <http://127.0.0.1:8080/>，选择内置 CSV 或导入文件，在原游戏捕获入口后自动求解、执行并记录无伤证据。Normal 模式使用同一 CSV 求解核心连续运行各回合。

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
node --test tools/*_test.mjs
python generic-engine/tools/test_unpack_sample.py
```

模型候选必须经过逐 tick 复验；只有原游戏实际运行并核对输入、HP/KR、伤害、观察与合法结束事件后，才能报告真机通过。
`unknown` 表示预算或模型能力内尚未求得路线，不能据此断言无解或“有无缝”。真实游戏修改后应重新生成证据；历史记录只适用于记录中的源身份。

架构与历史恢复方式见 [项目说明](docs/architecture.md)。`c2-sans-fight/` 保留原 Bad Time Simulator 项目的作者与许可信息；Live SDK 的许可位于 `generic-engine/portable/LICENSE.txt`。
