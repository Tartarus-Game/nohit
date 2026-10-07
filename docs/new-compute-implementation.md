# 新计算模式实现规格

本文规定后续实现和验收的主线。主求解器为紧凑动力学状态格动态规划；原版引擎用于提取规则、逐步差分和最终实机验收。已有原版快照搜索与事件策略路线只作为验证夹具，不能计入新计算核的覆盖率或性能。

本文是实现规格，不是声称完整内核已经实现。Platforms4Hard 已落地的纯计算切片、实际计时及实时反例见 [实施记录](new-compute-platforms4hard.md)。所有原版回合按存在无伤解的前提继续开发；未找到路线首先作为模型、搜索或资源问题处理。

## 1. 当前实现与缺口

| 现有位置 | 可复用部分 | 必须补齐的部分 |
|---|---|---|
| `nohit/engine/source_compiled.py` | Numba编译循环、预分配数组、访问表、父指针、A/B距离场算子 | 坐标/速度取整合并有损；固定状态数量裁剪；状态缺少完整横向速度、模态、接触和输入记忆；不是精确状态格核 |
| `nohit/engine/c2spec.py` | 常量、事件顺序线索 | 引用参考XML与实际导出须逐项核对；不能凭模块名认定已保真 |
| `nohit/engine/c2step.py` | 微步、分数落地、双轴速度的实现线索 | 包含替代固体判定，尚未完成实际回合微步差分；不直接作为已验证转移函数 |
| `nohit/baker/` | CSV解析、环境对象、光栅化 | 增加240Hz时间相位、平台反射、动态边框、条件伤害；禁止把依赖玩家状态的未来弹幕烘成唯一轨迹 |
| `nohit/dashboard/server.py` | 服务、版本检查、记录 | 增加明确的模型能力门禁与阶段计时；未覆盖机制不能静默切换成原版搜索 |
| `c2-sans-fight/engine_oracle.js` | 原版真值、状态和路线夹具 | 主线只调用逐步对照/回放；快照分支与事件策略求解保留为显式调试功能 |
| `c2-sans-fight/live_acceptance.js` | 正常速度三回合观察 | 增加新计算模型ID、初始条件和首个轨迹分歧记录 |

## 2. 三层接口与唯一主流程

```text
CSV/实际游戏规则/固定随机种子
    -> compile_wave -> WaveProgram + MechanismCapabilities
    -> prepare_environment -> EnvironmentSchedule + CollisionTables
    -> solve_lattice(initial_state, tables, transition_kernel, limits)
    -> reconstruct -> action_sequence + state_trace
    -> independent_original_replay
    -> realtime_three_round_acceptance
```

`compile_wave` 只解释关卡指令一次，输出类型化事件、单位、事件排序、停止条件和闭环机制清单。`prepare_environment` 只准备环境，不携带答案路线。`transition_kernel` 是纯函数/编译函数，不调用C2、不保存或恢复游戏JSON。

所有产物携带 `csv_sha256/runtime_sha256/data_sha256/kernel_id/model_version/seed/clock_id/input_schedule_id`。缓存分别区分机器码、关卡预处理、状态格结果和已验收路线。`fresh=1` 明确绕过关卡预处理和路线缓存，不清空机器码；另用 `cold_process` 和 `empty_build_cache` 标记真正冷条件。

遇到未覆盖机制返回 `unsupported_mechanism` 和具体指令，不能返回伪路线，也不能悄悄调用原版快照搜索。

## 3. 状态：保存全部影响未来的信息

时间层固定后，候选状态分为玩家状态和必要的分支环境状态：

```text
PlayerState:
  x, y, dx, dy                  # 世界坐标中心、px/s，初版保留float64位模式
  mode, gravity_direction       # 红/蓝等模态、当前重力方向
  gravity_value, max_fall_speed  # 原版持久变量，是否可省须通过依赖分析证明
  support_kind, support_id       # 地板/边界/平台及具体支撑对象
  contact_flags                 # 有效的双轴接触/边界标志
  input_latches, previous_keys   # 原版读取的按键边沿、前一微步输入
  jump_memory                   # 原版实际存在的跳跃锁存/蓄力记忆

EnvironmentState (仅在分支影响环境时存在):
  script_pc, script_clock, variables_live_to_future
  rng_state, active_hazard_signature, event_timer_signature
  target_samples, mode_switches_live_to_future
```

字段由实际导出的事件/行为读写依赖确定，不能只套用报告中的七元组。若跳跃持续时间完全由速度和按键锁存确定，则不额外引入虚构的 `tau`；若存在计时器，则不能用速度代替它。支撑ID若仅在同层由坐标和环境唯一推导，可从状态移到派生值，否则必须保留。

路径代价、最小安全距离、父指针是标签，不与物理状态混写。若代价包含换键次数，上一操作必须属于状态或代价标签的区分维度。

不允许用 `round(x*10)`、`round(y*100)` 或速度分箱宣称精确等价。首版使用有限float64状态的精确字段比较；哈希仅加速查找，碰撞后比较全部键字段。近似相同不合并。NaN/无穷直接报模型错误，不能进入访问表。

若以后改固定点，须给出单位与取整规则并证明所有转移闭合，或明确为保守抽象及其误差；“采用整数”本身不能证明与原版浮点积分一致。

## 4. 时间与转移函数

先锁定 `fixed_240hz` 模型：每个控制帧60Hz，对应四个240Hz微步；同一帧按键恒定。需要微步换键时创建另一输入调度模型，不能把两个动作空间的完整性混为一谈。

微步内的事件、行为更新、接触、伤害和输入读取顺序从实际 `c2runtime.js/data.js` 提取，并以逐步差分确认。不得把报告中的一般方程直接当作原版执行顺序。

转移接口：

```text
advance_control_frame(state, action, absolute_microtick, environment)
  -> successor_state | collision_rejection | model_error
  -> microstep_trace[4]
```

必须覆盖：上一速度形成的位移与新输入速度赋值的先后；水平后垂直的逐像素子步和rollback；按键边沿与释放截断；重力分段的端点与持久值；平台对流、落地偏移8.05与边缘脱离；边框接触；红蓝转换；瞬移；重力冲击的速度赋值和时间顺序。

`SansSlam` 不能一概实现为“立即传送到地板并清零速度”。现有原版轨迹出现750px/s冲击，应按实际规则建模。接触用精灵/支撑几何、伤害用独立4×4命中盒，两者不能合并成同一个大小。

每个微步及其内部运动子步都检查必要的接触与伤害。仅检查60Hz帧末会漏掉穿越障碍的受击。固定步长模型验收与正常时钟验收分别记录。

## 5. 环境预处理与条件碰撞表

### 5.1 外生环境

不依赖玩家路径的CSV事件可提前展开，包括固定种子的独立随机量、骨头轨迹、平台位置/速度、边框和预定模态事件。平台反射必须在发生的微步或子区间处理，不能在整帧内用恒定速度越过反射点。

烘焙按独立伤害条件分层：普通伤害、蓝骨移动条件、其他已覆盖颜色条件；边界合法域和支撑表单独保存。条件由完整状态按原版规则判定，不用“按着方向键”等近似代替真实速度/移动状态。

伤害表完成命中盒的构型空间膨胀后，用点查询。分数坐标可查询单元的保守覆盖，但这种保守表可能排除贴边真解，不能据此宣布原版无解。精确模式需细化到已验证的格点，或对边界单元使用预编译的局部几何判定；记录 `collision_model=exact|conservative`。

同理，“两个时间端点障碍物的并集”不自动覆盖中间扫过的所有位置。微步相位表、扫掠包络或局部动态判定须覆盖完整位移；不同方法的保守性分别注明。

### 5.2 闭环环境

含 `GetHeartPos` 的瞄准激光及受玩家位置影响的分支，不能生成一张通用于所有候选的 `B[t,y,x]`。发射事件从候选状态提取目标，写入紧凑环境状态；后续危险区按事件签名缓存，静态危险区仍共享。

独立的 `RND` 可预展开；若路径改变脚本执行分支或随机调用次数，则 RNG/脚本状态必须进入键。`Multi` 子回合状态同理。初版不覆盖的闭环指令由能力门禁阻止运行。

### 5.3 内存布局

危险掩码采用uint64位行；支撑表采用连续结构数组；距离场按需要生成，不能默认保存整个时域的全部uint8距离场。

Platforms4Hard按435×160、438控制帧×4微步估算，一份全微步位掩码约15.2MB，一份uint8距离场约121.9MB，尚不含第二颜色和状态队列。这只是容量估算，不是计时实测。采用空间裁剪、事件区间共享、按需时间块和有上限的缓存；不得以一个固定50000状态队列假装无限容量。

## 6. 状态格动态规划与无损合并

固定安全余量、固定输入调度、固定模型后，每层枚举全部允许操作。使用双缓冲状态数组、开放寻址访问表和连续父指针；相同完整状态只保留更低可加代价的标签。

```text
current = {initial_state}
for each control frame:
    next.clear()
    for state in current:
        for action in declared_action_alphabet:
            child = kernel.advance(state, action)
            if exact collision: continue
            key = complete_future_state(child)
            lookup by hash, then compare full key
            insert child or relax additive cost
    if next is empty: report exhausted_in_declared_model
    swap(current, next)
reconstruct a route reaching the compiled EndAttack condition
```

不能按空间带、代价排名或平台距离任意删去状态。排序可改变处理顺序，不能改变最终保留集合。事件宏可作为优先展开顺序；没有等价性证明时不得替代逐控制帧动作集。

资源上限到达时返回 `resource_limit`；时间用完返回 `budget_limit`。完整保留最后一层及尚未展开的索引，或回退到最后完整层续算。内存不足可扩容/分块/落盘；若未实现这些操作，就明确停止，不裁成beam后继续宣称完整。

动态哈希查找是期望常数时间，不宣称每次严格O(1)。稠密直接访问表只有在状态积和无损索引已经证明可容纳时使用。

## 7. 最优性与余量

先实现“固定余量下找任意完整无伤路线”，再实现可加代价最小化。输入时长、换键次数等按精确状态的Bellman松弛处理。

不要仅以“历史最小余量优先、输入成本次之”合并相同物理状态：未来更窄的瓶颈会抹平历史余量优势，原来较便宜的标签可能反而最优。需要保留余量/成本的Pareto标签，或更简单地外层对固定余量做单调可行性查询，再在可行余量下优化成本。

保守碰撞表返回无候选时，细化空间/时间或触发精确边界核。资源受限/抽象受限的结果不能用于最优性证明或原版无解结论。

## 8. 正确性门禁

每种机制经过四级检查：

1. 微步差分：同一个初始状态与输入，比较x/y/dx/dy、模态、重力、接触、按键锁存、平台状态和伤害；报告首个分歧及前一微步。精确模式要求同规则同运算顺序的位级结果，使用容差时明确降低保证级别。
2. 合并检查：相同键候选在声明动作集下的后继键、伤害判定和事件输出一致；哈希碰撞不产生误合并。
3. 全路线独立原版回放：从真实回合初态执行新核动作到原版EndAttack，HP不变、KR0。
4. 正常速度三回合：不改HP/碰撞/位置，记录计时差异与按键边沿失效。失败保留为反例，修正模型或增加已声明的鲁棒约束后重新解算。

位级float状态的有限性不意味着状态数量实用；只能对已声明有限模型和完整枚举保证不漏解。保守抽象可提供安全见证，但不能自动提供原版无解证明。报告中的15ms、1ms重规划与复杂度声明均须本机实测/前提验证，不作为已经达到的指标。

## 9. Platforms4Hard 首个完整实施切片

只需要覆盖该CSV实际使用的resize、teleport、blue mode、pause/resume、单平台反射、BoneVRepeat和EndAttack；首版不夹带瞄准激光/Multi机制。

实施顺序与退出条件：

1. 锁定实际游戏哈希、初始微步相位及规则依赖；从已验收438帧路线导出每微步真值和输入。验收路线只提供差分夹具，不作为搜索种子或缓存答案。
2. 校准微步纯转移核，分别覆盖走平台、提前起跳、短/长按、释放、落地、反射点和脱离边缘。差分通过后才接搜索。
3. 编译该CSV外生环境，逐微步核对平台/骨头几何及碰撞分类；共享表覆盖任意玩家候选，而非只覆盖一条夹具路线。
4. 以完整状态精确比较替换现有有损合并，取消beam裁剪，固定余量先找可行路线。记录实际唯一状态数和资源峰值。
5. 关闭路线/预处理缓存从第0帧求解，不使用oracle分支或宏答案；独立回放和实机三回合通过。
6. 分析耗时后再做A/B优化。两版本必须同模型、同完整状态集合、同动作空间、同输出判定。不能通过变粗量化或少保留状态冒充提速。

## 10. 冷启动计时和结果接口

```text
Timing:
  process_startup_ms, game_load_ms, kernel_load_ms
  compile_ms (仅构建模式), csv_compile_ms
  environment_prepare_ms, collision_prepare_ms
  transition_ms, dedup_ms, relaxation_ms, reconstruction_ms
  independent_replay_ms, realtime_acceptance_ms
  first_route_wall_ms, first_accepted_wall_ms
```

嵌套阶段使用互斥统计，不能把同一时间重复相加。编译、预烘焙、路线三个缓存命中分别记录。首次路线计时从声明起点到返回路线，实机时间独立列出。性能测量同时给出硬件、运行时、版本、seed、微步率、余量、精度、唯一状态数、微步次数、内存峰值和重复次数。

结果类型：`candidate_found / unsupported_mechanism / budget_limit / resource_limit / model_mismatch / exhausted_in_declared_model`。另有 `original_replay_passed`、`realtime_passed_three` 两个验证字段，不能用候选找到状态替代验收。

## 11. 交付界限

完成上述Platforms4Hard切片后，才称“新计算模式已在该回合落地”。随后按能力矩阵接入四向重力、条件骨头、独立随机激光、闭环瞄准、Multi和Final。

现有10回合通过记录继续有效，但归入原版参照路线集合；新核覆盖数从实际通过差分和实机验收的回合开始单独统计。本文及能力清单不代表这些实现工作已经全部完成。
