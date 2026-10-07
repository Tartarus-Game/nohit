"""
nohit.baker.parser
~~~~~~~~~~~~~~~~~~
Construct 2 attack CSV script parser & TimelineVM runtime.
Supports line delay timeline clock accumulation, array command expansions
(BoneVRepeat, BoneHRepeat, PlatformRepeat), dynamic variable evaluation, and bytecode execution.
"""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Any, Sequence

from nohit.common.constants import (
    FPS,
    DIR_RIGHT, DIR_DOWN, DIR_LEFT, DIR_UP,
    BONE_WHITE, HEART_MODE_BLUE,
)
from nohit.common.coords import CombatZone
from nohit.common.types import Command

# Fast trigonometric lookup for 90-degree aligned directions (0: Right, 1: Down, 2: Left, 3: Up)
DIR_COS: dict[int, float] = {0: 1.0, 1: 0.0, 2: -1.0, 3: 0.0}
DIR_SIN: dict[int, float] = {0: 0.0, 1: 1.0, 2: 0.0, 3: -1.0}


class ParsedAttack:
    """Container of parsed and scheduled timeline commands and metadata."""
    __slots__ = (
        "commands",
        "initial_zone",
        "initial_heart_pos",
        "initial_heart_mode",
        "slam_frames",
        "end_frame",
        "raw_script_name",
    )

    def __init__(
        self,
        commands: list[Command],
        initial_zone: CombatZone | None = None,
        initial_heart_pos: tuple[float, float] | None = None,
        initial_heart_mode: int = HEART_MODE_BLUE,
        slam_frames: list[int] | None = None,
        end_frame: int = 150,
        raw_script_name: str = "",
    ):
        self.commands = commands
        self.initial_zone = initial_zone
        self.initial_heart_pos = initial_heart_pos
        self.initial_heart_mode = initial_heart_mode
        self.slam_frames = slam_frames or []
        self.end_frame = end_frame
        self.raw_script_name = raw_script_name

    def get_commands_for_frame(self, frame: int) -> list[Command]:
        """Returns all commands scheduled for the specified discrete frame."""
        return [c for c in self.commands if c.frame == frame]


class AttackScriptParser:
    """Parser and virtual machine for C2 attack scripts."""

    def __init__(self, fps: int = FPS, random_seed: int = 42, attack_seed: int | None = None):
        self.fps = fps
        if attack_seed is None:
            self.rng = random.Random(random_seed)
        else:
            from .attack_rng import AttackRandom
            self.rng = AttackRandom(attack_seed)

    def parse_file(
        self,
        csv_path: str | Path,
        expand_repeats: bool = True,
        max_frames: int = 150,
    ) -> ParsedAttack:
        path = Path(csv_path)
        if not path.is_file():
            raise FileNotFoundError(f"Attack script file not found: {path}")

        with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
            content = f.read()

        return self.parse_text(
            content,
            expand_repeats=expand_repeats,
            max_frames=max_frames,
            script_name=path.name,
        )

    def parse_text(
        self,
        csv_text: str,
        expand_repeats: bool = True,
        max_frames: int = 150,
        script_name: str = "custom",
    ) -> ParsedAttack:
        lines = [line.strip() for line in csv_text.splitlines() if line.strip()]

        # Detect whether script contains TimelineCPU instructions
        vm_keywords = ("SET", "JMP", "RND", "SUB", "ADD", "MUL", "DIV", "MOD", "FLOOR", "SIN", "COS")
        is_cpu_script = any(
            any(f",{kw}," in f",{line}," or line.startswith(f"{kw},") for kw in vm_keywords)
            for line in lines
        )

        if is_cpu_script:
            commands = self._execute_vm(lines, max_frames=max_frames)
        else:
            commands = self._parse_linear(lines, max_frames=max_frames)

        if expand_repeats:
            commands = self._expand_repeat_commands(commands)

        # Extract initial keyframe parameters
        initial_zone: CombatZone | None = None
        initial_heart_pos: tuple[float, float] | None = None
        initial_heart_mode: int = HEART_MODE_BLUE
        slam_frames: list[int] = []
        end_frame: int = max_frames

        for cmd in commands:
            if cmd.cmd_type in ("CombatZoneResize", "CombatZoneResizeInstant") and initial_zone is None:
                p = cmd.params
                if "x1" in p and "y1" in p and "x2" in p and "y2" in p:
                    initial_zone = CombatZone(x1=p["x1"], y1=p["y1"], x2=p["x2"], y2=p["y2"])
            elif cmd.cmd_type == "HeartTeleport" and (initial_heart_pos is None or cmd.frame == 0):
                if "x" in cmd.params and "y" in cmd.params:
                    initial_heart_pos = (cmd.params["x"], cmd.params["y"])
            elif cmd.cmd_type == "HeartMode":
                if "mode" in cmd.params:
                    initial_heart_mode = cmd.params["mode"]
            elif cmd.cmd_type == "SansSlam":
                slam_frames.append(cmd.frame)
            elif cmd.cmd_type == "EndAttack":
                end_frame = min(end_frame, cmd.frame)

        return ParsedAttack(
            commands=commands,
            initial_zone=initial_zone,
            initial_heart_pos=initial_heart_pos,
            initial_heart_mode=initial_heart_mode,
            slam_frames=slam_frames,
            end_frame=end_frame,
            raw_script_name=script_name,
        )

    def _eval_token(self, token: str, variables: dict[str, Any]) -> Any:
        token = token.strip()
        if not token:
            return 0
        if token.startswith("$"):
            var_name = token[1:]
            return variables.get(var_name, 0)
        try:
            if "." in token:
                return float(token)
            return int(token)
        except ValueError:
            return token

    def _parse_linear(self, lines: list[str], max_frames: int) -> list[Command]:
        commands: list[Command] = []
        clock = 0.0

        for line in lines:
            parts = [p.strip() for p in line.split(",")]
            # Strip trailing empty columns
            while len(parts) > 2 and parts[-1] == "":
                parts.pop()

            if len(parts) < 2:
                continue

            delay_str = parts[0]
            try:
                delay = float(delay_str) if delay_str else 0.0
            except ValueError:
                delay = 0.0

            clock += delay
            frame = int(round(clock * self.fps))

            cmd_type = parts[1]
            raw_args = parts[2:]
            params = self._build_params(cmd_type, raw_args, {})

            commands.append(Command(
                frame=frame,
                time_s=clock,
                cmd_type=cmd_type,
                params=params,
                raw_args=raw_args,
            ))

        return commands

    def _execute_vm(self, lines: list[str], max_frames: int) -> list[Command]:
        commands: list[Command] = []
        variables: dict[str, Any] = {}
        clock = 0.0
        line_idx = 1  # 1-indexed to align with C2 script line numbering
        steps = 0
        max_steps = 50000

        line_map = {i + 1: lines[i] for i in range(len(lines))}
        max_time_s = max_frames / float(self.fps)

        # Pre-scan for labels: e.g. ":Begin", ":End"
        label_map: dict[str, int] = {}
        for idx in range(1, len(lines) + 1):
            l_str = line_map[idx]
            p_list = [p.strip() for p in l_str.split(",")]
            if len(p_list) >= 2 and p_list[1].startswith(":"):
                lbl = p_list[1].lstrip(":")
                label_map[lbl] = idx

        def _resolve_target(tok: Any) -> int:
            stok = str(tok).strip().lstrip(":")
            if stok in label_map:
                return label_map[stok]
            try:
                return int(float(tok))
            except (ValueError, TypeError):
                return line_idx + 1

        while line_idx in line_map and steps < max_steps:
            steps += 1
            line = line_map[line_idx]
            parts = [p.strip() for p in line.split(",")]
            while len(parts) > 2 and parts[-1] == "":
                parts.pop()

            if len(parts) < 2:
                line_idx += 1
                continue

            delay_str = parts[0]
            try:
                delay = float(delay_str) if delay_str else 0.0
            except ValueError:
                delay = 0.0

            clock += delay
            frame = int(round(clock * self.fps))

            cmd = parts[1]
            args = parts[2:]

            if cmd.startswith(":"):
                line_idx += 1
                continue
            elif cmd == "SET" and len(args) >= 2:
                var_name = args[0].lstrip("$")
                variables[var_name] = self._eval_token(args[1], variables)
                line_idx += 1
            elif cmd == "ADD" and len(args) >= 3:
                dest = args[0].lstrip("$")
                a = float(self._eval_token(args[1], variables))
                b = float(self._eval_token(args[2], variables))
                variables[dest] = a + b
                line_idx += 1
            elif cmd == "SUB" and len(args) >= 3:
                dest = args[0].lstrip("$")
                a = float(self._eval_token(args[1], variables))
                b = float(self._eval_token(args[2], variables))
                variables[dest] = a - b
                line_idx += 1
            elif cmd == "MUL" and len(args) >= 3:
                dest = args[0].lstrip("$")
                a = float(self._eval_token(args[1], variables))
                b = float(self._eval_token(args[2], variables))
                variables[dest] = a * b
                line_idx += 1
            elif cmd == "DIV" and len(args) >= 3:
                dest = args[0].lstrip("$")
                a = float(self._eval_token(args[1], variables))
                b = float(self._eval_token(args[2], variables))
                variables[dest] = (a / b) if b != 0.0 else 0.0
                line_idx += 1
            elif cmd == "MOD" and len(args) >= 3:
                dest = args[0].lstrip("$")
                a = float(self._eval_token(args[1], variables))
                b = float(self._eval_token(args[2], variables))
                variables[dest] = (a % b) if b != 0.0 else 0.0
                line_idx += 1
            elif cmd == "FLOOR" and len(args) >= 2:
                dest = args[0].lstrip("$")
                a = float(self._eval_token(args[1], variables))
                variables[dest] = math.floor(a)
                line_idx += 1
            elif cmd == "SIN" and len(args) >= 2:
                dest = args[0].lstrip("$")
                ang = float(self._eval_token(args[1], variables))
                variables[dest] = math.sin(math.radians(ang))
                line_idx += 1
            elif cmd == "COS" and len(args) >= 2:
                dest = args[0].lstrip("$")
                ang = float(self._eval_token(args[1], variables))
                variables[dest] = math.cos(math.radians(ang))
                line_idx += 1
            elif cmd == "RND" and len(args) >= 2:
                dest = args[0].lstrip("$")
                max_val = int(float(self._eval_token(args[1], variables)))
                variables[dest] = self.rng.randint(0, max(0, max_val - 1))
                line_idx += 1
            elif cmd == "JMPABS" and len(args) >= 1:
                target = _resolve_target(self._eval_token(args[0], variables))
                line_idx = target
            elif cmd == "JMPREL" and len(args) >= 1:
                offset = int(float(self._eval_token(args[0], variables)))
                line_idx += offset
            elif cmd == "JMPZ" and len(args) >= 2:
                target = _resolve_target(self._eval_token(args[0], variables))
                val = float(self._eval_token(args[1], variables))
                line_idx = target if val == 0.0 else line_idx + 1
            elif cmd == "JMPNZ" and len(args) >= 2:
                target = _resolve_target(self._eval_token(args[0], variables))
                val = float(self._eval_token(args[1], variables))
                line_idx = target if val != 0.0 else line_idx + 1
            elif cmd in ("JMPE", "JMPNE", "JMPL", "JMPNL") and len(args) >= 3:
                target = _resolve_target(self._eval_token(args[0], variables))
                va = float(self._eval_token(args[1], variables))
                vb = float(self._eval_token(args[2], variables))
                if cmd == "JMPE":
                    cond = (va == vb)
                elif cmd == "JMPNE":
                    cond = (va != vb)
                elif cmd == "JMPL":
                    cond = (va < vb)
                else:
                    cond = (va >= vb)
                line_idx = target if cond else line_idx + 1
            elif cmd == "EndAttack":
                commands.append(Command(frame=frame, time_s=clock, cmd_type=cmd, params={}, raw_args=args))
                break
            else:
                eval_args = [str(self._eval_token(a, variables)) for a in args]
                params = self._build_params(cmd, eval_args, variables)
                commands.append(Command(frame=frame, time_s=clock, cmd_type=cmd, params=params, raw_args=args))
                line_idx += 1

            if clock > max_time_s + 5.0:
                break

        return commands

    def _build_params(self, cmd_type: str, args: list[str], vars_dict: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {}
        try:
            if cmd_type in ("CombatZoneResize", "CombatZoneResizeInstant"):
                if len(args) >= 4:
                    params["x1"] = float(args[0])
                    params["y1"] = float(args[1])
                    params["x2"] = float(args[2])
                    params["y2"] = float(args[3])
                if len(args) > 4 and args[4]:
                    params["callback"] = args[4]
            elif cmd_type == "CombatZoneSpeed" and len(args) >= 1:
                params["speed"] = float(args[0])
            elif cmd_type == "HeartTeleport" and len(args) >= 2:
                params["x"] = float(args[0])
                params["y"] = float(args[1])
            elif cmd_type == "HeartMode" and len(args) >= 1:
                params["mode"] = int(float(args[0]))
            elif cmd_type == "HeartMaxFallSpeed" and len(args) >= 1:
                params["speed"] = float(args[0])
            elif cmd_type == "BoneV" and len(args) >= 5:
                params["x"] = float(args[0])
                params["y"] = float(args[1])
                params["height"] = float(args[2])
                params["direction"] = int(float(args[3]))
                params["speed"] = float(args[4])
                params["color"] = int(float(args[5])) if len(args) > 5 and args[5] != "" else BONE_WHITE
            elif cmd_type == "BoneVRepeat" and len(args) >= 7:
                params["start_x"] = float(args[0])
                params["start_y"] = float(args[1])
                params["height"] = float(args[2])
                params["direction"] = int(float(args[3]))
                params["speed"] = float(args[4])
                params["count"] = int(float(args[5]))
                params["spacing"] = float(args[6])
                params["color"] = int(float(args[7])) if len(args) > 7 and args[7] != "" else BONE_WHITE
            elif cmd_type == "BoneH" and len(args) >= 5:
                params["x"] = float(args[0])
                params["y"] = float(args[1])
                params["width"] = float(args[2])
                params["direction"] = int(float(args[3]))
                params["speed"] = float(args[4])
                params["color"] = int(float(args[5])) if len(args) > 5 and args[5] != "" else BONE_WHITE
            elif cmd_type == "BoneHRepeat" and len(args) >= 7:
                params["start_x"] = float(args[0])
                params["start_y"] = float(args[1])
                params["width"] = float(args[2])
                params["direction"] = int(float(args[3]))
                params["speed"] = float(args[4])
                params["count"] = int(float(args[5]))
                params["spacing"] = float(args[6])
                params["color"] = int(float(args[7])) if len(args) > 7 and args[7] != "" else BONE_WHITE
            elif cmd_type == "BoneStab" and len(args) >= 4:
                params["direction"] = int(float(args[0]))
                params["height"] = float(args[1])
                params["warn_time"] = float(args[2])
                params["stab_time"] = float(args[3])
            elif cmd_type == "Platform" and len(args) >= 5:
                params["x"] = float(args[0])
                params["y"] = float(args[1])
                params["width"] = float(args[2])
                params["direction"] = int(float(args[3]))
                params["speed"] = float(args[4])
                params["reverse"] = bool(int(float(args[5]))) if len(args) > 5 and args[5] else False
            elif cmd_type == "PlatformRepeat" and len(args) >= 7:
                params["start_x"] = float(args[0])
                params["start_y"] = float(args[1])
                params["width"] = float(args[2])
                params["direction"] = int(float(args[3]))
                params["speed"] = float(args[4])
                params["count"] = int(float(args[5]))
                params["spacing"] = float(args[6])
            elif cmd_type == "SansSlam" and len(args) >= 1:
                params["direction"] = int(float(args[0]))
            elif cmd_type == "SansBody" and len(args) >= 1:
                params["pose"] = args[0]
            elif cmd_type == "GasterBlaster" and len(args) >= 8:
                params["size"] = int(float(args[0]))
                params["spawn_x"] = float(args[1])
                params["spawn_y"] = float(args[2])
                params["target_x"] = float(args[3])
                params["target_y"] = float(args[4])
                params["angle"] = float(args[5])
                params["wait_time"] = float(args[6])
                params["beam_time"] = float(args[7])
        except (ValueError, IndexError):
            pass
        return params

    def _expand_repeat_commands(self, commands: list[Command]) -> list[Command]:
        expanded: list[Command] = []
        for cmd in commands:
            if cmd.cmd_type == "BoneVRepeat":
                p = cmd.params
                direction = p.get("direction", 0)
                cos_val = DIR_COS.get(direction, 0.0)
                sin_val = DIR_SIN.get(direction, 0.0)
                count = p.get("count", 0)
                spacing = p.get("spacing", 0.0)
                for i in range(count):
                    # Repeats step BACKWARD along the spacing axis:
                    #     x_i = start_x - cos(direction) * spacing * i
                    # so a right-facing group (direction 0) is laid out at
                    # start_x, start_x - 120, start_x - 240, ... and the
                    # leftward group (direction 2) at start_x, start_x + 120, ...
                    #
                    # Verified against the live engine's 32 bone instances at
                    # tick 200 (h=95, abs x):
                    #     0.5 120.5 240.5   390.5 510.5 630.5 750.5 870.5 990.5 ...
                    # which is exactly {128 - 120i} shifted by the 12-frame spawn
                    # delay, and {503 + 120i} for the direction-2 line. The tests
                    # in tests/unit/test_baker.py::TestParser pin this too.
                    xi = p["start_x"] - cos_val * spacing * i
                    yi = p["start_y"] - sin_val * spacing * i
                    expanded.append(Command(
                        frame=cmd.frame,
                        time_s=cmd.time_s,
                        cmd_type="BoneV",
                        params={
                            "x": xi,
                            "y": yi,
                            "height": p["height"],
                            "direction": direction,
                            "speed": p["speed"],
                            "color": p.get("color", BONE_WHITE),
                        },
                        raw_args=cmd.raw_args,
                    ))
            elif cmd.cmd_type == "BoneHRepeat":
                p = cmd.params
                direction = p.get("direction", 0)
                cos_val = DIR_COS.get(direction, 0.0)
                sin_val = DIR_SIN.get(direction, 0.0)
                count = p.get("count", 0)
                spacing = p.get("spacing", 0.0)
                for i in range(count):
                    # Repeats step BACKWARD along the spacing axis:
                    #     x_i = start_x - cos(direction) * spacing * i
                    # so a right-facing group (direction 0) is laid out at
                    # start_x, start_x - 120, start_x - 240, ... and the
                    # leftward group (direction 2) at start_x, start_x + 120, ...
                    #
                    # Verified against the live engine's 32 bone instances at
                    # tick 200 (h=95, abs x):
                    #     0.5 120.5 240.5   390.5 510.5 630.5 750.5 870.5 990.5 ...
                    # which is exactly {128 - 120i} shifted by the 12-frame spawn
                    # delay, and {503 + 120i} for the direction-2 line. The tests
                    # in tests/unit/test_baker.py::TestParser pin this too.
                    xi = p["start_x"] - cos_val * spacing * i
                    yi = p["start_y"] - sin_val * spacing * i
                    expanded.append(Command(
                        frame=cmd.frame,
                        time_s=cmd.time_s,
                        cmd_type="BoneH",
                        params={
                            "x": xi,
                            "y": yi,
                            "width": p["width"],
                            "direction": direction,
                            "speed": p["speed"],
                            "color": p.get("color", BONE_WHITE),
                        },
                        raw_args=cmd.raw_args,
                    ))
            elif cmd.cmd_type == "PlatformRepeat":
                p = cmd.params
                direction = p.get("direction", 0)
                cos_val = DIR_COS.get(direction, 0.0)
                sin_val = DIR_SIN.get(direction, 0.0)
                count = p.get("count", 0)
                spacing = p.get("spacing", 0.0)
                for i in range(count):
                    # Repeats step BACKWARD along the spacing axis:
                    #     x_i = start_x - cos(direction) * spacing * i
                    # so a right-facing group (direction 0) is laid out at
                    # start_x, start_x - 120, start_x - 240, ... and the
                    # leftward group (direction 2) at start_x, start_x + 120, ...
                    #
                    # Verified against the live engine's 32 bone instances at
                    # tick 200 (h=95, abs x):
                    #     0.5 120.5 240.5   390.5 510.5 630.5 750.5 870.5 990.5 ...
                    # which is exactly {128 - 120i} shifted by the 12-frame spawn
                    # delay, and {503 + 120i} for the direction-2 line. The tests
                    # in tests/unit/test_baker.py::TestParser pin this too.
                    xi = p["start_x"] - cos_val * spacing * i
                    yi = p["start_y"] - sin_val * spacing * i
                    expanded.append(Command(
                        frame=cmd.frame,
                        time_s=cmd.time_s,
                        cmd_type="Platform",
                        params={
                            "x": xi,
                            "y": yi,
                            "width": p["width"],
                            "direction": direction,
                            "speed": p["speed"],
                        },
                        raw_args=cmd.raw_args,
                    ))
            else:
                expanded.append(cmd)
        return expanded


def parse_csv_timeline(csv_path: str | Path, fps: int = FPS, attack_seed: int | None = None) -> list[Command]:
    """Convenience helper parsing CSV file into expanded list of Command objects."""
    parser = AttackScriptParser(fps=fps, attack_seed=attack_seed)
    parsed = parser.parse_file(csv_path, expand_repeats=True)
    return parsed.commands


def parse_attack(csv_path: str | Path, fps: int = FPS) -> ParsedAttack:
    """Convenience helper parsing CSV file into ParsedAttack structure."""
    parser = AttackScriptParser(fps=fps)
    return parser.parse_file(csv_path, expand_repeats=True)
