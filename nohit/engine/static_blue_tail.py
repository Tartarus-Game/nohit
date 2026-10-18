"""Sufficient EOF fact: every remaining bone is blue and exactly stationary."""
import numpy as np


def stationary_blue_rows(bones):
    if not len(bones):return []
    if hasattr(bones,'rows'):
        rows=np.asarray(bones.rows[:bones.count])
    else:
        rows=np.asarray([[b.x,b.y,b.w,b.h,b.vx,b.vy,b.color,b.direction] for b in bones],dtype=float)
    if rows.ndim!=2 or rows.shape[1]!=8 or not np.isfinite(rows).all():return None
    if np.any(rows[:,4:6]!=0.) or np.any(rows[:,6]!=1.):return None
    return rows.tolist()


def valid_static_blue(details):
    count=details.get('active_bones')
    rows=details.get('static_blue_bones')
    if type(count) is not int or count<=0 or not isinstance(rows,list) or len(rows)!=count:return False
    try:array=np.asarray(rows,dtype=float)
    except (ValueError,TypeError):return False
    return bool(array.shape==(count,8) and np.isfinite(array).all() and
                np.all(array[:,4:6]==0.) and np.all(array[:,6]==1.))


def blue_tail_collision(state,details):
    if not details.get('active_bones') or (state[2]==0. and state[3]==0.):return False
    x,y=state[:2]
    for bx,by,w,h,*_ in details.get('static_blue_bones',[]):
        if x+2.>=min(bx,bx+w) and x-2.<=max(bx,bx+w) and y+2.>=min(by,by+h) and y-2.<=max(by,by+h):return True
    return False
