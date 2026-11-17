import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../dist/server/index.js';

const origin='https://cardioresearch.example';
const get=path=>worker.fetch(new Request(origin+path),{});

test('public experiments expose aggregate evidence, preserve denominators and never enable hosted training',async()=>{
 const agreement=await(await get('/api/disagreement/uci')).json();
 assert.equal(agreement.n,303);
 assert.equal(agreement.patterns.reduce((n,p)=>n+p.n,0),agreement.n);
 for(const row of agreement.pairs)for(const p of row){
  assert.equal(p.both_correct+p.both_wrong+p.only_a_correct+p.only_b_correct,agreement.n);
  assert.equal(p.disagree,p.only_a_correct+p.only_b_correct);
 }
 assert.equal(agreement.summary.disagreement_n,94);
 const lab=await(await get('/api/experiment-lab')).json();
 assert.equal(lab.runner.available,false);
 assert.deepEqual(lab.runner.available_datasets,[]);
 assert.equal(lab.runner.active_job,null);
 assert.deepEqual(new Set(lab.runs.map(r=>r.config.dataset+':'+r.config.algorithm)),new Set(['uci:logistic_regression','uci:random_forest','brfss:logistic_regression','brfss:random_forest']));
 for(const run of lab.runs){
  assert.equal(run.learning_curve.length,5);
  const full=run.learning_curve.find(p=>p.fraction===1);
  assert.deepEqual(full.validation,run.baseline);
  assert.ok(run.stress.some(p=>p.kind==='drop_feature'));
 }
 const temporal=await(await get('/api/temporal/brfss')).json();
 assert.deepEqual(temporal.cohorts.map(c=>c.n),[85748,85748,452464]);
 // No record-level inputs or trained estimator objects are exposed by the new endpoints.
 const check=value=>{if(!value||typeof value!=='object')return;for(const [key,child]of Object.entries(value)){
  assert.ok(!['row_id','row_ids','y_true','y_pred','probabilities','coef_','estimators_'].includes(key),key);check(child);
 }};
 [agreement,lab,temporal].forEach(check);
 for(const path of ['/data/disagreement.json','/data/temporal.json','/data/experiment-lab.json','/data/processed/brfss.pkl'])assert.equal((await get(path)).status,404);
});

test('hosted training rejects both same-origin and cross-origin mutations',async()=>{
 for(const path of ['/api/experiment-lab/runs','/api/experiment-lab/runs/fake/cancel']){
  const request=site=>new Request(origin+path,{method:'POST',headers:{Origin:site,'Content-Type':'application/json'},body:'{}'});
  assert.equal((await worker.fetch(request(origin),{})).status,405);
  assert.equal((await worker.fetch(request('https://unrelated.example'),{})).status,403);
 }
});
