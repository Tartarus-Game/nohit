import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source=fs.readFileSync(new URL('../../c2-sans-fight/custom_wave_acceptance.js',import.meta.url),'utf8');
const attack=[3019589746608161,3868174782291034,9836012384209519,7974524067202295,
  8140934880742138,6503092777075739,4163262150020477,336730486351203,508841962091807,165116925986465,
  1226268899238104,6981383464931416];
const families=[9590353435551898,6631597198329078,9784977049754561,8627438680975019];
function fixture() {
  class Runtime {tick(){} trigger(...args){return this.nativeTrigger?.(...args);}}
  const rt=new Runtime(),keys={};
  rt.types_by_index=[...attack.map(sid=>({sid,instances:[]})),...families.map(sid=>({sid,members:[],instances:[]})),
    {sid:456555951765879,instances:[{ra:2}]}];
  rt.varsBySid={2569112556112449:{data:3},5359025861573384:{data:0}};
  rt.Hd={fc:[]};rt.ih=null;rt.isloading=false;rt.running_layout={name:'BattleScreen',Y:8667945925241823};
  const geometry=(uid,x,y,width,height)=>({uid,x,y,width,height,angle:0,collisionsEnabled:true,ga:null,
    bbox:{left:x,top:y,right:x+width,bottom:y+height},update_bbox(){}});
  rt.types_by_index.push({sid:5960708907117077,instances:[geometry(1,320,320,16,16)]},
    {sid:6657741784745805,instances:[geometry(2,30,200,580,5),geometry(3,30,200,5,200),
      geometry(4,30,395,580,5),geometry(5,605,200,5,200)]});
  rt.types_by_index.find(t=>t.sid===5960708907117077).instances[0].ga={hr:[-.5,.5,-.5,-.5,.5,-.5,.5,.5]};
  const physical={tick:12,initial:[320,320,0,0,0,0,0,1,750,0,0],
    initial_environment:[30,200,610,400,0,1,0,1/30,750,0,0,0,0,0,30,200,610,400,30,200,610,400],
    vpad:Array(14).fill(0),arena:{target:[30,200,610,400],size:[580,200],speed:0,callback:''},
    rpgtext:[],HP:92,KR:0,SimulatorMode:2,SingleAttack:'custom'};
  const uiType={sid:6163397057824361,instances:[]};rt.types_by_index.push(uiType);
  rt.types_by_index.find(t=>t.sid===8627438680975019).members.push(uiType);
  for(const [i,name] of ['HP','PlayerName','QuitMessage'].entries()) {
    const fields=[name,'','','',0,0,0.1,0];
    physical.rpgtext.push({typeSid:uiType.sid,uid:100+i,familyOffset:0,fields,vars:fields.slice()});
    uiType.instances.push({uid:100+i});
  }
  const hashes=['664b5d93dbd5159976d490663ac64c49c8eb7dc68c9aac92fba940b6fa2a3de9',
    '9f70e7179fe4260002321a75e5170e96583439bb39988b92ed93da42a0a402c7'];let hashIndex=0;
  const window={cr:{runtime:Runtime},TASRunner:{getKeyboardInstance:()=>({keyMap:keys})},
    NoHitSolverState:{capturePhysical:()=>structuredClone(physical)}};
  window.cr.plugins_={Function:{prototype:{cnds:{OnFunction(){}}}}};
  const context=vm.createContext({window,cr:window.cr,location:{search:'?custom_acceptance=1'},URLSearchParams,
    document:{getElementById:()=>({c2runtime:rt})},fetch:async()=>({ok:true,arrayBuffer:async()=>new ArrayBuffer(0)}),
    crypto:{subtle:{digest:async()=>Uint8Array.from(Buffer.from(hashes[hashIndex++],'hex')).buffer}},Uint8Array,TextEncoder});
  vm.runInContext(source,context);return {rt,keys,physical,A:window.__CUSTOM_WAVE,window,geometry};
}
test('EOF endpoint is observed with exact native queue, source and input facts',async()=>{
  const f=fixture();await f.A.sourceReady;f.A.captureEof({requireRelease:false});const e=f.A.captureEof();
  assert.equal(e.timeline.width_field,'ra');assert.equal(e.timeline.width,2);
  assert.equal(e.wait_queue.is_array,true);assert.equal(e.wait_queue.length,0);
  assert.equal(e.attack_types.length,attack.length);assert.equal(e.owned_keys.length,12);
  assert.equal(e.callback_contract,'original-custom-empty-eof-v1');
  assert.equal(e.physical.tick,12);assert.equal(e.physical.vpad.length,14);
  assert.equal(e.source_sha256['data.js'].length,64);
  assert.deepEqual(Array.from(e.heart_geometry.collision_polygon),[-.5,.5,-.5,-.5,.5,-.5,.5,.5]);
});
for(const [name,mutate] of [
  ['missing hazard type',f=>f.rt.types_by_index.shift()],
  ['missing family',f=>f.rt.types_by_index.splice(12,1)],
  ['residual platform',f=>f.rt.types_by_index.find(t=>t.sid===1226268899238104).instances.push({uid:9})],
  ['missing wait queue',f=>delete f.rt.Hd.fc],['pending wait',f=>f.rt.Hd.fc.push({})],
  ['missing layout transition field',f=>delete f.rt.ih],['pending layout',f=>f.rt.ih={}],
  ['loading',f=>f.rt.isloading=true],['wrong layout',f=>f.rt.running_layout.Y=0],
  ['previous Confirm still down',f=>f.physical.vpad[11]=1],['alternate owned key still down',f=>f.keys[13]=true],
  ['arena callback',f=>f.physical.arena.callback='BoneV'],['arena resizing',f=>f.physical.arena.target[0]=31],
  ['dialogue still alive',f=>f.physical.rpgtext.push({uid:1})],['not EOF',f=>f.rt.varsBySid[2569112556112449].data=2],
  ['passive UI callback',f=>f.physical.rpgtext[0].fields[3]='BoneV'],
  ['passive UI replaced',f=>f.physical.rpgtext[0].uid=999],
  ['malformed border polygon',f=>f.rt.types_by_index.find(t=>t.sid===6657741784745805).instances[0].ga={}],
])test(name+' cannot certify an EOF endpoint',async()=>{
  const f=fixture();await f.A.sourceReady;f.A.captureEof({requireRelease:false});mutate(f);assert.throws(()=>f.A.captureEof());
});

function terminalFixture(f) {
  f.rt.tickcount=12;f.A.started=true;
  f.rt.Qf=[{Y:6451037740410459,sheet:{name:'Battle'},vh:'playermovement',Ya(){return 23;}}];
  const params=['EndAttack',Array(9).fill(0)];
  const action={Y:9188948149072352,index:0,Ka:params};
  const event={Y:441595194418922,sheet:{name:'Timeline'},Fc:[action]};
  f.rt.Ea=()=>({Ia:event,Wb:0});
  f.rt.types_by_index.find(t=>t.sid===456555951765879).instances[0].pc=i=>['0,HeartMode,1','0,SET,x,2','0,EndAttack'][i];
  const loaded=['0','EndAttack',...Array(9).fill(0)];
  f.rt.types_by_index.push({sid:3081225054711249,instances:[{ra:loaded.length,pc:i=>loaded[i]}]});
  const platform=f.geometry(9,100,300,50,8);platform.instance_vars=[1];
  f.rt.types_by_index.find(t=>t.sid===1226268899238104).instances.push(platform);
  const inst={exps:{Param(ret){ret.set_int(0);}}};
  return {event,action,call:()=>f.rt.trigger(f.window.cr.plugins_.Function.prototype.cnds.OnFunction,inst,'endattack')};
}

test('EndAttack records distinct native entry/return and the actual Timeline caller',async()=>{
  const f=fixture();await f.A.sourceReady;const t=terminalFixture(f);
  f.physical.initial[3]=111;
  f.rt.nativeTrigger=()=>{
    f.physical.initial[3]=129;
    f.rt.types_by_index.find(t=>t.sid===1226268899238104).instances=[];
    return 17;
  };
  assert.equal(t.call(),17);
  const e=f.A.events[0],s=e.snapshots;
  assert.equal(s.schema_version,1);assert.equal(s.source,'timeline');
  assert.equal(s.source_line,3);assert.equal(s.caller.event_sid,441595194418922);
  assert.equal(s.caller.action_sid,9188948149072352);assert.equal(s.caller.action_index,0);
  assert.equal(s.caller.loaded_line[1],'EndAttack');assert.equal(s.caller.raw_source_line,'0,EndAttack');
  assert.equal(s.before.capture_phase,'before_native_endattack');
  assert.equal(s.after.capture_phase,'after_native_endattack');
  assert.equal(s.before.physical.initial[3],111);assert.equal(s.after.physical.initial[3],129);
  assert.equal(s.before.platforms.length,1);assert.equal(s.after.platforms.length,0);
  assert.equal(s.before.borders.length,4);assert.equal(s.before.heart_geometry.uid,1);
  assert.equal(s.source_sha256['data.js'].length,64);
  f.physical.initial[0]=48;f.physical.initial[1]=453;
  assert.equal(f.rt.Qf[0].Ya(),23);
  assert.equal(s.before_movement.capture_phase,'before_native_player_movement');
  assert.equal(s.before_movement.event_sid,6451037740410459);
  assert.equal(s.before_movement.group_name,'playermovement');
  assert.equal(s.before_movement.physical.initial[0],48);
  assert.equal(s.before.physical.initial[0],320);
});

test('callback EndAttack cannot acquire direct Timeline provenance from the loaded row',async()=>{
  const f=fixture();await f.A.sourceReady;const t=terminalFixture(f);
  t.event.Y=123;t.event.sheet.name='RPGText';t.action.Y=456;
  t.call();const s=f.A.events[0].snapshots;
  assert.equal(s.source,'other');assert.equal(s.caller.event_sid,123);
  assert.equal(s.caller.loaded_line[1],'EndAttack');
});
