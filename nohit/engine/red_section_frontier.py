"""Exact red relation expansion using batched C-space sections.

Only the collision observation is factored. Dynamics, correlated occupancy,
microtick safety, endpoint identities and predecessor reconstruction are unchanged.
"""
import numpy as np
from numba import njit
from .cspace_slice import section_collision_bits
from .red_dense_frontier import prepare, advance_dense, DenseFrontier, _compact


def section_domain(wave,cspace,start,hold,traces):
    """Exclude invalid grid geometry and floating-point overflow from the proof."""
    ox,oy=cspace.origin;size=cspace.cell_size
    if not np.isfinite([ox,oy,size]).all() or size<=0:return False
    # Grid baking casts expanded coordinates to signed int64. Prove those
    # conversions stay in range as well as the SAT floating-point operations.
    limit=1.e9
    if max((limit+2.+abs(ox))/size,(limit+2.+abs(oy))/size)>=2.**62:return False
    for trace in traces:
        if not np.isfinite(trace).all() or np.any(np.abs(trace)>limit):return False
    for table in (wave.geometry_white,wave.geometry_blue):
        boxes=table[start+1:start+hold+1].reshape(-1,4)
        # Padded rows are all NaN. Other nonfinite shapes need the old query.
        boxes=boxes[~np.isnan(boxes).all(axis=1)]
        if not np.isfinite(boxes).all() or np.any(np.abs(boxes)>limit):return False
        if np.any(boxes[:,2]<boxes[:,0]) or np.any(boxes[:,3]<boxes[:,1]):return False
    polys=cspace.polygons[start+1:start+hold+1].reshape(-1,8)
    polys=polys[np.isfinite(polys[:,0])]
    return bool(np.isfinite(polys).all() and np.all(np.abs(polys)<=limit))


def bake_observations(tx,ty,white,blue,polygons,start,max_bytes):
    mappings=[];values=[]
    for trace in (tx,ty):
        ids=np.empty(trace.shape[:3],np.int32);axis=[]
        for micro in range(trace.shape[2]):
            raw=np.ascontiguousarray(trace[:,:,micro,0])
            # Preserve bit-distinct positions; sorting changes observation IDs only.
            unique,inverse=np.unique(raw.view(np.uint64),return_inverse=True)
            order=np.argsort(unique.view(np.float64),kind='stable')
            reverse=np.empty(len(order),np.int32);reverse[order]=np.arange(len(order))
            ids[:,:,micro]=reverse[inverse].reshape(raw.shape)
            axis.append(unique[order].view(np.float64))
        mappings.append(ids);values.append(axis)
    sizes=np.array([len(v) for v in values[1]],np.int64)
    words=[(len(x)*len(y)+63)//64 for x,y in zip(*values)]
    offsets=np.r_[0,np.cumsum(words)].astype(np.int64)
    required=int(offsets[-1])*16
    if required>max_bytes:return None,required
    hit=np.zeros((2,int(offsets[-1])),np.uint64)
    for micro,(xs,ys) in enumerate(zip(*values)):
        tick=start+micro+1
        hit[:,offsets[micro]:offsets[micro+1]]=section_collision_bits(xs,ys,white[tick],blue[tick],polygons[tick])
    return (*mappings,sizes,offsets,hit),required


@njit(cache=True)
def _advance(bits,old_nx,old_ny,controls,tx,ty,xmap,ymap,nx,ny,posx,posy,posny,offsets,hit,hold):
    out=np.zeros((nx*ny+63)//64,np.uint64)
    usedx=np.zeros(nx,np.bool_);usedy=np.zeros(ny,np.bool_)
    count=0;edges=0;checks=0
    for word in range(len(bits)):
        if bits[word]==0:continue
        for b in range(64):
            oldkey=word*64+b
            if oldkey>=old_nx*old_ny:break
            if not bits[word]&(np.uint64(1)<<np.uint64(b)):continue
            ix=oldkey//old_ny;iy=oldkey%old_ny
            for a in range(len(controls)):
                edges+=1;x=xmap[a,ix];y=ymap[a,iy];key=x*ny+y
                w=key//64;bit=np.uint64(1)<<np.uint64(key%64)
                if out[w]&bit:continue
                checks+=1;safe=True
                for micro in range(hold):
                    observation=int(posx[a,ix,micro])*posny[micro]+int(posy[a,iy,micro])
                    ow=offsets[micro]+observation//64;ob=np.uint64(1)<<np.uint64(observation%64)
                    moving=tx[a,ix,micro,1]!=0. or ty[a,iy,micro,1]!=0.
                    if (hit[0,ow]&ob) or (moving and (hit[1,ow]&ob)):
                        safe=False;break
                if safe:out[w]|=bit;usedx[x]=True;usedy[y]=True;count+=1
    return out,usedx,usedy,count,edges,checks


def advance_section_dense(wave,front,controls,start,hold,cspace,*,max_product_cells=200_000_000,max_cache_bytes=128_000_000):
    if max_product_cells<1 or max_cache_bytes<1:raise ValueError('budget')
    prepared,reason=prepare(wave,front,controls,start,hold)
    if prepared is None:return 'unsupported',None,{'reason':reason}
    if front.count==0:return 'complete',front,{'joint_states':0}
    canonical,traces,endpoints,maps=prepared;nx,ny=map(len,endpoints)
    if nx*ny>max_product_cells:return 'resource_limit',None,{'product_cells':nx*ny}
    if not section_domain(wave,cspace,start,hold,traces):
        status,out,stats=advance_dense(wave,front,controls,start,hold,cspace,max_product_cells=max_product_cells)
        stats['section_domain_fallback']=True;return status,out,stats
    observation,required=bake_observations(*traces,wave.geometry_white,wave.geometry_blue,cspace.polygons,start,max_cache_bytes)
    if observation is None:
        status,out,stats=advance_dense(wave,front,controls,start,hold,cspace,max_product_cells=max_product_cells)
        stats['section_budget_fallback']=True;return status,out,stats
    bits,ux,uy,count,edges,checks=_advance(front.bits,len(front.x),len(front.y),canonical,*traces,*maps,nx,ny,*observation,hold)
    if not (ux.all() and uy.all()):
        bits=_compact(bits,ny,np.cumsum(ux)-1,np.cumsum(uy)-1,int(ux.sum()),int(uy.sum()))
        endpoints=[endpoints[0][ux],endpoints[1][uy]]
    template=front.template.copy();e=wave.env_schedule[start+hold]
    template[6]=e[4];template[7]=e[5];template[8]=e[8];template[9]=e[12];template[10]=0.
    out=DenseFrontier(*endpoints,bits,template,int(count))
    return 'complete',out,dict(joint_states=int(count),product_cells=nx*ny,edges=edges,
        collision_edges=checks,section_bytes=required,resident_bytes=out.resident_bytes)
