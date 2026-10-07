# 全部原版回合覆盖记录

2026-10-05本轮重新执行全部24例子：16个EndAttack、8个正常死亡、0个运行错误。seed=42。加速无伤是候选证据，正常时间连续三回合才是实时验收。待机基线不是求解失败或死局判定。

| 回合 | 输入 | 原版结果 | HP / KR | 帧数 | 实时三回合 |
|---|---|---|---|---|---|
| sans_bluebone.csv | candidate | end_attack (加速无伤) | 92 / 0 | 382 | 通过 |
| sans_bonegap1.csv | candidate | end_attack (加速无伤) | 92 / 0 | 396 | 通过 |
| sans_bonegap1fast.csv | candidate | end_attack (加速无伤) | 92 / 0 | 384 | 待验收 |
| sans_bonegap2.csv | candidate | end_attack (加速无伤) | 92 / 0 | 420 | 通过 |
| sans_boneslideh.csv | candidate | end_attack (加速无伤) | 92 / 0 | 462 | 通过 |
| sans_boneslidev.csv | idle_baseline | end_attack | 47 / 25 | 358 | 待验收 |
| sans_bonestab1.csv | idle_baseline | game_over | 0 / -1 | 312 | 待验收 |
| sans_bonestab2.csv | idle_baseline | game_over | 0 / -1 | 322 | 待验收 |
| sans_bonestab3.csv | idle_baseline | end_attack | 14 / 13 | 378 | 待验收 |
| sans_final.csv | idle_baseline | game_over | 0 / -1 | 568 | 待验收 |
| sans_intro.csv | idle_baseline | game_over | 0 / -1 | 157 | 待验收 |
| sans_multi1.csv | idle_baseline | end_attack | 4 / 3 | 510 | 待验收 |
| sans_multi2.csv | idle_baseline | end_attack | 10 / 9 | 655 | 待验收 |
| sans_multi3.csv | idle_baseline | game_over | 0 / -1 | 456 | 待验收 |
| sans_platformblaster.csv | idle_baseline | end_attack | 27 / 26 | 540 | 待验收 |
| sans_platformblasterfast.csv | idle_baseline | end_attack | 20 / 19 | 504 | 待验收 |
| sans_platforms1.csv | idle_baseline | game_over | 0 / -1 | 245 | 待验收 |
| sans_platforms2.csv | idle_baseline | game_over | 0 / -1 | 248 | 待验收 |
| sans_platforms3.csv | idle_baseline | end_attack | 25 / 24 | 480 | 待验收 |
| sans_platforms4.csv | idle_baseline | end_attack | 35 / 19 | 438 | 待验收 |
| sans_platforms4hard.csv | idle_baseline | end_attack | 30 / 29 | 438 | 待验收 |
| sans_randomblaster1.csv | idle_baseline | game_over | 0 / -1 | 315 | 待验收 |
| sans_randomblaster2.csv | candidate | end_attack (加速无伤) | 92 / 0 | 504 | 通过 |
| sans_spare.csv | idle_baseline | end_attack (加速无伤) | 92 / 0 | 19 | 待验收 |

完整逐帧记录：`coverage-latest.json`。实时证据路径与三回合 HP/KR 摘要在其 `acceptance` 字段中。

RandomBlaster2 的前三回合通过后曾观察到后续掉血，单独保存在 later_observed_failure；本记录采用用户指定的三回合门槛，不据此宣称任意连续时长或所有 seed 稳定。

RandomBlaster2 seed42 已换成每个240Hz微步检查2px余量的新路线，真实三回合均HP92、KR0、碰撞0。记录 `bonesgap1-20261005-000657-119498.json`，截图 `bonesgap1-20261005-000726-655544.png`；它已经由实时验收接口提升为默认路线。此前加速无伤但实战失败的新候选已隔离保存。

速度：BoneGap1 新路线约224–230ms；RandomBlaster2 新余量路线原版搜索约62.6s（含安全前缀续算）。百毫秒目标尚未在复杂回合达成。
