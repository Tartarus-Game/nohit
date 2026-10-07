// Exercise the production bridge against the checked-in native AJAX plugin.
import assert from 'node:assert/strict';
import {createHash,webcrypto} from 'node:crypto';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const runtimeSource=fs.readFileSync(new URL('../../c2-sans-fight/c2runtime.js',import.meta.url),'utf8');
const nativeAjax=runtimeSource.slice(runtimeSource.indexOf('function tc('),runtimeSource.indexOf('function uc('));
const bridge=fs.readFileSync(new URL('../../c2-sans-fight/csv_source_bridge.js',import.meta.url),'utf8');
const sha=value=>createHash('sha256').update(value).digest('hex');
function boot(options={}) {
  const raw=options.raw??Buffer.from('0,SansText,你好\n0,EndAttack\n');
  const text=new TextDecoder().decode(raw).replace(/\r\n/g,'\n');
  const source={id:sha(raw),raw_sha256:sha(raw),sha256:sha(text),text,name:'test.csv',byte_count:raw.length,url:'/api/csv-source/'+sha(raw)+'.csv'};
  options.mutate?.(source);
  const calls=[],requests=[],fetches=[],events=new Map(),cancelled=[];
  let context,ajax,attached=!options.lateRuntime,resolveFetch;
  const gate=options.deferred?new Promise(resolve=>resolveFetch=resolve):Promise.resolve();
  class Runtime {
    trigger(method,inst,value) {
      if(method===context.tc.prototype.c.Zg&&inst.rc==='custom')calls.push('native completed(custom)');
      return 'trigger-result';
    }
    tick(){calls.push('tick');return 'tick-result';}
  }
  const rt=new Runtime();rt.types_by_index=[];
  class Request {
    open(method,url){this.method=method;this.url=url;}
    setRequestHeader(){}
    send(){if(options.requestThrows)throw Error('native request exception');requests.push(this);}
  }
  const badge={textContent:''};
  context={URLSearchParams,TextEncoder,TextDecoder,Uint8Array,crypto:webcrypto,
    location:{search:options.query??'?csvtas=1&csv_source='+sha(raw)},
    document:{getElementById:id=>id==='c2canvas'?(attached?{c2runtime:rt}:null):id==='tas-status-badge'?badge:null},
    cr:{runtime:attached?Runtime:null,plugins_:{Function:{prototype:{cnds:{OnFunction(){}}}}}},
    XMLHttpRequest:Request,mb:(a,b)=>String(a).toLowerCase()===String(b).toLowerCase(),
    __CSV_TAS:{cancel:error=>cancelled.push(error)},
    c2_callFunction(name){calls.push(name);if(name===options.functionThrows)throw Error('native '+name+' exception');},
    cr_setSuspended(value){rt.suspended=value;},
    addEventListener:(name,callback)=>events.set(name,callback),
    fetch:async(url)=>{fetches.push(url);await gate;if(options.fetchError)throw Error(options.fetchError);
      return {ok:options.ok!==false,json:async()=>{if(options.invalidJSON)throw Error('invalid JSON');return source;},
        arrayBuffer:async()=>raw.buffer.slice(raw.byteOffset,raw.byteOffset+raw.byteLength)};},
  };
  context.window=context;vm.createContext(context);vm.runInContext(nativeAjax,context,{filename:'native-ajax-from-c2runtime.js'});
  ajax=new context.tc.prototype.S({b:rt});ajax.D();rt.types_by_index.push({sid:1871150019731238,instances:[ajax]});
  vm.runInContext(bridge,context,{filename:'csv_source_bridge.js'});
  function emit(name){rt.trigger(context.cr.plugins_.Function.prototype.cnds.OnFunction,{},name);}
  function complete({status=200,bytes=raw,error=false}={}) {
    const request=requests.at(-1);assert(request,'native AJAX request must exist');
    if(error){request.onerror();return;}
    Object.assign(request,{readyState:4,status,responseText:new TextDecoder().decode(bytes)});request.onreadystatechange();
  }
  return {context,source,raw,text,rt,ajax,calls,requests,fetches,badge,cancelled,emit,complete,resolveFetch,
    tick:()=>rt.tick(),async ready(){await context.__CSV_SOURCE_READY?.catch(()=>{});await Promise.resolve();},
    attach(){attached=true;context.cr.runtime=Runtime;events.get('nohit-runtime-ready')?.();}};
}

for(const raw of [Buffer.from('0,SansText,你好\n0,EndAttack\n'),Buffer.from('\ufeff0,SansText,你好\r\n0,EndAttack\r\n')])
test('native AJAX loads immutable bytes and MenuCustomRun follows its completion: '+sha(raw).slice(0,8),async()=>{
  const g=boot({raw});await g.ready();g.tick();assert.equal(g.requests.length,0);
  g.emit('AttackLoadFinished');g.tick();assert.equal(g.requests.length,1);
  assert.equal(g.requests[0].url,g.source.url);assert.equal(g.requests[0].method,'GET');
  assert.equal(g.source.raw_sha256,sha(raw));assert.equal(g.source.sha256,sha(g.text));
  assert(!g.calls.includes('MenuCustomRun'));g.complete();g.tick();g.tick();
  assert.equal(g.ajax.zd,g.text);assert.equal(g.context.__CSV_SOURCE_BRIDGE.status,'entered');
  assert.equal(g.calls.filter(name=>name==='MenuModeCustom').length,1);
  assert.equal(g.calls.filter(name=>name==='MenuCustomRun').length,1);
  assert(g.calls.indexOf('native completed(custom)')<g.calls.indexOf('MenuCustomRun'));
});

test('the bridge stays inert outside csvtas mode',()=>{
  const g=boot({query:'?attack=custom'});g.emit('AttackLoadFinished');g.tick();
  assert.equal(g.context.__CSV_SOURCE_BRIDGE,undefined);assert.equal(g.fetches.length,0);assert.equal(g.requests.length,0);
});

test('source and runtime readiness gates both precede native loading',async()=>{
  const g=boot({deferred:true,lateRuntime:true});g.attach();g.emit('AttackLoadFinished');g.tick();assert.equal(g.requests.length,0);
  g.resolveFetch();await g.ready();g.tick();assert.equal(g.requests.length,1);assert(!g.calls.includes('MenuCustomRun'));
});

for(const [label,options] of [
  ['missing registered identity',{query:'?csvtas=1'}],['HTTP failure',{ok:false}],
  ['network failure',{fetchError:'offline'}],['invalid JSON',{invalidJSON:true}],
  ['changed text hash',{mutate:s=>s.sha256='0'.repeat(64)}],
  ['foreign identity',{mutate:s=>s.id='0'.repeat(64)}],
  ['raw hash mismatch',{mutate:s=>s.raw_sha256='0'.repeat(64)}],
  ['foreign download URL',{mutate:s=>s.url='/api/csv-source/'+'0'.repeat(64)+'.csv'}],
])test(label+' never starts original custom execution',async()=>{
  const g=boot(options);await g.ready();g.emit('AttackLoadFinished');g.tick();
  assert.equal(g.context.__CSV_SOURCE_BRIDGE.status,'failed');assert(!g.calls.includes('MenuCustomRun'));
  assert.equal(g.rt.suspended,true);assert(g.cancelled.length>0);
});

test('stale custom response text cannot replace completion of the new request',async()=>{
  const g=boot();await g.ready();g.ajax.rc='custom';g.ajax.zd=g.text;
  g.emit('AttackLoadFinished');g.tick();g.tick();assert(!g.calls.includes('MenuCustomRun'));
  g.complete();g.tick();assert.equal(g.calls.filter(name=>name==='MenuCustomRun').length,1);
});

for(const [label,completion] of [
  ['native HTTP error',{status:500}],['native network error',{error:true}],
  ['changed response text',{bytes:Buffer.from('0,EndAttack\n')}],
])test(label+' fails instead of hanging in native_loading',async()=>{
  const g=boot();await g.ready();g.emit('AttackLoadFinished');g.tick();g.complete(completion);g.tick();
  assert.equal(g.context.__CSV_SOURCE_BRIDGE.status,'failed');assert(!g.calls.includes('MenuCustomRun'));
  assert.equal(g.rt.suspended,true);
});

for(const name of ['MenuModeCustom','MenuCustomRun'])test(name+' exceptions fail closed',async()=>{
  const g=boot({functionThrows:name});await g.ready();g.emit('AttackLoadFinished');
  assert.doesNotThrow(()=>g.tick());
  if(g.requests.length){g.complete();assert.doesNotThrow(()=>g.tick());}
  assert.equal(g.context.__CSV_SOURCE_BRIDGE.status,'failed');assert.equal(g.rt.suspended,true);
});
