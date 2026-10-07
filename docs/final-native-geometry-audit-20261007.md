# Final 原版受伤的独立几何审计

本次共享 CSV 链路的新 Normal 运行完成 23 轮，Final 在模型 frame 5950 触发原版 `DamagePlayer`，因此完整战役验收未通过。已经定位到具体的几何差异：碰撞框 UID1871 的原版方向为 −11°，模型为 −10°。同一玩家位置下，独立 SAT 判定原版发生重叠，模型没有重叠。这里没有运行新求解、恢复游戏快照或修改生产代码。

## 轨迹和时间对齐

- Final 捕获边界：原版 post tick55334；`clock_start_ms=230558.33333316274`。
- `DamagePlayer` 回调：tick61283；提交后的受伤状态：post tick61284，即模型 frame5950。
- frame0..5950 的 65,461 个玩家状态分量逐项完全相等；输入、Confirm 和逐帧 dt 没有差异。
- 受伤帧输入：动作索引5949，mask5（Left+Up），Confirm=false；dt=`0.004166666666656965`。
- 玩家中心：`(325.53593749991245, 287.4999999998884)`；原版 PlayerHitbox UID98 为轴对齐4×4方形。
- 状态第8项330是 MaxFallSpeed；不是 JumpStrength。
- 原版 HP92/KR0 变成 HP91/KR10。此时 CSV line156，场地为 `[239,226,404,391]`。

对齐详情：[alignment.json](../scratch/final-native-geometry-20261007/alignment.json)。原版 snapshot 为失败后只读 `saveToJSONString()` 的结果，没有恢复操作。

## 独立碰撞计算

从原版保存的 hitbox 世界位置、宽高、角度和 hotspot 重建矩形四角，以两个矩形所有边的法向作为分离轴。表中的最小轴重叠量是各单位轴上投影交集长度的最小值；正值表示在所有轴上重叠，负值表示存在分离轴。它不是可直接相加的统一安全半径。

| 原版 hitbox UID | 原版角度 | 模型角度 | 原版最小轴重叠 | 模型最小轴重叠 | 原版相交 |
| --- | ---: | ---: | ---: | ---: | --- |
| 1866 | 2° | 2° | −5.351930628300181 | −5.351930628300181 | 否 |
| 1871 | −11° | −10° | **+0.101873499224439** | **−2.705605147563631** | **是** |
| 1876 | −23° | −22° | −4.571459358750872 | −7.431868805495583 | 否 |
| 1881 | −36° | −35° | −5.7189452135735905 | −8.608475173414774 | 否 |

碰撞的 UID1871 与原版 GasterBlaster UID1868、可见 GasterBlast1 UID1870 对应。原版与模型 hitbox 高度均为26.25，来自 `BaseSize=35` 的3/4；并非视觉激光宽度随机摆动造成。正角度的 UID1866 几何和 SAT 结果一致。负角度的另外两条也呈现同样的1°差异。

原版 UID1871 的中心线起点为 `(137.52034518156105,339.70216596256995)`，方向为 −11°，长度1000。完整原版 instance、模型 polygon 和每个分离轴结果见 [native-geometry-audit.json](../scratch/final-native-geometry-20261007/native-geometry-audit.json)。可重复执行 [audit_native_geometry.py](../scratch/final-native-geometry-20261007/audit_native_geometry.py)，只读取已保存证据。

## 负角度取整的直接反例

Final 源 CSV 第138..156行从 `gt=0, gin=1` 开始循环，每次使用 `Ang=180-10*gt`，之后 `gt+=gin`、`gin+=0.015`。独立重算相关三次生成得到：

| 从0计数的生成次数 | 原始 Ang | 向下取整 | Python int 向零截断 | 原版/模型实测 |
| --- | ---: | ---: | ---: | --- |
| 17 | −10.399999999999864 | −11 | −10 | −11 / −10 |
| 18 | −22.949999999999847 | −23 | −22 | −23 / −22 |
| 19 | −35.649999999999835 | −36 | −35 | −36 / −35 |

这些数值证据定位了原版与模型的整数语义差异。下面进一步沿原版源码确认其类型规则；此报告不将尚未重验的修复宣称为通过。

## 原版整数转换与参数类型

[原版导出 runtime 第266行](../jcw87-c2-sans-fight/c2runtime.js#L266) 的 System.int 为：

```javascript
p.prototype["int"] = function(a,b) {
  z(b) ? (a.H(parseInt(b,10)), isNaN(a.data) && (a.data=0)) : a.H(b);
};
```

同文件第5行 `z(a)` 判断 `typeof a === "string"`，第252行 `a.H` 对应 `t.prototype.H=function(g){this.type=hc.Nf;this.data=Math.floor(g)}`。因此数值参数向下取整；字符串参数先做十进制 `parseInt`，无法解析则结果置0。

这两种情况在原版 Timeline 里确实同时存在：[Timeline.xml](../repo_jcw87/Event%20sheets/Timeline.xml) 第212行把 `$变量` 对应的 `TLVars.Get` 直接推入当前行，第224行把非变量的 Token 字符串直接推入。第331..333行调用函数时不做数值转换。第405行 SET 保存参数原类型；第418行 ADD、第444行 MUL 显式 float 转换后产生数值。当前模型的 `load_line` 和 SET 已保留这种类型，GasterBlaster 入口先 `eval_arg`/float 再 int 才丢失了区别。

| 输入来源 | 交给 System.int 的值 | 原版结果 |
| --- | --- | ---: |
| CSV 直接填 `-10.4` | 字符串 `"-10.4"` | −10 |
| SET 保存 `-10.4` 再读取变量 | 字符串 `"-10.4"` | −10 |
| MUL/ADD 运算结果 | 数值 −10.4 | −11 |
| CSV 直接填 `-1e3` | 字符串 `"-1e3"` | −1 |
| 无法解析的字符串 | 如 `"invalid"` | 0 |

[Battle.xml](../repo_jcw87/Event%20sheets/Battle.xml) 精确对应位置：

| 参数 | 字段 | 源码行 | 规则 |
| --- | --- | ---: | --- |
| 0 | Size | 5506 | `int(Function.Param(0))` |
| 1 | 起始 X | 5509 | `int(Function.Param(1))` |
| 2 | 起始 Y | 5512 | `int(Function.Param(2))` |
| 3 | EndX | 5516 | `int(Function.Param(3))` |
| 4 | EndY | 5520 | `int(Function.Param(4))` |
| 5 | EndAng | 5524 | `int(Function.Param(5))` |
| 6 | Timer | 5528 | 原参数，不取整 |
| 7 | BlastTime | 5532 | 原参数，不取整 |

所以最小正确修复应在保留类型的参数边界实现原版整数转换，并覆盖六个整数参数，不能只改 EndAng，也不能把字符串先转float后统一floor。

快照中还有负坐标的独立证据：最新 GasterBlaster UID1953 尚处于 ENTER，当前 TLVars.Y 为数值 `-98.9723780324482`，目标 EndY=171。包含创建当tick在内，按原版 `y+=(171-y)*dt*10` 递推14次，起点floor=−99得到 `22.202345852545022`，与原版快照逐位相等；起点int=−98则得到 `22.75344827531338`，相差 `0.5511024227683592`。负坐标取整与负角度取整是同一原版规则。

## 证据身份与结论边界

- 完整证据 manifest：[bonesgap1-20261007-080740-765042.json](../tools/real-game/bonesgap1-20261007-080740-765042.json)，62分片、123140078字节，合并 SHA256 `bfdd411a1078386d4f14bfb559a7fc8e59dbf591174015ea2964f545ebf06bd7`；结果为 `failed_damage`、23轮。
- 原版 snapshot SHA256：`33d873444ed66534a010034f313aef2eb69b4366ce8369d8102b184fe7e3d437`。
- Final 完整候选 SHA256：`a3a32c766823c18dad59437d65e0180c0c4630d046ac2d4fa913dea7b67a2b57`。
- 几何审计 JSON SHA256：`0dc56e7cec0154d448b561da4f9527eb7ac7289738fd3f10ff1501bfbfbf9df1`。
- 原始 Final 文件 SHA256：`ff3d6f0c1b2c2f3bdb290109086ec3c9f7c3f6e628809512ac943dc7408c1078`；实际 TLPlay 文本 SHA256：`b5b5bbef8406d6074e6e27762dd48a450109485b070fc9e4b2c9705461a8f907`。二者口径不同，不应互换。

本次失败是一个已复现的模型几何偏差。它发生在旧 Final 前沿耗尽的 frame7643 之前，不能归因于该处恢复策略，也不证明 Final 无解。当前模型候选的 verified 标志只说明按该模型重放通过，不等于原版无伤证书；修复后必须重新生成候选并重新执行原版验收。
