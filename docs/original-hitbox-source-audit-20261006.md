# Original hitbox and damage phase source audit

This is a read-only source audit. It does not change the game, solver, model,
or chart, and does not establish native no-hit completion or native UNSAT.

## Conclusion

During a normal visible-heart attack, the original damage event checks a
centered, axis-aligned **4 by 4 square at the final Heart position**. Its
configuration-space footprint is `[-2,2] x [-2,2]`, not a Euclidean radius-2
disk. Rectangle contact counts as overlap. No source evidence was found for a
smaller hitbox, pixel-rounded hitbox following, or periodic hidden-heart
invulnerability that would explain the current long-window model obstruction.

## Identity and shape

- `repo_jcw87/Bad Time Simulator (Sans Fight).caproj:948` defines PlayerHitbox,
  SID `728293317807613`, Sprite, hotspot `(0.5,0.5)`.
- `repo_jcw87/Layouts/System.xml:954` defines UID 57, width 4, height 4, angle 0,
  invisible, collisions enabled.
- In the served `c2-sans-fight/data.js`, this is **type64**, not type65.
  PlayerHeart SID `5960708907117077` is **type54**, not type55.
- The hitbox frame is `images/playerhitbox-sheet0.png`, 4 by 4, hotspot
  `(0.5,0.5)`, empty custom collision polygon. Sprite construction initializes
  raw `.ga` from this polygon (`c2runtime.js:395`). Empty `.ga.jg()` means
  `!this.hr.length` (`:19`), so collision falls back to the quad.
- A repository-wide PlayerHitbox search found only creation, following, and
  the three overlap checks. There are no hitbox size/angle/collision mutations.

## Position and phase

`repo_jcw87/Event sheets/Battle.xml:7748` begins PlayerDamage, after
PlayerMovement, Bones, BoneStab, GasterBlasters, MenuBones, CombatZone, and
SansAnimation. Layout startup creates the hitbox on PlayerHeart's layer.
The first Every-tick damage action (`:7769`, SID `601136598806736`) sets its
position to PlayerHeart image point 0 before damage overlap checks.

The exported action references function-table entry 110,
`V.prototype.e.Eo`. This calls `Heart.nf(0,true)` and `Heart.nf(0,false)`.
`nf` (`c2runtime.js:405`) maps image point 0 to index -1 and directly returns
`this.x` or `this.y`. There is no rounding or previous-position use.

## Collision and damage predicates

Runtime overlap `Fy` (`c2runtime.js:142-144`) requires both collision-enable
flags, updates bounding boxes, rejects disjoint boxes/quads, and then tests
custom polygons only where nonempty. It has **no visibility or opacity gate**.
Its same-layer/equivalent-transform branch is the ordinary battle case; any
certificate transfer must still establish that the hazard geometry and layer
transform used by the model match those native objects.

`Qa.Xw` (`:7`) rejects only strict separation. `Xb.Kp` (`:11-12`) checks
quad centers and all edge pairs; the segment intersection helper `va` uses
closed comparisons. Boundary contact of these nondegenerate rectangles is
therefore collision, consistent with a closed-square C-space obstacle.

PlayerDamage's outer gate is `LastDamageTime < time - 0.033`.
On a no-hit path this cannot grant recurring immunity, although initialization
and the global time origin must be respected. The attack-family gates are:

- AttackSprite (`Battle.xml:7890`): overlap, positive Damage, **Heart visible**.
- AttackTiled (`:7977`): overlap and positive Damage; no Heart visibility gate.
- Attack9Patch (`:8017`): overlap and positive Damage; color 0 unconditional,
  color 1 requires CustomMovement moving, color 2 requires not moving.

Heart is hidden only by MenuFightEnemy, MenuCheckSans, MenuUseItem, MenuSpare,
or the HP-at-most-zero death sequence. EndAttack and HeartTeleport show it.
There is no attack-phase periodic visibility exception in this event sheet.

## Diagnostic warning

The adapter's friendly `collision_poly` alias points at raw `.Ua`, while the
engine collision implementation reads raw **`.ga`**. This is a diagnostic
alias discrepancy, not evidence that native collision uses the wrong shape.
Read-only native captures should inspect `.ga`, actual hitbox dimensions,
angle, center, collision-enabled flag, and layer transforms explicitly.

## Beam/bone polygons and layer equivalence

The further source audit identifies these concrete damaging types:

| Type | SID | Export type | Plugin | Raw custom polygon |
| --- | --- | --- | --- | --- |
| GasterBlastHit | 165116925986465 | 42 | TiledBg | `ga=null` |
| BoneH | 3019589746608161 | 29 | NinePatch | `ga=null` |
| BoneV | 3868174782291034 | 30 | NinePatch | `ga=null` |
| BoneStabH | 6503092777075739 | 36 | NinePatch | `ga=null` |
| BoneStabV | 8140934880742138 | 35 | NinePatch | `ga=null` |

The runtime world-instance creation defaults undefined `.ga` to null.
Only the Sprite constructor assigns a collision polygon; the NinePatch (`Y`)
and TiledBg (`zc`) constructors do not. Their exported object definitions have
texture data but no animation collision polygon. Thus their actual damage
geometry is the full bquad, regardless of transparency in the rendered texture.

Heart starts on CombatZone (`BattleScreen.xml:523`), as does its created hitbox.
BoneH is created on CombatZone (`Battle.xml:4493`), BoneV on
CombatZoneClipped (`:4537`), and GasterBlaster on CombatZone (`:5447`), with
GasterBlastHit in its created container. BoneStabH/V use CombatZoneClipped.

Both layers (`BattleScreen.xml:507,571`) have parallax `(1,1)`, zoom-rate 1,
default scale 1 and angle 0. Exported layer entries agree on all transformation
fields; their difference in force-own-texture affects rendering only. A scan
of **all** source event sheets finds no layer scale, layer angle, or parallax
mutation. Screen shake changes layout scroll, common to both layers. Therefore
the normal attack source follows the runtime's equivalent-transform overlap
branch, with no additional relative layer transformation.

Existing linear native captures listed in
`scratch/realhell-linear-native-independent-verdict.json` cover the requested
window only through tick **1488**, not 1528. In ticks 1264--1488, their active
hazard records contain 950 GasterBlastHit observations, 27 BoneStabH, and 27
BoneStabV, exactly the polygon-free plugin types above. Those records include
actual bbox/bquad but do **not** include raw `.ga` or layer fields. The polygon
and layer conclusions here are source-derived invariants, not additional live
measurements. No custom Sprite collision polygon is being ignored for those
recorded active hazards. In particular MenuBone's genuine custom Sprite
polygons must not be generalized to these beam/stab objects.

## Source hashes (SHA256)

- `c2-sans-fight/c2runtime.js`:
  `664B5D93DBD5159976D490663AC64C49C8EB7DC68C9AAC92FBA940B6FA2A3DE9`
- `c2-sans-fight/data.js`:
  `9F70E7179FE4260002321A75E5170E96583439BB39988B92ED93DA42A0A402C7`
- `repo_jcw87/Event sheets/Battle.xml`:
  `92161897251B4CADE135B52292CFB0AE3A3E437C82FFDCA06E564C7479B32467`
