import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const html = fs.readFileSync(new URL('../../nohit/dashboard/static/index.html', import.meta.url),'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function page() {
  const elements = new Map(), keys=[],draws=[],requests=[];let fetchResult;let submitted;
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
    fetch:async(url,options)=>{submitted={url,payload:JSON.parse(options.body)};requests.push(submitted);return {ok:true,json:async()=>fetchResult};}});
  vm.runInContext(script,context,{filename:'csv.html'});
  Object.assign(element('initial-state'),{value:'[320,304,0,0,0,0,0,1,750,0,0]'});
  element('initial-environment').value='null';element('fps').value='30';element('seconds').value='30';
  element('width').value='3000';element('speed').value='1';
  return {element,keys,context,draws,requests,evaluate:code=>vm.runInContext(code,context),
    result(value){context.testResult=value;vm.runInContext('showResult(testResult)',context);},
    async submit(value){fetchResult=value;await element('solve-form').events.submit({preventDefault(){}});return submitted;}};
}

function candidate() {
  const frames=[0,.04,.1].map((time,index)=>({tick:index,time_seconds:time,dt:index===2?.06:.04,
    player:[320+index,304,0,0,0,0,0,1,750,0,0],env:Array(22).fill(0),bounds:[133,251,508,391],white:[],blue:[],polygons:[],platforms:[]}));
  return {status:'candidate_found',verified:true,actions:[2,4],confirm_sequence:[false,true],trajectory:frames.map(f=>f.player),
    wall_seconds:2,game_seconds:.1,visualization:{schema_version:1,scope:'verified_source_model',frame_count:3,frames}};
}

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
