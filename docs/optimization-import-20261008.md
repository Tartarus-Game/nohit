# 优化版集成与本机性能实测（2026-10-08）

本文件记录：交付包 `nohit-source-v7` 如何进入本仓库、哪些文件被刻意改动、
在本机（Windows / i9-13900HX）上重跑出来的数字、以及这些数字**不能**说明什么。

## 结论

- 交付包已按声明路径**逐字节**安装进本项目。`DELIVERY_MANIFEST.json` 声明的
  1954 个文件中，1951 个与交付冻结完全一致，2 个是刻意的本机兼容改动，0 个缺失。
- 全部 73 个 `nohit/engine/**` 文件与冻结一致；性能内核
  `nohit/engine/native_frontier.cpp` 的 sha256 为
  `a581129d4963c9c88c3b2a7398b6301e8dce875ac87c2efa669f48ebb8dec185`，
  与第八轮报告声明的"当前性能源码 SHA256"相同，因此下面测的就是被验证过的那个内核。
- 本机实测复现了交付声明的主要方向，绝对数字不同（硬件与系统都不同）：

| 指标 | 交付报告（Linux, EPYC 9V74） | 本机（Windows, i9-13900HX） | 本次结论 |
|---|---:|---:|---|
| 移动算子压力（10 万状态） | 4.45× | **4.24×** | 同向，输出逐字节一致 |
| Final 模型求解 round7→round8 | 10.6519 s → 9.2734 s（1.15×） | 7.2666 s → 6.6790 s（**1.088×**） | 同向，见证指纹一致 |
| Final 峰值 RSS | −11.6% | 227.0 → 206.7 MiB（**−8.9%**） | 同向 |
| Final 进程 CPU 总用时 | +7.4% | **+12.3%** | 同向（用更多 CPU 换更少墙钟） |
| Final 空代码缓存冷启动（外部墙钟） | 13.28 / 14.28 s | **10.20 / 10.12 s** | 未导入 Numba/LLVM |
- 与本项目**原有搜索路径**（`--search-strategy fixed`）相比，同一入口、同一时钟：

| 攻击 | 旧路径 | 优化版 native | 结果一致性 |
|---|---:|---:|---|
| `sans_bonegap1`（409 tick） | 8.397 s 解出 | **0.128 s 解出** | 到达 tick、game_seconds、verified 全部相同 |
| `sans_final`（3154 tick） | 45 s 预算内 `unknown`，最深 tick 2562 | **6.753 s 解出** | 优化版给出完整已验证路线 |

## 交付包是什么

- `DELIVERY_MANIFEST.json`：`format=nohit-source-v7`，`base_commit=479597f`，
  1954 个文件，每个文件带 `bytes` 与 `sha256`。
- 它是**完整项目根**：`nohit/`（包）、`tools/`、`tests/`、`docs/`、`data/`、
  `c2-sans-fight/`、`haogesans-export/`，外加 `OPTIMIZATION.patch`
  （相对 `479597f` 的全部源码改动）与 `RUN_OPTIMIZED.md`。
- 交付包**不含**仓库独有的 `haoge-runtime/`、`tools/haoge/`、`docs/haoge-run.md`，
  也不含 `hrzq/`（自制攻击包，仓库未跟踪）。

## 集成方式

```
479597f  (交付 base)
  └─ ce3575b  round8 optimized source: base + OPTIMIZATION.patch
321? 320ea64 (haoge)  ─┐
                       ├─ 9d5871b  Merge round 3-8 optimized source into haoge
  ce3575b ────────────┘
        └─ fe73646  dashboard: NOHIT_GAME_DIR / HP-KR 策略（本条刻意保留）
        └─ 654ff77  tools: benchmark_round8_request 的 Windows 移植
```

合并策略是**交付冻结在它包含的每个路径上获胜**：交付是一个 1954 文件、
自带证据与测试的完整冻结，逐块合并求解器语义会同时破坏两边的验证链，
所以任何交付能提供的路径都以交付内容为准，仓库独有的文件（`haoge-runtime/`、
`tools/haoge/`、`docs/haoge-run.md`）原样保留。`pre-round8-import` 标签指向合并前的
`320ea64`，旧状态一行 `git checkout` 就能取回。

安装与校验脚本（不进版本库，位于 `scratch/round8-import/`）：

- `install_delivery.py --delivery <交付根>`：按 manifest 逐文件写入并回读校验；
- `verify_install.py --delivery <交付根>`：对每个声明文件比对项目路径与交付路径的字节。

本次结果：`identical=1951, differing=2, missing=0`。完整的交付副本保存在
`scratch/delivery-round8/`（766 MiB，`scratch/` 已被忽略），因为每个文件现在都在
项目路径上，这个副本只当校验基线用，可以随时删除。

## 刻意保留的两处差异

1. `nohit/dashboard/server.py`（`fe73646`）。交付冻结把本分支在 base 之后加的
   两条仪表盘能力去掉了，而仓库独有的 `haoge-runtime/` 验收流程依赖它们：
   `NOHIT_GAME_DIR` 指定另一份同源 Construct 2 导出作为 `/game/` 的服务目录；
   连续对局记录可以声明自己的 `baselineHP` 与**有界**的 `maxKR`/`krPolicy`，
   而不是硬编码 92/0。两者都是**追加式**的：不带 `baselineHP`/`maxKR` 的记录仍然是
   原来的严格判定（HP 必须等于 92、KR 必须恒为 0）。这次改动没有触碰任何
   `nohit/engine/**`，所以交付的引擎源码哈希与上面的性能数字都不受影响。
2. `tools/benchmark_round8_request.py`（`654ff77`）。该工具在模块层 `import resource`，
   Windows 上根本起不来，无法运行交付自带的复现命令。改成可选导入 + 用
   `GetProcessMemoryInfo` 取峰值 RSS，测量口径、子进程协议与输出字段全部不变。
   同样没有触碰求解器源码。

另外 `.gitignore` 保留仓库版本：它是交付版本的严格超集（只多了忽略上游 haoge 资源的
若干行），且与求解器无关。

## 被交付冻结覆盖掉的仓库改动

以下 9 个路径上的改动在合并后由交付冻结接管。它们属于同一分支在 `479597f` 之后
的另一条工作线，交付冻结里没有对应内容：

| 路径 | 仓库原改动 | 合并后 |
|---|---|---|
| `nohit/engine/csv_completion.py` | `vitality_events()` / `AUDITED_VITALITY_COMMANDS` | 交付版本（导入改为函数内惰性，冷启动优化） |
| `nohit/engine/csv_solver.py` | 上报 `scripted_vitality_events` / `scripted_damage_present` | 交付版本（改为 `health_model` + `allow_scripted_healing/damage` + `source_contract`，并有 `test_scripted_healing_admission.py` 覆盖） |
| `nohit/engine/canonical_solver.py` | 同上审计常量 | 交付版本 |
| `nohit/engine/compact_wave.py` | 使用 `executable_resize_callback` | 交付版本 |
| `nohit/engine/resumable_wave.py` | 使用 `executable_resize_callback` | 交付版本 |
| `nohit/engine/parametric_environment.py` | 使用 `executable_resize_callback` | 交付版本（回到 `tlresume or audited_no_action_function`，更保守） |
| `nohit/engine/native_function_dispatch.py` | 新增 `executable_resize_callback()` | 交付版本（该函数保留为死代码，无人调用） |
| `tests/unit/test_timeline_pause_resize.py` | 随上述引擎改动更新 | 交付版本（与交付引擎自洽） |
| `nohit/dashboard/server.py` | NOHIT_GAME_DIR + HP/KR 策略 | **已按上文恢复** |

判断依据：两条工作线解决的是同一批问题（脚本化治疗/伤害的准入、可执行 resize 回调、
换一份同源导出做验收），交付冻结的写法更通用且自带测试（`source_contract.py`、
`test_scripted_healing_admission.py`），所以以交付为准，只把仓库独有 Node 流程真正
依赖的仪表盘能力恢复了回来。

## 本机运行环境与必需设置

| 项 | 值 |
|---|---|
| CPU | 13th Gen Intel Core i9-13900HX，24 核 / 32 逻辑核 |
| Python | 3.12.13（`.venv`，uv 管理） |
| numpy / numba / pytest | 2.5.3 / 0.68.0 / 9.1.1 |
| C++ 编译器 | `C:\msys64\ucrt64\bin\g++.exe`（MSYS2 MinGW-w64，GCC 16.2.0，x86_64-w64-mingw32） |
| Node | 已安装（原版游戏回放验收用，本次未跑） |

优化版的 native 路径**必须有 C++17 编译器**：`native_backend.load_backend()` 用
`shutil.which('g++')` 或 `clang++` 找编译器，找不到就抛
`Native CSV backend needs g++ or clang++; install a C++17 compiler or select fixed search`。
本机原本没有任何 C++ 编译器（`cl.exe`/`g++`/`clang++` 均不在 PATH），本次用
`pacman -S mingw-w64-ucrt-x86_64-gcc` 装进了已有的 MSYS2（新增 22 MiB 下载 / 约 488 MiB 安装）。
`C:\msys64\usr\bin\g++.exe` 是 MSYS/MSYS2 变体（目标 `x86_64-pc-cygwin`），
编出来的 DLL 依赖 `msys-2.0.dll`，在原生 CPython 里 **加载失败**
（`WinError 1114` + `NtCreateDirectoryObject ... 0xC0000022`），所以必须用 ucrt64 那一套。

跑 native 路径需要三个环境设置，都不改交付源码：

1. `PATH` 前置 `C:\msys64\ucrt64\bin`。编译期 `cc1plus` 与运行期 DLL 都靠它。
2. `TMP` / `TEMP` / `TMPDIR` 指向工作区内的可写目录
   （本次 `.cold-cache\cxx-tmp`）。本会话的沙箱不允许写系统 `%TEMP%`，
   g++ 会报 `Cannot create temporary file in C:\Users\lf\AppData\Local\Temp: Permission denied`；
   正常的非沙箱 Windows 会话没有这个问题。
3. 空代码缓存运行（`--empty-code-cache`）会把内核编到一个全新的临时目录，
   而 Python 3.8+ 的 `ctypes.CDLL` 用 `LOAD_LIBRARY_SEARCH_*`（**不看 PATH**），
   所以那里找不到 `libstdc++-6.dll` / `libgcc_s_seh-1.dll` / `libwinpthread-1.dll`。
   解决办法二选一：把这三个 DLL 复制到内核所在目录（普通运行即可），
   或让进程用 `os.add_dll_directory()` 注册工具链目录
   （本次用 `.cold-cache\pyshim\sitecustomize.py` + `PYTHONPATH`，零源码改动）。

复现命令（PowerShell，`$R` 为仓库根）：

```powershell
$env:PATH = 'C:\msys64\ucrt64\bin;' + $env:PATH
$env:NOHIT_NATIVE_CACHE = "$R\.cold-cache\native-round8"   # 该目录需含上面三个运行库 DLL
$env:TMP = $env:TEMP = $env:TMPDIR = "$R\.cold-cache\cxx-tmp"
$env:PYTHONPATH = "$R\.cold-cache\pyshim"                  # 仅空代码缓存运行需要
```

## 实测数据

原始输出在 `scratch/round8-import/`（`summary.json` 与各 `bm-*.json`、`e2e-*.json`）。

### 1. 移动算子压力（`tools/benchmark_movement_sweep.py`）

10 万状态、25 px/轴位移、20% 状态处于旧墙接触位置必须回退扫描；
同一进程内交替跑交付的第七轮 C++ 源码与本次内核，5 次取中位数。

| | 中位数 |
|---|---:|
| round7 C++ | 20.122 ms |
| round8 C++ | 4.741 ms |
| **加速** | **4.24×**（交付声明 4.45×） |

全部输出与 round7 逐字节相同（脚本自带断言），另抽 512 个状态与 Python 标量玩家方程
逐位比对通过。该基准只覆盖这个算子压力样本，不代表整关求解速度。

### 2. Final：round7 vs round8（`tools/benchmark_round8_request.py --compare`）

交付报告给的复现命令，同一 CSV、同一入口（`round7/normal-delivery/23-sans_final-entry.json`）、
原生 dt、`--workers 8 --width 8192 --seconds 45`，每版 3 个新进程交替。

| 指标（中位数） | round7 C++ | round8 C++ | 变化 |
|---|---:|---:|---:|
| 模型求解 | 7.2666 s | 6.6790 s | 1.088× |
| 进程外部墙钟 | 7.4296 s | 6.8336 s | 1.087× |
| 进程 CPU 总用时 | 13.9844 s | 15.7031 s | +12.3% |
| 峰值 RSS | 227.0 MiB | 206.7 MiB | −8.9% |
| 见证指纹 | `4c9171e6d92655a5` | `4c9171e6d92655a5` | 完全相同 |

三对运行全部 `status=candidate_found`、`verified=true`，且新旧找到的是**同一条路线**。
`bonegap1` / `bluebone` 两关在第一次探测就解出（~0.08 s），因此新旧几乎无差别
（1.008× / 1.027×），指纹同样一致。

### 3. 空代码缓存冷启动（`--empty-code-cache`）

只清代码缓存、不清操作系统文件缓存，每个样本一个新进程，含首次 C++ 编译、
导入、完整求解与独立模型验证：

| 样本 | 外部墙钟 | 其中求解 | 本次是否新编译 | 是否导入 numba |
|---|---:|---:|---|---|
| 1 | 10.195 s | 7.161 s | 是 | 否 |
| 2 | 10.121 s | 7.133 s | 是 | 否 |

交付报告在 Linux 上是 13.28 / 14.28 s；两边都没达到"含冷启动低于 10 秒"的目标。

### 4. 端到端：优化版 native vs 本项目旧搜索路径

`tools/solve_csv.py --search-strategy native|fixed`，同一 CSV、同一入口、同一 `--seconds`。

| 攻击 | 策略 | 状态 | 到达 tick | `wall_seconds` | game_seconds |
|---|---|---:|---:|---:|---:|
| `sans_bonegap1` | `fixed`（旧） | candidate_found, verified | 409 | 8.397 | 6.82 |
| `sans_bonegap1` | `native`（新） | candidate_found, verified | 409 | **0.128** | 6.82 |
| `sans_final` | `fixed`（旧） | **unknown（wall_budget）** | 2562 | 45.407 | — |
| `sans_final` | `native`（新） | candidate_found, verified | **3154** | **6.753** | 52.57 |

这说明集成带来的是**可用性**上的变化，而不只是常数加速：同一预算下旧路径解不出的
Final，新引擎 6.8 s 给出完整路线。`fixed` 的 8.397 s 里含 Numba 内核的首次编译
（磁盘缓存已存在），所以这个比值偏向乐观，不能当成纯算法加速比。

## 验证

- **字节级安装核对**：`verify_install.py` → `identical=1951, differing=2（均为上文的刻意改动）, missing=0`。
- **引擎冻结完整性**：73 个 `nohit/engine/**` 文件全部与交付一致；
  `native_frontier.cpp` sha256 = `a581129d…`，与交付报告声明的性能源码一致。
- **交付自带定向回归**：`tests/unit` 中交付补丁涉及/新增的 11 个文件
  （`test_native_backend`、`test_native_math`、`test_native_spatial_index`、
  `test_csv_solver`、`test_csv_warmup`、`test_resumable_wave`、`test_control_quotient`、
  `test_source_verification`、`test_scripted_healing_admission`、
  `test_same_tick_slam_speed`、`test_linear_observation_replay`）
  → **148 passed, 1 failed**。唯一失败是
  `test_default_cpu_workers_respect_affinity_quota_and_api_limit`，
  它 monkeypatch `os.sched_getaffinity` 与 `/sys/fs/cgroup/cpu.max`，
  在 Windows 上不存在，属平台限制而非集成缺陷。
- **全量 `tests/unit` 与合并前基线对比**：见下一节。
- **结果一致性**：所有 round7/round8 成对运行产出同一见证指纹；
  移动算子输出逐字节相同；端到端 native/fixed 在 bonegap1 上到达同一 tick。

### 全量单元测试：合并前 vs 合并后

（本节数字由 `scratch/round8-import/pytest-unit-premerge.txt` 与
`pytest-unit-current.txt` 对比得到，忽略了 3 个依赖 `scratch/` 夹具、在 worktree 里
无法收集的测试模块。）

PLACEHOLDER_TESTS

仓库文档本来就说明"完整仓库旧测试集并非全部通过"（第六轮报告保留了既存失败比较），
所以这里的目标不是全绿，而是**确认集成没有引入新的失败**。

## 局限

- 交付报告的数字来自 Linux / EPYC 9V74 / g++ 13.3，本次来自 Windows / i9-13900HX /
  g++ 16.2.0。两边**不可直接相减**；有意义的对照是同机同编译器的 round7 vs round8，
  以及同机的 native vs fixed。
- 样本量小（每版 3 个新进程），且本机是混合架构（P 核/ E 核），
  绝对延迟会随负载波动；这里的结论只到"方向一致、量级一致"。
- `Haoge Final` 在交付里本身就是 `unknown`（本轮诊断 120 s 仍未解出），本次没有重跑
  Haoge 全流程（需要 Node + 原版事件引擎回放，且交付的 23 条验收记录绑定交付源码哈希）。
- 交付包不含 `hrzq/`（自制攻击包），它仍是仓库未跟踪的本地资产。
- 本次没有跑原版游戏的逐帧验收（`tools/native_optimized_replay.mjs` /
  `tools/native_replay_batch.py`），因此没有任何"已在原版游戏中通过"的新声明。
- Windows 上 `benchmark_cold_native.py`、`benchmark_solver_request.py`、
  `benchmark_dialogue_certificate.py`、`benchmark_baseline_cold.py`、
  `benchmark_dashboard_cold.py` 仍不可直接运行（依赖 `resource` / `/proc`），
  本次只移植了实际使用的 `benchmark_round8_request.py`。

## 复现清单

```powershell
# 0. 环境（见上）
# 1. 安装核对
.venv\Scripts\python.exe scratch\round8-import\verify_install.py --delivery scratch\delivery-round8

# 2. 移动算子压力
.venv\Scripts\python.exe -m tools.benchmark_movement_sweep --out movement.json --states 100000 --repeats 5

# 3. Final 与新旧的成对对照
.venv\Scripts\python.exe -m tools.benchmark_round8_request c2-sans-fight/sans_final.csv `
  --entry tools/optimization-results/round7/normal-delivery/23-sans_final-entry.json `
  --compare --repeats 3 --out final-paired.json

# 4. 冷启动
.venv\Scripts\python.exe -m tools.benchmark_round8_request c2-sans-fight/sans_final.csv `
  --entry tools/optimization-results/round7/normal-delivery/23-sans_final-entry.json `
  --empty-code-cache --repeats 2 --out final-cold.json

# 5. 端到端 旧/新
.venv\Scripts\python.exe -m tools.solve_csv c2-sans-fight/sans_final.csv `
  --entry tools/optimization-results/round8/normal-delivery/23-sans_final-entry.json `
  --search-strategy native --seconds 45 --width 8192 --workers 8 --memory-mb 256 --out native.json
.venv\Scripts\python.exe -m tools.solve_csv c2-sans-fight/sans_final.csv `
  --entry tools/optimization-results/round8/normal-delivery/23-sans_final-entry.json `
  --search-strategy fixed  --seconds 45 --width 8192 --workers 8 --memory-mb 256 --out fixed.json
```
