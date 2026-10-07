# GasterBlaster 类型保留修复独立审查

修复正确保留了 literal/SET 字符串与算术数值的区别，并对 Size、起始 X/Y、EndX/Y、EndAng 六个字段使用同一原版整数转换。没有改写其他命令。独立运行修复及 Final 反例测试45项通过；既有 signed ANGLE 回归30项通过。新 helper 另外与逐字复制原版 System.int 分支的 V8 计算结果比对311组输入，零差异。

审查范围为 `native_numbers.py`、`compact_wave.py` 的构造器/调用入口，以及 `resumable_wave.py` 的同一调用入口。没有执行完整新求解、原版游戏或恢复检查点。

## 类型与数值边界

- 两个 backend 都把 `args[:6]` 的已加载值直接交给构造器，未先调用 `eval_arg` 或 float。`load_line` 和 SET 原本就保留类型，MUL/ADD 生成数值，因此 literal、SET、MUL 三条路径均覆盖。
- `native_int` 的字符串正则只接受 ASCII 十进制数字前缀，前导空白显式使用 ECMAScript WhiteSpace/LineTerminator。`﻿` 被接受，Python额外视为空白的 `\u0085`、`\u001c` 等不被接受。
- 数值 −10.4 得到 −11；字符串 `"-10.4"` 得到 −10；`"-1e3"` 得到 −1；`"0x10"` 得到0；无有效数字前缀的字符串得到 +0。
- 表达式层面，数值 −0 和字符串 `"-0.4"` 保留 −0。数值 NaN、正负 Infinity 原样经过 Math.floor；只有无法解析的字符串置 +0，不能把数值 NaN 也静默改为0。
- 原版 instance-variable setter（导出 runtime 第280行）对已有数值变量直接赋传入数值，不把 NaN/Infinity 归零。位置 setter（第275行）也不做有限值过滤。

311组可复核的输入与 V8 期望保存在 [native-int-v8-oracle-20261007.json](../scratch/native-int-v8-oracle-20261007.json)。其中覆盖0..255的所有前导字符、额外 ECMAScript 空白、超长数字前缀、最小/最大浮点数、负零和非有限值。它验证的是整数表达式转换，不是完整游戏对所有异常值的支持。

## 发现并反馈的负零位置赋值细节

原版 GasterBlaster 创建在 +0,+0（Battle.xml 第5450..5451行），然后 SetX/SetY 的实现仅在 `old !== candidate` 时赋值。因为 JavaScript 的 +0===−0，起点 −0 不会覆盖已有 +0；EndX、EndY、EndAng 的实例变量赋值仍保留 −0。

该规则还覆盖 ENTER 的插值与吸附，以及 LEAVE 的逐tick运动，不能只在构造器里处理。源码对应动作均为 SetX/SetY：ENTER 第5660/5675/5690/5705行，LEAVE 第5928/5931行。生产负责人随后在构造器、ENTER、LEAVE 三处实现了相等赋值跳过，并增加正式负零回归；独立最终静态复查通过，可以冻结代码。helper 和 End/角度变量的结果未被改变。负责人报告近邻9文件198项通过；本审查没有重复该整组运行。本项没有被误当作 Final frame5950 的致伤原因。

## 仍未修复的其他整数站点

以下是确定存在的代码路径风险；本次只读列出，没有扩大生产修改。原版各站点及具体行号、17份CSV逐行引用保存在 [source-integer-sites-audit-20261007.json](../scratch/source-integer-sites-audit-20261007.json)，由 [audit_integer_sites_20261007.py](../scratch/audit_integer_sites_20261007.py) 静态生成。

| 命令/路径 | Battle.xml 整数参数位置 | 当前两个backend的差异 | 套餐静态调用行数 |
| --- | --- | --- | ---: |
| BoneH / BoneV | 4500..4518 / 4544..4562，参数0..5 | 先eval_arg/float再Python int，丢失字符串/数值区别 | 530 / 894 |
| Platform | 2768..2808，参数0..5 | 同上，位置、宽度、方向、速度、反向值均有此路径 | 264 |
| BoneHRepeat / BoneVRepeat / PlatformRepeat | Count/Spacing：4617/4621、4709/4713、2864/2868；生成后再次调用单体函数 | Count/Spacing先转换；生成的X/Y为数值，却仍使用Python int；不能把原始literal类型套到生成的坐标上 | 44 / 113 / 9 |
| BoneStab | 4983/4987，方向/高度 | 入口/构造器先数值化再Python int | 974 |
| SineBones | 4778..4790，Count/Spacing/Speed/Height；随后调用BoneV | 输入字段及生成骨头坐标/高度存在同类路径 | 52 |
| HeartTeleport / HeartMode / HeartMaxFallSpeed | 3137/3140、3057、3156 | 相同类型丢失，属于玩家/环境更新而非攻击实体构造器 | 81 / 143 / 16 |
| CombatZoneSpeed | 6547，参数0 | 原版int，模型当前直接float，连普通小数literal也会保留小数 | 12 |

Repeat还有一层重要的类型转换：StartX/Y、Width或Height、Direction、Speed 在源码中是 System 的 `type=number` 局部变量。导出runtime第264行 `r.prototype.lu` 的 SetValue 对这些变量的字符串输入先执行 `parseFloat`；所以转发给单体的宽度、方向、速度同样已经是数值，负小数需要floor。它与把原值放进TLVars字典的Timeline SET不同。Count/Spacing则先System.int，再赋给局部数值变量。

有界、独立的微型模型调用已经复现了三种未修路径，未运行任何求解：

1. `MUL,h,-1,12.9` 后 `BoneV,200,300,$h,0,0`：当前 bbox 为 `[200,288,210,300]`；原版整数规则要求高度−13，故 bbox 应为 `[200,287,210,300]`。
2. `MUL,x,-1,12.9` 后 `Platform,$x,330,40,0,0`：当前 X=−12，原版应为−13。
3. `PlatformRepeat,-12.9,330,40,0,0,1,140`：即使起点是literal，Repeat的减法也把子调用X变成数值−12.9；当前 X=−12，原版应为−13。直接 `Platform,-12.9,...` 的正确结果却仍是−12。

这些是按原版源码建立的模型反例，不冒充已执行的原生验收。

## 17份套餐中的实际证据边界

- 9个文件有570条上述整数参数使用变量的调用，但出现变量本身不证明会触发负小数差异。
- 直接整数参数没有发现科学记数法、数字后缀、异常前导空白等非标准数字literal。所有166条固定参数Repeat的每个生成X/Y都做了floor/int静态比较，没有发现差异。
- 变量来自 RND 后整数加减的部分保持整数；直接读取 HeartX/HeartY 的部分需要真实玩家轨迹判断，不能仅凭变量名认定危险。套餐的12条 CombatZoneSpeed 参数全部是正整数，当前值没有此差异。
- 17份文件没有 DIV/MOD/SIN/COS/ANGLE 命令；没有从这些操作找到套餐内 NaN/Infinity 的具体来源。通用模型 DIV/MOD 除零现在回退0，而原版算术可能产生非有限值，这是独立的上游语义问题，不属于本次整数helper修复，也未被套餐数据证明触发。

因此当前证据支持“其他通用命令仍有可构造的整数语义缺口”，不支持“17份套餐已经因该缺口失败”。后续应按真实触发样本修复并增加原版反例，不把静态风险数量当成失败率。
