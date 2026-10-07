# 两版算子实测

seed=42；每次重新烘焙并求解，未复用路线。JIT 首次调用单列于 JSON。
动作、轨迹、前沿数量和终止帧与 baseline 完全一致；此处不代表原版游戏验收。

| 回合 | 结果 | baseline 端到端 | A 端到端 | B 端到端 | B 搜索 |
|---|---|---:|---:|---:|---:|
| sans_bluebone.csv | 候选 | 502.26ms | 363.63ms | 336.62ms | 193.19ms |
| sans_bonegap1.csv | 候选 | 218.76ms | 177.96ms | 161.23ms | 67.84ms |
| sans_bonegap1fast.csv | 无候选 | 136.78ms | 103.22ms | 101.77ms | 6.11ms |
| sans_bonegap2.csv | 候选 | 426.91ms | 363.31ms | 326.66ms | 224.36ms |
| sans_boneslideh.csv | 候选 | 526.09ms | 435.90ms | 395.78ms | 285.49ms |
| sans_platforms3.csv | 候选 | 734.91ms | 671.59ms | 685.58ms | 580.06ms |
| sans_platforms4hard.csv | 无候选 | 303.86ms | 246.40ms | 255.21ms | 107.19ms |

完整样本、阶段耗时、源码哈希和运行环境见 latest.json。无候选不等于死局。
