import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import worker from '../dist/server/index.js';

for (const [name, scope] of [['metrics-insights','frozen_prediction_analysis'],['development-study','exploratory_train_only']]) {
 test(`${name} exposes saved aggregates without observation-level data`, async () => {
  const response = await worker.fetch(new Request(`https://cardio.example/api/${name}`), {});
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('Cache-Control'), 'no-store');
  const data = await response.json();
  assert.deepEqual(data, JSON.parse(fs.readFileSync(new URL(`../data/${name}.json`, import.meta.url))));
  assert.equal(data.scope, scope);
  assert.equal(data.inputs_unchanged, true);
  const forbidden = ['row_id','row_ids','sample_ids','target','targets','y_true','probabilities','input_values','coef_','estimators_'];
  const check = value => {if(!value || typeof value !== 'object')return; for(const [key,child] of Object.entries(value)){assert.ok(!forbidden.includes(key),key);check(child)}};
  check(data);
  assert.equal((await worker.fetch(new Request(`https://cardio.example/data/${name}.json`),{})).status,404);
 });
}
