"""
nohit.baker
~~~~~~~~~~~
C-space Hazard Baker package.
Exports `bake_cspace` pipeline and underlying parser, rasterizer, and dilator modules.
"""

from __future__ import annotations

from nohit.common.types import BakeResult, PlatformInstance
from .dilator import (
    bake_cspace,
    dilate_cspace,
    dilate_2d,
    dilate_3d,
    dilate_cspace_2d,
    pack_hazard_tensor,
    unpack_hazard_tensor,
)
from .parser import (
    AttackScriptParser,
    ParsedAttack,
    parse_attack,
    parse_csv_timeline,
)
from .rasterizer import (
    RasterizerConfig,
    RasterResult,
    rasterize_csv,
    rasterize_timeline,
)

__all__ = [
    "bake_cspace",
    "dilate_cspace",
    "dilate_2d",
    "dilate_3d",
    "dilate_cspace_2d",
    "pack_hazard_tensor",
    "unpack_hazard_tensor",
    "PlatformInstance",
    "BakeResult",
    "AttackScriptParser",
    "ParsedAttack",
    "parse_attack",
    "parse_csv_timeline",
    "RasterizerConfig",
    "RasterResult",
    "rasterize_csv",
    "rasterize_timeline",
]
