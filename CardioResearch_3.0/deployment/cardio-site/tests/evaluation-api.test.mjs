import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import worker, {parseCSV} from '../dist/server/index.js';

const get=path=>worker.fetch(new Request('https://cardioresearch.example'+path),{});
const reports=JSON.parse(fs.readFileSync(new URL('../data/evaluation.json',import.meta.url)));
test('public diagnostics use fixed predictions and export exact metrics with their context',async()=>{
 for(const ds of ['brfss','uci']){
  const result=await(await get('/api/evaluation/'+ds)).json();
  assert.deepEqual(result.metrics,reports.datasets[ds].metrics);
  assert.equal(result.confusion.flat().reduce((a,b)=>a+b,0),result.n);
  const file=await get('/api/evaluation-export/'+ds);assert.equal(file.status,200);
  assert.match(file.headers.get('content-disposition'),/attachment.*evaluation.json/);
  assert.deepEqual(await file.json(),result);
  const csv=parseCSV(await(await get('/api/evaluation-export/'+ds+'?format=csv')).text());
  const header=csv.shift().cells;const column=name=>header.indexOf(name);
  const recall=csv.find(row=>row.cells[column('metric')]==='recall').cells;
  assert.equal(Number(recall[column('value')]),result.metrics.recall);
  assert.equal(Number(recall[column('ci_lower')]),result.intervals.recall[0]);
  assert.equal(recall[column('evaluation')],result.evaluation);
  assert.equal(recall[column('weighting')],'unweighted');
  assert.equal(Number(csv.find(row=>row.cells[column('metric')]==='TP').cells[column('value')]),result.confusion[1][1]);
  assert.equal((await get('/api/evaluation-export/'+ds+'?format=html')).status,422);
 }
 assert.equal((await get('/api/evaluation/unknown')).status,400);
});

test('transfer exposes aggregates for three unused centers and no record-level inputs',async()=>{
 const response=await get('/api/transfer/uci');assert.equal(response.status,200);
 const payload=await response.json();assert.equal(payload.cohorts.length,3);
 assert.equal(payload.cohorts.reduce((n,c)=>n+c.n,0),617);
 const text=JSON.stringify(payload);
 assert.ok(!text.includes('cleveland_0'));
 assert.ok(!text.includes('row_id'));
 for(const c of payload.cohorts){assert.ok(c.metrics.roc_auc>=0&&c.metrics.roc_auc<=1);assert.ok(c.n>c.positive);}
 assert.equal((await get('/data/transfer.json')).status,404);
 assert.equal((await get('/data/evaluation.json')).status,404);
});

test('benchmark CSV preserves UCI fold variability and health reports the actual release',async()=>{
 const text=await(await get('/api/research-export/uci')).text();
 const rows=parseCSV(text), header=rows.shift().cells;
 assert.ok(header.includes('roc_auc_fold_sd'));
 assert.ok(Number(rows[3].cells[header.indexOf('roc_auc_fold_sd')])>0);
 const release=JSON.parse(fs.readFileSync(new URL('../package.json',import.meta.url)));
 assert.equal((await(await get('/api/health')).json()).version,release.version);
});
