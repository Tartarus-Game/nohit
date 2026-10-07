"""Experimental target-oriented exact relational composition.

Does not replace the resident production experiment. It consumes exact axis
maps prepared by its caller; all accepted exits retain actual safe witnesses.
"""
import numpy as np
from numba import njit
from .cspace import collision_query


def inverse_maps(mapping, size):
    """CSR inverse of each exact finite axis function, including all aliases."""
    offsets=[];parents=[]
    for row in mapping:
        order=np.argsort(row,kind='stable')
        count=np.bincount(row,minlength=size)
        offsets.append(np.r_[0,np.cumsum(count)])
        parents.append(order)
    return np.asarray(offsets,dtype=np.int64),np.asarray(parents,dtype=np.int64)


@njit(cache=True)
def pull_kernel(joint,old_nx,old_ny,template,controls,tx,ty,
                xoffset,xparent,yoffset,yparent,new_nx,new_ny,
                start,hold,env,white,blue,payload,max_states):
    # This is exact joint membership with a witness index, not marginal reachability.
    lookup=np.full(old_nx*old_ny,-1,np.int32)
    for i in range(len(joint)):lookup[joint[i]]=i
    visited=np.zeros((new_nx*new_ny+63)//64,np.uint64)
    keys=np.empty(max_states,np.uint64);parents=np.empty(max_states,np.int64);masks=np.empty(max_states,np.uint8)
    n=0;candidate_edges=0;collision_edges=0
    for a in range(len(controls)):
        mask=controls[a]
        for x in range(new_nx):
            if xoffset[a,x]==xoffset[a,x+1]:continue
            for y in range(new_ny):
                if yoffset[a,y]==yoffset[a,y+1]:continue
                key=x*new_ny+y;word=key//64;bit=np.uint64(1)<<np.uint64(key%64)
                if visited[word]&bit:continue
                found=False
                for px in range(xoffset[a,x],xoffset[a,x+1]):
                    ix=xparent[a,px]
                    for py in range(yoffset[a,y],yoffset[a,y+1]):
                        iy=yparent[a,py];candidate_edges+=1
                        parent=lookup[ix*old_ny+iy]
                        if parent<0:continue
                        collision_edges+=1;s=template.copy();safe=True
                        for micro in range(hold):
                            tick=start+micro+1
                            s[0],s[2]=tx[a,ix,micro,0],tx[a,ix,micro,1]
                            s[1],s[3]=ty[a,iy,micro,0],ty[a,iy,micro,1]
                            s[4]=mask;s[6]=env[tick,4];s[7]=env[tick,5]
                            s[8]=env[tick,8];s[9]=env[tick,12];s[10]=0.
                            if collision_query(white,blue,tick,s,0.,payload):safe=False;break
                        if not safe:continue
                        if n==max_states:return False,keys[:n],parents[:n],masks[:n],candidate_edges,collision_edges
                        visited[word]|=bit;keys[n]=key;parents[n]=parent;masks[n]=mask;n+=1;found=True;break
                    if found:break
    return True,keys[:n],parents[:n],masks[:n],candidate_edges,collision_edges
