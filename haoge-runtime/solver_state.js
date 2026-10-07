// Read the full discrete operator boundary directly from the original runtime.
// This module never changes game variables or physical state.
(() => {
    window.NoHitSolverState = {
        captureArena(rt) {
            const zone=rt.types_by_index.find(t=>t.sid===141231765387603)?.instances[0];
            const target=zone?.instance_vars?.slice(0,4),size=[zone?.width,zone?.height];
            const speed=rt.varsBySid[3111584688851152]?.data,callback=rt.varsBySid[1052618449272991]?.data;
            if(!target||target.length!==4||![...target,...size,speed].every(Number.isFinite)||typeof callback!=='string')
                throw Error('Original arena continuation is incomplete');
            return {target,size,speed,callback};
        },
        capture(rt) {
            const instance = sid => rt.types_by_index.find(t => t.sid === sid)?.instances[0];
            const h = instance(5960708907117077), zone = instance(141231765387603);
            if (!h || !zone) throw Error('Original heart/arena is not ready');
            const movement = h.behavior_insts.find(b => b.type.name === 'CustomMovement');
            if (!movement) throw Error('Original CustomMovement is not ready');
            const keys = window.TASRunner.getKeyboardInstance().keyMap;
            const mask = (keys[37]?1:0)|(keys[39]?2:0)|(keys[38]?4:0)|(keys[40]?8:0)|(keys[88]||keys[16]?16:0);
            const direction = ((Math.round(h.angle / (Math.PI / 2)) % 4) + 4) % 4;
            const maxFall = rt.varsBySid[963626393445968].data;
            const mode = h.instance_vars[0], slammed = h.instance_vars[1], slamDamage = h.instance_vars[2];
            zone.update_bbox();
            const b = zone.bbox, bounds = [b.left,b.top,b.right,b.bottom];
            const globals = Object.fromEntries(rt.all_global_vars.map(v => [v.name,v.data]));
            return {
                initial: [h.x,h.y,movement.dx,movement.dy,mask,slammed,mode,direction,maxFall,slamDamage,0],
                initial_environment: [...bounds,mode,direction,0,rt.dt,maxFall,0,0,0,slamDamage,0,...bounds,...bounds],
                clock_start_ms: rt.last_tick_time,
                tick: rt.tickcount, time: rt.kahanTime.sum,
                timeline: rt.varsBySid[3521916820909801].data,
                running: rt.varsBySid[164016619418963].data,
                HP: globals.HP, KR: globals.KR,
            };
        },
        // The physical operator's previous-input latch is the committed VPad,
        // not the keyboard map that will be sampled on the following tick.
        // Keep capture() unchanged for existing campaign/oracle callers.
        capturePhysical(rt) {
            const result = window.NoHitSolverState.capture(rt);
            result.arena = window.NoHitSolverState.captureArena(rt);
            const types = rt.types_by_index;
            const pad = types.find(t => t.sid === 9768267065126338)?.instances[0]?.instance_vars;
            if (!pad || pad.length < 14 || !pad.slice(0,14).every(Number.isFinite))
                throw Error('Original committed VPad is not ready');
            const keys = window.TASRunner.getKeyboardInstance().keyMap;
            result.physical_keymask = result.initial[4];
            result.physical_confirm = !!(keys[90] || keys[13]);
            result.initial[4] = (pad[2]?1:0)|(pad[3]?2:0)|(pad[0]?4:0)|(pad[1]?8:0)|(pad[5]?16:0);
            result.initial_confirm = !!pad[4];
            result.previous_confirm = !!pad[11];
            result.vpad = pad.slice();
            result.line = rt.varsBySid[2569112556112449]?.data;
            result.dt = rt.dt;
            if (!Number.isInteger(result.line) || !Number.isFinite(result.timeline) || !Number.isFinite(result.dt))
                throw Error('Original Timeline observation is incomplete');
            const globals = Object.fromEntries(rt.all_global_vars.map(v => [v.name,v.data]));
            result.SimulatorMode = globals.SimulatorMode;
            result.SingleAttack = globals.SingleAttack;
            const family = types.find(t => t.sid === 8627438680975019);
            result.rpgtext = (family?.members || []).flatMap(type => {
                const offset = type.family_var_map?.[family.family_index];
                return (type.instances || []).map(instance => ({uid:instance.uid,typeSid:type.sid,
                    familyOffset:offset,vars:instance.instance_vars.slice(),
                    fields:Number.isInteger(offset)?instance.instance_vars.slice(offset,offset+8):null}));
            });
            return result;
        }
    };
})();
