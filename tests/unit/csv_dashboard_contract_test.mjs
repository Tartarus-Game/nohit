import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const html = fs.readFileSync(new URL('../../nohit/dashboard/static/index.html', import.meta.url),'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function page(search='') {
  const elements = new Map(), keys=[],draws=[],requests=[],timers=new Map(),opened=[],navigations=[];
  let fetchResult,submitted,responder,timerId=0,now=1000;const events={};
  const popup={closed:false,location:{replace(url){popup.url=url;}},close(){this.closed=true;}};
  const context2d = new Proxy({}, {get:(target,key)=>target[key] || ((...args)=>draws.push({method:key,args})),set:(target,key,value)=>(target[key]=value,true)});
  function element(id) {
    if(!elements.has(id)) elements.set(id,{id,value:'',textContent:'',hidden:false,disabled:false,dataset:{},events:{},attributes:{},
      addEventListener(type,callback){this.events[type]=callback;},
      setAttribute(key,value){this.attributes[key]=value;},classList:{toggle(){}},getContext(){return context2d;}});
    return elements.get(id);
  }
  for(const match of html.matchAll(/id="([^"]+)"/g)) element(match[1]);
  for(const match of html.matchAll(/<\w+\b([^>]*\bid="([^"]+)"[^>]*)>/g)) {
    const target=element(match[2]);target.hidden=/\bhidden\b/.test(match[1]);
    target.disabled=/\bdisabled\b/.test(match[1]);target.checked=/\bchecked\b/.test(match[1]);
  }
  for(const bit of [1,2,4,8,32]) {
    const key=element('key-'+bit);key.dataset.bit=String(bit);key.classList.toggle=(name,on)=>key.active=on;keys.push(key);
  }
  const globals={document:{getElementById:element,querySelectorAll:()=>keys},URLSearchParams,
    location:{search,origin:'http://localhost:8765',assign:url=>navigations.push(url)},
    addEventListener(type,handler){events[type]=handler;},
    open(url,target){opened.push({url,target});return popup;},
    requestAnimationFrame:()=>1,cancelAnimationFrame(){},performance:{now:()=>now},
    setInterval(callback){timers.set(++timerId,callback);return timerId;},clearInterval(id){timers.delete(id);},
    fetch:async(url,options)=>{const request={url,payload:options?.body?JSON.parse(options.body):null};
      requests.push(request);if(options?.body)submitted=request;
      if(responder)return responder(request);
      return {ok:true,json:async()=>fetchResult};}};
  globals.window=globals;
  const context=vm.createContext(globals);
  vm.runInContext(script,context,{filename:'csv.html'});
  Object.assign(element('initial-state'),{value:'[320,304,0,0,0,0,0,1,750,0,0]'});
  element('initial-environment').value='null';element('fps').value='30';element('seconds').value='30';
  element('width').value='3000';element('speed').value='1';
  return {element,keys,context,draws,requests,timers,opened,navigations,popup,evaluate:code=>vm.runInContext(code,context),
    respond(callback){responder=callback;},
    advance(milliseconds){now+=milliseconds;},
    message(data,{origin='http://localhost:8765',source=popup}={}){events.message({origin,source,data});},
    async tick(){for(const callback of [...timers.values()])await callback();},
    result(value){context.testResult=value;vm.runInContext('showResult(testResult)',context);},
    async launch(value){fetchResult=value;await element('native-button').events.click();return submitted;},
    async submit(value){fetchResult=value;await element('solve-form').events.submit({preventDefault(){}});return submitted;}};
}

function candidate() {
  const frames=[0,.04,.1].map((time,index)=>({tick:index,time_seconds:time,dt:index===2?.06:.04,
    player:[320+index,304,0,0,0,0,0,1,750,0,0],env:Array(22).fill(0),bounds:[133,251,508,391],white:[],blue:[],polygons:[],platforms:[]}));
  return {status:'candidate_found',verified:true,actions:[2,4],confirm_sequence:[false,true],trajectory:frames.map(f=>f.player),
    wall_seconds:2,game_seconds:.1,visualization:{schema_version:1,scope:'verified_source_model',frame_count:3,frames}};
}

function entryCandidate() {
  const result=candidate(),entry=result.visualization.frames[0];
  result.dt_sequence=[.04,.04,.06];
  result.visualization={schema_version:1,mode:'entry',scope:'verified_source_model_entry',
    frame_count:1,candidate_frame_count:3,frames:[entry]};
  return result;
}

test('failed solve locates CSV/tick/seconds and replays a separate incomplete route',()=>{
  const p=page(),route={actions:[2,0],confirm_sequence:[false,true],
    trajectory:[[320,304,0,0,0,0,0,1,750,0,0],[321,304,0,0,0,0,0,1,750,0,0],[322,304,0,0,0,0,0,1,750,0,0]],
    dt_sequence:[.04,.04,.06],prefix_verified:true,complete:false,reached_tick:2,input_cost:{churn:2}};
  const result={status:'unknown',verified:false,actions:[],confirm_sequence:[],reason:'native_search_limited',
    failure_diagnostics:{last_safe_tick:2,last_safe_seconds:.1,reason:'native_search_limited',
      failure:{tick:3,seconds:.14,kind:'retained_frontier_collision',csv:{line:12,column:2,row:['0','BoneV']}},routes:[route]}};
  p.result(result);
  assert.equal(p.element('failure-dialog').hidden,false);assert.match(p.element('failure-location').textContent,/tick 3.*0.140 秒/);
  assert.match(p.element('failure-location').textContent,/第 12 行/);assert.equal(p.element('prefix-routes').hidden,false);
  assert.equal(p.element('timeline').max,2);assert.equal(p.keys.find(k=>k.dataset.bit==='32').active,true);
  assert.equal(result.actions.length,0);assert.match(p.element('visualization-warning').textContent,/尚未完成/);
  p.element('failure-close').events.click();assert.equal(p.element('failure-dialog').hidden,true);
});

test('unverified failure route cannot enable playback',()=>{
  const p=page();p.result({status:'unknown',verified:false,actions:[],failure_diagnostics:{routes:[{prefix_verified:false,complete:false}]}});
  assert.equal(p.element('play').disabled,true);assert.equal(p.element('prefix-routes').hidden,true);
});

test('fewest-operation preference is sent to the solver request',async()=>{
  const p=page();p.element('csv-path').value='test.csv';p.element('objective').value='fewest_operations';
  const request=await p.submit({status:'unknown',verified:false});
  assert.equal(request.payload.objective,'fewest_operations');
});

test('human-friendly selection enables difficulty analysis and preserves the request mode',async()=>{
  const p=page();p.element('csv-path').value='test.csv';p.element('objective').value='human_friendly';
  p.element('objective').events.change();
  const request=await p.submit({status:'unknown',verified:false});
  assert.equal(request.payload.objective,'human_friendly');assert.equal(request.payload.analyze_difficulty,true);
});

test('difficulty reports per-side pixels, timing limits, CSV cursor and never claims human impossibility',()=>{
  const p=page(),result=candidate();result.difficulty={status:'analyzed',score:90,label:'极限',minimum_clearance_px:3,
    operations:{arrow_changes:2,confirm_presses:1},timing_coverage:{tested_events:1,total_events:2},
    human_feasibility:{estimate:'manual_play_extremely_demanding',flags:['帧级操作']},
    hard_points:[{tick:1,seconds:.04,clearance_px:3,csv:{line:12}}],
    timing_events:[{tick:1,seconds:.04,kind:'arrows',csv:{line:12},early_safe_ticks_tested:0,late_safe_ticks_tested:0,
      early_safe_ms_tested:0,late_safe_ms_tested:0,frame_exact_locally:true}]};
  p.result(result);
  assert.equal(p.element('difficulty-panel').hidden,false);
  assert.match(p.element('difficulty-summary').textContent,/最小单侧余量 3/);
  assert.match(p.element('difficulty-details').textContent,/CSV 执行游标第 12 行/);
  assert.match(p.element('difficulty-details').textContent,/±1 tick 均碰撞/);
  assert.match(p.element('difficulty-scope').textContent,/不证明其他路线/);
  p.element('difficulty-seek').value='1';p.element('difficulty-seek').events.change();
  assert.equal(Number(p.element('timeline').value),1);
});

test('Dashboard solving is a main entry and defaults to light preview without budget tuning',async()=>{
  const advanced=html.slice(html.indexOf('<details id="advanced-settings"'),html.indexOf('</form>'));
  assert.doesNotMatch(advanced,/id="solve-button"/);
  assert.match(html,/>在 Dashboard 解算<\/button>/);
  const p=page();p.element('csv-path').value='C:/long.csv';
  const request=await p.submit({status:'unknown',verified:false,reason:'wall_budget'});
  assert.equal(request.payload.budget_mode,'auto');assert.equal(request.payload.visualization_mode,'entry');
  assert.equal('seconds' in request.payload,false);assert.equal('width' in request.payload,false);
  p.element('full-geometry').checked=true;
  assert.equal((await p.submit({status:'unknown',verified:false})).payload.visualization_mode,'full');
});

test('entry preview plays the full exact trajectory and inputs without inventing later geometry',()=>{
  const p=page();p.result(entryCandidate());
  assert.equal(p.element('play').disabled,false);assert.equal(p.element('timeline').max,2);
  assert.match(p.element('visualization-warning').textContent,/轻量轨迹.*仅起点.*几何/);
  p.element('next').events.click();p.element('next').events.click();
  assert.match(p.element('frame-counter').textContent,/0\.100 s/);
  assert.deepEqual(p.keys.filter(k=>k.active).map(k=>k.dataset.bit),['4','32']);
  const frame=JSON.parse(p.element('frame-data').textContent);
  assert.equal(frame.bounds,null);assert.equal(frame.env,null);assert.equal(frame.geometry_available,false);
  assert.deepEqual(frame.player,entryCandidate().trajectory[2]);
});

test('entry preview rejects incomplete exact clocks and mismatched source entry',()=>{
  for(const mutate of [r=>r.dt_sequence.pop(),r=>r.dt_sequence[2]=0,r=>r.visualization.frames[0].player=[1],
    r=>r.visualization.frames[0].player=[...r.trajectory[0]].map((x,i)=>i?x:x+1)]){
    const p=page(),r=entryCandidate();mutate(r);p.result(r);
    assert.equal(p.element('play').disabled,true);assert.equal(p.element('visualization-warning').hidden,false);
  }
});

test('native launch keeps Dashboard open, shares progress identity and receives only its own result',async()=>{
  const p=page();p.element('csv-path').value='C:/x.csv';await p.launch({id:'a'.repeat(64)});
  assert.equal(p.navigations.length,0);assert.equal(p.opened.length,1);
  const url=new URL(p.popup.url,'http://localhost:8765'),id=url.searchParams.get('progress_id');
  assert(id);assert.equal(url.searchParams.get('mute'),'1');
  p.respond(async request=>({ok:true,json:async()=>({state:'running',phase:'search',tick:51,
    alive_states:123,elapsed_seconds:2,expanded_states:456,progress_id:id})}));
  await p.tick();assert(p.requests.some(r=>r.url==='/api/progress/'+id));
  assert.equal(p.element('p-tick').textContent,'51');assert.equal(p.element('p-alive').textContent,'123');
  const message={type:'nohit:csv-result',progress_id:id,result:entryCandidate()};
  p.message(message,{origin:'http://evil.test'});assert.equal(p.element('play').disabled,true);
  p.message(message,{source:{}});assert.equal(p.element('play').disabled,true);
  p.message({...message,progress_id:'stale'});assert.equal(p.element('play').disabled,true);
  p.message(message);assert.equal(p.element('play').disabled,false);
  p.message({type:'nohit:csv-status',progress_id:id,status:'playing'});
  assert.match(p.element('native-progress').textContent,/原游戏.*执行中/);
  p.message({type:'nohit:csv-status',progress_id:id,status:'completed'});
  assert.match(p.element('native-progress').textContent,/原游戏.*执行完成/);
});

test('retry switches polling only from the active game and ignores stale in-flight progress',async()=>{
  const p=page();p.element('csv-path').value='C:/x.csv';await p.launch({id:'a'.repeat(64)});
  const first=new URL(p.popup.url,'http://localhost').searchParams.get('progress_id');
  let release;
  p.respond(request=>new Promise(resolve=>{release=()=>resolve({ok:true,json:async()=>({state:'done',phase:'stale',progress_id:first})});}));
  const stale=p.tick();
  p.message({type:'nohit:csv-status',previous_progress_id:first,progress_id:'retry-id',status:'solving'});
  release();await stale;
  assert.notEqual(p.element('p-phase').textContent,'stale');
  p.respond(async()=>({ok:true,json:async()=>({state:'running',phase:'verify',progress_id:'retry-id',tick:71})}));
  await p.tick();assert.equal(p.requests.at(-1).url,'/api/progress/retry-id');
  assert.equal(p.element('p-tick').textContent,'71');
  p.message({type:'nohit:csv-status',previous_progress_id:'unrelated',progress_id:'wrong',status:'solving'});
  await p.tick();assert.equal(p.requests.at(-1).url,'/api/progress/retry-id');
});

test('query monitoring is read-only and never derives ETA from budget percentages',async()=>{
  const p=page('?progress_id=read-only');
  p.respond(async()=>({ok:true,json:async()=>({state:'running',phase:'search',progress_id:'read-only',
    elapsed_seconds:3,tick:9,expanded_states:20,fraction:.99,fraction_basis:'wall_budget'})}));
  await p.tick();assert.equal(p.requests[0].url,'/api/progress/read-only');
  assert(p.requests.every(r=>r.payload===null));assert.equal(p.element('p-tick').textContent,'9');
  assert.match(p.element('request-progress').textContent,/只读.*结果/);
  assert.doesNotMatch(html,/id="p-(?:fraction|fill)"|线性外推/);
  assert.equal(p.element('p-eta').textContent,'估算中');
});

test('Dashboard ETA displays server estimates with stage scope and clears them when unavailable or terminal',async()=>{
  assert.match(html,/预计剩余（估算）/);
  const p=page('?progress_id=estimated');
  let snapshot={progress_id:'estimated',state:'running',phase:'prepare',elapsed_seconds:2,
    eta_seconds:null,eta_basis:'unknown',fraction:.9,fraction_basis:'wall_budget'};
  p.respond(async()=>({ok:true,json:async()=>snapshot}));await p.tick();
  assert.equal(p.element('p-eta').textContent,'估算中');
  snapshot={...snapshot,phase:'search',eta_seconds:12.5,eta_basis:'csv_literal_duration_estimate'};await p.tick();
  assert.equal(p.element('p-eta').textContent,'12.5 s');
  assert.match(p.element('p-eta-note').textContent,/当前搜索/);
  assert.match(p.element('p-eta-note').textContent,/准备.*后续.*验证.*变化/);
  snapshot={...snapshot,phase:'verify',eta_seconds:3.25,eta_basis:'scalar_replay_tick_rate'};await p.tick();
  assert.equal(p.element('p-eta').textContent,'3.3 s');assert.match(p.element('p-eta-note').textContent,/当前.*复验/);
  for(const seconds of [null,-1,Infinity,'9']) {
    snapshot={...snapshot,eta_seconds:seconds};await p.tick();assert.equal(p.element('p-eta').textContent,'估算中');
  }
  snapshot={...snapshot,eta_seconds:0,eta_basis:'unknown'};await p.tick();
  assert.equal(p.element('p-eta').textContent,'估算中');
  snapshot={...snapshot,state:'done',eta_seconds:12,eta_basis:'csv_literal_duration_estimate'};await p.tick();
  assert.equal(p.element('p-eta').textContent,'—');assert.match(p.element('p-eta-note').textContent,/已结束/);
});

test('native retry clears the preceding ETA while its new progress channel is waiting',async()=>{
  const p=page();p.element('csv-path').value='C:/x.csv';await p.launch({id:'a'.repeat(64)});
  const id=new URL(p.popup.url,'http://localhost').searchParams.get('progress_id');
  p.respond(async()=>({ok:true,json:async()=>({progress_id:id,state:'running',phase:'search',
    eta_seconds:20,eta_basis:'csv_literal_duration_estimate'})}));await p.tick();
  assert.equal(p.element('p-eta').textContent,'20.0 s');
  p.message({type:'nohit:csv-status',previous_progress_id:id,progress_id:'next-eta',status:'solving'});
  assert.equal(p.element('p-eta').textContent,'估算中');
});

test('closing the running game stops Dashboard polling and keeps both solve entries usable',async()=>{
  const p=page();p.element('csv-path').value='C:/x.csv';await p.launch({id:'a'.repeat(64)});
  const count=p.requests.length;p.popup.close();await p.tick();
  assert.equal(p.requests.length,count);assert.equal(p.timers.size,0);
  assert.match(p.element('native-progress').textContent,/标签页已关闭.*停止/);
  assert.equal(p.element('solve-button').disabled,false);assert.equal(p.element('native-button').disabled,false);
});

test('elapsed time continues across unchanged server snapshots and freezes on completion',async()=>{
  const p=page('?progress_id=slow-phase');
  let snapshot={progress_id:'slow-phase',state:'running',phase:'compile',elapsed_seconds:3,updated_at:10};
  p.respond(async()=>({ok:true,json:async()=>snapshot}));await p.tick();
  p.advance(2500);await p.tick();assert.equal(p.element('p-elapsed').textContent,'5.50 s');
  snapshot={...snapshot,state:'done',elapsed_seconds:7,updated_at:14};await p.tick();
  assert.equal(p.element('p-elapsed').textContent,'7.00 s');assert.equal(p.timers.size,0);
});

test('a verified candidate displays no-handler warnings without disabling playback and clears stale warnings',()=>{
  const p=page(),result=candidate();
  result.warnings=[{line:5,command:'setmaxhp',reason:'native_function_has_no_handler'},
    {line:6,command:'damafeeplayer',reason:'native_function_has_no_handler'},
    {line:153,command:'NoTooth',reason:'native_function_has_no_handler'}];
  p.result(result);
  const warning=p.element('source-warnings');
  assert.equal(warning.hidden,false);assert.match(warning.textContent,/警告.*继续/);
  for(const item of result.warnings)assert(warning.textContent.includes(`第 ${item.line} 行「${item.command}」`));
  assert.match(warning.textContent,/原游戏没有对应处理函数/);assert.doesNotMatch(warning.textContent,/native_function_has_no_handler/);
  assert.equal(p.element('play').disabled,false);assert.equal(p.element('status').dataset.kind,'success');
  p.result(candidate());assert.equal(warning.hidden,true);assert.equal(warning.textContent,'');
});

test('sanitized direct damage warns without blocking the verified model candidate',()=>{
  const p=page(),result=candidate();
  result.warnings=[{line:2,command:'DamagePlayer',reason:'scripted_damage_disabled'}];p.result(result);
  assert.match(p.element('source-warnings').textContent,/第 2 行「DamagePlayer」：CSV 直接伤害\/回血指令无法按无伤脚本处理，已禁用（保留延时）/);
  assert.equal(p.element('source-warnings').hidden,false);assert.equal(p.element('play').disabled,false);
});

test('automatic budget result shows its profile and a useful retry message without asking for tuning',()=>{
  const p=page();p.result({status:'unknown',verified:false,reason:'wall_budget',budget_selection:{mode:'auto',profile:'long'}});
  assert.match(p.element('budget-status').textContent,/自动预算.*长谱/);assert.equal(p.element('budget-status').hidden,false);
  assert.match(p.element('empty-stage').textContent,/自动尝试后仍未找到完整路线，可重试\/查看详情/);
  assert.doesNotMatch(p.element('empty-stage').textContent,/调整.*预算/);
  p.result({status:'unknown',verified:false,reason:'wall_budget',budget_selection:{mode:'manual',profile:'manual'}});
  assert.match(p.element('budget-status').textContent,/手动预算/);assert.match(p.element('empty-stage').textContent,/调整起点或计算预算/);
});

test('terminal proof failure reports the finite avoidance candidate and ends progress without claiming success',async()=>{
  const p=page();p.element('csv-path').value='C:/weakened.csv';
  const result={status:'unknown',verified:false,reason:'terminal_invariant_unproven',actions:[],
    terminal_reasons:['callback_exhaustion_unproven','neutral_release_clock_exhausted'],
    reached_tick:53000,diagnostic_prefix_masks:[0,2],budget_selection:{mode:'auto',profile:'long'}};
  await p.submit(result);
  assert.match(p.element('status').textContent,/避障候选.*终点.*未证明/);
  assert.equal(p.element('status').dataset.kind,'unknown');
  assert.match(p.element('scope-tag').textContent,/终点.*未证明.*未知/);
  assert.match(p.element('status-detail').textContent,/回调.*执行完毕/);
  assert.match(p.element('status-detail').textContent,/释放按键.*时钟/);
  assert.match(p.element('status-detail').textContent,/不能证明无解/);
  assert.doesNotMatch(p.element('empty-stage').textContent,/未找到完整路线|可调整.*预算/);
  assert.match(p.element('empty-stage').textContent,/有限避障候选.*\n.*终点/);
  assert.equal(p.element('progress-state').textContent,'已结束 · 终点未证明');
  assert.equal(p.element('p-eta-note').textContent,'本次解算已结束。');
  assert.equal(p.element('play').disabled,true);assert.equal(p.timers.size,0);
  const raw=JSON.parse(p.element('result-data').textContent);
  assert.deepEqual(raw.terminal_reasons,result.terminal_reasons);assert.equal(raw.status,'unknown');
});

test('unknown terminal proof reasons retain their code and missing details stay explicitly unknown',()=>{
  for(const reasons of [undefined,['future_terminal_condition']]) {
    const p=page();p.result({status:'unknown',verified:false,reason:'terminal_invariant_unproven',terminal_reasons:reasons});
    assert.match(p.element('status-detail').textContent,reasons?/尚未分类.*future_terminal_condition/:/未返回具体.*原因/);
    assert.equal(p.element('play').disabled,true);assert.equal(p.element('status').dataset.kind,'unknown');
  }
});

test('POST completion and request failure always leave progress in a terminal state',async()=>{
  const p=page();p.element('csv-path').value='C:/x.csv';await p.submit({status:'unknown',verified:false,reason:'wall_budget'});
  assert.equal(p.element('progress-state').textContent,'已结束 · 未知');
  await p.submit(candidate());assert.equal(p.element('progress-state').textContent,'已完成');
  p.respond(async()=>{throw Error('disconnected');});await p.submit({});
  assert.equal(p.element('progress-state').textContent,'失败');assert.equal(p.element('p-eta').textContent,'—');
});

test('frame zero is observation; later frames show the input that reached them',()=>{
  const p=page();p.result(candidate());
  assert.equal(p.element('key-label').textContent,'起点观测');assert(p.keys.every(k=>!k.active));
  p.element('next').events.click();
  assert.deepEqual(p.keys.filter(k=>k.active).map(k=>k.dataset.bit),['2']);
  p.element('next').events.click();
  assert.deepEqual(p.keys.filter(k=>k.active).map(k=>k.dataset.bit),['4','32']);
  assert.match(p.element('frame-counter').textContent,/0\.100 s/);
});

test('displayed hazard hitbox matches the source collision radius 2, not the larger wall-contact body',()=>{
  const p=page();p.result(candidate());
  assert(p.draws.some(call=>call.method==='fillRect'&&JSON.stringify(call.args)==='[318,302,4,4]'));
  assert(!p.draws.some(call=>call.method==='fillRect'&&call.args[2]===16&&call.args[3]===16));
  assert.match(html,/受伤判定框 4 × 4/);
});

test('playback obeys returned frame times, including unequal time steps',()=>{
  const p=page();p.result(candidate());p.element('play').events.click();
  p.evaluate('animate(1045)');assert.equal(p.element('timeline').value,1);
  p.evaluate('animate(1095)');assert.equal(p.element('timeline').value,1);
  p.evaluate('animate(1105)');assert.equal(p.element('timeline').value,2);assert.equal(p.element('play').textContent,'播放');
});

test('a following unknown request clears the prior candidate and cannot display stale playback',async()=>{
  const p=page();p.result(candidate());p.element('csv-path').value='C:/sample.csv';
  await p.submit({status:'unknown',reason:'wall_budget',verified:false,actions:[]});
  assert.equal(p.element('play').disabled,true);assert.equal(p.element('empty-stage').hidden,false);
  assert.match(p.element('status-detail').textContent,/不能证明无解/);assert.equal(p.element('status').dataset.kind,'unknown');
  assert.equal(p.element('game-time').textContent,'—');
});

test('request uses the direct path or exact pasted CSV API contract',async()=>{
  const p=page();p.element('csv-path').value='C:/Users/example/welcome.csv';
  const unknown={status:'unknown',reason:'wall_budget',verified:false,actions:[]};
  const a=await p.submit(unknown);assert.equal(a.url,'/api/solve-csv');assert.equal(a.payload.csv_path,'C:/Users/example/welcome.csv');
  assert.equal(a.payload.fps,30);assert.equal(a.payload.budget_mode,'auto');
  assert.equal('seconds' in a.payload,false);assert.equal('width' in a.payload,false);
  assert.equal(a.payload.initial.length,11);assert.equal(a.payload.initial_environment,null);
  p.element('text-tab').events.click();p.element('custom-csv').value='0,HeartMode,0\n0.1,EndAttack\n';
  const b=await p.submit(unknown);assert.equal(b.payload.custom_csv,p.element('custom-csv').value);assert(!('csv_path' in b.payload));
});

test('manual budget remains an explicit advanced option for source-model requests',async()=>{
  const p=page();p.element('csv-path').value='C:/x.csv';p.element('budget-mode').value='manual';
  p.element('seconds').value='7.5';p.element('width').value='1234';
  const request=await p.submit({status:'unknown',verified:false,reason:'wall_budget'});
  assert.equal(request.payload.budget_mode,'manual');assert.equal(request.payload.seconds,7.5);assert.equal(request.payload.width,1234);
});

test('CSV requests always use the current solver and carry live progress identity',async()=>{
  const p=page();p.element('csv-path').value='C:/Users/example/welcome.csv';
  const fresh=await p.submit({status:'unknown',reason:'wall_budget',verified:false,actions:[]});
  assert.equal(fresh.url,'/api/solve-csv');
  assert.equal(typeof fresh.payload.progress_id,'string');
  assert(fresh.payload.progress_id.length>0);
  assert.equal('max_bindings' in fresh.payload,false);
  assert.doesNotMatch(html,/id="engine"|old\.html|renderOldEngine/);
});

test('the file picker submits the chosen CSV text and never a path',async()=>{
  const p=page();p.element('file-tab').events.click();
  p.element('csv-file').files=[{name:'picked.csv',size:64,text:async()=>'0,HeartMode,0\n0.1,EndAttack\n'}];
  const a=await p.submit({status:'unknown',reason:'wall_budget',verified:false,actions:[]});
  assert.equal(a.url,'/api/solve-csv');
  assert.equal(a.payload.custom_csv,'0,HeartMode,0\n0.1,EndAttack\n');
  assert(!('csv_path' in a.payload));
  assert.equal(typeof a.payload.progress_id,'string');
  p.element('csv-file').files=[];
  const b=await p.submit({status:'unknown',reason:'wall_budget',verified:false,actions:[]});
  assert.equal(b,a);   // no second request was issued
  assert.match(p.element('request-progress').textContent,/请先选择一个 CSV 文件/);
});

test('inconsistent geometry and input lengths refuse playback',()=>{
  const p=page(),r=candidate();r.visualization.frames.pop();p.result(r);
  assert.equal(p.element('visualization-warning').hidden,false);assert.equal(p.element('play').disabled,true);
  assert.equal(p.evaluate('frames.length'),0);
});

test('unsupported mechanisms show source lines rather than a search-budget failure',()=>{
  const p=page();p.result({status:'unknown',verified:false,reason:'unsupported_mechanism',issues:[
    {line:5,command:'setmaxhp',reason:'mechanism_not_validated'},
    {line:163,command:'DamagePlayer',reason:'mechanism_not_validated'}]});
  assert.match(p.element('status').textContent,/CSV.*尚未支持/);
  assert.doesNotMatch(p.element('status').textContent,/有限搜索/);
  assert.match(p.element('status-detail').textContent,/第 5 行.*setmaxhp/);
  assert.match(p.element('status-detail').textContent,/第 163 行.*DamagePlayer/);
  assert.doesNotMatch(p.element('empty-stage').textContent,/预算后重试/);
  assert.equal(p.element('play').disabled,true);
});

test('a missing endpoint does not retry when other source mechanisms remain unsupported',async()=>{
  const p=page();p.element('csv-path').value='C:/original.csv';
  await p.submit({status:'unknown',verified:false,reason:'unsupported_mechanism',issues:[
    {reason:'missing_endattack'},{line:5,command:'setmaxhp',reason:'mechanism_not_validated'}]});
  assert.equal(p.requests.length,1);
});

for(const lateSnapshot of [false,true])test('EOF retry starts fresh live progress after '+(lateSnapshot?'a delayed old snapshot':'the first progress channel completed'),async()=>{
  const p=page(),posts=[];p.element('csv-path').value='C:/no-endpoint.csv';
  let releaseFirst,releaseSecond,releaseSnapshot;
  const reply=value=>({ok:true,json:async()=>value});
  p.respond(request=>{
    if(request.payload) {
      posts.push(request.payload);
      return new Promise(resolve=>{
        if(posts.length===1)releaseFirst=()=>resolve(reply({status:'unknown',verified:false,
          reason:'unsupported_mechanism',issues:[{reason:'missing_endattack'}]}));
        else releaseSecond=()=>resolve(reply({status:'unknown',verified:false,reason:'wall_budget'}));
      });
    }
    const id=request.url.split('/').at(-1);
    const snapshot={progress_id:id,state:id===posts[0].progress_id?'done':'running',
      phase:id===posts[0].progress_id?'old-phase':'search',tick:id===posts[0].progress_id?1:99};
    return lateSnapshot&&id===posts[0].progress_id
      ?new Promise(resolve=>{releaseSnapshot=()=>resolve(reply(snapshot));}):reply(snapshot);
  });
  const pending=p.submit({});const oldPoll=p.tick();if(!lateSnapshot)await oldPoll;
  releaseFirst();await new Promise(setImmediate);
  assert.equal(posts.length,2);assert.equal(posts[1].termination_policy,'eof_hazards_drained');
  assert.notEqual(posts[1].progress_id,posts[0].progress_id);
  assert.equal(p.evaluate('progressId'),posts[1].progress_id);
  if(lateSnapshot){releaseSnapshot();await oldPoll;assert.notEqual(p.element('p-phase').textContent,'old-phase');}
  await p.tick();assert.equal(p.requests.at(-1).url,'/api/progress/'+posts[1].progress_id);
  assert.equal(p.element('p-tick').textContent,'99');
  releaseSecond();await pending;
});

if(process.env.CSV_API_URL) test('live short CSV request satisfies the page geometry contract',async()=>{
  const reply=await fetch(process.env.CSV_API_URL,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    custom_csv:'0,HeartMode,0\n0.1,SansText,abc\n0,SansText,a\n0,EndAttack\n',initial:[320,304,0,0,0,0,0,1,750,0,0],fps:30,seconds:5,width:10,max_ticks:100})});
  const result=await reply.json();assert.equal(reply.status,200,JSON.stringify(result));assert.equal(result.status,'candidate_found');
  const p=page();p.result(result);assert.equal(p.element('visualization-warning').hidden,true,p.element('visualization-warning').textContent);assert(p.evaluate('frames.length')>1);
});

if(process.env.CSV_API_URL) test('live budget exhaustion remains unknown and provides no playable candidate',async()=>{
  const reply=await fetch(process.env.CSV_API_URL,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    custom_csv:'0,HeartMode,0\n0.1,SansText,abc\n0,EndAttack\n',initial:[320,304,0,0,0,0,0,1,750,0,0],fps:30,seconds:0,width:10,max_ticks:100})});
  const result=await reply.json();assert.equal(reply.status,200);assert.equal(result.status,'unknown');assert.equal(result.verified,false);
  const p=page();p.result(result);assert.equal(p.evaluate('frames.length'),0);assert.equal(p.element('play').disabled,true);
});
