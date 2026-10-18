# vcpkg / xmake 与 C++ 库加速实验（2026-10-18）

先保存的基线为 `9b568239bbb3abd925cb78a4cb8effd6d45e8803`，随后在 `codex/performance-realhell` 开发。命令行推送因缺少凭据失败，已连接 GitHub 的写接口返回 `403 Resource not accessible by integration`；本轮未成功推送远端。已有基线和新增代码均保留为本地提交。

## 构建和实现

- 原生核心现在通过 `xmake.lua` 构建；`tools.build_native` 负责隔离配置目录、安装镜像和身份清单。运行时的源码编译也调用 xmake，未改用其他第三方包管理器。
- `vcpkg.json` 固定 baseline `bf19794383e8fb95eba5aa553235bc8ec2271688`。实测 xmake 3.1.2、GCC 13.3、Linux x86_64 / AMD EPYC 9V74。
- Highway 1.4.0：将没有命中空间索引的矩形遍历改为批量 SIMD 比较，保留 binary64 运算、NaN 比较语义、白／蓝骨判断和标量尾部。静态 SIMD 目标随 CPU 构建设置选择，没有额外的 libhwy 动态库依赖。
- pdqsort 2019-07-30#2：用于搜索排名的全序排序，原始索引为最终裁决。稳定排序及其他排序保持原实现。
- 四边形轴投影也曾尝试 SIMD，但局部测量更慢，已撤掉该路径。默认同时启用两个保留的库；可分别关闭，见 [构建说明](native-build.md)。第三方许可随源码提供。

## 完整 Real HELL 对照

输入和上一轮相同：最终补全版仅按现有默认导入流程禁用第 4 行 `DamagePlayer,0`；弹幕数量、速度和内容未削弱，没有补 EndAttack。未处理的原文件存在非有限 KR 问题，见 [上一轮说明](realhell-final-and-diagnostics-20261018.md)。准备后 CSV SHA256 为 `fcef25222b9c0a96949de5dbc6e3cc35fff4a84e95a82ebf9f3c4174178fcc2a`。

保存的原版 60 Hz 入口／时钟 SHA256 为 `c5b478d6834b58ff1e32b8bbab437896f606848f835d744d1967b3953c72f477`。搜索 width=8192、workers=4、memory_mb=1024、seconds=30，EOF 策略为 `eof_hazards_drained`。每项在新进程中从零运行源程序和独立验证；只复用编译后的代码及输入时钟，未复用路线或世界。库组合按轮次轮换顺序，旧版本另在未修改的独立工作区重跑三次。

| 版本 | 三次解算耗时（秒） | 成功次数 | 成功中位数（秒） |
| --- | --- | --- | --- |
| 原版本 `9b56823` | 10.134 / 15.128 / 8.994 | 3/3 | 10.134 |
| xmake 标准库版 | 15.124 / 12.623 / 9.255 | 3/3 | 12.623 |
| 仅 Highway | 12.611 / 12.871 / 28.330（unknown） | 2/3 | 12.741 |
| 仅 pdqsort | 9.216 / 9.657 / 8.616 | 3/3 | 9.216 |
| Highway + pdqsort | 9.191 / 8.792 / 8.707 | 3/3 | 8.792 |

两库合用相对原版本的本轮中位数缩短约 **13.24%**。这是小样本实测，搜索分支竞争和主机调度会影响路线与耗时，不能当作固定倍数。首次额外组合试跑为 unknown，已保存；不计入随后定义的三轮交错对照。另一次新的完整原游戏验收中，解算耗时 **12.746 秒**，同样保留。这些结果不支持“每次都在 10 秒内”的结论。

上述时间包括独立模型验证，不含依赖安装和 xmake 编译；本次本机原生构建约 8 秒。未证明“首次源码编译加完整解算 ≤10 秒”。

## 原游戏回放与边界一致性

两库合用版本重新求解后，在未修改的原 Construct 2 `c2runtime.js` 和 `data.js` 中完整回放 **27,953 tick / 465.883 秒**。HP 始终 92、KR 始终 0，没有 DamagePlayer 调用，实际目标读取和逐 tick 玩家状态匹配。原版 EOF 和静止蓝骨释放输入尾部证明均通过。入口哈希与上述对照完全一致。

碰撞 ABI 对照覆盖 **124,304** 个查询，包括 NaN、无穷、反向矩形、ULP 边界、蓝骨静止免伤、屏外坐标和多角度四边形，结果逐字节一致。最终微基准的屏外 256 矩形查询约为标准版的 **1.73 倍**吞吐；已索引的矩形和四边形约持平。这是局部测量，不代表完整求解倍数。另构建 portable 指令集版本，重复这 124,304 个查询，结果同样一致。

## 全样本与回归

前后使用同一批捕获入口，以 width=1024、workers=4、memory_mb=512、搜索预算 5 秒逐项运行。共 44 个索引：43 个实际 CSV，另一个用户文件缺失。前后均为 **35 个成功、8 个 unknown、1 个 missing**，状态变化为零；完整进程耗时小于 1 秒的均为 **29 个**。

| 样本 | 原版本（秒） | 两库组合（秒） |
| --- | --- | --- |
| can/sans_final | 0.693 | 0.698 |
| hrzq/waterfall | 5.435 | 1.860 |

仍为 unknown 的项目包括 `sans_realhell_extreme`、`branch1`、`hell`、`part1`、`ruins`、`snowdin`、`xtest` 及单列的削弱版回归。原因包括预算、能力范围和终止不变量未证明，不能据此判定弹幕无解。本轮不是此前“更宽搜索后 37 个成功”的实验，预算和搜索宽度必须区分。

Python 测试 **1467 passed / 1 xfailed**，JavaScript 测试 **317 passed**。代码缓存新增了头文件、xmake 配置和 vcpkg manifest 的身份检查；选择不同库组合会使用不同代码镜像。已安装的匹配镜像通过不带编译器的新进程加载测试。

## 证据与复现

精选证据位于 [`artifacts/library-acceleration-20261018`](../artifacts/library-acceleration-20261018/summary.json)：各轮完整结果压缩件、全样本前后时间及状态、首次失败、完整原版回放、新路线／入口、碰撞对照、安装包版本和测试日志。`summary.json` 绑定输入、原游戏文件、代码镜像和回放哈希。

```sh
vcpkg install --triplet x64-linux
python -m tools.build_native --install
python -m tools.build_accelerators --native
python -m pytest tests -q
node --test tools/*_test.mjs tests/unit/*_test.mjs
```

`tools.benchmark_library_variants` 用于四组合新进程对照，`tools.benchmark_native_libraries` 用于局部碰撞对照；完整命令参数和关闭库的方法见 [原生构建说明](native-build.md)。没有证明理论极限、全局最优路线或全部样本在 1 秒以内。
