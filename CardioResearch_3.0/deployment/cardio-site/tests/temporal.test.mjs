import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const report=JSON.parse(fs.readFileSync(new URL('../data/temporal.json',import.meta.url),'utf8'));
const evaluation=JSON.parse(fs.readFileSync(new URL('../data/evaluation.json',import.meta.url),'utf8')).datasets.brfss;
const close=(actual,expected)=>assert.ok(Math.abs(actual-expected)<1e-12,`${actual} != ${expected}`);

test('cross-year baseline reproduces the frozen held-out evaluation and mask keeps the same cohort',()=>{
 const [base,masked,transfer]=report.cohorts;
 assert.deepEqual(report.cohorts.map(c=>c.id),['test_2023','masked_2023','transfer_2024']);
 assert.equal(base.n,evaluation.n);assert.deepEqual(base.confusion,evaluation.confusion);
 for(const metric of ['average_precision','roc_auc','recall','precision','specificity','f1','accuracy','brier'])close(base.metrics[metric],evaluation.metrics[metric]);
 for(const key of ['n','positive','negative','threshold'])assert.equal(masked[key],base[key]);
 assert.equal(transfer.n+report.schema.unknown_target_removed,report.schema.source_raw_rows);
 assert.equal(report.schema.target_mismatches,0);
});

test('each temporal cohort has internally consistent class, confusion, calibration and missingness counts',()=>{
 for(const cohort of report.cohorts){
  const [[tn,fp],[fn,tp]]=cohort.confusion;
  assert.equal(tn+fp,cohort.negative);assert.equal(fn+tp,cohort.positive);assert.equal(tn+fp+fn+tp,cohort.n);
  close(cohort.metrics.recall,tp/(tp+fn));close(cohort.metrics.precision,tp/(tp+fp));close(cohort.metrics.specificity,tn/(tn+fp));
  close(cohort.metrics.accuracy,(tp+tn)/cohort.n);close(cohort.metrics.f1,2*tp/(2*tp+fp+fn));
  assert.equal(cohort.calibration.reduce((sum,b)=>sum+b.n,0),cohort.n);
  for(const [feature,n] of Object.entries(cohort.feature_missingness)){assert.ok(Number.isInteger(n)&&n>=0&&n<=cohort.n,feature);}
  if(cohort.id!=='test_2023')for(const feature of ['hypertension','cholesterol'])assert.equal(cohort.feature_missingness[feature],cohort.n);
  assert.equal(cohort.weighting,'unweighted');assert.equal(cohort.threshold,report.threshold);
 }
});

test('transfer preserves the frozen model protocol and explicitly declares absent source predictors',()=>{
 assert.deepEqual(new Set(report.schema.absent),new Set(['BPHIGH6','TOLDHI3']));
 assert.equal(report.schema.present.length,9);assert.equal(report.schema.required.length,11);
 assert.equal(report.provenance.refit,false);assert.equal(report.provenance.recalibration,false);assert.equal(report.provenance.threshold_retuning,false);
 assert.equal(report.provenance.frozen_files_unchanged,true);
 for(const hash of ['model_sha256','source_sha256','codebook_sha256'])assert.match(report.provenance[hash],/^[a-f0-9]{64}$/);
 assert.ok(report.limitations.ru.length>=4&&report.limitations.kk.length>=4);
 assert.ok(!JSON.stringify(report).includes('row_id'),'aggregate report must not contain row identifiers');
});
