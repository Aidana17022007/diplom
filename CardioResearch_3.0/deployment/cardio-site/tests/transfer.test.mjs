import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {transferMetrics,parseTransferRows,evaluateTransfer} from '../scripts/evaluate-transfer.mjs';

test('transfer metrics handle tied scores, ranking, confusion and absent classes',()=>{
  const perfect=transferMetrics([0,0,1,1],[0.1,0.2,0.8,0.9]);
  assert.equal(perfect.roc_auc,1);assert.equal(perfect.average_precision,1);
  assert.equal(perfect.balanced_accuracy,1);assert.equal(perfect.mcc,1);
  assert.deepEqual(perfect.confusion,[[2,0],[0,2]]);
  const tied=transferMetrics([0,1,0,1],[0.5,0.5,0.5,0.5]);
  assert.equal(tied.roc_auc,0.5);assert.equal(tied.average_precision,0.5);
  assert.equal(tied.brier,0.25);assert.deepEqual(tied.confusion,[[0,2],[0,2]]);
  const mixed=transferMetrics([1,0,1,0],[0.9,0.9,0.5,0.1]);
  assert.equal(mixed.roc_auc,0.625);assert.ok(Math.abs(mixed.average_precision-7/12)<1e-14);
  const noPositive=transferMetrics([0,0],[0.1,0.2]);
  assert.equal(noPositive.roc_auc,null);assert.equal(noPositive.average_precision,null);assert.equal(noPositive.recall,null);
  assert.throws(()=>transferMetrics([1],[NaN]));assert.throws(()=>transferMetrics([],[]));
});

test('source parser preserves zero, missing fields, feature order and binary severity mapping',()=>{
  const raw={center:'VA',severity:'2',age:'60',sex:'1',cp:'4',trestbps:'0',chol:'0',fbs:'?',restecg:'0',thalach:'',exang:'1',oldpeak:'-0.5',slope:'2',ca:'',thal:''};
  const [row]=parseTransferRows([raw]);
  assert.equal(row.target,1);assert.equal(row.values.chol,0);assert.equal(row.values.fbs,null);
  assert.equal(row.values.oldpeak,-0.5);assert.equal(row.values.thalach,null);
  assert.throws(()=>parseTransferRows([{...raw,severity:'-1'}]));
  assert.throws(()=>parseTransferRows([{...raw,age:'oops'}]));
});

test('published transfer report is aggregate-only and bound to the frozen artifact',()=>{
  const modelBytes=readFileSync(new URL('../data/models.json',import.meta.url));
  const models=JSON.parse(modelBytes);
  const report=JSON.parse(readFileSync(new URL('../data/transfer.json',import.meta.url)));
  assert.equal(report.provenance.model_file_sha256,createHash('sha256').update(modelBytes).digest('hex'));
  assert.equal(report.model.version,models.datasets.uci.version);assert.equal(report.protocol.selection_changed,false);
  assert.equal(report.protocol.fit_performed,false);assert.equal(report.model.threshold,0.5);
  assert.deepEqual(report.cohorts.map(row=>[row.center,row.n,row.positive]),[['Hungary',294,106],['Switzerland',123,115],['VA',200,149]]);
  assert.equal(report.cohorts.reduce((sum,row)=>sum+row.n,0),617);
  assert.equal(report.cohorts[1].quality.zero_values.chol,123);
  for(const cohort of report.cohorts){
    assert.equal(cohort.metrics.confusion.flat().reduce((a,b)=>a+b,0),cohort.n);
    assert.equal(cohort.eligible_subset.n+cohort.eligible_subset.excluded,cohort.n);
    assert.equal(cohort.quality.exact_matches_to_cleveland,0);
    assert.equal('rows' in cohort,false);assert.equal('predictions' in cohort,false);
    assert.equal(Object.keys(cohort.missingness).length,13);
  }
  assert.throws(()=>evaluateTransfer([],models));
  assert.throws(()=>evaluateTransfer([],{datasets:{uci:{...models.datasets.uci,threshold:0.4}}}));
});
