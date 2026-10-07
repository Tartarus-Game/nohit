// Opt-in observer of the actual engine. Does not write HP, positions, or input.
(() => {
    const params=new URLSearchParams(location.search);
    if (!params.has('acceptance')||params.has('oracle')) return;
    const continuous = new URLSearchParams(location.search).has('continuous');
    const A = window.__LIVE_ACC = { rows: [], hits: [], runs: [], started: false, done: false, error: null };
    const install = setInterval(() => {
        const rt = window.c2runtime || document.getElementById('c2canvas')?.c2runtime;
        if (!rt || !window.TASRunner) return;
        clearInterval(install);
        const proto = rt.constructor.prototype, inner = proto.tick;
        const trigger = proto.trigger;
        proto.trigger = function (method, inst, value) {
            if (continuous && A.done && method === cr.plugins_.Function.prototype.cnds.OnFunction &&
                String(value).toLowerCase() === 'tlplay') {
                A.rows = []; A.hits = []; A.started = false; A.done = false;
                A.endAttackObserved = false; A.end = null;
            }
            if (method === cr.plugins_.Function.prototype.cnds.OnFunction &&
                String(value).toLowerCase() === 'endattack' && A.started && !A.done) {
                A.endAttackObserved = true;
            }
            return trigger.apply(this, arguments);
        };
        proto.tick = function () {
            if (window.__TAS_CLOCK?.enabled && !window.__TAS_CLOCK.stepping) return;
            const result = inner.apply(this, arguments);
            try {
                const g = Object.fromEntries(rt.all_global_vars.map(v => [v.name, v.data]));
                const s = window.TASRunner.getState();
                const T = rt.varsBySid[3521916820909801]?.data;
                const running = rt.varsBySid[164016619418963]?.data;
                if (!A.started && s.actionCount > 0 && g.HP > 0 && T >= 0 && T < 0.05 && running) {
                        A.started = true; A.hpMax = g.MaxHP; A.wave = s.currentWave;
                }
                if (A.started && !A.done) {
                    const types = rt.types_by_index;
                    const heart = types.find(t => t?.sid === 5960708907117077)?.instances[0];
                    const hb = types.find(t => t?.sid === 728293317807613)?.instances[0];
                    const row = { tick: rt.tickcount, T, HP: g.HP, KR: g.KR, running,
                        planned: s.plannedFrame, clock: s.clockFrame, playing: s.isPlaying,
                        x: heart?.x, y: heart?.y, dt: rt.dt,
                        up: !!window.TASRunner.getKeyboardInstance()?.keyMap?.[38],
                        left: !!window.TASRunner.getKeyboardInstance()?.keyMap?.[37],
                        right: !!window.TASRunner.getKeyboardInstance()?.keyMap?.[39],
                        down: !!window.TASRunner.getKeyboardInstance()?.keyMap?.[40],
                        mode: heart?.instance_vars?.[0], angle:heart?.angle,
                        dx: heart?.behavior_insts?.find(b => b.type.name === 'CustomMovement')?.dx,
                        dy: heart?.behavior_insts?.find(b => b.type.name === 'CustomMovement')?.dy };
                    if (A.rows.length && (g.HP < A.rows[A.rows.length - 1].HP||g.KR>A.rows[A.rows.length - 1].KR)) {
                        row.hp_decreased=g.HP<A.rows[A.rows.length-1].HP;
                        row.kr_increased=g.KR>A.rows[A.rows.length-1].KR;
                        row.bones = types.filter(t => ['t30', 't31'].includes(t?.name))
                            .flatMap(t => t.instances.map(b => ({ type: t.name, x: b.x, y: b.y,
                                w: b.width, h: b.height, overlap: hb ? rt.testOverlap(hb, b) : null })));
                        row.hazards=[];
                        for(const familySid of [9590353435551898,6631597198329078,9784977049754561]){
                            const family=types.find(t=>t.sid===familySid);if(!family)continue;
                            for(const member of family.members)for(const b of member.instances){
                                const offset=member.family_var_map[family.family_index];
                                if(!b.instance_vars[offset])continue;
                                row.hazards.push({uid:b.uid,type_sid:member.sid,x:b.x,y:b.y,w:b.width,h:b.height,angle:b.angle,
                                    damage:b.instance_vars[offset],color:familySid===9590353435551898?b.instance_vars[offset+2]:0,
                                    overlap:hb?rt.testOverlap(hb,b):null});
                            }
                        }
                        A.hits.push(row);
                    }
                    A.rows.push(row);
                    // Timeline T resets at every CSV command and Running=0 can
                    // mean a dialogue/script pause. Neither proves round end.
                    // Only the original EndAttack trigger completes acceptance.
                    if (g.HP <= 0 || A.endAttackObserved) {
                        A.done = true;
                        if (!continuous || g.HP <= 0) { proto.tick = inner; proto.trigger = trigger; }
                        A.end = { HP: g.HP, T, running, endAttackObserved: !!A.endAttackObserved };
                        A.runs.push({ wave: A.wave, rows: A.rows, hits: A.hits, startHP: A.rows[0].HP, end: A.end });
                        if (continuous && (A.runs.length >= 3||g.HP <= 0)) {
                            cr_setSuspended(true);
                            const passed=A.runs.length===3&&A.runs.every(r=>r.startHP===92&&r.end.HP===92&&r.end.endAttackObserved&&r.hits.length===0&&r.rows.length>0&&r.rows.every(row=>row.HP===92&&row.KR===0));
                            A.result={passed,complete_rounds:A.runs.filter(r=>r.end.endAttackObserved).length};
                            const badge=document.getElementById('tas-status-badge');
                            const mode=window.__TAS_CLOCK?.enabled?'卡顿补偿':'实时';
                            if(badge){badge.className='tas-badge '+(passed?'completed':'deadlock');badge.textContent=mode+(passed?'三回合无伤已通过':'无伤验收未通过');}
                            const seed=window.__TAS_SEED?.seed;
                            // Wait until the current driver step is accounted for.
                            A.recordPromise=Promise.resolve().then(()=>fetch('/api/acceptance',{method:'POST',headers:{'Content-Type':'application/json'},
                                body:JSON.stringify({wave:A.wave,seed,candidate_id:params.get('candidate'),
                                    clock:window.__TAS_CLOCK?.enabled?'original-runtime-realtime-catchup-240hz':'original-runtime-realtime',
                                    compensation:window.__TAS_CLOCK?{...window.__TAS_CLOCK.stats,debtMs:window.__TAS_CLOCK.clock.debtMs,error:window.__TAS_CLOCK.error}:null,
                                    criterion:'three-original-EndAttack-no-damage',result:A.result,plan:window.TASRunner.getPlan(),trace:{runs:A.runs}})}))
                                .then(async response=>{const data=await response.json();if(!response.ok)throw Error(data.error||'Recording failed');A.saved=data;return data;})
                                .catch(e=>{A.recordError=String(e);});
                        }
                    }
                }
            } catch (e) { A.error = String(e.stack || e); }
            return result;
        };
    }, 1);
})();
