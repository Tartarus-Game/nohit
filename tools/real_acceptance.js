#!/usr/bin/env node
/**
 * Real-machine acceptance test for the nohit TAS.
 *
 * Single judgement criterion: the heart's HP must never drop during the round.
 *
 * Sequence:
 *   1. wait until TASRunner has fetched a plan (the server solves on demand;
 *      a full-round plan at 60 Hz takes seconds, so this is not instant)
 *   2. bootstrap the round: HP = MaxHP, KR = 0, then call StartAttack()
 *   3. hook Runtime.prototype.tick and record HP / position / inputs / plan
 *      frame for long enough to cover the whole attack plus margin
 *   4. report drops, drift and coverage
 *
 * Run with:  <ego_script>{... require this file ...}</ego_script>
 * The body below is plain page-context JS, so it is pasted into ego_script
 * rather than required.
 */

// ---- tunables -------------------------------------------------------------
const PLAN_WAIT_S = 60;      // how long to wait for the server solve
const MIN_PLAN_FRAMES = 50;  // a real plan is at least this long
const TICKS_PER_PLAN_FRAME = 4;  // 240 fps engine / 60 Hz plan
const EXTRA_TICKS = 400;     // record past the end of the plan

const result = {
  planFrames: 0,
  hpStart: null, hpMin: null, hpEnd: null,
  drops: [],
  lastPlanFrame: 0,
  inputTicks: 0,
  xRange: null, yRange: null,
  ticksRecorded: 0,
  errors: [],
};

// ---- 1. wait for the plan -------------------------------------------------
for (let i = 0; i < PLAN_WAIT_S; i++) {
  try {
    const s = await page.evaluate(() => {
      const T = window.TASRunner && window.TASRunner.getState();
      return T ? { n: T.actionCount } : { n: 0 };
    });
    result.planFrames = s.n;
    if (s.n >= MIN_PLAN_FRAMES) break;
  } catch (e) {
    result.errors.push('plan wait: ' + String(e).slice(0, 120));
  }
  await new Promise(r => setTimeout(r, 1000));
}

if (result.planFrames < MIN_PLAN_FRAMES) {
  console.log('NO_PLAN ' + JSON.stringify(result));
} else {
  // ---- 2. bootstrap the round --------------------------------------------
  const prep = await page.evaluate(() => {
    const cv = document.getElementById('c2canvas');
    const rt = window.c2runtime || (cv && cv.c2runtime);
    window.__rt = rt;
    const gv = () => { const o = {}; (rt.all_global_vars || []).forEach(v => { o[v.name] = v.data; }); return o; };
    const setG = (n, v) => { const x = (rt.all_global_vars || []).find(y => y.name === n); if (x) x.data = v; };
    setG('HP', gv().MaxHP); setG('KR', 0);
    try { window.c2_callFunction('StartAttack', []); } catch (e) {}
    const T = window.TASRunner.getState();
    return { HP: gv().HP, MaxHP: gv().MaxHP, actions: T.actionCount, fps: rt.fps };
  });
  result.hpStart = prep.HP;
  result.fps = prep.fps;
  result.planFrames = prep.actions;

  // ---- 3. record ----------------------------------------------------------
  const ticks = Math.min(6000, result.planFrames * TICKS_PER_PLAN_FRAME + EXTRA_TICKS);
  const trace = await page.evaluate((n) => {
    const rt = window.__rt;
    const gv = () => { const o = {}; (rt.all_global_vars || []).forEach(v => { o[v.name] = v.data; }); return o; };
    const inst = (rt.types_by_index || []).find(t => t && t.name === 't55').instances[0];
    const kb = (rt.types_by_index || []).map(t => t && t.instances && t.instances[0]).find(i => i && i.keyMap);
    const proto = rt.constructor.prototype, orig = proto.tick;
    const rows = []; let i = 0;
    return new Promise(resolve => {
      proto.tick = function () {
        const r = orig.apply(this, arguments);
        i++;
        const S = window.TASRunner.getState();
        rows.push({
          i, hp: gv().HP,
          x: +inst.x.toFixed(2), y: +inst.y.toFixed(2),
          L: kb && kb.keyMap[37] ? 1 : 0,
          R: kb && kb.keyMap[39] ? 1 : 0,
          U: kb && kb.keyMap[38] ? 1 : 0,
          f: S.plannedFrame,
        });
        if (i >= n) { proto.tick = orig; resolve(rows); }
        return r;
      };
    });
  }, ticks);

  // ---- 4. summarise -------------------------------------------------------
  result.ticksRecorded = trace.length;
  result.hpMin = Math.min(...trace.map(r => r.hp));
  result.hpEnd = trace[trace.length - 1].hp;
  for (let k = 1; k < trace.length; k++) {
    if (trace[k].hp !== trace[k - 1].hp) {
      result.drops.push({ tick: trace[k].i, planFrame: trace[k].f, from: trace[k - 1].hp, to: trace[k].hp });
    }
  }
  result.lastPlanFrame = Math.max(...trace.map(r => r.f));
  result.inputTicks = trace.filter(r => r.L || r.R || r.U).length;
  result.xRange = [Math.min(...trace.map(r => r.x)), Math.max(...trace.map(r => r.x))];
  result.yRange = [Math.min(...trace.map(r => r.y)), Math.max(...trace.map(r => r.y))];
  result.firstDrop = result.drops[0] || null;
  result.dropCount = result.drops.length;
  result.PASS = result.drops.length === 0;
  // keep the payload small
  result.drops = result.drops.slice(0, 12);

  console.log('E2E ' + JSON.stringify(result));
}
