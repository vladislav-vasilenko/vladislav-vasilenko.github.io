import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const c=vm.createContext({});vm.runInContext(fs.readFileSync(new URL('../archive-web/learning-impact.js',import.meta.url),'utf8'),c);const {model}=c.LearningImpact;
test('identical four-hour actions are explained without inventing differences in effort',()=>{
 const data=model([{label:'A',action:'publish_project',action_effort_hours:4,vacancy_count:37},{label:'B',action:'publish_project',action_effort_hours:4,vacancy_count:7}]);assert.equal(data.constant,true);assert.equal(data.effort,4);assert.equal(data.maxY,37);assert.equal(data.items[0].action_effort_hours,data.items[1].action_effort_hours);
});
test('filter and limit preserve the existing priority order and never include completed items',()=>{
 const data=model([{action:null},{action:'learn',action_effort_hours:8,vacancy_count:10},{action:'validate',action_effort_hours:1,vacancy_count:3}], 'validate',1);assert.equal(data.items.length,1);assert.equal(data.items[0].action,'validate');assert.equal(data.constant,false);
});
