# nohit 全正统回合 FRS-DP 求解器与 jcw87 原版底座交接文档 — 2026-10-06

## 1. 接手目标与当前结论

接手总目标：
以官方权威原版 [Bad Time Simulator (Sans Fight)](https://jcw87.github.io/c2-sans-fight/)（`jcw87` 正统 108 项资源）为唯一物理基准底座，使用统一拓扑 DAG-DP（FRS-DP）算法实现对原版全部 23 个正统回合（`sans_*.csv`）的亚秒级求解、240Hz 逻辑步长原版离线单步验算（HP 92 / KR 0 / 0 hits）、以及正常速度本地 8103 端口前台可见浏览器连续三轮无伤实机闭环通关。完成原版全通与机制泛化后，再对极限谱面 `Real HELL` 发起最终攻坚。

当前状态定性结论：
1. **底座纯正性已彻底确立**：已将魔改/衍生版整体移入备份目录 `c2-sans-fight-derivative-backup/`；`c2-sans-fight/` 已 100% 替换为官方 `jcw87/c2-sans-fight`（`gh-pages` 分支）正统资源（包含 23 个官方 `sans_*.csv`、官方 `c2runtime.js` 235KB、官方 `data.js` 236KB 及全部媒体音效）。
2. **切片攻坚完全闭环（Platforms4Hard）**：单一完备拓扑 DAG-DP（FRS-DP，`search_frs_dp_bellman`）已彻底消灭历史 87.75 秒 DFS 瓶颈，实现 **245.86ms 极速热解算（加速 357 倍）**，并在前台真实 Chrome 正常速度下达成**连续三轮完整 EndAttack，HP 92/92/92，KR 0/0/0，0 hits 完全无伤通过**（遥测记录：`tools/real-game/bonesgap1-20261005-194325-726883.json`，候选已固化为 `tools/oracle-plans/sans_platforms4hard-42.json`）。
3. **Milestone 1（通用环境编译器与双平面 C-Space）核心代码已交付**：
   - 类型系统：`nohit/engine/compact_types.py`（定义 `GeometryArray` 与 `CompiledWave`，兼容历史 3 元组并支持强类型属性）；
   - 通用波次编译器：`nohit/engine/compact_wave.py`（41.9KB，内置 `TimelineVM` 连续运动学虚拟机，支持 23 个正统波次，实现白骨/蓝骨双平面 uint64 位打包危险掩码，单次烘焙 < 50ms）；
   - 单元测试矩阵：`test_compact_platform.py`（13/13 通过）、`test_challenger_m1_*.py`（48/48 通过）、`test_compact_wave_all.py`（203/203 通过），全量 264/264 单元测试通过。
4. **E2E 自动化测试基础设施完全闭环**：
   - 全局测试基建文档：`TEST_INFRA.md`、`TEST_READY.md`；
   - 参数化运行器：`tools/test_oracle_replay.mjs` 与 `tools/verify_and_run_live.mjs` 支持全 23 波次驱动；
   - 全量调度套件：`tests/run_e2e.py` **75/75 项真实场景端到端测试 100% 满分通过（耗时 1.43s）**。
5. **当前处于停顿点的具体原因与打开问题（Milestone 1 Gate Iteration 2）**：
   - M1 门禁评估中，代码契约（Reviewer 1 APPROVE）、物理保真（Reviewer 2 APPROVE）、位掩码压力（Challenger 2 APPROVE）、零容忍法医审计（Auditor 1 CLEAN）已获 4 票全绿批准；
   - 对抗挑战者 1（`challenger_1`）触发了有效的一票否决拦截：在 `sans_intro.csv` 中发现正弦骨波（`SineBones`）在波谷极低值时由于未做非负截断产生负高度（`25 - 28 = -3.0`），导致坐标颠倒（`top=232, bottom=230`）。该颠倒包围盒经自机膨胀半径外推后被错误烘焙为 4,755 个幽灵危险像素，在安全区域凭空制造了致死碰撞。
   - 专家复现并锁定了数学根因，双层防御方案已成型，等待落盘。接手人第一步即为落实该修复并签署通过门禁。

---

## 2. 先读这些关键现有产物

以下路径均为工作区相对路径：
- `PROJECT.md`：总指挥建立的系统全景规划（含 F1~F14 功能矩阵与 6 个里程碑路线图）。
- `TEST_READY.md` 与 `TEST_INFRA.md`：全 23 回合 E2E 黑盒验证基础设施接入规范。
- `.agents/teamwork/orchestrator_6/GATE_STATUS.md`：Milestone 1 门禁评估最新表决板。
- `nohit/engine/compact_types.py`：新一代紧凑几何强类型结构体系。
- `nohit/engine/compact_wave.py`：新版通用波次编译器（`TimelineVM` 连续运动学虚拟机与双平面 uint64 烘焙器）。
- `nohit/engine/compact_lattice.py`：核心 FRS-DP 求解器（第 434-621 行 `search_frs_dp_bellman`，245ms 极速贝尔曼等价类折叠）。
- `nohit/engine/compact_solver.py`：解算器入口与阶段计时器。
- `c2-sans-fight/`：官方 `jcw87` 纯正底座（含 108 个文件、23 个官方 CSV 与注入的 TAS 探针）。
- `c2-sans-fight-derivative-backup/`：此前使用的魔改/衍生版完整备份。
- `tools/oracle-plans/sans_platforms4hard-42.json`：已晋升的 Platforms4Hard 连续三轮无伤黄金路线（候选 ID：`1f39f386...`）。
- `tools/real-game/bonesgap1-20261005-194325-726883.json`：Platforms4Hard 正常速度前台连续 3 轮 EndAttack、HP 92/KR 0/0 hits 实机遥测证据。

---

## 3. Git 与工作树未提交状态

当前分支：`main`，无远端。
请严格保护工作树中的未跟踪与修改文件，**切勿执行 `git clean -fd` 或批量重置**。

未提交修改与重要新增：
- `c2-sans-fight/`：底座已同步为 jcw87 正统代码，`index.html` 注入了 `window.TASRunner` 异步等待与测试探针。
- `c2-sans-fight-derivative-backup/`：保留了历史魔改切片备份。
- `nohit/engine/compact_wave.py`、`nohit/engine/compact_types.py`、`nohit/engine/compact_lattice.py`、`nohit/engine/compact_solver.py`。
- `tests/run_e2e.py`、`tests/unit/test_compact_wave_all.py`、`tests/test_m1_challenger_stress.py`。
- `tools/` 下全套辅助与评测脚本（`tools/uv_py.bat` 是稳定 Python 运行器）。

---

## 4. 运行中的服务与守护环境

1. **守护进程保护约束（R5 强制约束）**：
   - **8103 服务**：原版游戏 HTTP 服务器（当前以后台守护任务运行，加载 `c2-sans-fight/`）。访问入口：`http://127.0.0.1:8103/game/index.html`。
   - **8102 服务**：校准与历史服务（当前以后台守护任务运行）。
   - **注意**：系统环境曾发生过服务重启。若接手后发现端口未监听，请执行：
     ```cmd
     tools\uv_py.bat tools\build_kernels.py
     tools\uv_py.bat start_dashboard.py 8103  (以 Daemon 模式启动)
     tools\uv_py.bat start_dashboard.py 8102  (以 Daemon 模式启动)
     ```
2. **Python 运行环境**：
   - 必须使用项目内 `uv` 托管的 Python：
     `tools\uv_py.bat`（内部绑定 `<user>\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe` 并配置了合法 `PYTHONPATH`）。
   - **切勿**直接使用 `.venv\Scripts\python.exe` 启动（该旧 launcher 存在 libffi-8.dll 路径缺失问题）。

---

## 5. 待完成工作与建议接手顺序

### 第一步：落实 SineBones 负高度双层防御（关闭 M1 Gate 2 门禁）
在 `nohit/engine/compact_wave.py` 中实施双层纵深防御：
1. **生成端截断**：定位到 `SineBones` 运动学更新逻辑，将高度计算施加非负约束：
   ```python
   # 确保正弦波谷不穿透地表为负高度
   h = max(0.0, float(h_base + sine_val))
   ```
2. **底层 Numba 烘焙端防御**：在 `_build_geometry_fast_njit` 膨胀写入循环中增加边界合法性守卫：
   ```python
   # 拦截任何倒置或退化的无效包围盒
   if right <= left or bottom <= top:
       continue
   ```
3. **验证门禁**：
   运行压测套件与全量波次单元测试：
   ```cmd
   tools\uv_py.bat -m pytest tests/test_m1_challenger_stress.py -q
   tools\uv_py.bat -m pytest tests/unit/test_compact_wave_all.py -q
   ```
   确认全绿后，在 `.agents/teamwork/orchestrator_6/GATE_STATUS.md` 中签署 `Gate Result: PASSED`。

### 第二步：启动 Milestone 2（Tier 1 正交骨阵求解与实机验收）
针对官方首批正交骨阵波次展开端到端 FRS-DP 求解：
1. **目标波次**：
   - `sans_bonegap1.csv`（单骨缝跳跃，6.6s）
   - `sans_bonegap1fast.csv`（快速骨缝，6.4s）
   - `sans_bonegap2.csv`（错位双骨缝，7.0s）
   - `sans_boneslideh.csv`（横向滑骨，7.7s）
   - `sans_boneslidev.csv`（纵向滑骨，5.97s）
   - `sans_bluebone.csv`（蓝骨静止免伤判定，6.37s）
2. **解算与验证流水线**：
   - 调用通用 FRS-DP 求解器生成候选路线 JSON；
   - 执行 240Hz 原版单步离线验算：
     ```cmd
     node tools/test_oracle_replay.mjs --attack sans_bonegap1 --plan tools/operator-results/compact-bonegap1.json
     ```
   - 执行前台 8103 浏览器连续 3 轮实机闭环验收：
     ```cmd
     node tools/verify_and_run_live.mjs --attack sans_bonegap1 --plan tools/operator-results/compact-bonegap1.json --continuous 3
     ```
   - 验证通过后自动晋升路线至 `tools/oracle-plans/`。

### 第三步：按既定分级梯度向前推进后续 Tier
- **Tier 2（平台全系与骨刺猛摔）**：`sans_platforms1~4` 与 `sans_bonestab1~3`（固化平台生命周期与 9 重摔循环）；
- **Tier 3（加斯特光炮有向射线）**：`sans_intro` 与 `sans_multi1~3`（OBB 射线 C-Space 极速光刻）；
- **Tier 4（终盘全通与 Real HELL 决战）**：`sans_final` 终局大满贯与魔改极限谱面 `Real HELL` 攻坚。

---

## 6. 严禁事项与防作弊红线（保持绝对诚信）

1. **严禁硬编码或预存历史路线**：所有路线必须是由纯动力学状态格推导出的有效解。
2. **严禁修改原版游戏逻辑与参数**：严禁修改 HP（92）、KR（0）、游戏 $dt$、或碰撞判定盒来伪造通过。
3. **严禁回退至无头 C2 快照分支搜索**：必须坚持使用纯数学紧凑状态格（FRS-DP）。
4. **必须在前台可见窗口中进行真实验收**：严禁使用不可见的 Headless 模式进行实机糊弄。
5. **保护用户资产**：切勿杀除无关进程，保留工作区所有未跟踪历史实验记录。
