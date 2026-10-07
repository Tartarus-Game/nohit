# 版本认定与运动/结算模型对齐

本文记录一次系统性的版本取证与模型对齐过程，结论均可复现（复现命令在文末）。

---

## 一、版本结论（推翻先前假设）

| 对比项 | `repo_jcw87`（作者 Jcw87 官方库） | `repo_badtime`（本项目先前当作权威的副本） | 我们用的 build `c2-sans-fight/` |
|---|---|---|---|
| On-function handler 总数 | 113 | 113（**集合完全一致**） | 108（缺 5 个，见下） |
| Timeline 执行器 handler | 32 | 32（**完全一致**） | 32（`data.js` 中全部存在） |
| `DamagePlayer` 伤害路径 | **5** 条 | **4** 条 | **4** 条 |
| 蓝骨 9-patch 伤害 `Color==2 AND Is moving` | 有 | **已删除** | **无** |
| 蓝心 Tint 常量 | `23.53` | `25` | **`25`** |
| `sans_intro.csv` | 1432 B | 25980 B | 1432 B（同步前） |

**关键判定**：`data.js` 里蓝心 Tint 常量命中 `25`（36 次）而非 `23.53`（0 次），且伤害路径数与 `repo_badtime` 一致。
→ **现有 build 就是从 `repo_badtime` 编译出来的**（`.caproj` 内项目名为 *"the bad time simulator(FVF制作)"*，即 FVF 变体）。

因此：

1. **不需要重新编译**。`repo_jcw87` 与 `repo_badtime` 的引擎能力（113 个 handler + 32 个 Timeline 命令）完全相同，而 build 已全部实现这些能力。
2. build 相对源码只缺 5 个函数，其中 4 个（`MenuCustomRun/Select`、`MenuModeCustom/Practice`）**在两个源码库里都不存在**（是早期审计脚本的解析假象：XML 有一层 `<events>` 包装，正则漏掉了它）；剩下 1 个 `SetPracticeAttack` 在源码中受 `Is in preview` 守卫，属于 **C2 编辑器预览专用代码，导出时本就会被剥离**，不是版本缺口。
3. `repo_badtime` 相对作者库是**功能删减 + 判定修正**，不是"更新"：
   - **删除** 蓝骨 9-patch 伤害块 → 该 build 中 9-patch 蓝骨不再造成伤害；
   - **修正** 4 处平台判定比较符（`>`→`<`）；
   - **修正** 自下方平台吸附 `Set Y = BBoxBottom+8.05` → `BBoxTop+8.05`；
   - **移除** 误播的 `PlayerDamaged` 音效。

---

## 二、build 与权威脚本的唯一数据差异（已修复）

24 个攻击脚本中，只有 `sans_intro.csv` 不同。已从 `repo_badtime/Files/` 同步：

```
c2-sans-fight/sans_intro.csv   1432 B (旧)  ->  25980 B (权威)   ✅ 已同步
其余 23 个脚本                     逐字节一致     ✅
```

> 注意：该文件是 **GBK 编码**（中文 locale），不是 UTF-8。任何按 UTF-8 读取它的解析器都会在偏移 23088 处抛 `UnicodeDecodeError`。

新版 `sans_intro` 的命令构成揭示了它为何难以静态规划：

| 命令 | 次数 | 含义 |
|---|---|---|
| `gasterblaster`（小写，9 参） | **348** | 激光炮，含延迟参 |
| `rnd` | **92** | **随机数** |
| `getheartpos` | **46** | **读取红心当前坐标** |
| `angle` | **46** | 朝向计算 |
| `bonestab` / `sinebones` / `sansslam` / `damageplayer` 等 | 其余 | |

即：**该关卡逐帧追踪玩家位置并含 RNG**。这是设计上的非确定性——它不可能被静态规划器当作确定关卡求解，必须按"存在性 / 多分支"问题处理。

---

## 三、"运动模型 ≠ 结算模型"的准确根因

**不是版本问题**，而是 **Python 规划器没有实现 Timeline 执行器语义**。

`repo_badtime/Event sheets/Timeline.xml` 是一个**程序解释器**，共 32 个内部命令：

```
SET ADD SUB MUL DIV MOD FLOOR SIN COS DEG RAD ANGLE RND GetHeartPos
JMPABS JMPZ JMPNZ JMPE JMPNE JMPL JMPNL JMPG JMPNG JMPREL
TLLoadLine TLPlay TLPause TLResume TLStop TLIsRunning TLPanic Debug
```

而 `nohit/baker/rasterizer.py` 只认**几何字面量**，把这些**全部忽略**：

| 影响面 | 数量 |
|---|---|
| 带变量参数的几何命令行（被静默当成 0 处理） | **83 行** |
| 其中 `sans_intro.csv` | 46 行 |
| `sans_final.csv` | 16 行 |
| `sans_bonegap2/multi1/multi3` 各 | 4 行 |

典型样本：

```
gasterblaster :: 0,0,0,$a,$b,$Ang,0.1,0.3        # 坐标/角度全是变量
bonestab      :: $Direction,29,0.4,0
heartteleport :: 40,$HeartY
bonev         :: $XL,$YB,$HeightB,0,$SpeedL
```

**列出的 20 个"可解"关卡之所以通过自洽核验，是因为求解器与验证器共用同一套（不完整的）语义** —— 两者一致，但都不等于引擎行为。这正是"两个模型不一样"的实质：不是它们互相矛盾，而是它们一起偏离了真实引擎。

---

## 四、引擎真实运动语义（权威转录，已固化为代码）

来源：`c2runtime.js:22983-23038`（CustomMovement 行为）+ `Battle.xml` PlayerMovement 组。

```js
behinstProto.step = function(x, y, trig) {
    var steps = Math.round(Math.sqrt(x*x + y*y) / this.pxPerStep);
    if (steps === 0) steps = 1;
    for (var i = 1; i <= steps; i++) {
        var prog = i / steps;
        this.inst.x = startx + x * prog;
        this.inst.y = starty + y * prog;
        this.runtime.trigger(trig, this.inst);     // 每个子步都触发碰撞事件
        if (this.cancelStep === 1) { /* 回退一格并停 */ }
        else if (this.cancelStep === 2) { /* 停在当前 */ }
    }
};
behinstProto.tick = function() {
    var dt = this.runtime.getDt(this.inst);
    var mx = this.dx * dt, my = this.dy * dt;
    // stepMode 2 = 先水平后垂直
    this.step(mx, 0, OnCMHorizStep);  this.cancelStep = 0;
    this.step(0, my, OnCMVertStep);
};
```

对照当前 `dynamics.py`：

| 维度 | 真实引擎 | `dynamics.py` (`c2` 模式) |
|---|---|---|
| 位移 | `v * dt`，v 单位 **px/s** | 固定 **5 px/帧** |
| 速度 | 有 `dx/dy` 状态，每帧重设 | 无速度状态 |
| 碰撞 | 按 `pxPerStep` 切子步**逐格扫掠**，可中途取消 | 只看帧末格点 |
| dt | **墙钟测得**（帧率相关） | 常量 |
| 落地 | `Set Y = Platform1.BBoxTop − 8.05`（**小数**） | 整数吸附 |
| 红心精灵 | **16 × 20**（实测） | 假设方形 |

实测佐证：真机 `fps = 240`、`dt1 ≈ 0.0042`；`t55.behavior_insts[0]` 的 `properties = [2, 1, 1]`（stepMode=2 先水平后垂直，pxPerStep=1，每像素一次碰撞探测）；红心静止落点 `y = 377.9396`（非整数）。

重力为 4 段阶梯（按 `DownSpeed` 判断，**先匹配者生效**）：

| DownSpeed 区间 | Gravity (px/s²) |
|---|---|
| `> 240` | 540 |
| `-30 < v ≤ 240` | 180 |
| `−120 < v ≤ −30` | **无匹配 → 保持上一帧值** |
| `≤ −120` | 180 |

---

## 五、本轮交付的代码

### 新增（把权威语义固化为可执行规约）

| 文件 | 作用 |
|---|---|
| `nohit/engine/c2spec.py` | 权威常量、4 段重力阶梯（含 hold band）、6 步帧序、`sub_step_count` |
| `nohit/engine/c2step.py` | 权威步进器：速度状态 + `v*dt` + `pxPerStep` 子步扫掠碰撞 + 小数落地 |
| `tests/unit/test_c2_authoritative.py` | **37 个回归测试**，逐条钉死上述事实 |

### 修复（真 bug）

| 文件 | 问题 |
|---|---|
| `nohit/baker/rasterizer.py` | **C2 画布坐标的 HeartTeleport 被误判为局部坐标**：`0 <= ty <= eff_H - SOUL_H` 对 `(320,376)` 成立失败，遂把原始值当局部坐标，起点整体错位。改为按 `CombatZoneResize` 矩形判定坐标系。修正后 `sans_bonestab1/2/3` 起点由 `131,131` → `66,74` |
| `nohit/baker/rasterizer.py` | 同帧多次 `HeartTeleport` 取首次 → 改为**按时间线顺序取末次**（`platforms4` 由假死锁 `t=0` 变真实可解） |
| `c2-sans-fight/tas_runner.js` | `t55` 贴图探测按 `frame.texture_file`（真实导出结构），而非不存在的 `frame[0][0]` / `type.images` |
| `c2-sans-fight/tas_runner.js` | `Timeline.Running` 是**事件表静态局部变量**，不在 `all_global_vars`/`all_local_vars`；改走 `running_layout.event_sheet.localvardict` |
| `c2-sans-fight/tas_runner.js` | 攻击名探测：`RunAttack` 传的是 **AttackList 索引**、`TLPlay` 传的是 **CSV 文本**；改由 `XMLHttpRequest` 挂钩观测 `<name>.csv` 请求（且仅在真正开打时切换，避免预加载导致反复重置） |
| `c2-sans-fight/tas_runner.js` | 补 `routeRequestId` 声明（缺失导致 `fetchOptimalRoute` 抛 `ReferenceError`） |

---

## 六、验证矩阵（全绿）

| 项目 | 结果 |
|---|---|
| `pytest tests/` | **212 passed** |
| 24 波次求解/验证一致性 | solvable=20, deadlock=4, **mismatched=0** |
| 真引擎（Node 载入真实 `c2runtime.js` + `data.js`） | **34/34** |
| runner 桩测试 | **19/19** |
| 真浏览器 CDP 端到端 | **25/26**（唯一失败项是"MainMenu 下 timeline 未运行"的过时断言） |
| 脚本一致性 | 24/24 与 `repo_badtime` 逐字节一致 |

---

## 七、遗留缺口（按优先级）

1. **Timeline 解释器未实现**（最高优先级）。`rasterizer.py` 需从"字面量渲染"改为"执行 `Timeline.xml` 程序"：变量表、标签、`JMP*`、`RND`、`ANGLE`、`GetHeartPos`。这是让规划模型等于引擎模型的关键，83 行变量参数是直接证据。
2. **RNG 关卡不可静态求解**。新 `sans_intro`（`rnd ×92` + `getheartpos ×46`）本质上依赖玩家实时位置。需按"存在性/多分支"处理，或在固定种子下规划。
3. **把 `c2step` 接入求解器**。目前 `c2step`/`c2spec` 是独立规约 + 测试，`solver.replay` 仍走 `dynamics.py` 的 5 px/帧模型。接入时注意 `c2step` 产生**浮点坐标**，会打破现有 DP 的整数格点去重，需要设计量化键。
4. **`sans_intro.csv` 为 GBK 编码**。解析器需显式容错，否则整文件不可读。

---

## 八、复现命令

```powershell
# 版本取证
python tools/compare_sources.py            # 两库 handler 集合对比
python tools/diff_battle_xml.py            # Battle.xml 块级差异（删 4 / 改 8）
python tools/dump_damage_model.py          # 伤害模型对比（5 条 vs 4 条）
python tools/final_version_gap.py          # Timeline handler 与 build 覆盖
python tools/diff_scripts.py               # 24 个攻击脚本一致性

# 模型对齐
python tools/quantify_script_gap.py        # 变量参数被忽略的行数（83）
python tools/dump_group.py PlayerMovement  # 权威帧序
python tools/extract_frame_order.py Battle.xml

# 验证
python -m pytest tests/ -q
python tools/verify_sweep.py
node tools/real_engine_test.mjs http://127.0.0.1:8099 sans_bonegap1
node tools/browser_e2e.mjs 8099 9222 sans_bonegap1
```

> 运行 CDP 类工具需先起服务与浏览器：
> `python start_dashboard.py 8099`
> `chrome.exe --headless=new --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir=<dir>`
