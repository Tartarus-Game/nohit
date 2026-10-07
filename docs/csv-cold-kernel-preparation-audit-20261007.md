# CSV 首请求冷准备独立审计

审计时启动入口只调用 `canonical_solver.warm_kernel()`；共享 CSV 解算入口实际使用的 bounded/dialogue 递推、去重、恢复与标量验证签名未全部在监听请求前准备。磁盘 Numba 缓存存在，也仍需要在新进程中加载与物化签名。后续获准完成下述最小实现并通过正确性测试，未执行真实关卡求解或性能实验。

## 两次首请求的直接证据

| 运行 | Intro总耗时 | bounded kernel materialization | 环境准备 | dialogue relation / world / verify |
| --- | ---: | ---: | ---: | --- |
| 080740 manifest | 模型41.668319秒；外层请求约42.164秒 | **37.630775秒** | 0.029830秒 | 3.088875 / 0.415963 / 0.441811秒 |
| 新8144运行 | 外层请求11.2080秒 | **7.327723秒** | 0.020887秒 | 2.70303 / 0.309015 / 0.361656秒 |

第一条记录由独立审查直接从完整 manifest 的 `computedPlans[0].plan` 提取，结果在 [intro-cold-preparation-evidence-20261007.json](../scratch/intro-cold-preparation-evidence-20261007.json)。bounded的实际搜索时间只有0.000048秒，因为随后进入dialogue分支。两次dialogue自己的materialization均约0.00033秒，说明重成本已经由先运行的bounded准备阶段支付。

第二条为主任务报告的当前验收观测，未重复读取其完整记录。另有Final同进程重复调用 `_held_trace` 首次7.6128秒、随后0.0092秒的主任务观测，进一步区分了冷准备与热执行。

## 启动遗漏的具体入口

`start_dashboard.py` 当前warm只覆盖旧 canonical DAG 的 `search`、`step_action_into` 的一个入口以及 `collision_query`。源码显示 CSV 另外使用：

| 入口 | CSV调用处 | 合成输入需要覆盖的签名要点 |
| --- | --- | --- |
| `local_relation._expand`、`parallel_expansion._expand_parallel_kernel` | bounded与dialogue的 `prepare_expansion` | 状态float64二维、controls int64一维、start/hold int64；env二维、platform/white/blue三维float64；payload为uint8四维cells、float64三维polygons、三个float64 |
| `bounded_frontier._held_trace` | bounded恢复准备与轨迹重建 | float64二维states、int64一维masks、int64 start/stop、二维env、三维platform |
| `exact_state_dedup._unique_first` | `unique_state_indices` | float64二维states、int64 bit/capacity、uint64 jump_word/hash_mask |
| `selection_buckets._first_representatives` | `_select`→`unique_bucket_indices` | uint64二维raw、uint64 hash_mask、int64 capacity；空前沿不会自然触发选择入口 |
| `discrete_operator.step_mask_into`、`sample_position` | 独立标量/联合验证与目标读取 | float64一维state/env、二维platform；mask为Python/NumPy int64；直接dispatcher需要准备，不能仅依赖在其他JIT函数内内联 |
| `cspace._bake` | 每个binding及dialogue临时world的 `bake_cspace` | 三组float64三维几何、float64 origin/cell、int64尺寸 |
| `compact_wave._build_geometry_fast_njit` | reference编译/标量重放 | 二维float64扁平几何、int32一维counts及int64尺寸 |

实际平台使用9列，状态11列，环境22列；数组长度通常不产生新的Numba类型签名，但dtype、维数、C/A布局、可写性、整型宽度会。后续正确性测试确认上表10个dispatcher在warm后均有签名，第二次调用不新增签名；尚未以新的实际HTTP首请求声称已经消除了所有冷请求成本。

## 最小准备方案与验证建议

已新增 [csv_warmup.py](../nohit/engine/csv_warmup.py) 的 `warm_csv_kernels()`，并在 [start_dashboard.py](../start_dashboard.py) 中HTTP服务器开始监听前调用。内部生成两行小型合法环境、一个完整玩家状态、空几何与空9列平台，不读取CSV、原版状态、任何路线或关卡缓存。

依次执行极小的几何构建/CSpace烘焙、`prepare_expansion` 空前沿（它已准备串行和并行且恢复线程mask）、`_held_trace` 空前沿、完整去重与选择bucket各一个样本，以及标量 `step_mask_into`、`sample_position`、`collision_query` 入口。只保留编译代码，不持有合成轨迹或绑定。按入口记录启动准备秒数；准备失败则不宣告服务ready。

保留每个请求现有的materialization字段作为诊断；准备时间进入startup指标，不能从总延迟报告中隐藏。冷启动、磁盘缓存加载、新进程首请求、同进程热请求分开报告。现有42秒请求不能用去掉编译后的数字冒充实测响应时间。

建议测试：

1. 启动顺序测试确认warm成功后才bind/listen；用函数替身证明warm没有调用CSV解析、求解、路线加载或外部I/O。
2. 独立子进程先warm，再运行固定两tick合成入口探针；比较dispatcher签名集合，确认探针未引入新签名。对特定性能测试可在warm后禁止新签名编译，避免仅靠脆弱的时间阈值。
3. 检查线程mask恢复、合成输入未被修改、第二次warm幂等；用红/蓝/平台/激光的极小合成数据覆盖分支，但不预先求解任何真实关卡。
4. 另起进程分别记录有磁盘缓存与独立空缓存目录的startup时间；不删除共享缓存。只有获得主任务的空闲窗口后执行。

实现正确性结果：[test_csv_warmup.py](../tests/unit/test_csv_warmup.py) 两项通过（0.68秒，现有编译缓存条件下）。测试禁止CSV读取/编译、绑定构造和搜路入口，确认warm不调用它们；检查线程mask恢复、10个dispatcher已物化及二次签名复用；launcher顺序为runtime选择→canonical准备→CSV准备→bind→serve。该耗时是测试结果，不作为用户首请求性能承诺。只修改以上新模块、启动脚本、测试文件，已验收的8144生产源码由主任务提前备份。
