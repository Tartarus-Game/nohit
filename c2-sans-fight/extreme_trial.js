// Baseline observation only: no movement, HP, geometry, or clock writes.
(() => {
  const rt = document.getElementById('c2canvas').c2runtime;
  const proto = rt.constructor.prototype;
  const tick = proto.tick, trigger = proto.trigger;
  const A = window.__EXTREME_TRIAL = {rows: [], hits: [], started: false, done: false,
    wave: 'sans_realhell_extreme', control_policy: 'no-input-baseline',
    csv_sha256: '3b6252bc2d97a6ae5f82d63b8c8e82175cf1d819e85728e2f1fe9b1001106299',
    endAttackObserved: false};
  proto.trigger = function(method, inst, value) {
    if (method === cr.plugins_.Function.prototype.cnds.OnFunction) {
      const name = String(value).toLowerCase();
      const selected = rt.all_global_vars.find(v => v.name === 'SingleAttack')?.data;
      if (name === 'tlplay' && selected === A.wave && !A.started) { A.started = true; A.start = performance.now(); }
      if (name === 'endattack' && A.started) A.endAttackObserved = true;
    }
    return trigger.apply(this, arguments);
  };
  proto.tick = function() {
    const out = tick.apply(this, arguments);
    if (!A.started || A.done) return out;
    const g = Object.fromEntries(rt.all_global_vars.map(v => [v.name, v.data]));
    const h = rt.types_by_index[55].instances[0];
    const row = {tick: rt.tickcount, elapsed_ms: performance.now()-A.start,
      dt: rt.dt, HP: g.HP, KR: g.KR, attack: g.SingleAttack,
      T: rt.varsBySid[3521916820909801]?.data,
      x: h?.x, y: h?.y, mode: h?.instance_vars?.[0], angle: h?.angle};
    if (!A.rows.length) A.startHP = g.HP;
    const prev = A.rows[A.rows.length-1];
    if (prev && (row.HP < prev.HP || row.KR > prev.KR)) A.hits.push(row);
    A.rows.push(row);
    if (A.hits.length || A.endAttackObserved || row.elapsed_ms > 15000) {
      A.done = true; A.stop = A.hits.length ? 'first-damage' : A.endAttackObserved ? 'EndAttack' : 'observation-timeout';
      proto.tick = tick; proto.trigger = trigger;
      cr_setSuspended(true);
      A.recordPromise = fetch('/api/acceptance', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({kind:'realhell-no-input-baseline',wave:A.wave,csv_sha256:A.csv_sha256,
          clock:'original-runtime-realtime',control_policy:A.control_policy,
          result:{passed:false,stop:A.stop,endAttackObserved:A.endAttackObserved},
          trace:{rows:A.rows,hits:A.hits}})}).then(r=>r.json()).then(r=>(A.saved=r));
    }
    return out;
  };
  // Hide unrelated default route UI during the custom script baseline.
  const overlay = document.getElementById('tas-controller-overlay');
  if (overlay) overlay.style.display = 'none';
})();
