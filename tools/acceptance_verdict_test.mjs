import {test} from 'node:test';
import assert from 'node:assert/strict';
import {assertLiveRuns} from './acceptance_verdict.mjs';
const clean=()=>({startHP:92,minHP:92,endHP:92,maxKR:0,hits:0,endAttackObserved:true,rows:1500});
test('three complete clean rounds pass',()=>assert.doesNotThrow(()=>assertLiveRuns([clean(),clean(),clean()],3)));
for(const patch of [{startHP:91},{minHP:91},{endHP:91},{maxKR:1},{hits:1},{endAttackObserved:false},{rows:0}]) {
    test('rejects '+JSON.stringify(patch),()=>assert.throws(()=>assertLiveRuns([clean(),{...clean(),...patch},clean()],3)));
}
test('a missing round cannot pass',()=>assert.throws(()=>assertLiveRuns([clean(),clean()],3)));
