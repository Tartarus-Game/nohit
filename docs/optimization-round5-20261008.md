# 第五轮：因果观测分段、连续验证和内存优化

## 实际改动

1. 带对话且有 GetHeartPos 的攻击，按真实观测点分段搜索。只提交观测前的输入，再用这条已提交路线的玩家位置续跑源脚本。每个中间物理帧仍执行原方程和碰撞检查。
2. 带对话但没有玩家读取的攻击，只生成一次固定对话时钟下的世界；路线随后经独立的标量源方程验证。省掉猜测路线、重建相同世界的迭代。
3. 验证一条完整输入序列时只保留一个连续环境状态，输入与目标观测身份使用分块收集、末尾拼接。公开的纯分支 API 仍保留克隆语义。
4. 已知完整观测历史可以单次执行并只发布最终绑定，避免为每个历史前缀分配全波形数组。
5. 观测采样只构造移动阶段需要的 dt、旧边界和平台字段，私有独占目标续跑免去世界深拷贝。只读采样与完整纯预览做了差分测试。
6. C++ 只选择所需的最佳桶代表和补充候选，避免全部边排序。固定世界基准中，路线和全部状态位模式保持一致。
7. 密集骨头矩形使用数组打包，严格比较保留原 Python 方程的相等、带符号零及 NaN 首操作数语义。原生搜索的临时世界不额外生成白/蓝合并展示数组。

## 毫秒级结果与冷启动

固定 Haoge RandomBlaster1 原生捕获入口，8 工作线程，宽度 3000。每次都是全新的 Python 进程，未使用路线或世界缓存。

| 测量范围 | 中位耗时 | 次数 |
| --- | ---: | ---: |
| 复用已编译代码的完整新进程 | 332.85 ms | 3 |
| 其中求解及模型验证 | 215.53 ms | 3 |
| 其中搜索内核 | 22.68 ms | 3 |
| 删除代码缓存后的完整新进程，包含首次 C++ 编译 | 2318.55 ms | 2 |

新进程本身峰值 RSS 约 32 MiB；首次编译的编译器子进程峰值 RSS 约 155 MiB，不能把前者当作整个冷启动进程树的内存上限。该攻击通过了未经修改的 Haoge C2 事件运行时无伤回放。

`tools/benchmark_solver_request.py` 可复现这组测量。源码缓存只缓存已编译代码。

## 验证器内存和时间

同一条旧 Haoge Platforms4 审计路线，分别在新进程中使用旧验证流程和新连续流程；二者保留完全相同的最终控制环境身份。

| 指标 | 旧流程 | 新流程 |
| --- | ---: | ---: |
| 验证时间 | 11.180 s | 1.002 s |
| 进程峰值 RSS | 224.55 MiB | 61.59 MiB |

这是固定审计路线的验证器对照，不能当作整关求解速度。两份原始 JSON 和旧验证代码随源码一起提供。新流程约快 11.2 倍，峰值 RSS 下降约 72.6%。

C++ 选择器另有一次固定原版 Final 世界的对照：22.98 s → 15.59 s，两个版本均扩展 22,139,834 个状态，输出路线与完整轨迹 SHA-256 一致。该单次对照不是整关统计，也不是跨关统一加速倍数。

## 原生验收

原版当前记录独立验证：17,692 个连续原生 tick、13,991 个匹配输入、153,637 个非终止状态分量一致。

当前源代码验收文件位于 `tools/optimization-results/round5/normal-current` 和 `round5/haoge-current`。旧的 round3、round4 以及其他 round5 子目录是不同阶段的历史或诊断记录，各自记录绑定当时源代码哈希，不能替代当前版本的验收。

- 新回归测试共 126 项通过，包括连续验证与公开纯乘积算子身份一致、目标采样差分、历史绑定差分、目标读取后的因果分段、密集几何差分以及轨迹篡改拒绝。
- 原版 Normal 在 60 Hz 完整新运行中连续完成 24 轮，HP92、KR0、零 DamagePlayer，最终到 Win2。独立验证器读取完整运行记录。
- Haoge 已有 18 个不同攻击通过原生回放，新增 RandomBlaster1 和 BlueBone。Haoge 原脚本的字面量负 DamagePlayer 治疗显式允许；判定为存活且没有非负 DamagePlayer 调用，HP 不要求恒定。

## 尚未达到的目标

所有整关计算毫秒级尚未实现。最新原版 Final 在一次完整 Normal 运行中耗时约 16.09 s，其他 23 轮约 46–291 ms。Haoge BlueBone 和 Platforms4 仍需秒级；不同入口时钟、搜索预算和同时运行的工作会影响时间。

Haoge BoneGap1Fast、BoneStab2、Platforms1、Platforms3 尚未解决；RandomBlaster2 有快速模型候选，但原生回放仍发生伤害，不能算成功。Haoge Final 包含正数脚本 DamagePlayer，当前物理投影合同仍拒绝。上述情况不构成无解证明。原版 240 Hz Final 仍未解决。

尝试过持续数帧的输入块搜索：所有中间帧都执行了精确方程，但未找到 Final 完整路线，因此发布的默认算法仍采用通过验收的逐帧前沿与观测分段。

## 复现

```bash
python -m pytest -q tests/unit/test_linear_observation_replay.py

NOHIT_GAME_DIR=haogesans-export NOHIT_SCRIPTED_HEALING=1 \
NOHIT_FPS=60 NOHIT_SEARCH_STRATEGY=native NOHIT_SECONDS=8 \
node tools/native_optimized_replay.mjs sans_randomblaster1

python -m tools.benchmark_solver_request haogesans-export/sans_randomblaster1.csv \
  --entry tools/optimization-results/round5/haoge-current/sans_randomblaster1-entry.json \
  --healing --reuse-code --out request-warm-code.json
# 去掉 --reuse-code 就包含空代码缓存的首次编译。
```
