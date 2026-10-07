(() => {
const rt = window.c2runtime || document.getElementById('c2canvas').c2runtime;
return {state:window.TASRunner?.getState(),globals:rt.all_global_vars.map(v=>[v.name,v.data]),T:rt.varsBySid[3521916820909801]?.data,acc:window.__ACC && {started:window.__ACC.started,n:window.__ACC.rows.length,err:window.__ACC.err},types:rt.types_by_index.filter(t=>['t55','t65','t31'].includes(t.name)).map(t=>({name:t.name,n:t.instances.length,instances:t.instances.slice(0,2).map(i=>({x:i.x,y:i.y,w:i.width,h:i.height,vars:i.instance_vars,beh:i.behavior_insts?.map(b=>({name:b.type.name,dx:b.dx,dy:b.dy}))}))}))};
})()
