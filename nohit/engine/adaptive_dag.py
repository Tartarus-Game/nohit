"""Exact layered DAG dynamic programming over a supplied dynamics operator.

The only state reduction is bit-identical Markov state plus the previous
control used by switch cost. Each layer is completed before the next begins;
equal successors receive Bellman cost relaxation. Neither reward weights nor
preferred clearance participate in reachability. A budget stop is not UNSAT.
"""
import numpy as np
from numba import njit
from .canonical_lattice import step_into, collision
from .compact_lattice import same_state, state_hash


@njit(cache=True, inline='always')
def direct_collision(white, blue, tick, state, margin, collision_data):
    return collision(white, blue, tick, state, margin)


def create_coast_hint(transition,collision_query):
    """Create an exact held-input forecast used only for soft ordering.

    The returned count excludes the first collision tick. Forecasts must stop
    before an unbound player observation; they never certify full reachability.
    """
    @njit(cache=True)
    def survival(state,mask,start_tick,stop_tick,env,platforms,white,blue,collision_data,up=0,margin=0.):
        q=state.copy()
        survived=0
        for tick in range(start_tick+1,min(stop_tick,len(env)-1)+1):
            transition(q,mask,up,env[tick],platforms[tick],q)
            if collision_query(white,blue,tick,q,margin,collision_data):break
            survived+=1
        return survived
    return survival


def create_landing_hint(transition):
    """Soft distance from a held-input ballistic landing to moving support.

    Damage is deliberately ignored in this forecast: the outer edge remains
    subject to its exact predicate, and this hint can only reorder alternatives.
    The source platform behavior is downward-gravity only. Other modes return
    no preference, as do states already supported at the control boundary.
    """
    @njit(cache=True)
    def gap(state,mask,start_tick,stop_tick,env,platforms,up=0):
        if len(state)<8 or state[6]!=1. or state[7]!=1. or not platforms.shape[1]:return 0.
        for p in platforms[start_tick]:
            if (p[6] and abs(state[1]-(p[1]-8.05))<.2 and abs(state[3]-p[5])<.01
                    and state[0]+8.>p[0] and state[0]-8.<p[0]+p[2]):return 0.
        q=state.copy()
        best=1.e12
        for tick in range(start_tick+1,min(stop_tick,len(env)-1)+1):
            previous_y=q[1]
            transition(q,mask,up,env[tick],platforms[tick],q)
            if q[6]!=1. or q[7]!=1.:break
            for index in range(platforms.shape[1]):
                p=platforms[tick,index]
                old=platforms[tick-1,index]
                if (p[6] and old[6] and previous_y<=old[1]-8.+.1 and q[1]>=p[1]-8.-.1
                        and q[3]>=p[5]-.01):
                    # Collision uses the heart's 8px solid hitbox. Favor a
                    # little interior landing clearance without rejecting edges.
                    lo=p[0]-6.;hi=p[0]+p[2]+6.
                    distance=max(lo-q[0],q[0]-hi,0.)
                    best=min(best,distance)
                    if best==0.:return 0.
        return min(best,128.)/32. if best<1.e12 else 0.
    return gap


@njit(cache=True,inline='always')
def nearest_support(state,platform_row):
    if len(state)<8 or state[6]!=1. or state[7]!=1.:return -1
    nearest=1.e12;selected=-1
    for index in range(len(platform_row)):
        p=platform_row[index]
        if p[6]:
            distance=abs(state[1]-(p[1]-8.05))+.25*max(p[0]-8.-state[0],state[0]-p[0]-p[2]-8.,0.)
            if distance<nearest:nearest=distance;selected=index
    return selected


@njit(cache=True,inline='always')
def support_center_target(state,env_row,platform_row):
    """Return nearest support's horizontal center, or the ordinary arena center."""
    selected=nearest_support(state,platform_row)
    if selected>=0:return platform_row[selected,0]+platform_row[selected,2]*.5
    return (env_row[0]+env_row[2])*.5


def create_support_coast_hint(transition,collision_query):
    """Forecast legal horizontal feedback that follows moving support.

    The supplied jump/release remains held; horizontal input is reselected
    every four physics ticks. It is a soft forecast, never a safety certificate.
    """
    @njit(cache=True)
    def survival(state,mask,start_tick,stop_tick,env,platforms,white,blue,collision_data,allowed_mask_count=32):
        q=state.copy();survived=0;control=mask
        for tick in range(start_tick+1,min(stop_tick,len(env)-1)+1):
            if ((tick-start_tick-1)%4==0 and len(q)>=8 and q[6]==1. and q[7]==1. and platforms.shape[1]):
                selected=nearest_support(q,platforms[tick-1])
                if selected>=0:
                    p=platforms[tick-1,selected]
                    future=platforms[min(tick+3,stop_tick,len(env)-1),selected]
                    target=future[0]+future[2]*.5
                    carry=0.
                    if abs(q[1]-(p[1]-8.05))<.2 and abs(q[3]-p[5])<.01 and p[0]-8.<q[0]<p[0]+p[2]+8.:
                        carry=p[4]
                    best=1.e12
                    for lateral in (0,1,2,17,18):
                        trial=(mask&12)|lateral
                        if trial>=allowed_mask_count:continue
                        speed=0. if lateral==0 else (-150. if lateral==1 else 150. if lateral==2 else -75. if lateral==17 else 75.)
                        predicted=q[0]+env[tick,7]*(q[2]+3.*(speed+carry))
                        error=abs(predicted-target)
                        if error<best:best=error;control=trial
            transition(q,control,0,env[tick],platforms[tick],q)
            if collision_query(white,blue,tick,q,0.,collision_data):break
            survived+=1
        return survived
    return survival


@njit(cache=True, inline='always')
def finalize_hash(h):
    # Float lattice coordinates often have 30+ zero low mantissa bits. Taking
    # FNV's low bits directly makes an entire red-heart time layer collide in
    # one hash bucket. Avalanche every bit before masking the table index.
    h ^= h >> np.uint64(30)
    h *= np.uint64(0xbf58476d1ce4e5b9)
    h ^= h >> np.uint64(27)
    h *= np.uint64(0x94d049bb133111eb)
    return h ^ (h >> np.uint64(31))


@njit(cache=True, inline='always')
def identity_hash(state, ux, up):
    h = state_hash(state) ^ np.uint64((ux + 1) * 3 + up + 1)
    return finalize_hash(h)


@njit(cache=True)
def grow1(array, capacity):
    out = np.empty(capacity, array.dtype)
    out[:len(array)] = array
    return out


@njit(cache=True)
def grow2(array, capacity):
    out = np.empty((capacity, array.shape[1]), array.dtype)
    out[:len(array)] = array
    return out


def create_search_kernel(transition, collision_query):
    """Specialize one recurrence for an exact Numba transition/query pair.

    transition(state, ux, up, env[t], platforms[t], out)
    collision_query(white, blue, t, state, margin, collision_data) -> bool

    State width is supplied by initial. The legacy five-field operator uses
    six blue/down actions; general operators receive all nine directional
    pairs. collision_data is a typed tuple, allowing pre-baked C-space arrays
    without a Python callback in the hot loop.
    """
    @njit(cache=True)
    def kernel(white, blue, env, platforms, initial, max_nodes=500000,
               max_expansions=5000000, margin=0., lookahead=60,
               initial_capacity=4096, weights=None, collision_data=None):
        if weights is None:
            weights = np.array([1., 1., 1., 0.])
        if len(weights) != 4:
            raise ValueError('expected four ranking weights')
        for weight in weights:
            if not np.isfinite(weight) or weight < 0. or weight > 1000.:
                raise ValueError('ranking weights must be finite and between 0 and 1000')
        if max_nodes < 1 or max_expansions < 1 or initial_capacity < 1:
            raise ValueError('search capacities must be positive')
        layers = (len(env) - 1 + 3) // 4
        visits = np.zeros(layers + 1, np.int64)
        empty = np.empty((0, 2), np.int8)
        if collision_query(white, blue, 0, initial, 0., collision_data):
            return 1, 0, 0, visits, empty

        # Only two layers contain physical states. Earlier layers keep compact
        # ancestry, not float state copies or a global heap/hash table.
        cap = min(max_nodes, initial_capacity)
        current = np.empty((cap, len(initial)), np.float64)
        following = np.empty_like(current)
        current_ids = np.empty(cap, np.int32)
        following_ids = np.empty(cap, np.int32)
        current_cost = np.empty(cap, np.float64)
        following_cost = np.empty(cap, np.float64)
        parent = np.empty(cap, np.int32)
        action_x = np.empty(cap, np.int8)
        action_up = np.empty(cap, np.int8)
        ancestry_cap = cap
        current[0] = initial
        current_ids[0] = 0
        current_cost[0] = 0.
        parent[0] = -1
        action_x[0] = 0
        action_up[0] = int(initial[4]) if len(initial) == 5 else 0
        count = 1
        total = 1
        expanded = 0
        visits[0] = 1
        q = np.empty(len(initial), np.float64)
        slots_size = 1
        while slots_size < cap * 2:
            slots_size *= 2
        slots = np.full(slots_size, -1, np.int32)

        for frame in range(layers):
            slots[:] = -1
            next_count = 0
            vertical_count = 3 if (len(initial) != 5 or env[min(frame*4+1, len(env)-1), 4] == 0) else 2
            for index in range(count):
                if expanded >= max_expansions:
                    return 2, frame, expanded, visits, empty
                expanded += 1
                old_id = current_ids[index]
                for up_index in range(vertical_count):
                    up = 0 if up_index == 0 else (1 if up_index == 1 else -1)
                    for x_index in range(3):
                        ux = 0 if x_index == 0 else (-1 if x_index == 1 else 1)
                        q[:] = current[index]
                        safe = True
                        edge_cost = 0.
                        for micro in range(1, 5):
                            tick = frame*4 + micro
                            if tick >= len(env):
                                break
                            transition(q, ux, up, env[tick], platforms[tick], q)
                            if collision_query(white, blue, tick, q, 0., collision_data):
                                safe = False
                                break
                            if weights[0] and margin > 0. and collision_query(white, blue, tick, q, margin, collision_data):
                                edge_cost += weights[0] * .25
                        if not safe:
                            continue
                        end_tick = min((frame + 1)*4, len(env)-1)
                        # Baked future occupancy at the endpoint is a soft
                        # preference only. No repeated dynamics rollout.
                        if weights[1] and lookahead > 0:
                            forecast_tick = min(end_tick + lookahead*4, len(env)-1)
                            if collision_query(white, blue, forecast_tick, q, margin, collision_data):
                                edge_cost += weights[1]
                        if weights[2]:
                            arena = env[end_tick]
                            edge_cost += weights[2] * abs(q[0]-(arena[0]+arena[2])*.5) / max(1., arena[2]-arena[0])
                        if weights[3]:
                            edge_cost += weights[3] * (int(ux != action_x[old_id]) + int(up != action_up[old_id]))
                        cost = current_cost[index] + edge_cost
                        h = identity_hash(q, ux, up)
                        slot = np.int64(h & np.uint64(slots_size-1))
                        found = -1
                        while slots[slot] >= 0:
                            candidate = slots[slot]
                            candidate_id = following_ids[candidate]
                            if action_x[candidate_id] == ux and action_up[candidate_id] == up and same_state(following[candidate], q):
                                found = candidate
                                break
                            slot = (slot+1) & (slots_size-1)
                        if found >= 0:
                            # Bellman relaxation occurs before this successor
                            # layer can be expanded. Improving its parent is
                            # therefore sufficient; no descendants are stale.
                            if cost < following_cost[found]:
                                following_cost[found] = cost
                                parent[following_ids[found]] = old_id
                            continue
                        if total == max_nodes:
                            return 2, frame, expanded, visits, empty
                        if total == ancestry_cap:
                            ancestry_cap = min(max_nodes, ancestry_cap*2)
                            parent = grow1(parent, ancestry_cap)
                            action_x = grow1(action_x, ancestry_cap)
                            action_up = grow1(action_up, ancestry_cap)
                        if next_count == cap:
                            cap = min(max_nodes, cap*2)
                            current = grow2(current, cap)
                            following = grow2(following, cap)
                            current_ids = grow1(current_ids, cap)
                            following_ids = grow1(following_ids, cap)
                            current_cost = grow1(current_cost, cap)
                            following_cost = grow1(following_cost, cap)
                            while slots_size < cap*2:
                                slots_size *= 2
                            slots = np.full(slots_size, -1, np.int32)
                            for previous in range(next_count):
                                previous_id = following_ids[previous]
                                rh = identity_hash(following[previous], action_x[previous_id], action_up[previous_id])
                                rs = np.int64(rh & np.uint64(slots_size-1))
                                while slots[rs] >= 0:
                                    rs = (rs+1) & (slots_size-1)
                                slots[rs] = previous
                            slot = np.int64(h & np.uint64(slots_size-1))
                            while slots[slot] >= 0:
                                slot = (slot+1) & (slots_size-1)
                        slots[slot] = next_count
                        following[next_count] = q
                        following_ids[next_count] = total
                        following_cost[next_count] = cost
                        parent[total] = old_id
                        action_x[total] = ux
                        action_up[total] = up
                        total += 1
                        next_count += 1
                        visits[frame+1] += 1
            if not next_count:
                return 1, frame+1, expanded, visits, empty
            current, following = following, current
            current_ids, following_ids = following_ids, current_ids
            current_cost, following_cost = following_cost, current_cost
            count = next_count

        best = 0
        for index in range(1, count):
            if current_cost[index] < current_cost[best]:
                best = index
        node = current_ids[best]
        route = np.empty((layers, 2), np.int8)
        for frame in range(layers-1, -1, -1):
            route[frame, 0] = action_x[node]
            route[frame, 1] = action_up[node]
            node = parent[node]
        return 0, layers, expanded, visits, route
    return kernel


search = create_search_kernel(step_into, direct_collision)


@njit(cache=True, inline='always')
def next_jump_latch(env, frame):
    tick=min(frame*4+1,len(env)-1)
    if env[tick,4]==0.:
        return 0
    direction=int(env[tick,5])
    return 1 if direction==0 else 4 if direction==1 else 2 if direction==2 else 8


@njit(cache=True, inline='always')
def projected_hash(state, latch):
    bits=state.view(np.uint64)
    h=np.uint64(1469598103934665603)
    for i in range(len(state)):
        value=np.uint64(int(state[i])&latch) if i==4 else bits[i]
        h=(h^value)*np.uint64(1099511628211)
    return h


@njit(cache=True, inline='always')
def projected_equal(a,b,latch):
    aa=a.view(np.uint64);bb=b.view(np.uint64)
    for i in range(len(a)):
        if i==4:
            if int(a[i])&latch != int(b[i])&latch:
                return False
        elif aa[i]!=bb[i]:
            return False
    return True


@njit(cache=True, inline='always')
def equivalent_controls(a,b,env,frame):
    """Equal event-sheet input effects on every tick of this control hold.

    This quotient is specific to discrete_operator's documented key logic.
    Opposite keys are never assumed equivalent merely from net displacement:
    every active jump latch and the next frame's consumed latch are checked.
    """
    ax=((a>>1)&1)-(a&1); ay=((a>>2)&1)-((a>>3)&1)
    bx=((b>>1)&1)-(b&1); by=((b>>2)&1)-((b>>3)&1)
    av=75 if a&16 else 150; bv=75 if b&16 else 150
    for micro in range(1,5):
        tick=frame*4+micro
        if tick>=len(env): break
        if env[tick,4]==0.:
            if ax*av!=bx*bv or ay*av!=by*bv:
                return False
        else:
            direction=int(env[tick,5])
            jump=1 if direction==0 else 4 if direction==1 else 2 if direction==2 else 8
            if bool(a&jump)!=bool(b&jump): return False
            if direction==0 or direction==2:
                if ay*av!=by*bv: return False
            elif ax*av!=bx*bv: return False
    latch=next_jump_latch(env,frame+1)
    return a&latch==b&latch


def create_demand_kernel(transition, collision_query, control_masks=False, project_input_latch=False, guidance_query=None, dead_end_query=None, dead_cache_factory=None,navigation_query=None):
    """Demand-evaluate V(t,s)=OR_u(Q(t,s,u) AND V(t+1,F(t,s,u))).

    This is the same finite time-DAG reachability recurrence as forward FRS.
    It memoizes a state as false ONLY after every legal action has failed.
    Short-circuit success needs one witness, not every reachable frontier.
    All untried actions stay on the explicit stack. Scores order those actions
    only; there is no beam, heap, coordinate binning, or heuristic rejection.
    """
    coast_hint=create_coast_hint(transition,collision_query)
    landing_hint=create_landing_hint(transition)
    support_coast_hint=create_support_coast_hint(transition,collision_query)
    @njit(cache=True)
    def kernel(white, blue, env, platforms, initial, max_nodes=500000,
               max_expansions=5000000, margin=0., lookahead=60,
               initial_capacity=4096, weights=None, collision_data=None, guidance_data=None, progress_actions=None,navigation_data=None,allowed_mask_count=32,coast_ticks=0,landing_weight=0.,platform_center=False,discrepancy_limit=-1):
        if weights is None:
            weights = np.array([1., 1., 1., 0.])
        if len(weights) != 4:
            raise ValueError('expected four ranking weights')
        for weight in weights:
            if not np.isfinite(weight) or weight < 0. or weight > 1000.:
                raise ValueError('ranking weights must be finite and between 0 and 1000')
        if max_nodes < 1 or max_expansions < 1 or initial_capacity < 1:
            raise ValueError('search capacities must be positive')
        layers = (len(env)-1+3)//4
        visits = np.zeros(layers+1, np.int64)
        empty = np.empty((0, 2), np.int8)
        if collision_query(white, blue, 0, initial, 0., collision_data):
            return 1, 0, 0, visits, empty
        width = len(initial)
        action_count = 32 if control_masks else 9
        path = np.empty((layers+1, width), np.float64)
        path[0] = initial
        # Entries retain ALL safe, untried successors until this subproblem is
        # proven false. Their states are small compared to all-layer storage.
        successors = np.empty((layers, action_count, width), np.float64)
        ordered_x = np.empty((layers, action_count), np.int8)
        ordered_up = np.empty((layers, action_count), np.int8)
        scores = np.empty((layers, action_count), np.float64)
        sizes = np.full(layers, -1, np.int32)
        cursor = np.zeros(layers, np.int32)
        chosen = np.zeros((layers, 2), np.int8)
        discrepancies=np.zeros(layers+1,np.int32)
        representatives=np.empty((layers,action_count),np.int8)
        representative_count=np.zeros(layers,np.int32)
        for f in range(layers):
            n=0
            for action in range(action_count):
                if control_masks and action>=allowed_mask_count:continue
                equivalent=False
                if project_input_latch:
                    for previous in range(n):
                        if equivalent_controls(action,int(representatives[f,previous]),env,f):
                            equivalent=True
                            break
                if not equivalent:
                    representatives[f,n]=action
                    n+=1
            representative_count[f]=n
        cap = min(max_nodes, initial_capacity)
        dead_states = np.empty((cap, width), np.float64)
        dead_frame = np.empty(cap, np.int32)
        slot_size = 1
        while slot_size < cap*2:
            slot_size *= 2
        slots = np.full(slot_size, -1, np.int32)
        dead_count = 0
        expanded = 0
        generated = 1
        furthest = 0
        visits[0] = 1
        frame = 0
        q = np.empty(width, np.float64)
        forecast = np.empty(width, np.float64)
        certified_states=np.empty((action_count,width),np.float64)
        certified_values=np.empty(action_count,np.bool_)
        proof_cache=dead_cache_factory(white,env,platforms) if dead_cache_factory is not None else None
        while frame >= 0:
            if frame>furthest:
                furthest=frame
                if progress_actions is not None:
                    progress_actions[:frame]=chosen[:frame]
            if frame == layers:
                return 0, layers, expanded, visits, chosen.copy()
            if sizes[frame] < 0:
                if expanded >= max_expansions:
                    return 2, furthest, expanded, visits, empty
                expanded += 1
                n = 0
                certificates=0
                count = representative_count[frame]
                if not control_masks and width == 5 and env[min(frame*4+1,len(env)-1),4] != 0:
                    count = 6
                for action in range(count):
                    if control_masks:
                        ux, up = int(representatives[frame,action]), 0
                    else:
                        x_index = action % 3
                        up_index = action // 3
                        ux = 0 if x_index == 0 else (-1 if x_index == 1 else 1)
                        up = 0 if up_index == 0 else (1 if up_index == 1 else -1)
                    q[:] = path[frame]
                    safe = True
                    score = 0.
                    for micro in range(1,5):
                        tick = frame*4+micro
                        if tick >= len(env):
                            break
                        transition(q, ux, up, env[tick], platforms[tick], q)
                        if collision_query(white, blue, tick, q, 0., collision_data):
                            safe = False
                            break
                        if weights[0] and margin > 0. and collision_query(white, blue, tick, q, margin, collision_data):
                            score += .25*weights[0]
                    if not safe:
                        continue
                    if dead_end_query is not None:
                        prior=-1
                        for ci in range(certificates):
                            eq=True
                            for axis in range(width):
                                if q.view(np.uint64)[axis]!=certified_states[ci].view(np.uint64)[axis]:eq=False;break
                            if eq:prior=ci;break
                        if prior>=0:
                            dead=certified_values[prior]
                        else:
                            dead=dead_end_query(white,env,platforms,frame+1,q,proof_cache)
                            certified_states[certificates]=q
                            certified_values[certificates]=dead
                            certificates+=1
                        if dead:continue
                    # Exact source-specific bisimulation: previous mask is
                    # consumed only by the NEXT tick's jump-key edge. Later
                    # ticks read the newly supplied input, never these bits.
                    # Keep original states/inputs for replay; project identity
                    # only, and only when explicitly enabled for that operator.
                    if project_input_latch:
                        latch=next_jump_latch(env,frame+1)
                        duplicate=False
                        for previous in range(n):
                            if projected_equal(successors[frame,previous],q,latch):
                                duplicate=True
                                break
                        if duplicate:
                            continue
                    end_tick = min((frame+1)*4,len(env)-1)
                    if guidance_query is not None and weights[0]:
                        _,_,ox,oy,cell_size=collision_data
                        distance=guidance_query(guidance_data,end_tick,q[0],q[1],ox,oy,cell_size,q[2]!=0. or q[3]!=0.)
                        score-=weights[0]*max(-32.,min(32.,distance))/32.
                    if weights[1] and lookahead > 0:
                        if coast_ticks>0:
                            # Exact held-input rollout is a bounded optional
                            # ordering hint for support-dependent movement.
                            # Failure here NEVER rejects an otherwise safe edge.
                            stop=min(len(env)-1,end_tick+coast_ticks)
                            # Forecast survival uses the true damage predicate.
                            # Clearance preference has its own weight; otherwise
                            # weight=0 would still reject narrow forecast routes.
                            survived=coast_hint(q,ux,end_tick,stop,env,platforms,white,blue,collision_data,up,0.)
                            if platform_center and control_masks:
                                survived=max(survived,support_coast_hint(q,ux,end_tick,stop,env,platforms,white,blue,collision_data,allowed_mask_count))
                            score+=weights[1]*4.*(stop-end_tick-survived)/max(1,stop-end_tick)
                            if landing_weight:
                                score+=weights[1]*landing_weight*landing_hint(q,ux,end_tick,stop,env,platforms,up)
                        elif navigation_query is not None:
                            # A baked coarse temporal cost allows future turns;
                            # it is never used as a reachability predicate.
                            _,_,ox,oy,cell_size=collision_data
                            nav,stride=navigation_data
                            score+=weights[1]*navigation_query(nav,end_tick,q[0],q[1],ox,oy,cell_size,stride)
                        else:
                            for fraction in range(1,5):
                                lead = max(1, lookahead*fraction//4)
                                ft = min(end_tick+lead*4,len(env)-1)
                                dt = (ft-end_tick)/240.
                                forecast[:] = q
                                forecast[0] += q[2]*dt
                                forecast[1] += q[3]*dt
                                if guidance_query is not None:
                                    _,_,ox,oy,cell_size=collision_data
                                    distance=guidance_query(guidance_data,ft,forecast[0],forecast[1],ox,oy,cell_size,q[2]!=0. or q[3]!=0.)
                                    score-=weights[1]*(5-fraction)*.1*max(-64.,min(64.,distance))/64.
                                elif collision_query(white, blue, ft, forecast, margin, collision_data):
                                    score += weights[1]*(5-fraction)*.1
                    if weights[2]:
                        arena=env[end_tick]
                        target_x=(arena[0]+arena[2])*.5
                        if platform_center:
                            target_x=support_center_target(q,arena,platforms[end_tick])
                        score += weights[2]*abs(q[0]-target_x)/max(1.,arena[2]-arena[0])
                    if weights[3]:
                        if control_masks:
                            changed = ux ^ int(path[frame,4])
                            changes = 0
                            for bit in range(5):
                                changes += (changed >> bit) & 1
                        else:
                            previous_x = chosen[frame-1,0] if frame else 0
                            previous_up = chosen[frame-1,1] if frame else int(initial[4])
                            changes = int(ux!=previous_x)+int(up!=previous_up)
                        score += weights[3]*changes
                    # Insertion sort of at most32 controls. No global heap.
                    pos=n
                    while pos and score < scores[frame,pos-1]:
                        scores[frame,pos]=scores[frame,pos-1]
                        ordered_x[frame,pos]=ordered_x[frame,pos-1]
                        ordered_up[frame,pos]=ordered_up[frame,pos-1]
                        successors[frame,pos]=successors[frame,pos-1]
                        pos-=1
                    scores[frame,pos]=score
                    ordered_x[frame,pos]=ux
                    ordered_up[frame,pos]=up
                    successors[frame,pos]=q
                    n+=1
                sizes[frame]=n
                cursor[frame]=0
            descended=False
            while cursor[frame]<sizes[frame]:
                action=cursor[frame]
                cursor[frame]+=1
                next_discrepancy=discrepancies[frame]+int(action>0)
                if discrepancy_limit>=0 and next_discrepancy>discrepancy_limit:continue
                q[:]=successors[frame,action]
                identity=projected_hash(q,next_jump_latch(env,frame+1)) if project_input_latch else state_hash(q)
                h=finalize_hash(identity^np.uint64(frame+1)*np.uint64(0x9e3779b97f4a7c15))
                slot=np.int64(h&np.uint64(slot_size-1))
                known_dead=False
                while slots[slot]>=0:
                    row=slots[slot]
                    equal=projected_equal(dead_states[row],q,next_jump_latch(env,frame+1)) if project_input_latch else same_state(dead_states[row],q)
                    if dead_frame[row]==frame+1 and equal:
                        known_dead=True
                        break
                    slot=(slot+1)&(slot_size-1)
                if known_dead:
                    continue
                if generated>=max_nodes:
                    return 2,furthest,expanded,visits,empty
                chosen[frame,0]=ordered_x[frame,action]
                chosen[frame,1]=ordered_up[frame,action]
                path[frame+1]=q
                discrepancies[frame+1]=next_discrepancy
                frame+=1
                generated+=1
                visits[frame]+=1
                if frame<layers:
                    sizes[frame]=-1
                descended=True
                break
            if descended:
                continue
            if discrepancy_limit>=0:
                # This iteration delayed alternatives. It has NOT proved the
                # original state dead, so never publish its failure to memo.
                sizes[frame]=-1
                frame-=1
                continue
            # All successors of this exact (time, Markov state) are false.
            if dead_count==cap:
                cap=min(max_nodes,cap*2)
                dead_states=grow2(dead_states,cap)
                dead_frame=grow1(dead_frame,cap)
                while slot_size<cap*2:
                    slot_size*=2
                slots=np.full(slot_size,-1,np.int32)
                for row in range(dead_count):
                    identity=projected_hash(dead_states[row],next_jump_latch(env,dead_frame[row])) if project_input_latch else state_hash(dead_states[row])
                    rh=finalize_hash(identity^np.uint64(dead_frame[row])*np.uint64(0x9e3779b97f4a7c15))
                    rs=np.int64(rh&np.uint64(slot_size-1))
                    while slots[rs]>=0:
                        rs=(rs+1)&(slot_size-1)
                    slots[rs]=row
            identity=projected_hash(path[frame],next_jump_latch(env,frame)) if project_input_latch else state_hash(path[frame])
            h=finalize_hash(identity^np.uint64(frame)*np.uint64(0x9e3779b97f4a7c15))
            slot=np.int64(h&np.uint64(slot_size-1))
            while slots[slot]>=0:
                slot=(slot+1)&(slot_size-1)
            slots[slot]=dead_count
            dead_states[dead_count]=path[frame]
            dead_frame[dead_count]=frame
            dead_count+=1
            sizes[frame]=-1
            frame-=1
        return (1 if discrepancy_limit<0 else 2),furthest,expanded,visits,empty
    return kernel


demand_search = create_demand_kernel(step_into, direct_collision)
