import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const html = fs.readFileSync(new URL('../../nohit/dashboard/static/index.html', import.meta.url),'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function page() {
  const elements = new Map(), keys=[],draws=[];let fetchResult;let submitted;
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
  const context=vm.createContext({document:{getElementById:element,querySelectorAll:()=>keys},
    requestAnimationFrame:()=>1,cancelAnimationFrame(){},performance:{now:()=>1000},
    setInterval:()=>1,clearInterval(){},
    fetch:async(url,options)=>{submitted={url,payload:JSON.parse(options.body)};return {ok:true,json:async()=>fetchResult};}});
  vm.runInContext(script,context,{filename:'csv.html'});
  Object.assign(element('initial-state'),{value:'[320,304,0,0,0,0,0,1,750,0,0]'});
  element('initial-environment').value='null';element('fps').value='30';element('seconds').value='30';
  element('width').value='3000';element('bindings').value='1';element('speed').value='1';
  return {element,keys,context,draws,evaluate:code=>vm.runInContext(code,context),
    result(value){context.testResult=value;vm.runInContext('showResult(testResult)',context);},
    async submit(value){fetchResult=value;await element('solve-form').events.submit({preventDefault(){}});return submitted;}};
}

function candidate() {
  const frames=[0,.04,.1].map((time,index)=>({tick:index,time_seconds:time,dt:index===2?.06:.04,
    player:[320+index,304,0,0,0,0,0,1,750,0,0],env:Array(22).fill(0),bounds:[133,251,508,391],white:[],blue:[],polygons:[],platforms:[]}));
  return {status:'candidate_found',verified:true,actions:[2,4],confirm_sequence:[false,true],trajectory:frames.map(f=>f.player),
    wall_seconds:2,game_seconds:.1,visualization:{schema_version:1,scope:'verified_source_model',frame_count:3,frames}};
}

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
  assert.equal(a.payload.fps,30);assert.equal(a.payload.seconds,30);assert.equal(a.payload.initial.length,11);assert.equal(a.payload.initial_environment,null);
  p.element('text-tab').events.click();p.element('custom-csv').value='0,HeartMode,0\n0.1,EndAttack\n';
  const b=await p.submit(unknown);assert.equal(b.payload.custom_csv,p.element('custom-csv').value);assert(!('csv_path' in b.payload));
});

test('engine selector routes to the chosen solver and asks for live progress',async()=>{
  const p=page();p.element('csv-path').value='C:/Users/example/welcome.csv';
  const unknown={status:'unknown',reason:'wall_budget',verified:false,actions:[]};
  const fresh=await p.submit(unknown);
  assert.equal(fresh.url,'/api/solve-csv');
  assert.equal(typeof fresh.payload.progress_id,'string');
  assert(fresh.payload.progress_id.length>0);
  p.element('engine').value='old';p.element('text-tab').events.click();
  p.element('custom-csv').value='0,HeartMode,0\n6.4,EndAttack\n';
  p.element('fps').value='60';p.element('seconds').value='10';
  const legacy=await p.submit({is_deadlock:false,W:200,H:160,T:385,initial_state:[96,0],
    stats:{bake_ms:45,dp_ms:48424,total_ms:48469,peak_states:67468},hazard_runs:[[]],
    platforms:[[]],trajectory:[[96,0,0,1,0]],action_sequence:[],slam_frames:[]});
  assert.equal(legacy.url,'/api/solve');
  assert.equal(legacy.payload.custom_csv,'0,HeartMode,0\n6.4,EndAttack\n');
  assert.equal(legacy.payload.T,600);
  assert.equal(legacy.payload.wave,null);
  assert.match(p.element('scope-tag').textContent,/栅格模型/);
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

test('the legacy engine refuses a bare local path instead of silently mis-solving',async()=>{
  const p=page();p.element('engine').value='old';p.element('csv-path').value='C:/tmp/not_a_wave.csv';
  const submitted=await p.submit({is_deadlock:false,stats:{},hazard_runs:[],trajectory:[]});
  assert.equal(submitted,undefined);
  assert.match(p.element('request-progress').textContent,/旧引擎只接受仓库内波次名/);
});

test('inconsistent geometry and input lengths refuse playback',()=>{
  const p=page(),r=candidate();r.visualization.frames.pop();p.result(r);
  assert.equal(p.element('visualization-warning').hidden,false);assert.equal(p.element('play').disabled,true);
  assert.equal(p.evaluate('frames.length'),0);
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
