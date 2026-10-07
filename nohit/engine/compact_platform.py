"""Pure world-coordinate blue-heart transition, first Platforms4Hard slice.

No game runtime/checkpoints are used. Environment is an explicit input. This
module is calibrated independently before connecting the complete lattice.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class Player:
    x: float
    y: float
    dx: float
    dy: float
    previous_up: int = 0


@dataclass(frozen=True, slots=True)
class Platform:
    x: float
    y: float
    width: float
    height: float = 7.0
    dx: float = 90.0
    dy: float = 0.0


def _overlap(x, y, platform, offset=0.0):
    return (x + 8 > platform.x and x - 8 < platform.x + platform.width
            and y + offset + 8 > platform.y and y + offset - 8 < platform.y + platform.height)


def _solid(x, y, dy, p, offset=0.0):
    border = x - 8 < 118 or x + 8 > 543 or y + offset - 8 < 236 or y + offset + 8 > 386
    return border or (_overlap(x, y, p, offset) and p.y > y + offset
            and dy >= p.dy and y + 8 <= p.y + 2)


def microstep(s: Player, action, p: Platform, dt=1.0 / 240.0):
    """p is the platform after its own behaviour tick, before player events."""
    ux, up = action
    x = s.x
    movement = s.dx * dt
    count_x = max(1, int(math.floor(abs(movement) + .5)))
    for sub in range(1, count_x + 1):
        candidate = s.x + movement * (sub / count_x)
        if _solid(candidate, s.y, s.dy, p):
            break
        x = candidate
    y, dy = s.y, s.dy
    move = dy * dt
    count = max(1, int(math.floor(abs(move) + .5)))
    start = y
    for sub in range(1, count + 1):
        candidate = start + move * (sub / count)
        if _solid(x, candidate, dy, p):
            y = start + move * ((sub - 1) / count)
            dy = 0.0
            break
        y = candidate
    if up and not s.previous_up and _solid(x, y, dy, p, 1.0):
        dy -= 180.0
    if s.previous_up and not up and dy < -30:
        dy = -30.0
    gravity = 0.0
    if 15 < dy < 240:
        gravity = 540.0
    elif -30 < dy <= 15:
        gravity = 180.0
    elif -120 < dy <= -30:
        gravity = 450.0
    elif dy <= -120:
        gravity = 180.0
    if not _solid(x, y, dy, p, .2):
        dy = min(750.0, dy + gravity * dt)
    dx = 0.0
    if _overlap(x, y, p, .5) and dy >= p.dy and y + 8 <= p.y + 2:
        dx, dy, y = p.dx, p.dy, p.y - 8.05
    dx += ux * 150.0
    return Player(x, y, dx, dy, up)


def platform_at(microtick: int):
    """Compiled reflective platform schedule for the first supported wave."""
    if not 0 <= microtick <= 1752:
        raise ValueError("unsupported platform horizon")
    phase = microtick
    if phase < 976:
        return Platform(151.0 + .375 * phase, 336.0, 31.0)
    return Platform(517.0 - .375 * (phase - 976), 336.0, 31.0,
                    dx=-90.0, dy=math.sin(math.pi) * 90.0)
