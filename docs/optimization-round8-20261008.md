# 第八轮：按需历史记录、分片精确去重与空白位移证书

## 达到与未达到的目标

本轮主要改动 C++ 搜索和保守工作空间估算。最终冻结源码的实测：Final模型求解约快1.15倍，100,000状态的高速移动算子约快4.45倍。没有达到整关普遍再快20倍、所有任务毫秒级、所有关卡含冷启动低于10秒，也没有挖尽8核潜力。Haoge Final必须以本报告末尾的本轮原生验收结果为准。

## 相同入口、交替新进程对照

每版三个新进程，旧／新交替运行；相同CSV、真实入口、原生dt、8核预算，代码预加载但世界和路线不缓存。基线为交付的第七轮C++源码，Python解释、验证和本轮工作空间估算相同。不是完整旧仓库的对照。包含完整模型求解及独立源验证，不含随后C2事件引擎验收。全部Final输入／轨迹指纹一致，全部Blue输入／轨迹指纹也一致。

| 指标（中位数） | 第七轮C++ | 本轮 | 变化 |
|---|---:|---:|---:|
| 原版Final完整模型求解 | 10.6519 s | 9.2734 s | 1.15× |
| Final进程CPU总用时 | 21.6371 s | 23.2302 s | 增加7.4% |
| Final进程峰值RSS | 237.48 MiB | 209.82 MiB | 减少11.6% |
| Haoge Blue完整模型求解 | 0.7647 s | 0.7001 s | 1.09× |

Final本轮各样本平均有效核数：2.51, 2.42, 2.33。多核去重和桶归并提高了利用率，但同步也增加CPU总用时。全部时间并未满核；不以占用率代替速度指标。样本存在负载波动，不能把一次最快值当成保证延迟。

移动算子压力基准：100,000个状态、25像素/轴位移，20%状态处于旧墙接触位置必须回退原扫描；不含世界生成、编译、搜索或游戏验收。第七轮中位数27.165 ms，本轮6.099 ms，4.45倍。全部输出逐字节一致，另抽样512项逐位比较原Python标量玩家方程。该结果只适用于此算子压力样本。

Final两次空代码缓存、新进程的外部墙钟：13.2789, 14.2761 s，含首次C++编译、导入、完整求解和独立模型验证。均已验证，未导入Numba/LLVM；只清空代码缓存，未清空操作系统文件缓存。仍超过10秒。

## 保留的实现

- 每帧只清空与当前父状态数和控制数相匹配的哈希表范围，避免窄前沿反复清空最大宽度表。
- 连续数组预存成本与随机序号，比较不再频繁读取大状态对象。总比较顺序保留可存活预览、目标距离、成本、随机序号和原索引。
- 大前沿按混合哈希分片精确去重，各片内按原父状态／控制顺序保留首项，合并后才依原顺序生成随机序号。空间桶归并也可在各片内取同一比较器的最佳代表。分片使用已租用的线程，计算线程不超过调用预算；小前沿保留串行归并以减少同步。完整状态逐位比较不变；哈希省略帧内共享的尾部字段不会省略相等性判断。
- 历史路径只为每帧实际保留的状态分配父索引和控制。普通宽度每项3字节，宽度超过65535时4字节；恢复及最终路径仍读取真实祖先。容量按需精确预留，工作空间估算增加帧头开销。
- 每帧预存按原表达式计算的重力sin/cos；跳跃与不跳跃分支共用一次真实位移结果，再分别执行原输入／重力更新。
- 对旧墙和旧平台做保守扫掠包围盒检查。只有整段位移确认无实体时，才直接使用原循环最后一个样本；任何不确定或墙接触情况执行原逐像素扫描，保留垂直墙接触、移动平台、Slammed、带符号零和伤害语义。
- 补全目标评分、哈希表增长和回退临时量的工作空间计数。memory_mb是内部工作空间预算，不是整个进程RSS硬限额；源世界张量、Python对象及分配器开销另外占内存，RSS实测单列。

## 验证范围

本轮针对性回归152项通过，12.53秒。新增非整数/负零重力方向、旧墙/移动平台扫掠、浮点边缘、零/负dt以及4096宽度、1/3/7线程回退检查；移动算子全量差分另见基准。完整仓库旧测试集并非全部通过，第六轮报告保留既存失败比较。本轮不重复声称全仓库全绿。

阶段诊断final-frozen-profile.json的时间是跨并发探针的阶段墙钟求和，不是进程CPU时间，也不能相加当作请求延迟。它绑定冻结源码SHA；诊断编译版本额外插入计时，性能比较使用未插入计时的源码。

当前性能源码SHA256：a581129d4963c9c88c3b2a7398b6301e8dce875ac87c2efa669f48ebb8dec185。当前原版验收目录为round8/normal-delivery及round8/haoge-delivery，其他轮次为历史记录。所有当前回放均在打包前核对engine源码哈希。

## 复现

```bash
python -m tools.benchmark_round8_request c2-sans-fight/sans_final.csv --entry tools/optimization-results/round7/normal-delivery/23-sans_final-entry.json --compare --repeats 3 --out final-paired.json
python -m tools.benchmark_round8_request c2-sans-fight/sans_final.csv --entry tools/optimization-results/round7/normal-delivery/23-sans_final-entry.json --empty-code-cache --repeats 2 --out final-cold.json
python -m tools.benchmark_movement_sweep --out movement.json
NOHIT_RETRY=1 NOHIT_BENCH_OUT=normal-new node tools/solve_normal_native.mjs
python -m tools.verify_normal_native normal-new/campaign.json --out normal-new/verdict.json
NOHIT_GAME_DIR=haogesans-export NOHIT_SCRIPTED_HEALING=1 NOHIT_FPS=60 NOHIT_SEARCH_STRATEGY=native python -m tools.native_replay_batch sans_intro sans_bluebone --cpu-budget 8 --processes 4 --out haoge-new
```

源码包包含原版未修改素材、完整源码、原版Haoge导出、上一轮C++参考、差分测试和当前验收记录。

## 当前原生游戏验收

原版Normal 60 Hz 连续24轮passed=true、Win2，17692原生tick、13991个匹配输入、153637个非终止状态分量一致，HP92、KR0、零伤害调用。独立验证passed=true。Final成功尝试用时8.3661秒；本轮首次8秒搜索预算成功。该预算仅约束搜索阶段，完整模型求解／验证另有开销，不能把它当作整场游戏总耗时。

Haoge的23个非Final攻击全部通过冻结源码的原版事件引擎回放：仅允许脚本负数治疗，零非负DamagePlayer调用、物理状态逐tick一致、存活并达到EndAttack。采用独立攻击进程（非连续战役），4进程、每进程2个搜索线程，总预算8核；不与Final诊断同时运行。批次完整捕获／求解／回放用时41.867秒，该值不能冒充求解器延迟或吞吐加速比例。

Haoge Final本轮120秒、8线程预算诊断仍为unknown，verified=False，用时117.136秒，最深诊断tick11729。显式允许原脚本效果，没有得到完整路线，也没有完成原生路线回放，因此不能判为已解出或无解。入口、失败结果及源码指纹在round8/haoge-final-delivery。结尾脚本正数伤害与严格零非负伤害合同的差别仍见第六轮报告；本诊断合同下也尚未成功。
