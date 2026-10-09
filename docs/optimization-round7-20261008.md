# 第七轮：减少计算、回收空闲核与哈希退化修复

CPU 的潜力尚未挖尽；整关再快 20 倍、所有任务毫秒级和所有关卡含冷启动低于 10 秒仍未实现。不要把提高 CPU 占用率当成提高效率。宽前沿去重与代表状态选择、因果段之间的依赖和原生验收仍有串行开销。

## 当前固定入口对照

两版使用相同 Haoge Blue CSV、捕获入口、时钟、128 宽度和 8 核预算；每版三个独立进程。编译代码预加载，世界与路线不缓存；包含世界生成、搜索和独立源模型验证，不含随后原生游戏验收。基线替换第六轮 C++、动态搜索、候选选择与骨头数组实现；不是完整旧仓库的对照。机器负载有波动，结果仅代表此次样本。

| 指标（中位数） | 第六轮结构 | 本轮 | 变化 |
|---|---:|---:|---:|
| 完整模型求解 | 2.1568 s | 1.3548 s | 1.59× |
| 求解进程 CPU 总用时 | 4.0352 s | 1.5493 s | 减少 61.6% |
| 求解进程峰值 RSS | 97.29 MiB | 71.79 MiB | 减少 26.2% |

本轮整个求解平均仅占约 1.15 核，不能声称整段满核。首先运行便宜的主要搜索，主要搜索失败再投入预测策略，避免为简单任务启动大量最终无用的推测计算。空闲线程可帮助较宽前沿的物理扩展、未来预览和排名准备；总计算线程受调用者预算限制。

整数坐标退化基准（空白红心源攻击，31 tick、27,086 扩展、41,505 唯一状态，宽度1024）：1.0044 s → 33.27 ms，30.19×。两版完整输入与每帧轨迹逐字节相同，另逐帧用原标量玩家方程检查。此为整个原生搜索内核基准，排除世界生成、编译和进程启动；不代表原版攻击普遍提升30倍。

原版 Blue 两次空代码缓存进程：外部墙钟 6.5283 s、5.3939 s，包含首次 C++ 编译、导入、求解与独立模型验证，未导入 Numba/LLVM。编译器峰值内存单独记录；文件系统缓存未清空。这个样本低于10秒，不能外推至 Final。

## 改动

- 碰撞索引按帧并行计数和填充，前缀和串行执行；取消全局临时成员清单和重复游标数组。
- 搜索线程完成后回收预算供仍在运行的任务扩展前沿。排名压缩保持父状态和控制的原始顺序，最终仍按策略优先级选择成功方案。
- 密集骨头的私有提议状态使用连续 C 数组和融合 C++ 更新/几何打包。独立证书用列连续 NumPy 数组，仍运行原 Python/NumPy 解释路径；没有把候选代码充当独立证书。
- 控制等价类先批量提取少量不同上下文，再调用原函数；默认工作线程数同时受亲和性和 cgroup CPU 配额限制。命令行入口默认避免额外 BLAS 线程池，保留用户显式设置。
- 原始 FNV 的整数浮点位模式会集中到少量低位桶。探测链达到128后重建索引并混合高低位；完整状态逐位比较不变，不舍弃任何物理字段。
- 大宽度主要搜索从512个状态开始，耗尽时沿真实祖先恢复、重算精确前缀并扩大至指定上限。长回溯最多512 tick；没有借用其他路线或改写世界。大前沿缓存原始空间桶结果以减少重复 floor。它仍是有限束搜索，失败只能报告 unknown。
- 独立 Haoge 攻击可用受预算限制的多个原生进程并行验收；带继承状态的 Normal 连续战役仍按关卡顺序运行。

## 验证与限制

139 项针对性测试通过，98.48秒；日志在 round7/regression-delivery.txt。覆盖碰撞边界、非有限浮点、带符号零、控制上下文、源回放及脚本效果合同。没有声称全仓库测试全绿；第六轮报告保留旧测试集的既存失败情况。

当前冻结源码的验收记录见 round7/normal-delivery、round7/haoge-delivery；最终统计见本报告尾部。历史目录绑定历史源码哈希，不是当前验收证据。

Haoge Final 不允许被默认为已解出：其结尾含正数脚本 DamagePlayer，严格禁止所有非负调用的合同与结尾不相容，这不证明物理弹幕无解。显式允许脚本效果的诊断也必须有完整原生回放才可判成功。之前90秒诊断仍 unknown。更高 CPU 占用无法消除有限搜索失败或这种合同差别。

## 复现

```bash
python -m tools.benchmark_cpu_request haogesans-export/sans_bluebone.csv --entry tools/optimization-results/round5/haoge-current/sans_bluebone-entry.json --healing --width 128 --baseline --repeats 3 --out blue-old.json
python -m tools.benchmark_cpu_request haogesans-export/sans_bluebone.csv --entry tools/optimization-results/round5/haoge-current/sans_bluebone-entry.json --healing --width 128 --repeats 3 --out blue-new.json
python -m tools.benchmark_hash_frontier --out integer-frontier.json
python -m tools.benchmark_cold_native --waves sans_bluebone --repeats 2 --output cold.json
NOHIT_RETRY=1 NOHIT_BENCH_OUT=normal-new node tools/solve_normal_native.mjs
python -m tools.verify_normal_native normal-new/campaign.json --out normal-new/verdict.json
NOHIT_GAME_DIR=haogesans-export NOHIT_SCRIPTED_HEALING=1 NOHIT_FPS=60 NOHIT_SEARCH_STRATEGY=native python -m tools.native_replay_batch sans_intro sans_bluebone --cpu-budget 8 --processes 4 --out haoge-new
```

## 当前原版验收

Normal 60 Hz 连续24轮通过，17,693原生tick、13,991匹配输入、153,637个非终止状态分量一致，HP92、KR0、零伤害调用，独立验证passed=true。Final成功尝试16.2508秒；此前8秒尝试失败并重试，不能把16.25秒当成整场总耗时。

Haoge 23个非Final攻击全部通过当前源码的原版事件引擎回放（每个攻击独立进程），仅允许原脚本负数治疗，零非负DamagePlayer调用，逐tick物理状态一致，最终EndAttack。所有记录均核对当前engine源码哈希。批次并行预算8核、4进程、每进程2个搜索工作线程；这不等同连续战役，且另有Final诊断同期运行，不用本次批次时长声称吞吐加速。

Haoge Final本轮显式脚本效果诊断：unknown，verified=False，用时90.436秒，最深诊断tick11722。预算90秒、2个搜索工作线程，与原生批次同时运行；未得到完整路线，不能判为已解出或无解。完整入口和失败结果保存在round7/haoge-final-delivery。
