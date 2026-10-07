"""Experimental collision-observation quotient; dynamics remain unmerged.

For fixed tick, geometry, margin zero and slam_damage zero, collision_query
observes only the exact position bits and the moving boolean. Cache entries
are shared solely inside one complete edge-expansion call.
"""
import numpy as np
from numba import njit
from .cspace import collision_query

def advance_cached_dense(wave,front,controls,start,hold,cspace,*,max_product_cells=200_000_000,max_cache_bytes=128_000_000):
    """Checked optional accelerator; unsupported domains and budgets stay explicit."""
    from .red_dense_frontier import prepare,advance_dense,DenseFrontier,_compact
    if max_product_cells<1 or max_cache_bytes<1:raise ValueError('budget')
    prepared,reason=prepare(wave,front,controls,start,hold)
    if prepared is None:return 'unsupported',None,{'reason':reason}
    if front.count==0:return 'complete',front,{'joint_states':0}
    canonical,traces,endpoints,maps=prepared;nx,ny=map(len,endpoints)
    if nx*ny>max_product_cells:return 'resource_limit',None,{'product_cells':nx*ny}
    observation,bytes_needed=observation_maps(*traces,max_bytes=max_cache_bytes)
    if observation is None:
        status,out,stats=advance_dense(wave,front,controls,start,hold,cspace,max_product_cells=max_product_cells)
        stats['cache_budget_fallback']=True;return status,out,stats
    bits,ux,uy,count,edges,checks,queries,cached=advance_cached(front.bits,len(front.x),len(front.y),front.template,canonical,*traces,*maps,nx,ny,*observation,start,hold,wave.env_schedule,wave.geometry_white,wave.geometry_blue,cspace.payload)
    stats=dict(joint_states=int(count),product_cells=nx*ny,edges=edges,collision_edges=checks,collision_queries=queries,collision_cache_hits=cached,collision_cache_bytes=bytes_needed)
    if not (ux.all() and uy.all()):
        bits=_compact(bits,ny,np.cumsum(ux)-1,np.cumsum(uy)-1,int(ux.sum()),int(uy.sum()))
        endpoints=[endpoints[0][ux],endpoints[1][uy]]
    template=front.template.copy();e=wave.env_schedule[start+hold]
    template[6]=e[4];template[7]=e[5];template[8]=e[8];template[9]=e[12];template[10]=0.
    out=DenseFrontier(*endpoints,bits,template,int(count));stats['resident_bytes']=out.resident_bytes
    return 'complete',out,stats

def observation_maps(tx,ty,max_bytes=128_000_000):
    mappings=[];sizes=[]
    for trace in (tx,ty):
        mapping=np.empty(trace.shape[:3],dtype=np.int32);counts=[]
        for micro in range(trace.shape[2]):
            values=np.ascontiguousarray(trace[:,:,micro,0])
            unique,ids=np.unique(values.view(np.uint64),return_inverse=True)
            mapping[:,:,micro]=ids.reshape(values.shape);counts.append(len(unique))
        mappings.append(mapping);sizes.append(counts)
    offsets=[0]
    for nx,ny in zip(*sizes):offsets.append(offsets[-1]+2*nx*ny)
    bytes_needed=2*((offsets[-1]+63)//64)*8
    if bytes_needed>max_bytes:return None,bytes_needed
    return (*mappings,np.asarray(sizes[1],np.int64),np.asarray(offsets,np.int64)),bytes_needed

@njit(cache=True)
def advance_cached(bits,old_nx,old_ny,template,controls,tx,ty,xmap,ymap,nx,ny,
                   posx,posy,posny,offsets,start,hold,env,white,blue,payload):
    out=np.zeros((nx*ny+63)//64,np.uint64);usedx=np.zeros(nx,np.bool_);usedy=np.zeros(ny,np.bool_)
    known=np.zeros((offsets[-1]+63)//64,np.uint64);hit=np.zeros_like(known)
    count=0;edges=0;checks=0;queries=0;cached=0
    for word in range(len(bits)):
        if bits[word]==0:continue
        for b in range(64):
            oldkey=word*64+b
            if oldkey>=old_nx*old_ny:break
            if not bits[word]&(np.uint64(1)<<np.uint64(b)):continue
            ix=oldkey//old_ny;iy=oldkey%old_ny;s=template.copy()
            for a in range(len(controls)):
                edges+=1;x=xmap[a,ix];y=ymap[a,iy];key=x*ny+y;w=key//64;bit=np.uint64(1)<<np.uint64(key%64)
                if out[w]&bit:continue
                checks+=1;safe=True
                for micro in range(hold):
                    tick=start+micro+1;s[0],s[2]=tx[a,ix,micro,0],tx[a,ix,micro,1]
                    s[1],s[3]=ty[a,iy,micro,0],ty[a,iy,micro,1];s[4]=controls[a]
                    s[6]=env[tick,4];s[7]=env[tick,5];s[8]=env[tick,8];s[9]=env[tick,12];s[10]=0.
                    moving=int(s[2]!=0. or s[3]!=0.)
                    observation=offsets[micro]+2*(int(posx[a,ix,micro])*posny[micro]+int(posy[a,iy,micro]))+moving
                    ow=observation//64;ob=np.uint64(1)<<np.uint64(observation%64)
                    if known[ow]&ob:
                        cached+=1;collision=bool(hit[ow]&ob)
                    else:
                        queries+=1;collision=collision_query(white,blue,tick,s,0.,payload)
                        known[ow]|=ob
                        if collision:hit[ow]|=ob
                    if collision:safe=False;break
                if safe:out[w]|=bit;usedx[x]=True;usedy[y]=True;count+=1
    return out,usedx,usedy,count,edges,checks,queries,cached
