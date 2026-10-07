"""Unpruned native float64 DP for the calibrated Platforms4Hard slice.
Hash collisions compare every state field. No quantization or beam pruning.
External geometry/clock are supplied explicitly; no original runtime calls.
"""
import math
import numpy as np
from numba import njit


@njit(cache=True,inline="always")
def overlap(x,y,px,py,w,h,offset=0.0):
    return x+8>px and x-8<px+w and y+offset+8>py and y+offset-8<py+h


@njit(cache=True,inline="always")
def solid(x,y,dy,p,offset=0.0):
    px,py,w,h,pdx,pdy,dt=p
    return (x-8<118 or x+8>543 or y+offset-8<236 or y+offset+8>386
        or (overlap(x,y,px,py,w,h,offset) and py>y+offset and dy>=pdy and y+8<=py+2))


@njit(cache=True,inline="always")
def native_values(sx,sy,sdx,sdy,previous_up,ux,up,p,dt_override=-1.):
    px,py,w,h,pdx,pdy,dt=p
    if dt_override>0:
        dt=dt_override
    x=sx
    movement=sdx*dt
    count_x=max(1,int(math.floor(abs(movement)+.5)))
    for sub in range(1,count_x+1):
        candidate=sx+movement*(sub/count_x)
        if solid(candidate,sy,sdy,p):
            break
        x=candidate
    y,dy=sy,sdy
    move=dy*dt
    count=max(1,int(math.floor(abs(move)+.5)))
    start=y
    for sub in range(1,count+1):
        candidate=start+move*(sub/count)
        if solid(x,candidate,dy,p):
            y=start+move*((sub-1)/count)
            dy=0.0
            break
        y=candidate
    if up and not previous_up and solid(x,y,dy,p,1.0):
        dy-=180.0
    if previous_up and not up and dy < -30:
        dy=-30.0
    gravity=0.0
    if 15<dy<240:
        gravity=540.0
    elif -30<dy<=15:
        gravity=180.0
    elif -120<dy<=-30:
        gravity=450.0
    elif dy<=-120:
        gravity=180.0
    if not solid(x,y,dy,p,.2):
        dy=min(750.0,dy+gravity*dt)
    dx=0.0
    if overlap(x,y,px,py,w,h,.5) and dy>=pdy and y+8<=py+2:
        dx,dy,y=pdx,pdy,py-8.05
    dx+=ux*150.0
    return x,y,dx,dy,float(up)


@njit(cache=True,inline="always")
def native_micro_into(s,ux,up,p,out):
    x,y,dx,dy,previous=native_values(s[0],s[1],s[2],s[3],s[4],ux,up,p)
    out[0]=x
    out[1]=y
    out[2]=dx
    out[3]=dy
    out[4]=previous
    return out


@njit(cache=True)
def native_micro(s,ux,up,p):
    return native_micro_into(s,ux,up,p,np.empty(5,np.float64))


@njit(cache=True,inline="always")
def same_state(a,b):
    # Bit comparison includes tiny velocity components and input latch.
    aa=a.view(np.uint64)
    bb=b.view(np.uint64)
    for i in range(a.size):
        if aa[i]!=bb[i]:
            return False
    return True


@njit(cache=True,inline="always")
def state_hash(s):
    bits=s.view(np.uint64)
    h=np.uint64(1469598103934665603)
    for i in range(s.size):
        h=(h^bits[i])*np.uint64(1099511628211)
    return h


@njit(cache=True,inline="always")
def blocked_xy(mask, tick, xpos, ypos):
    xl, xh = int(math.floor(xpos)), int(math.ceil(xpos))
    yl, yh = int(math.floor(ypos)), int(math.ceil(ypos))
    for x in (xl,xh):
        for y in (yl,yh):
            xx = x-113
            yy = y-231
            if xx<0 or xx>=435 or yy<0 or yy>=160:
                return True
            if mask[tick,yy,xx//64] & (np.uint64(1)<<np.uint64(xx%64)):
                return True
    return False


@njit(cache=True,inline="always")
def blocked(mask,tick,s):
    return blocked_xy(mask,tick,s[0],s[1])


@njit(cache=True)
def search(mask, schedule, initial, max_states=100000, max_nodes=2000000):
    current=np.empty((max_states,5),np.float64)
    following=np.empty_like(current)
    current[0]=initial
    current_ids=np.zeros(max_states,np.int32)
    following_ids=np.empty_like(current_ids)
    parents=np.empty(max_nodes,np.int32)
    actions=np.empty((max_nodes,2),np.int8)
    parents[0]=-1
    size=1
    while size<max_states*4:
        size*=2
    slots=np.empty(size,np.int32)
    epochs=np.zeros(size,np.int32)
    count=1
    node_count=1
    layers=(len(mask)-1)//4
    history=np.zeros(layers+1,np.int32)
    history[0]=1
    for frame in range(layers):
        n=0
        for i in range(count):
            for up in range(2):
                for ux in range(-1,2):
                    child=current[i].copy()
                    safe=True
                    for micro in range(4):
                        tick=frame*4+micro+1
                        native_micro_into(child,ux,up,schedule[tick],child)
                        if blocked(mask,tick,child):
                            safe=False
                            break
                    if not safe:
                        continue
                    h=state_hash(child)
                    h^=h>>np.uint64(30)
                    h*=np.uint64(0xbf58476d1ce4e5b9)
                    h^=h>>np.uint64(27)
                    slot=np.int64(h & np.uint64(size-1))
                    while epochs[slot]==frame+1 and not same_state(following[slots[slot]],child):
                        slot=(slot+1)&(size-1)
                    if epochs[slot]==frame+1:
                        continue
                    if n==max_states or node_count==max_nodes:
                        return 2,frame,history,parents[:node_count],actions[:node_count],-1
                    epochs[slot]=frame+1
                    slots[slot]=n
                    following[n]=child
                    following_ids[n]=node_count
                    parents[node_count]=current_ids[i]
                    actions[node_count,0]=ux
                    actions[node_count,1]=up
                    node_count+=1
                    n+=1
        if n==0:
            return 1,frame,history,parents[:node_count],actions[:node_count],-1
        current,following=following,current
        current_ids,following_ids=following_ids,current_ids
        count=n
        history[frame+1]=n
    return 0,layers,history,parents[:node_count],actions[:node_count],int(current_ids[0])


@njit(cache=True,inline="always")
def product_micro_into(s,ux,up,p,out,tick):
    for member in range(0,s.size,5):
        dt=p[6]
        profile=(member//15)%3
        phase=(tick-1)%4
        if profile==1:
            if phase==0:
                dt=.0041
            elif phase==3:
                dt=4*p[6]-.0125
            else:
                dt=.0042
        elif profile==2:
            if phase==1:
                dt=.0041
            elif phase==2:
                dt=4*p[6]-.0125
            else:
                dt=.0042
        x,y,dx,dy,previous=native_values(s[member],s[member+1],s[member+2],s[member+3],s[member+4],ux,up,p,dt)
        out[member]=x
        out[member+1]=y
        out[member+2]=dx
        out[member+3]=dy
        out[member+4]=previous


@njit(cache=True,inline="always")
def product_blocked(mask,tick,s):
    for member in range(0,s.size,5):
        if blocked_xy(mask,tick,s[member],s[member+1]):
            return True
    return False


@njit(cache=True)
def search_depth_first(mask,schedule,initial,max_expansions=2000000,max_dead=500000,anticipation=0,deadband=6.0,h_toggle_weight=0.01):
    """Lazy exact graph traversal, no beam. Ordering affects speed, not actions.

    Stops at first witness; no optimality claim. A resource limit is explicit.
    Keeping the DFS stack avoids allocating unreachable future layers.
    """
    layers=(len(mask)-1)//4
    stack=np.empty((layers+1,initial.size),np.float64)
    stack[0]=initial
    children=np.empty((layers,6,initial.size),np.float64)
    choices=np.empty((layers,6,2),np.int8)
    scores=np.empty((layers,6),np.float64)
    counts=np.full(layers,-1,np.int32)
    cursors=np.zeros(layers,np.int32)
    route=np.empty((layers,2),np.int8)
    visits=np.zeros(layers+1,np.int64)
    size=1
    while size<max_dead*4:
        size*=2
    dead_depth=np.full(size,-1,np.int32)
    dead_state=np.empty((max_dead,initial.size),np.float64)
    dead_ids=np.empty(size,np.int32)
    dead_count=0
    depth=0
    expansions=0
    child=np.empty(initial.size,np.float64)
    forecast=np.empty(5,np.float64)
    while depth>=0:
        if depth==layers:
            return 0,depth,expansions,visits,route.copy()
        if counts[depth]<0:
            if expansions>=max_expansions:
                return 2,depth,expansions,visits,route[:0].copy()
            expansions+=1
            visits[depth]+=1
            n=0
            prev_ux=np.int8(0)
            if depth>0:
                prev_ux=route[depth-1,0]
            for up in range(2):
                for ux in range(-1,2):
                    child[:]=stack[depth]
                    safe=True
                    for micro in range(4):
                        tick=depth*4+micro+1
                        product_micro_into(child,ux,up,schedule[tick],child,tick)
                        if product_blocked(mask,tick,child):
                            safe=False
                            break
                    if not safe:
                        continue
                    duplicate=False
                    for j in range(n):
                        if same_state(children[depth,j],child):
                            duplicate=True
                            break
                    if duplicate:
                        continue
                    children[depth,n]=child
                    choices[depth,n,0]=ux
                    choices[depth,n,1]=up
                    # Platform center deadband
                    p=schedule[(depth+1)*4]
                    target_x=p[0]+p[2]/2.0
                    dist_to_center=abs(child[0]-target_x)
                    if dist_to_center<=deadband:
                        center_cost=0.0
                    else:
                        center_cost=dist_to_center-deadband
                    scores[depth,n]=center_cost+max(0.,child[1]-327.95)*3.0+up*0.01

                    # Horizontal toggle penalty (suppress PWM chatter)
                    if depth>0:
                        if ux!=prev_ux:
                            if ux!=0 and prev_ux!=0 and ux==-prev_ux:
                                scores[depth,n]+=h_toggle_weight*2.0
                            else:
                                scores[depth,n]+=h_toggle_weight

                    # Op-1: Nominal member 0 anticipation rollout
                    if anticipation>0:
                        forecast[0]=child[0]
                        forecast[1]=child[1]
                        forecast[2]=child[2]
                        forecast[3]=child[3]
                        forecast[4]=child[4]
                        horizon=min(anticipation*4,len(mask)-1-tick)
                        survived=0
                        for ahead in range(1,horizon+1):
                            future=tick+ahead
                            native_micro_into(forecast,0,up,schedule[future],forecast)
                            if blocked_xy(mask,future,forecast[0],forecast[1]):
                                break
                            survived+=1
                        scores[depth,n]+=1000*(horizon-survived)
                    if depth==0:
                        # Prefer settling the measured incoming momentum before a jump.
                        # Other first-frame actions stay in the graph for backtracking.
                        if ux!=0 or up!=0:
                            scores[depth,n]+=1000000
                    n+=1
            # Six-way insertion sort. Every safe distinct successor remains.
            for j in range(1,n):
                k=j
                while k>0 and scores[depth,k]<scores[depth,k-1]:
                    v=scores[depth,k-1]
                    scores[depth,k-1]=scores[depth,k]
                    scores[depth,k]=v
                    child=children[depth,k-1].copy()
                    children[depth,k-1]=children[depth,k]
                    children[depth,k]=child
                    action=choices[depth,k-1].copy()
                    choices[depth,k-1]=choices[depth,k]
                    choices[depth,k]=action
                    k-=1
            counts[depth]=n
            cursors[depth]=0
        if cursors[depth]>=counts[depth]:
            h=state_hash(stack[depth])^np.uint64(depth*1099511628211)
            h^=h>>np.uint64(30)
            h*=np.uint64(0xbf58476d1ce4e5b9)
            slot=np.int64(h & np.uint64(size-1))
            while dead_depth[slot]>=0 and not (dead_depth[slot]==depth and same_state(dead_state[dead_ids[slot]],stack[depth])):
                slot=(slot+1)&(size-1)
            if dead_depth[slot]<0:
                if dead_count>=max_dead:
                    return 2,depth,expansions,visits,route[:0].copy()
                dead_depth[slot]=depth
                dead_ids[slot]=dead_count
                dead_state[dead_count]=stack[depth]
                dead_count+=1
            counts[depth]=-1
            depth-=1
            continue
        j=cursors[depth]
        cursors[depth]+=1
        child=children[depth,j]
        h=state_hash(child)^np.uint64((depth+1)*1099511628211)
        h^=h>>np.uint64(30)
        h*=np.uint64(0xbf58476d1ce4e5b9)
        slot=np.int64(h & np.uint64(size-1))
        while dead_depth[slot]>=0 and not (dead_depth[slot]==depth+1 and same_state(dead_state[dead_ids[slot]],child)):
            slot=(slot+1)&(size-1)
        if dead_depth[slot]>=0:
            continue
        stack[depth+1]=child
        route[depth]=choices[depth,j]
        depth+=1
        if depth<layers:
            counts[depth]=-1
    return 1,0,expansions,visits,route[:0].copy()


@njit(cache=True)
def reconstruct_native(initial,actions,schedule):
    """Op-4: Fast native trajectory reconstructor avoiding Python-C ABI overhead."""
    layers=len(actions)
    trace=np.empty((layers+1,5),np.float64)
    trace[0]=initial[:5]
    state=initial[:5].copy()
    for frame_index in range(layers):
        ux=actions[frame_index,0]
        up=actions[frame_index,1]
        for micro in range(4):
            tick=frame_index*4+micro+1
            native_micro_into(state,ux,up,schedule[tick],state)
        trace[frame_index+1]=state
    return trace


TOTAL_CELLS = 435 * 160 * 48 * 2  # 6,681,600


@njit(cache=True, inline="always")
def get_equivalence_cell(x, y, dy, prev_up):
    # Equivalence binning: 4px x, 4px y, 40 px/s vy, prev_up
    ix = int((x - 113.0) * 0.25)
    if ix < 0:
        ix = 0
    elif ix >= 109:
        ix = 108

    iy = int((y - 231.0) * 0.25)
    if iy < 0:
        iy = 0
    elif iy >= 40:
        iy = 39

    ivy = int((dy + 200.0) * 0.025)
    if ivy < 0:
        ivy = 0
    elif ivy >= 24:
        ivy = 23

    iup = int(prev_up)
    if iup < 0:
        iup = 0
    elif iup > 1:
        iup = 1
    return ((ix * 40 + iy) * 24 + ivy) * 2 + iup


@njit(cache=True, inline="always")
def product_blocked_members_1_to_end(mask, tick, s):
    for member in range(5, s.size, 5):
        if blocked_xy(mask, tick, s[member], s[member + 1]):
            return True
    return False


@njit(cache=True)
def search_frs_dp_bellman(
    mask,
    schedule,
    initial,
    max_states=30000,
    deadband=6.0,
    h_toggle_weight=0.01,
    max_beam=0,
    anticipation=12,
    exact=True,
    max_expansions=10000000,
):
    """Time-layered FRS-DP with exact product-state Bellman folding by default.

    Strictly preserves all 9 perturbation members (45 fields) across all 4 microsteps.
    Hash collisions compare all state bits and the previous horizontal action.
    Optional approximate folding/beam caps generate witnesses, never prove no route.
    Minimizes accumulated Bellman cost (key chatter penalty + hazard clearance + platform centering).
    Reconstructs optimal witness trajectory in O(T) linear time.
    """
    if max_states < 1 or max_beam < 0 or max_expansions < 1:
        raise ValueError('FRS resource limits must be positive; beam 0 means uncapped')
    layers = (len(mask) - 1) // 4
    state_size = initial.size

    # Static pre-allocated double-buffered queues
    current_queue = np.empty((max_states, state_size), dtype=np.float64)
    next_queue = np.empty((max_states, state_size), dtype=np.float64)

    current_costs = np.empty(max_states, dtype=np.float64)
    next_costs = np.empty(max_states, dtype=np.float64)

    # Linear O(T) DAG history
    parent_history = np.empty((layers, max_states), dtype=np.int32)
    action_history = np.empty((layers, max_states, 2), dtype=np.int8)

    # Flat 1D epoch tables for O(1) Bellman folding
    table_size = 1
    if exact:
        while table_size < max_states * 4:
            table_size *= 2
    else:
        table_size = TOTAL_CELLS
    visited_epoch = np.zeros(table_size, dtype=np.int32)
    best_cost = np.empty(table_size, dtype=np.float64)
    cell_to_idx = np.empty(table_size, dtype=np.int32)
    discarded = False

    # Initialize root
    for k in range(state_size):
        current_queue[0, k] = initial[k]
    current_costs[0] = 0.0
    current_count = 1

    visits = np.zeros(layers + 1, dtype=np.int64)
    visits[0] = 1

    child = np.empty(state_size, dtype=np.float64)
    expansions = 0

    for frame in range(layers):
        next_count = 0
        epoch = frame + 1

        for i in range(current_count):
            if expansions >= max_expansions:
                return 2, frame, expansions, visits, np.empty((0, 2), dtype=np.int8)
            expansions += 1
            prev_ux = np.int8(0)
            if frame > 0:
                prev_ux = action_history[frame - 1, i, 0]

            parent_cost = current_costs[i]

            for up in range(2):
                for ux in range(-1, 2):
                    # Op-2: Member 0 fast reject
                    m0_x = current_queue[i, 0]
                    m0_y = current_queue[i, 1]
                    m0_dx = current_queue[i, 2]
                    m0_dy = current_queue[i, 3]
                    m0_prev = current_queue[i, 4]
                    m0_safe = True

                    for micro in range(4):
                        tick = frame * 4 + micro + 1
                        m0_x, m0_y, m0_dx, m0_dy, m0_prev = native_values(
                            m0_x, m0_y, m0_dx, m0_dy, m0_prev, ux, up, schedule[tick]
                        )
                        if blocked_xy(mask, tick, m0_x, m0_y):
                            m0_safe = False
                            break

                    if not m0_safe:
                        continue

                    # Full 9-member product dynamics
                    if state_size > 5:
                        for k in range(state_size):
                            child[k] = current_queue[i, k]
                        safe = True
                        for micro in range(4):
                            tick = frame * 4 + micro + 1
                            product_micro_into(child, ux, up, schedule[tick], child, tick)
                            if product_blocked_members_1_to_end(mask, tick, child):
                                safe = False
                                break
                        if not safe:
                            continue
                    else:
                        child[0] = m0_x
                        child[1] = m0_y
                        child[2] = m0_dx
                        child[3] = m0_dy
                        child[4] = m0_prev

                    # Bellman Cost calculation
                    step_cost = 0.0

                    # 1. Key toggle penalty
                    if frame > 0:
                        if ux != prev_ux:
                            if ux != 0 and prev_ux != 0 and ux == -prev_ux:
                                step_cost += h_toggle_weight * 2.0
                            else:
                                step_cost += h_toggle_weight

                    if up != current_queue[i, 4]:
                        step_cost += h_toggle_weight

                    if frame == 0:
                        if ux != 0 or up != 0:
                            step_cost += 1000.0

                    # 2. Platform centering & sinking
                    p = schedule[(frame + 1) * 4]
                    target_x = p[0] + p[2] * 0.5
                    dist_to_center = abs(child[0] - target_x)
                    if dist_to_center <= deadband:
                        center_cost = 0.0
                    else:
                        center_cost = dist_to_center - deadband

                    sink_cost = max(0.0, child[1] - 327.95) * 3.0
                    step_cost += center_cost + sink_cost

                    # Hazard Clearance penalty: penalize proximity to obstacles
                    last_tick = frame * 4 + 4
                    clearance_cost = 0.0
                    if blocked_xy(mask, last_tick, child[0] + 4.0, child[1]):
                        clearance_cost += 5.0
                    if blocked_xy(mask, last_tick, child[0] - 4.0, child[1]):
                        clearance_cost += 5.0
                    if blocked_xy(mask, last_tick, child[0], child[1] - 4.0):
                        clearance_cost += 5.0
                    if blocked_xy(mask, last_tick, child[0], child[1] + 4.0):
                        clearance_cost += 5.0
                    step_cost += clearance_cost

                    total_cost = parent_cost + step_cost

                    # Equivalence folding
                    if exact:
                        h = state_hash(child) ^ np.uint64(ux + 1)
                        h ^= h >> np.uint64(30)
                        h *= np.uint64(0xbf58476d1ce4e5b9)
                        cell = np.int64(h & np.uint64(table_size - 1))
                        while visited_epoch[cell] == epoch:
                            existing_idx = cell_to_idx[cell]
                            if (action_history[frame, existing_idx, 0] == ux and
                                    same_state(next_queue[existing_idx], child)):
                                break
                            cell = (cell + 1) & (table_size - 1)
                    else:
                        cell = get_equivalence_cell(child[0], child[1], child[3], child[4])

                    if visited_epoch[cell] != epoch:
                        if next_count >= max_states:
                            empty_route = np.empty((0, 2), dtype=np.int8)
                            return 2, frame, expansions, visits, empty_route
                        child_idx = next_count
                        next_count += 1
                        visited_epoch[cell] = epoch
                        best_cost[cell] = total_cost
                        cell_to_idx[cell] = child_idx
                        for k in range(state_size):
                            next_queue[child_idx, k] = child[k]
                        next_costs[child_idx] = total_cost
                        parent_history[frame, child_idx] = i
                        action_history[frame, child_idx, 0] = ux
                        action_history[frame, child_idx, 1] = up
                    else:
                        existing_idx = cell_to_idx[cell]
                        if not exact and (not same_state(next_queue[existing_idx], child) or
                                          action_history[frame, existing_idx, 0] != ux):
                            discarded = True
                        if total_cost < best_cost[cell]:
                            existing_idx = cell_to_idx[cell]
                            best_cost[cell] = total_cost
                            for k in range(state_size):
                                next_queue[existing_idx, k] = child[k]
                            next_costs[existing_idx] = total_cost
                            parent_history[frame, existing_idx] = i
                            action_history[frame, existing_idx, 0] = ux
                            action_history[frame, existing_idx, 1] = up

        if next_count == 0:
            empty_route = np.empty((0, 2), dtype=np.int8)
            return (3 if discarded else 1), frame, expansions, visits, empty_route

        # Cap states per frame to max_beam
        if max_beam > 0 and next_count > max_beam:
            discarded = True
            order = np.argsort(next_costs[:next_count])
            temp_parent = np.empty(max_beam, dtype=np.int32)
            temp_ux = np.empty(max_beam, dtype=np.int8)
            temp_up = np.empty(max_beam, dtype=np.int8)
            for j in range(max_beam):
                idx = order[j]
                temp_parent[j] = parent_history[frame, idx]
                temp_ux[j] = action_history[frame, idx, 0]
                temp_up[j] = action_history[frame, idx, 1]
                for k in range(state_size):
                    current_queue[j, k] = next_queue[idx, k]
                current_costs[j] = next_costs[idx]
            for j in range(max_beam):
                parent_history[frame, j] = temp_parent[j]
                action_history[frame, j, 0] = temp_ux[j]
                action_history[frame, j, 1] = temp_up[j]
                for k in range(state_size):
                    next_queue[j, k] = current_queue[j, k]
                next_costs[j] = current_costs[j]
            next_count = max_beam

        # Swap queue buffers
        current_queue, next_queue = next_queue, current_queue
        current_costs, next_costs = next_costs, current_costs
        current_count = next_count
        visits[frame + 1] = current_count

    # Backtracking: select minimum cost survivor
    best_idx = 0
    min_cost = current_costs[0]
    for k in range(1, current_count):
        if current_costs[k] < min_cost:
            min_cost = current_costs[k]
            best_idx = k

    route = np.empty((layers, 2), dtype=np.int8)
    curr = best_idx
    for f in range(layers - 1, -1, -1):
        route[f, 0] = action_history[f, curr, 0]
        route[f, 1] = action_history[f, curr, 1]
        curr = parent_history[f, curr]

    return 0, layers, expansions, visits, route
