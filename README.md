# nohit：原版回放与状态格候选求解

原版浏览器游戏为本目录 `c2-sans-fight` 中的 C2 导出。Python 快核负责候选生成，原版引擎回放和正常时间三回合无伤分开记录。

后续主线与具体实现契约见 [新计算模式实现规格](docs/new-compute-implementation.md)，最新落地情况见 [Platforms4Hard纯计算核](docs/new-compute-platforms4hard.md)，能力边界见 `tools/new-compute-capabilities.json`。该切片已实现独立CSV环境编译、纯微步动力学、完整浮点状态比较和不裁剪的可达性搜索；实时钟鲁棒性及其他回合覆盖仍需补齐。已有原版快照搜索/事件策略路线单独归类。

本轮新计算验证服务在8103端口。打开 [从头计算并自动TAS](http://127.0.0.1:8103/game/index.html?mode=single&attack=sans_platforms4hard&seed=42&compute=compact&acceptance=1&continuous=1)，页面会先等待路线生成，再启动游戏与验收。此入口不使用路线/关卡预处理缓存。

命令行独立重算：`.venv/Scripts/python.exe tools/solve_compact_platforms.py`。默认使用水平1px、垂直2px余量；输出明确区分候选和原版验收状态。

## 启动

现有 Windows 虚拟环境可直接使用。首次安装依赖后，或修改快核源码后，在游戏请求前明确构建算子：

```powershell
uv pip install --python .venv/Scripts/python.exe -r requirements-native.txt
.venv/Scripts/python.exe tools/build_kernels.py
.venv/Scripts/python.exe start_dashboard.py 8080
```

打开 [原版全部回合](http://127.0.0.1:8080/game/coverage.html) 或 [A/B 算子对比](http://127.0.0.1:8080/game/operators.html)。后者显示服务冷启动时间，每次重新求解并进行原版加速回放，不替换默认实时验收路线。本轮已启动的验证服务使用8102端口，8080为下次自行启动的示例。

`build/kernels` 是本机 CPU、Python/Numba 版本与源码对应的机器码产物，不含几何张量或路线。构建后的服务禁止请求期即时编译；版本、源码时间戳或产物变更需要显式重建。没有构建产物时仍支持开发模式，首次调用可能触发十几秒编译。产物不作为跨 Python 版本或跨机器通用二进制发行包。

## 两版算子

- A：按时间层并行生成距离场，把实际单点/水平两点/垂直两点/四角探针压入四个 nibble；整数坐标不会错误扩大到相邻锚点。
- B：在 A 上复用无平台情况下的四个垂直微步，使用按代价的每带限额堆选择与代数访问标记。平台保留原来的逐支撑面检查。

两版保留现有动作集、量化、余量、状态带、稳定 tie-break 和 beam 限额；没有增加完整性或全局最优性保证。`operator=baseline|a|b` 选择版本；`fresh=1` 强制重新烘焙和求解。默认仍为 baseline；平台上的 B 目前没有稳定速度收益。

```powershell
.venv/Scripts/python.exe tools/benchmark_operators.py --repeats 5
.venv/Scripts/python.exe tools/profile_cold.py --operator b --empty-compiler-cache
.venv/Scripts/python.exe tools/profile_cold.py --operator b --built-runtime
.venv/Scripts/python.exe -m pytest tests/unit/test_source_operators.py -q
```

差分检查只验证算子实现一致，不代替实际游戏验收。冷启动细分与限制见 `tools/operator-results/COLD.md`；各回合阶段耗时见 `tools/operator-results/latest.json`。

## 原版例子与版本管理

全部 24 个 CSV 已重新在原版引擎运行：16 个 EndAttack，8 个正常死亡，无基础设施错误；7 个加速无伤，5 个保留历史实时三回合通过证据。其余待机基线尚不是无伤候选。矩阵与逐帧记录保存在 `tools/real-game/coverage-latest.json`。

根仓库包含实际运行的游戏源码和资源。原游戏仓库的 Git 元数据保存在本地 `.vendor-git/c2-sans-fight.git`，可用 `git --git-dir=.vendor-git/c2-sans-fight.git status` 检查；两份参考仓库 `repo_badtime`、`repo_jcw87` 保持独立并忽略于根仓库。根仓库未设置远程，也未推送。
