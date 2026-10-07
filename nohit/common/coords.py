"""
nohit.common.coords
~~~~~~~~~~~~~~~~~~~
Construct 2 canvas coordinate system <-> C-space local grid coordinate system
bijective mapping functions and AABB envelope projections.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class CombatZone:
    """Represents a Construct 2 combat bounding box in canvas coordinates."""
    x1: float
    y1: float
    x2: float
    y2: float
    border_thickness: float = 5.0

    @property
    def inner_left(self) -> float:
        """Canvas X coordinate of inner left arena wall."""
        return self.x1 + self.border_thickness

    @property
    def inner_right(self) -> float:
        """Canvas X coordinate of inner right arena wall."""
        return self.x2 - self.border_thickness

    @property
    def inner_top(self) -> float:
        """Canvas Y coordinate of inner ceiling."""
        return self.y1 + self.border_thickness

    @property
    def inner_bottom(self) -> float:
        """Canvas Y coordinate of inner floor surface (y=0 in local C-space)."""
        return self.y2 - self.border_thickness

    @property
    def inner_width(self) -> float:
        """Internal usable width in canvas pixels."""
        return max(0.0, self.inner_right - self.inner_left)

    @property
    def inner_height(self) -> float:
        """Internal usable height in canvas pixels."""
        return max(0.0, self.inner_bottom - self.inner_top)


def c2_to_cspace_point(xc2: float, yc2: float, zone: CombatZone) -> tuple[float, float]:
    """Converts Construct 2 canvas point (xc2, yc2) to local C-space coordinate (x, y).

    In C-space, the bottom-left of the inner arena is (0, 0), +x is right, +y is up.
    """
    x = xc2 - zone.inner_left
    y = zone.inner_bottom - yc2
    return (x, y)


def cspace_to_c2_point(x: float, y: float, zone: CombatZone) -> tuple[float, float]:
    """Converts local C-space coordinate (x, y) to Construct 2 canvas point (xc2, yc2)."""
    xc2 = x + zone.inner_left
    yc2 = zone.inner_bottom - y
    return (xc2, yc2)


def c2_to_cspace_box(
    xc2: float,
    yc2: float,
    w: float,
    h: float,
    zone: CombatZone,
) -> tuple[float, float, float, float]:
    """Converts Construct 2 rectangle (xc2, yc2, w, h) to C-space AABB (xmin, ymin, xmax, ymax).

    In C2, (xc2, yc2) is the top-left corner, +Y goes downward.
    In C-space, (xmin, ymin) is the bottom-left corner, +y goes upward.
    """
    xmin = xc2 - zone.inner_left
    xmax = xmin + w
    ymax = zone.inner_bottom - yc2
    ymin = ymax - h
    return (xmin, ymin, xmax, ymax)


def cspace_to_c2_box(
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
    zone: CombatZone,
) -> tuple[float, float, float, float]:
    """Converts C-space AABB (xmin, ymin, xmax, ymax) to C2 rectangle (xc2, yc2, w, h)."""
    xc2 = xmin + zone.inner_left
    w = xmax - xmin
    h = ymax - ymin
    yc2 = zone.inner_bottom - ymax
    return (xc2, yc2, w, h)


def c2_to_cspace_velocity(vx_c2: float, vy_c2: float) -> tuple[float, float]:
    """Converts C2 velocity vector to C-space velocity vector.

    Horizontal direction is unchanged (+X right).
    Vertical direction is inverted (C2 +Y is down, C-space +Y is up).
    """
    return (vx_c2, -vy_c2)


def cspace_to_c2_velocity(vx: float, vy: float) -> tuple[float, float]:
    """Converts C-space velocity vector to C2 velocity vector."""
    return (vx, -vy)


def c2_to_grid(
    cx: float,
    cy: float,
    c2_x1: float,
    c2_y1: float,
    c2_x2: float,
    c2_y2: float,
    W: int = 200,
    H: int = 160,
) -> tuple[int, int]:
    """Normalized grid mapping from canvas bounds [c2_x1, c2_x2] x [c2_y1, c2_y2] to [0, W) x [0, H)."""
    gx = int(round((cx - c2_x1) / (c2_x2 - c2_x1) * W))
    gy = int(round((cy - c2_y1) / (c2_y2 - c2_y1) * H))
    return max(0, min(W - 1, gx)), max(0, min(H - 1, gy))


def grid_to_c2(
    gx: int,
    gy: int,
    c2_x1: float,
    c2_y1: float,
    c2_x2: float,
    c2_y2: float,
    W: int = 200,
    H: int = 160,
) -> tuple[float, float]:
    """Inverse normalized grid mapping from [0, W) x [0, H) to canvas coordinates."""
    cx = c2_x1 + (gx / float(W)) * (c2_x2 - c2_x1)
    cy = c2_y1 + (gy / float(H)) * (c2_y2 - c2_y1)
    return cx, cy
