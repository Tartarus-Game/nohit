# 全部内置 CSV 示例：性能优化与实测

这轮尚未达到“所有示例 1 秒内”。覆盖样本索引的全部 43 项：42 个文件存在，1 项缺失；另加入既有削弱版 Real HELL，实际运行 43 个案例。没有按旧 `nohit` 标签筛选，也没有改动任一测试源、速度、时钟或碰撞规则。

## 当前结果

默认 8 秒搜索预算、1024 宽度、4 workers、512 MiB：**36 个完整模型验证通过，7 个 unknown**。另对 `branch1` 使用 8192 宽度、8 workers、1024 MiB、30 秒预算，从零求解并验证耗时 **13.151 秒**；累计有 **37/43** 个案例得到完整模型验证路线。其余 6 个仍未通过，不能据此断言无解。

**29 个案例连续三轮新进程总耗时均低于 1 秒，三轮最大 0.925 秒。** 包括 24 个有合法 EndAttack 的常规原版案例，以及 cece、part2、part3、test-short、xinxin。原版完整 Real HELL 另列为 unknown。

## 计时边界

- Linux x86_64，Intel Xeon Platinum 8370C，Python 3.12.14、NumPy 2.3.5，CPU 配额 8。性能不能视为所有机器上的保证。
- 每项为独立 Python 进程，从 CSV 和捕获入口重新生成世界、搜索、逐 tick 独立复验、生成完整执行与完成证明。所有实际 tick 都执行；控制宏只减少决策分支。
- “求解”包含世界构建、搜索、完整模型验证和结果组装；“进程总耗时”另外包含进程启动、导入、入口解析、证据压缩写盘。原 C2 游戏回放是另一次验收，未算入求解的 1 秒数字。
- 主表使用**安装完成后的代码镜像**：四个数值模块和 C++ 镜像。没有跨请求世界、历史路线或答案缓存；预编译的是通用代码。所有主表测量均未导入 Numba。
- **首次编译没有隐藏进这 1 秒结果。** 另以 `sans_final` 禁用全部可选数值镜像、指定现场编译器、清空原生缓存实测：首次构建与求解 **6.696 秒**，进程总耗时 **6.876 秒**，首次原生装载/编译 **5.945 秒**。该次验证通过，`native_load.compiled=true`、`bundled=false`。因此不能把所有输入的“从源码第一次启动也小于 1 秒”说成已经达成。
- 所有现存原 CSV 的 SHA256 与索引一致。使用原 C2 事件引擎捕获的起点、确认键状态和 40000 项精确 dt；弱化版继续使用原固定入口，不再削弱。前后比较共享同一份捕获入口。

## 保留的改动

1. EOF 完成证明改用现有独立标量算子，避免在最后阶段额外导入/JIT Numba。
2. 为独立验证器增加严格浮点的骨骼数值循环，覆盖单体、密集集合、出生/移除、负尺寸、NaN、无穷和有符号零。原普通物化编译器仍保留对象方程作差分对照；验证不调用 C++ 搜索物理。
3. 在已确认整条预期轨迹有限的前提下，逐 tick 用原始双精度字节比较状态，减少重复 NumPy 临时数组。状态相等和真实碰撞检查均保留。
4. 无观测的完整对话源直接进入普通可行路径搜索，减少不必要的全局角落目标尝试；限制长世界小宽度预探测的耗时，并调整长世界控制宏的调度。
5. 单个 GetHeartPos 行的脚本默认使用 240/720 窗口，其他观测源保持 240/240。各次实际观测仍取自本次候选自己的运动。
6. 控制宏遵守调用方的有序候选选择要求，较低优先级任务不能因先完成而取消更高优先级任务。完整已知世界仍可选先找到的合法路线。定时预算和其他搜索分支仍会使慢例耗时波动，未承诺所有输入完全确定或最优。
7. 修正 SansSlam 的原生参数范围判断与数值转换：`HandLeft`、越界值按原事件忽略；十六进制及指数形式按原数值表达式处理。另对无未来 slam 的静止红心保留可证明安全的 slam-damage 配置，从而修复 test-short 的 EOF 完成证明。

## 主要变化

以下只比较构建＋搜索＋完整模型验证。首次失败的条目显示其原状态，不能把失败返回的时间当作有效解算速度。

| 案例 | 优化前 | 本轮最终 |
| --- | ---: | ---: |
| `can/sans_final` | 6.628 s | 0.692 s |
| `hrzq/cece-nohit` | 0.539 s | 0.099 s |
| `hrzq/part2` | 0.928 s | 0.440 s |
| `hrzq/part3` | 1.353 s | 0.490 s |
| `hrzq/branch2` | 5.164 s | 1.430 s |
| `hrzq/branch3` | 4.334 s | 1.712 s |
| `hrzq/hot-nohit` | 2.069 s | 1.370 s |
| `hrzq/part4-nohit` | 5.948 s | 4.615 s |
| `hrzq/part5` | error | 2.246 s |
| `regression/realhell-weakened` | 8.387 s | 7.820 s |

## 全量表

“总耗时三轮最大”仅为首轮总耗时低于 1 秒并追加两次复测的 29 项；其他条目保留完整首轮结果。表中 unknown 不计入任何达标数。

| 案例 | 原求解 s | 新求解 s | 新进程总计 s | 总耗时三轮最大 s | 模型结果 |
| --- | ---: | ---: | ---: | ---: | --- |
| `can/sans_bluebone-nohit` | 0.064 | 0.071 | 0.195 | 0.195 | 通过 |
| `can/sans_bonegap1-nohit` | 0.092 | 0.086 | 0.209 | 0.209 | 通过 |
| `can/sans_bonegap1fast-nohit` | 0.094 | 0.090 | 0.218 | 0.232 | 通过 |
| `can/sans_bonegap2-nohit` | 0.097 | 0.082 | 0.215 | 0.221 | 通过 |
| `can/sans_boneslideh-nohit` | 0.087 | 0.086 | 0.214 | 0.250 | 通过 |
| `can/sans_boneslidev` | 0.055 | 0.058 | 0.184 | 0.190 | 通过 |
| `can/sans_bonestab1` | 0.056 | 0.046 | 0.172 | 0.187 | 通过 |
| `can/sans_bonestab2` | 0.050 | 0.048 | 0.169 | 0.214 | 通过 |
| `can/sans_bonestab3` | 0.046 | 0.047 | 0.161 | 0.175 | 通过 |
| `can/sans_final` | 6.628 | 0.692 | 0.843 | 0.925 | 通过 |
| `can/sans_intro` | 0.094 | 0.109 | 0.231 | 0.231 | 通过 |
| `can/sans_multi1` | 0.066 | 0.077 | 0.215 | 0.215 | 通过 |
| `can/sans_multi2` | 0.091 | 0.089 | 0.228 | 0.249 | 通过 |
| `can/sans_multi3` | 0.094 | 0.080 | 0.208 | 0.208 | 通过 |
| `can/sans_platformblaster` | 0.087 | 0.089 | 0.207 | 0.230 | 通过 |
| `can/sans_platformblasterfast` | 0.083 | 0.091 | 0.217 | 0.222 | 通过 |
| `can/sans_platforms1` | 0.096 | 0.086 | 0.202 | 0.232 | 通过 |
| `can/sans_platforms2` | 0.126 | 0.124 | 0.236 | 0.236 | 通过 |
| `can/sans_platforms3` | 0.119 | 0.119 | 0.234 | 0.245 | 通过 |
| `can/sans_platforms4` | 0.140 | 0.138 | 0.246 | 0.305 | 通过 |
| `can/sans_platforms4hard` | 0.204 | 0.139 | 0.247 | 0.286 | 通过 |
| `can/sans_randomblaster1` | 0.193 | 0.209 | 0.323 | 0.338 | 通过 |
| `can/sans_randomblaster2-nohit` | 0.162 | 0.178 | 0.308 | 0.337 | 通过 |
| `can/sans_realhell_extreme` | 0.386 | 0.390 | 0.510 | — | native_search_limited |
| `can/sans_spare-nohit` | 0.029 | 0.023 | 0.131 | 0.136 | 通过 |
| `hrzq/branch1` | 8.125 | 8.134 | 8.253 | — | native_search_limited；加宽后通过 13.151 s |
| `hrzq/branch2` | 5.164 | 1.430 | 1.650 | — | 通过 |
| `hrzq/branch3` | 4.334 | 1.712 | 1.908 | — | 通过 |
| `hrzq/cece-nohit` | 0.539 | 0.099 | 0.221 | 0.233 | 通过 |
| `hrzq/hell` | 8.035 | 8.035 | 8.158 | — | native_observation_budget |
| `hrzq/hot-nohit` | 2.069 | 1.370 | 1.565 | — | 通过 |
| `hrzq/part1` | 8.022 | 8.033 | 8.143 | — | native_search_limited |
| `hrzq/part2` | 0.928 | 0.440 | 0.603 | 0.691 | 通过 |
| `hrzq/part3` | 1.353 | 0.490 | 0.663 | 0.725 | 通过 |
| `hrzq/part4-nohit` | 5.948 | 4.615 | 4.801 | — | 通过 |
| `hrzq/part5` | — | 2.246 | 2.540 | — | 通过 |
| `hrzq/ruins` | 3.038 | 2.939 | 3.080 | — | terminal_invariant_unproven |
| `hrzq/snowdin` | 4.082 | 4.203 | 4.319 | — | native_scope_or_resource_limit |
| `hrzq/test-short` | 0.180 | 0.059 | 0.173 | 0.173 | 通过 |
| `hrzq/waterfall` | 5.848 | 5.096 | 5.309 | — | 通过 |
| `hrzq/xinxin-nohit` | 0.754 | 0.333 | 0.491 | 0.551 | 通过 |
| `hrzq/xtest` | 8.027 | 8.025 | 8.139 | — | native_observation_budget |
| `user/real-hell` | — | — | — | — | 文件缺失 |
| `regression/realhell-weakened` | 8.387 | 7.820 | 8.426 | — | 通过 |

## 未解决的项目

- `sans_realhell_extreme`、`hrzq/part1`：常规与额外加宽搜索仍未求得完整路线。
- `hrzq/hell`、`hrzq/xtest`：观测窗口搜索达到预算，额外 30 秒尝试仍为 unknown。
- `hrzq/snowdin`：源末尾存在静止蓝骨，当前“EOF 后危险清空”规则无法建立完整终点；未把它改成一个虚构的 EndAttack。
- `hrzq/ruins`：EOF 仍保留平台，当前空世界无限尾部证明拒绝 `active_platforms_not_zero`。
- `data/user/real-hell.csv`：索引条目存在而文件缺失；同 SHA256 的原版文件 `c2-sans-fight/sans_realhell_extreme.csv` 已独立运行，保留该缺失状态。

这些包含搜索能力、终止证明和文件完整性问题，不能统一称为“已经 1 秒通过”。

## 正确性与原引擎

最终 Python **1450 通过、1 项预期失败**；Node **314 通过**；SDK 解包工具 **7 项通过**。新增对控制宏优先级、独立数值循环字节一致性、SansSlam 原生参数和 EOF 无额外 JIT 的检查。

24 个常规原版、part4、削弱版 Real HELL、加宽 branch1，共 **27 个真实案例**在原 Construct 2 事件引擎中逐 tick 回放通过，HP 92、KR 0、DamagePlayer 0、目标采样与非终点状态一致、EndAttack 合法。仅有 DOM、音频与渲染 stub，未更改原 c2runtime.js、data.js 或事件方程；这不是 GUI 录像。

另有 1 个合成参数谱面在原 C2 回放通过，覆盖本次修正的无效文本、越界、小数、十六进制、指数与空值。原引擎回放后，最终实现重新独立复验了 27 个案例的相同完整输入字、轨迹和源观测；该步骤只验证已有证据，**不是新的求解计时，也没有将这些路线读入任何新求解**。EOF 案例的通过数仅代表完整模型验证，未声称它们全部已经通过原引擎终点验收。

## 复现

```bash
python -m pip install -r requirements-accelerated.txt
python -m tools.build_accelerators --native
python -m zipfile -e artifacts/performance-samples-20261018/inputs.zip build/sample-inputs
python -m tools.benchmark_samples --out build/samples --entries-from build/sample-inputs --seconds 8
python -m tools.benchmark_samples --out build/samples-wide --entries-from build/sample-inputs \
  --case hrzq/branch1 --seconds 30 --width 8192 --workers 8 --memory-mb 1024
python -m pytest tests -q
node --test --test-reporter=tap tools/*_test.mjs tests/unit/*_test.mjs
python generic-engine/tools/test_unpack_sample.py
```

不指定 `--entries-from` 时工具会自行启动原 C2 捕获每项入口；新的捕获时钟可能与本表不同。所有运行证据逐项绑定源、入口、全部引擎源码与本机二进制。缺失文件、异常、超时和未完成求解都会出现在 summary.json 中。

证据保存在 `artifacts/performance-samples-20261018/`：前后完整记录与三轮复测、固定输入 ZIP、所有成功路线、原引擎回放及最终独立复验、源码/二进制身份和测试日志。历史加宽探索单独保存，没有混入默认参数的通过数或时间。

改动位于本地 `codex/performance-realhell`，本轮没有向 GitHub 写入。代码包含完整源码与当前 Linux/CPython 3.12/本机 CPU 匹配的机器码；其他平台可从源码构建。尚未达到所有示例 1 秒内，也未证明绝对理论极限。
