# 持键内核行索引回归审计（2026-10-07）

当前代码已包含修正后的共享持键内核，两类反例也已进入正式测试。本轮没有重复添加测试或修改生产文件；运行现有测试并通过进程内错误索引替换，确认测试确实能发现这些错误。

## 当前调用与历史报告的区别

当前 `nohit/engine/parametric_dag.py` SHA256 为
`DF907D8644B676E4F07CD3FD2633DF540BA1D6E324EC98C194624EAC877CC5F1`。
`_advance` 调用 `parametric_kernels.hold_kernel` 时传入完整的环境及平台时间表、绝对 `tick/stop`、视图起点 `start`。共享内核使用绝对 `future` 读取环境和平台，用 `future-origin_tick` 读取已切片的碰撞视图。持键内存在尚未绑定的目标观察时，仍走逐 tick 的环境扩展分支。

历史 `787A2DA7...` 版本没有这个融合调用，不能把当时的回退描述成当前状态。两个对应备份仍在原路径，字节和哈希相同。本轮测试及两次 mutation 的生产 DAG 前后哈希均为上述 `DF907D...`。

`scratch/check_hold_equivalence.py` 仍引用旧的私有 `_hold_kernel` 接口，不能直接作为当前共享内核的可运行验收脚本。它同时沿用 `tick-start` 切完整平台表的旧约定，无法替代对非零 `first` 活跃平台的实际反例。

历史 `kernel-boundary-diff.json` 固定的是 `BAC493B5...`：同参数模式 2043 项状态/判定相等，但实际调用索引模式有 220 项判定差异（208 次漏碰撞、12 次误碰撞），2043 项最终状态仍全部相同。其 416 项非零 `first` 样本的平台行内容均相同，不能据此确认活跃平台索引正确。这些是历史证据，本轮没有把旧内核重新接入生产。

## 正式测试与失败敏感性

执行：

```powershell
.\tools\uv_py.bat -m pytest -q tests/unit/test_parametric_hold_regressions.py tests/unit/test_parametric_kernels.py
```

结果：**20 passed in 0.69s**。

- `test_advance_checks_each_future_hazard_row`：10 项。分别在目标观察前后，让未来第 1、2、3、4 个微 tick 单独出现危险行，另含安全对照。保持玩家状态不变，直接要求实际 `_advance` 拒绝危险边，故不能被“状态字节一致”掩盖。
- `test_advance_uses_absolute_active_platform_rows_after_target`：2 项。真实 `GetHeartPos` 后 `first=8`，新旧平台行都活跃但高度不同。正确平台在第 12 tick 把玩家带至 `y=41.2`；危险变体同时要求 `_advance` 因触骨而返回 `None`，安全变体要求正确的位置和速度。
- `test_hold_uses_absolute_motion_and_local_collision_ticks`：8 项。覆盖持键 1/4 tick、视图起点 0/7、安全/危险，环境每行的 dt 刻意不同。

随后在两个独立 Python 进程里替换 `parametric_dag.hold_kernel` 的进程内引用，保留实际 `_advance` 调用、原始 `step_mask_into` 和 `collision_query`，只引入指定索引错误。没有改写任何生产源文件，也没有借用 scratch 实现。

| 替换的索引错误 | 测试结果 | 被覆盖的真实调用 |
| --- | --- | --- |
| 危险行改用持键局部计数 `0..3` | **13 failed, 7 passed**；8 项逐微 tick 危险测试、1 项平台危险测试及4项一般危险测试失败 | 37 次，其中16次 `origin_tick>0` |
| 完整平台表误用 `future-origin_tick` | **2 failed, 18 passed**；正是活跃平台的安全和危险两项失败 | 37 次，其中16次 `origin_tick>0` |

两次 pytest 返回码均为 1；审计驱动确认这个预期的失败后返回 0。这证明现有正式测试能够杀死两个错误索引变体。测试没有要求生产永远采用某一种融合实现；此处进程内替换仅用于验证当前接入点的覆盖能力。

复现 mutation 的核心（先导入 pytest 和对应模块，在新的 Python 进程运行）：

```python
from nohit.engine import parametric_dag as dag
from nohit.engine.discrete_operator import step_mask_into
from nohit.engine.cspace import collision_query

variant = "hazard"  # 另一次进程设为 "platform"

def wrong_rows(white, blue, env, platforms, state, mask,
               tick, stop, origin_tick, payload):
    q = state.copy()
    for local, future in enumerate(range(tick + 1, stop + 1)):
        platform_row = future - origin_tick if variant == "platform" else future
        hazard_row = local if variant == "hazard" else future - origin_tick
        step_mask_into(q, mask, env[future], platforms[platform_row], q)
        if collision_query(white, blue, hazard_row, q, 0., payload):
            return True, q
    return False, q

dag.hold_kernel = wrong_rows
```

此后对上述两个正式测试文件执行 `pytest.main`，应获得表中的失败结果。该替换仅活于当前进程。

## 文件核对

以下文件均存在；本轮直接读取本地字节计算 SHA256。

| 文件 | 字节数 | SHA256 |
| --- | ---: | --- |
| `nohit/engine/parametric_dag.py` | 25578 | `DF907D8644B676E4F07CD3FD2633DF540BA1D6E324EC98C194624EAC877CC5F1` |
| `nohit/engine/parametric_kernels.py` | 3963 | `F34928151E619C10178043E2354FE40F61B118E2D2235C9800750A9F792F8916` |
| `tests/unit/test_parametric_hold_regressions.py` | 5150 | `6E79ED34786CD17BA7869ACAFFDEA71A7154B34D5475792D00F281E69D088528` |
| `tests/unit/test_parametric_kernels.py` | 2094 | `131DA70764BAB299F9FC6684C7B139D6C89839006F8F7502C21D2C05D668F454` |
| `scratch/parametric_dag_before_performance.py` | 30956 | `BAC493B5DDE63788B08803AC7EF95C48BD1F21871C7B4AA3D8B88F3E037F9596` |
| `scratch/parametric_dag_accepted_FINAL.py` | 29070 | `787A2DA7B780B1730DB6F4F0394D826A2FE628E83BE8F68742D529AD597CE1E6` |
| `scratch/parametric_dag_FINAL_adopted.py` | 29070 | `787A2DA7B780B1730DB6F4F0394D826A2FE628E83BE8F68742D529AD597CE1E6` |
| `scratch/parametric_dag_batched_verified.py` | 34796 | `480F870A3FBE0C9BD2E4BF8D474D623F27399E56A2B56E32D5EF8180D4951402` |
| `scratch/kernel-boundary-diff.json` | 2310664 | `E98B1FF157E729CEFBCB7414A04491C8B29E1A61F76E749B56DBE9DD47972B59` |
| `scratch/kernel-boundary-diff.py` | 63550 | `56709A792F9788B40B7253017E15BBC50D5DC1F58D37E70E1B1F43450AAA2466` |
| `scratch/check_hold_equivalence.py` | 5151 | `CC42717BF925FB341FD321B06FCE8BC16538C2AA232F029F0EE4A81DECE214B6` |
| `scratch/validator-report.log` | 13254 | `5A3C8B87FE1D3C4B6EDF6A9180EFA3C9FDEFC1DDD559C97EA044768F23D200E4` |

这些测试确认所述索引回归的实际调用行为。它们没有证明所有游戏模型正确、完整搜索完备性或某一关一定有解，也没有测量 CPU 吞吐。当前内核在第一次碰撞时早退，旧私有内核会继续完成持键；拒绝边的内部末状态不属于 `_advance` 输出路线，不能将该实现差异误报为接受路线不等价。
