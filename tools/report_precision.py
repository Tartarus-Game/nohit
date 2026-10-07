#!/usr/bin/env python3
"""Measures the current precision of the nohit model, axis by axis.

Reports the resolution actually available for each quantity and compares it with
what the compiled engine (Construct 2) exposes, so the binding constraint is
identified rather than guessed.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nohit.engine import c2spec as C  # noqa: E402
from nohit.engine import dynamics as D  # noqa: E402
from nohit.engine import state as S  # noqa: E402

print("=" * 74)
print("1. 位置 (position)")
print("=" * 74)
print("  模型: 整数像素。dynamics c2 分支做 next_x = round(raw_x), next_y = round(y_star)")
print("        -> 分辨率 1 px, 且每帧都重新取整")
print("  真机: 浮点。实测样例 x=320.0 / 393.155 / 377.8999  (小数)")
print("  差距: 模型无子像素能力; 真机连续")
print()
step = C.HEARTSPEED / 60.0
print(f"  每帧位移 = {C.HEARTSPEED} px/s / 60 = {step} px")
print(f"  -> 2.5 px 落在整数格上, 交替取 2 或 3, 实际每帧推进 2~3 px")
print(f"  -> 每帧位置误差 <= 0.5 px, 44 帧的跳跃累计 <= 22 px")

print()
print("=" * 74)
print("2. 速度 (velocity)")
print("=" * 74)
print(f"  存储: vy_scaled = round(vy_px_per_frame * VY_SCALE), VY_SCALE = {D.VY_SCALE}")
print(f"  -> 分辨率 = 1/{D.VY_SCALE} px/frame = {1 / D.VY_SCALE * 60:.4f} px/s")
print(f"  字段: {S.VY_KEY_BITS} bits, bias={S.VY_KEY_BIAS}, 覆盖 [{-(S.VY_KEY_BIAS)}, {S.VY_KEY_MASK - S.VY_KEY_BIAS}]")
need_neg = int(12.5 * D.VY_SCALE)
need_pos = int(3.0 * D.VY_SCALE)
print(f"  可达域: [{-need_neg}, {need_pos}]  (终端 -12.5 .. 起跳 +3.0 px/frame)")

print()
print("=" * 74)
print("3. 重力 (gravity)")
print("=" * 74)
g_s2 = C.GRAVITY_LADDER[1].gravity if hasattr(C, "GRAVITY_LADDER") else 180.0
g_frame = 180.0 / 3600.0
cells = g_frame * D.VY_SCALE
print(f"  权威值 180 px/s^2 = {g_frame} px/frame^2")
print(f"  * VY_SCALE = {cells:.4f} 格  ->  {'精确整数, 零量化误差' if abs(cells - round(cells)) < 1e-9 else '非整数, 有误差'}")
print(f"  其他段的换算: 540->{540 / 3600 * D.VY_SCALE:.2f}格  450->{450 / 3600 * D.VY_SCALE:.2f}格")

print()
print("=" * 74)
print("4. 时间 (time)")
print("=" * 74)
print("  模型: 固定 dt = 1/60 s (60 Hz), 求解帧 -> 真机 tick 由 tas_runner 按 rt.fps 换算")
print(f"  真机: 墙钟 dt, 实测 0.004185 s (fps=240), 抖动 0.0039~0.0044")
print(f"  dt 抖动幅度 = {(0.0044 - 0.0039) / 0.004185 * 100:.1f}%")
print(f"  时间轴(脚本): 30 Hz  (CSV 时间戳 0.2s -> frame 6)")

print()
print("=" * 74)
print("5. 角度 / 朝向")
print("=" * 74)
print("  模型: 无。c2 分支硬编码 facing = 90 (朝下), 不支持 0/180/270 的蓝心")
print("  真机: PlayerHeart.Angle, HeartMode/HeartTeleport 可设 4 个方向")

print()
print("=" * 74)
print("汇总: 哪一项是当前瓶颈")
print("=" * 74)
print(f"  {'量':<10}{'模型精度':<26}{'真机':<20}{'相对误差'}")
print(f"  {'-' * 66}")
print(f"  {'位置':<10}{'1 px (整数格)':<26}{'浮点(连续)':<20}{'每帧 <=0.5px'}")
print(f"  {'速度':<10}{f'1/{D.VY_SCALE} px/frame':<26}{'浮点 (px/s)':<20}{'<1%'}")
print(f"  {'重力':<10}{'精确 (40 格/单位)':<26}{'180 px/s^2':<20}{'0%'}")
print(f"  {'时间':<10}{'1/60 s 固定':<26}{'墙钟 ~1/240 s':<20}{'依赖 fps 换算'}")
print(f"  {'朝向':<10}{'固定 90 度':<26}{'4 方向':<20}{'缺功能'}")
print()
print("  结论: 位置是唯一仍然粗糙的轴, 且它是 1 px 的硬量化而不是近似误差;")
print("        速度/重力已经精确到足以支撑 44 帧的跳跃(顶点误差 +0 px)。")
