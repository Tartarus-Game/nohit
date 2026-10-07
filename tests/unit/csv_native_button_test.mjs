import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const html=fs.readFileSync(new URL('../../nohit/dashboard/static/index.html',import.meta.url),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const id='a'.repeat(64);
function page(options={}) {
  const elements=new Map(),requests=[],navigations=[];let resolveFetch;
  const gate=options.deferred?new Promise(resolve=>resolveFetch=resolve):Promise.resolve();
  const drawing=new Proxy({}, {get:(target,key)=>target[key]??(()=>{}),set:(target,key,value)=>(target[key]=value,true)});
  function element(name) {
    if(!elements.has(name))elements.set(name,{value:'',textContent:'',disabled:false,hidden:false,dataset:{},events:{},
      addEventListener(type,handler){this.events[type]=handler;},setAttribute(){},getContext:()=>drawing});
    return elements.get(name);
  }
  const context=vm.createContext({document:{getElementById:element,querySelectorAll:()=>[]},URLSearchParams,
    location:{assign:url=>navigations.push(url)},performance:{now:()=>0},
    requestAnimationFrame:()=>1,cancelAnimationFrame(){},setInterval:()=>1,clearInterval(){},
    fetch:async(url,request)=>{requests.push({url,method:request.method,headers:request.headers,body:JSON.parse(request.body)});await gate;
      if(options.fetchError)throw Error(options.fetchError);
      return {ok:options.ok!==false,json:async()=>{if(options.invalidJSON)throw Error('invalid JSON');return options.result??{id};}};}});
  vm.runInContext(script,context,{filename:'csv.html'});
  element('seconds').value='7.5';element('width').value='1234';element('bindings').value='2';element('fps').value='30';
  return {element,requests,navigations,resolveFetch,click:()=>element('native-button').events.click()};
}

for(const fps of ['30','60','120','240'])test('native button registers a trimmed path then navigates with source and search parameters at '+fps+'Hz',async()=>{
  const p=page();p.element('csv-path').value='  C:\\用户\\欢迎 & 地狱.csv  ';p.element('fps').value=fps;
  await p.click();assert.equal(p.requests.length,1);assert.equal(p.requests[0].url,'/api/csv-source');
  assert.equal(p.requests[0].method,'POST');assert.equal(p.requests[0].headers['Content-Type'],'application/json');
  assert.deepEqual(p.requests[0].body,{csv_path:'C:\\用户\\欢迎 & 地狱.csv'});
  assert.equal(p.navigations.length,1);const url=new URL(p.navigations[0],'http://localhost');
  assert.equal(url.pathname,'/game/index.html');
  for(const [key,value] of Object.entries({csvtas:'1',csv_source:id,attack:'custom',custom_acceptance:'1',seed:'42',seconds:'7.5',width:'1234',max_bindings:'2',fps}))
    assert.equal(url.searchParams.get(key),value,key);
  assert.equal(url.searchParams.has('initial'),false);assert.equal(url.searchParams.has('actions'),false);
});

test('pasted CSV reaches registration byte-for-byte, including BOM, CRLF and surrounding whitespace',async()=>{
  const p=page();p.element('text-tab').events.click();
  const text='\ufeff0,SansText,你好\r\n0,EndAttack\r\n  ';
  p.element('custom-csv').value=text;await p.click();
  assert.deepEqual(p.requests[0].body,{custom_csv:text});assert.equal(p.navigations.length,1);
});

test('a picked file is read and registered by the native entry in file mode',async()=>{
  // The paste textarea is empty in file mode, so reading it registered an empty
  // source and the native launch did nothing.
  const p=page();p.element('file-tab').events.click();
  p.element('csv-file').files=[{name:'picked.csv',size:32,text:async()=>'0,HeartMode,0\n6.4,EndAttack\n'}];
  await p.click();
  assert.equal(p.requests.length,1);
  assert.equal(p.requests[0].url,'/api/csv-source');
  assert.deepEqual(p.requests[0].body,{custom_csv:'0,HeartMode,0\n6.4,EndAttack\n'});
  assert.equal(p.navigations.length,1);
  assert.match(p.navigations[0],/^\/game\/index\.html\?/);
  const url=new URL(p.navigations[0],'http://localhost');
  assert.equal(url.searchParams.get('csvtas'),'1');
  assert.equal(url.searchParams.get('csv_source'),id);
});

test('the native entry reports a missing pick instead of registering an empty source',async()=>{
  const p=page();p.element('file-tab').events.click();
  p.element('csv-file').files=[];
  await p.click();
  assert.equal(p.requests.length,0);assert.equal(p.navigations.length,0);
  assert.match(p.element('request-progress').textContent,/请先选择一个 CSV 文件/);
});

test('a pending registration disables native launch and rejects duplicate clicks',async()=>{
  const p=page({deferred:true});p.element('csv-path').value='C:/x.csv';
  const pending=p.click();assert.equal(p.element('native-button').disabled,true);
  await p.click();assert.equal(p.requests.length,1);assert.equal(p.navigations.length,0);
  p.resolveFetch();await pending;assert.equal(p.navigations.length,1);assert.equal(p.element('native-button').disabled,false);
});

for(const mode of ['path','text'])test('empty '+mode+' input does not register or navigate',async()=>{
  const p=page();if(mode==='text')p.element('text-tab').events.click();
  p.element(mode==='text'?'custom-csv':'csv-path').value=' \r\n ';await p.click();
  assert.equal(p.requests.length,0);assert.equal(p.navigations.length,0);assert.match(p.element('request-progress').textContent,/CSV/);
});

for(const [label,options] of [
  ['HTTP error',{ok:false,result:{error:'source not found'}}],['network exception',{fetchError:'offline'}],
  ['invalid JSON',{invalidJSON:true}],['missing identity',{result:{}}],
  ['malformed identity',{result:{id:'not-registered'}}],['error payload with HTTP 200',{result:{id,error:'failed registration'}}],
])test(label+' keeps the user on the form and permits retry',async()=>{
  const p=page(options);p.element('csv-path').value='C:/x.csv';await p.click();
  assert.equal(p.navigations.length,0);assert.equal(p.element('native-button').disabled,false);
  assert(p.element('request-progress').textContent.length>0);
});
