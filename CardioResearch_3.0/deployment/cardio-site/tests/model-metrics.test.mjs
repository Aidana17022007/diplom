import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
const bundle=await build({entryPoints:['client/src/modelMetrics.ts'],bundle:true,format:'esm',write:false});
const {sortedModels,compareModels,interpretMetricDelta,metricsFromConfusion,enrichMetricsRows,metricLabels,metricDefinitions}=await import('data:text/javascript;base64,'+Buffer.from(bundle.outputFiles[0].text).toString('base64'));
test('sorting keeps unavailable scores last in both directions and leaves rows unchanged',()=>{
  const rows=[{name:'missing',metrics:{brier:null}},{name:'A',metrics:{brier:.2}},{name:'B',metrics:{brier:.1}},{name:'invalid',metrics:{brier:NaN}}];
  assert.deepEqual(sortedModels(rows,'brier','asc').map(x=>x.name),['B','A','missing','invalid']);
  assert.deepEqual(sortedModels(rows,'brier','desc').map(x=>x.name),['A','B','missing','invalid']);
  assert.deepEqual(rows.map(x=>x.name),['missing','A','B','invalid']);
});

test('metric directions and percentage-point units never mistake a lower error for deterioration',()=>{
  assert.equal(Object.keys(metricLabels).length,13);
  assert.deepEqual(Object.keys(metricDefinitions),Object.keys(metricLabels));
  for(const key of ['brier','fpr','fnr']){
    assert.equal(interpretMetricDelta(key,-.1).numericPreference,'B');
    assert.equal(interpretMetricDelta(key,.1).numericPreference,'A');
  }
  assert.equal(interpretMetricDelta('recall',.03).percentagePoints,3);
  assert.equal(interpretMetricDelta('recall',.03).numericPreference,'B');
  assert.equal(interpretMetricDelta('average_precision',.03).percentagePoints,null);
  assert.equal(interpretMetricDelta('mcc',0).numericPreference,'equal');
  assert.equal(interpretMetricDelta('mcc',null).numericPreference,'unavailable');
  assert.equal(interpretMetricDelta('future_metric',.2).numericPreference,'unknown');
});

test('additional metrics use exact confusion counts and correctly retain negative MCC',()=>{
  const result=metricsFromConfusion([[40,10],[20,30]]);
  assert.equal(result.balanced_accuracy,.7);
  assert.ok(Math.abs(result.mcc-1/Math.sqrt(6))<1e-12);
  assert.equal(result.npv,2/3);assert.equal(result.fpr,.2);assert.equal(result.fnr,.4);
  assert.deepEqual(metricsFromConfusion([[0,50],[50,0]]),{balanced_accuracy:0,mcc:-1,npv:0,fpr:1,fnr:1});
});

test('missing, impossible and zero-denominator counts stay unavailable, not synthetic zero metrics',()=>{
  for(const matrix of [null,undefined,[[1,2,3],[4,5]],[[1,-1],[0,1]],[[Infinity,1],[1,1]],[[true,1],[0,1]],[[0,0],[0,0]]]){
    assert.ok(Object.values(metricsFromConfusion(matrix)).every(value=>value===null));
  }
  assert.deepEqual(metricsFromConfusion([[7,0],[0,0]]),{balanced_accuracy:null,mcc:null,npv:1,fpr:0,fnr:null});
});

test('outer CV enriches each fold first and uses equal fold means plus sample SD, never pooled or OOF counts',()=>{
  const input={name:'two unequal folds',metrics:{average_precision:.8,confusion:[[100,0],[0,100]]},folds:[{confusion:[[9,1],[1,9]]},{confusion:[[20,80],[80,20]]}]};
  const result=enrichMetricsRows([input],{dataset:'uci',experiment:'benchmark',evaluation:'mean_outer_cv_6_folds',weighting:'unweighted'})[0];
  assert.ok(Math.abs(result.metrics.mcc-.1)<1e-12);
  assert.ok(Math.abs(result.std.mcc-Math.sqrt(.98))<1e-12);
  assert.equal(result.metrics.balanced_accuracy,.55);
  assert.ok(Math.abs(result.std.balanced_accuracy-Math.sqrt(.245))<1e-12);
  assert.equal(result.metrics.average_precision,.8);
  assert.deepEqual(result.derived_metrics,{method:'mean_of_fold_metrics',folds:2,sd:'sample_ddof_1',undefined_metrics:[]});
  assert.equal(input.metrics.mcc,undefined);assert.equal(input.std,undefined);
  assert.notEqual(result.metrics.mcc,metricsFromConfusion([[29,81],[81,29]]).mcc);
});

test('undefined fold values invalidate the metric mean and SD without excluding that fold',()=>{
  const result=enrichMetricsRows([{name:'mixed',folds:[{confusion:[[5,0],[0,5]]},{confusion:[[0,5],[0,5]]}]}])[0];
  assert.equal(result.metrics.mcc,null);assert.equal(result.std.mcc,null);
  assert.equal(result.metrics.npv,null);assert.equal(result.std.npv,null);
  assert.equal(result.metrics.balanced_accuracy,.75);
  const missing=enrichMetricsRows([{name:'missing folds',metrics:{confusion:[[9,1],[1,9]]}}],{dataset:'uci',experiment:'benchmark',evaluation:'mean_outer_cv_6_folds',weighting:'unweighted'})[0];
  assert.equal(missing.metrics.balanced_accuracy,null);
  assert.equal(missing.derived_metrics.method,'unavailable');
});

test('single-evaluation enrichment retains source weighting, existing scores and no invented fold SD',()=>{
  const source={name:'weighted',metrics:{roc_auc:.82,confusion:[[4.5,.5],[1.5,3.5]]}};
  const result=enrichMetricsRows([source])[0];
  assert.equal(result.metrics.balanced_accuracy,.8);assert.equal(result.metrics.roc_auc,.82);
  assert.equal(result.derived_metrics.method,'confusion_counts');assert.equal(result.derived_metrics.sd,null);
  assert.equal(result.std.mcc,null);assert.equal(source.metrics.mcc,undefined);
});
test('comparison uses signed absolute differences and preserves undefined scores',()=>{
  const result=compareModels({name:'A',metrics:{roc_auc:.8,brier:.2,recall:null}},{name:'B',metrics:{roc_auc:.9,brier:.1,recall:.5}},['roc_auc','brier','recall','precision']);
  assert.ok(Math.abs(result[0].delta-.1)<1e-12);
  assert.equal(result[1].delta,-.1);
  assert.equal(result[2].delta,null);assert.equal(result[2].first,null);
  assert.deepEqual(result[3],{key:'precision',first:null,second:null,delta:null});
});
