"""Exact arrow-control congruence for known environment microtick blocks.

Only for reachability with a next-step input-latch state quotient. This does
not preserve arbitrary costs charged for pressing semantically unused keys.
"""
import numpy as np


def _jump_bit(row):
    direction=row[5]
    return 1 if direction==0. else 4 if direction==1. else 2 if direction==2. else 8


def control_classes(rows,controls,*,next_environment=None):
    """Partition all supplied controls; every alias has the same next language.

    Without a next environment, retain every actual final mask. Otherwise
    equivalent words give identical output fields except raw old keymask,
    whose next-step projection is identical. Every microtick kinematic and
    damage field is equal, so collision checks and terminal-latch equivalence
    are preserved even at walls, platforms, slams, and gravity changes.
    """
    rows=np.asarray(rows)
    if rows.ndim!=2 or rows.shape[1]<7 or not len(rows) or not np.isfinite(rows).all():
        raise ValueError('finite nonempty environment rows required')
    controls=tuple(controls)
    if any(isinstance(mask,(bool,np.bool_)) or not isinstance(mask,(int,np.integer)) or not 0<=mask<32 for mask in controls):
        raise ValueError('movement controls must be integers in [0,31]')
    if next_environment is not None:
        next_environment=np.asarray(next_environment)
        if next_environment.ndim!=1 or len(next_environment)<7 or not np.isfinite(next_environment).all():
            raise ValueError('finite next environment required')
    groups={}
    for raw in controls:
        mask=int(raw);ux=int(bool(mask&2))-int(bool(mask&1));up=int(bool(mask&4))-int(bool(mask&8))
        signature=[bool(mask&16)]
        for row in rows:
            if row[4]==0. and row[6]==0.:
                signature.append(('red',ux,up))
            else:
                signature.append(('blue',bool(mask&_jump_bit(row)),
                    up if row[5] in (0.,2.) else ux))
        if next_environment is None:
            signature.append(('full_mask',mask))
        elif next_environment[4]!=0. or next_environment[6]!=0.:
            signature.append(('next_jump',bool(mask&_jump_bit(next_environment))))
        groups.setdefault(tuple(signature),[]).append(mask)
    return tuple(tuple(group) for group in groups.values())
