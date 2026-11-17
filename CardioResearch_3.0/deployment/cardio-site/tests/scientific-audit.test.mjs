import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import worker from '../dist/server/index.js';

test('scientific audit exposes the saved aggregates without individual records',async()=>{
 const response=await worker.fetch(new Request('https://cardio.example/api/scientific-audit'),{});
 assert.equal(response.status,200);
 assert.equal(response.headers.get('Cache-Control'),'no-store');
 const report=await response.json();
 assert.deepEqual(report,JSON.parse(fs.readFileSync(new URL('../data/scientific-audit.json',import.meta.url))));
 assert.equal(report.production_model_replaced,false);
 assert.equal(report.scope,'saved_exploratory_diagnostics');
 assert.deepEqual(report.explanation.datasets.map(row=>row.profiles),[6,6]);
 assert.deepEqual(report.calibration.map(row=>row.n),[85748,85748]);
 const forbidden=['profiles_detail','row_ids','row_id','input_values','contributions','y_true','y_pred','probabilities','coef_','estimators_'];
 const check=value=>{if(!value||typeof value!=='object')return;for(const [key,child]of Object.entries(value)){assert.ok(!forbidden.includes(key),key);check(child)}};
 check(report);
 assert.equal((await worker.fetch(new Request('https://cardio.example/data/scientific-audit.json'),{})).status,404);
});
