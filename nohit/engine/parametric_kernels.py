"""Compiled arithmetic for parameterized DAG edges and soft action ordering.

The Python iterator retains environment binding, backtracking, and proof state.
These kernels batch the existing scalar operators without changing their order.
"""
import numpy as np
from numba import njit
from .discrete_operator import step_mask_into, step_action_into
from .cspace import collision_query, guidance_query, navigation_query
from .adaptive_dag import create_coast_hint, create_support_coast_hint, support_center_target


coast_survival=create_coast_hint(step_action_into,collision_query)
support_coast_survival=create_support_coast_hint(step_action_into,collision_query)


@njit(cache=True)
def hold_kernel(white,blue,env,platforms,state,mask,tick,stop,origin_tick,payload):
    """Advance absolute motion rows; collision arrays begin at origin_tick."""
    q=state.copy()
    for future in range(tick+1,stop+1):
        step_mask_into(q,mask,env[future],platforms[future],q)
        if collision_query(white,blue,future-origin_tick,q,0.,payload):
            return True,q
    return False,q


@njit(cache=True)
def coast_counts(state,masks,start,stop,env,platforms,white,blue,payload,support,mask_count):
    counts=np.zeros(len(masks),np.int64)
    if stop<=start:return counts
    for i in range(len(masks)):
        mask=int(masks[i])
        survived=coast_survival(state,mask,start,stop,env,platforms,white,blue,payload)
        if support:
            survived=max(survived,support_coast_survival(state,mask,start,stop,
                env[:stop+1],platforms[:stop+1],white,blue,payload,mask_count))
        counts[i]=survived
    return counts


@njit(cache=True)
def option_scores(state,old_mask,masks,tick,hold,origin_tick,env,platforms,
                  guide,navigation,ox,oy,cell_size,weights,lookahead_ticks,
                  forecast_ticks,forecast_dt,support,coast_stop,survived,
                  axis_preference,jump_bit):
    """Original score expressions, in original binary64 evaluation order.

    Forecast dt values are supplied from cached NumPy slice sums: Numba's sum
    or differences of prefix sums need not share NumPy's rounding order.
    Scores only order exact edges; no score can reject an action.
    """
    scores=np.empty(len(masks),np.float64)
    for i in range(len(masks)):
        mask=int(masks[i])
        probe=state.copy()
        for future in range(tick+1,min(tick+hold+1,len(env))):
            step_mask_into(probe,mask,env[future],platforms[future],probe)
        vx,vy=probe[2],probe[3]
        moving=vx!=0. or vy!=0.
        score=0.
        if weights[0]:
            score+=weights[0]*guidance_query(guide,min(tick+hold,len(env)-1)-origin_tick,
                probe[0],probe[1],ox,oy,cell_size,moving)
        if weights[1] and lookahead_ticks:
            score-=weights[1]*navigation_query(navigation,min(tick+hold,len(env)-1)-origin_tick,
                probe[0],probe[1],ox,oy,cell_size,16)*10.
        for f in range(len(forecast_ticks)):
            future=forecast_ticks[f];dt=forecast_dt[f];arena=env[future]
            x=max(arena[0]+13.,min(arena[2]-13.,state[0]+vx*dt))
            y=max(arena[1]+13.,min(arena[3]-13.,state[1]+vy*dt))
            if weights[1]:
                clearance=guidance_query(guide,future-origin_tick,x,y,ox,oy,cell_size,moving)
                score+=weights[1]*clearance
            center_x=(arena[0]+arena[2])*.5
            if support and weights[2]:
                forecast=probe.copy();forecast[0]=x;forecast[1]=y
                center_x=support_center_target(forecast,arena,platforms[future])
            score-=weights[2]*(abs(x-center_x)+abs(y-(arena[1]+arena[3])*.5))*.03
        score-=weights[3]*int(mask!=old_mask)
        if coast_stop>tick:
            score+=weights[1]*200.*survived[i]/(coast_stop-tick)
        if axis_preference>=0 and (mask&jump_bit)==axis_preference:
            score+=weights[1]*1.e5
        scores[i]=score
    return scores
