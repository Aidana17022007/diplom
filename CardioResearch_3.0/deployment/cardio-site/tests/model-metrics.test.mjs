import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
const bundle=await build({entryPoints:['client/src/modelMetrics.ts'],bundle:true,format:'esm',write:false});
const {sortedModels,compareModels}=await import('data:text/javascript;base64,'+Buffer.from(bundle.outputFiles[0].text).toString('base64'));
test('sorting keeps unavailable scores last in both directions and leaves rows unchanged',()=>{
  const rows=[{name:'missing',metrics:{brier:null}},{name:'A',metrics:{brier:.2}},{name:'B',metrics:{brier:.1}},{name:'invalid',metrics:{brier:NaN}}];
  assert.deepEqual(sortedModels(rows,'brier','asc').map(x=>x.name),['B','A','missing','invalid']);
  assert.deepEqual(sortedModels(rows,'brier','desc').map(x=>x.name),['A','B','missing','invalid']);
  assert.deepEqual(rows.map(x=>x.name),['missing','A','B','invalid']);
});
test('comparison uses signed absolute differences and preserves undefined scores',()=>{
  const result=compareModels({name:'A',metrics:{roc_auc:.8,brier:.2,recall:null}},{name:'B',metrics:{roc_auc:.9,brier:.1,recall:.5}},['roc_auc','brier','recall','precision']);
  assert.ok(Math.abs(result[0].delta-.1)<1e-12);
  assert.equal(result[1].delta,-.1);
  assert.equal(result[2].delta,null);assert.equal(result[2].first,null);
  assert.deepEqual(result[3],{key:'precision',first:null,second:null,delta:null});
});
