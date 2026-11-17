import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {build} from 'esbuild';
const bundle=await build({entryPoints:['client/src/dashboardData.ts'],bundle:true,format:'esm',write:false});
const {dashboardSummary,dashboardCalibration,dashboardMetric,dashboardUncertainty}=await import('data:text/javascript;base64,'+Buffer.from(bundle.outputFiles[0].text).toString('base64'));
const reports=JSON.parse(fs.readFileSync(new URL('../data/evaluation.json',import.meta.url))).datasets;

test('dashboard uses the actual BRFSS test and averaged UCI OOF counts without mixing protocols',()=>{
 for(const [ds,n,evaluation,expected] of [['brfss',85748,'locked_independent_test',[70294,8192,3578,3684]],['uci',303,'averaged_patient_oof',[141,23,29,110]]]){
  const record=reports[ds],result=dashboardSummary(record,ds);
  assert.equal(record.n,n);assert.equal(record.evaluation,evaluation);
  assert.deepEqual([result.tn,result.fp,result.fn,result.tp],expected);
  assert.equal(result.prevalence,record.positive/n);
  assert.equal(result.ap,record.metrics.average_precision);
  assert.ok(Math.abs(result.detectedShare-record.metrics.recall)<1e-12);
  assert.ok(Math.abs(result.detectedShare+result.missedShare-1)<1e-12);
  assert.ok(Math.abs(result.correctNegativeShare+result.falsePositiveShare-1)<1e-12);
 }
});
test('dashboard refuses stale datasets and inconsistent aggregate totals',()=>{
 assert.throws(()=>dashboardSummary(reports.uci,'brfss'),/dataset mismatch/);
 assert.throws(()=>dashboardSummary({...reports.uci,evaluation:'mean_outer_cv'},'uci'),/protocol mismatch/);
 assert.throws(()=>dashboardSummary({...reports.brfss,n:reports.brfss.n+1},'brfss'),/totals/);
 const record=structuredClone(reports.uci);record.calibration[1].n++;
 assert.throws(()=>dashboardSummary(record,'uci'),/Calibration counts/);
});

test('dashboard retains saved Wilson bounds and displays the correct conditional denominators',()=>{
 for(const [ds,denominators] of [['brfss',[7262,11876,78486,73872]],['uci',[139,133,164,170]]]){
  const record=reports[ds],estimates=dashboardUncertainty(record);
  assert.deepEqual(estimates.map(estimate=>estimate.denominator),denominators);
  assert.deepEqual(estimates.map(estimate=>estimate.key),['recall','precision','specificity','npv']);
  for(const estimate of estimates){
   assert.deepEqual(estimate.interval,record.intervals[estimate.key]);
   assert.equal(estimate.value,record.metrics[estimate.key]);
   assert.ok(estimate.interval[0]<=estimate.value&&estimate.value<=estimate.interval[1]);
  }
 }
});

test('uncertainty fails closed for inconsistent values or invalid interval bounds',()=>{
 const incorrectMetric=structuredClone(reports.brfss);incorrectMetric.metrics.precision=.99;
 assert.throws(()=>dashboardUncertainty(incorrectMetric),/metric disagrees/);
 for(const interval of [[.8,.2],[-.1,.8],[.2,1.1],[NaN,.8],[.1,.2],[.1],['0.4',.8]]){
  const invalid=structuredClone(reports.brfss);invalid.intervals.recall=interval;
  assert.throws(()=>dashboardUncertainty(invalid),/Invalid dashboard interval/);
 }
 const unavailable=structuredClone(reports.uci);delete unavailable.intervals;
 assert.ok(dashboardUncertainty(unavailable).every(estimate=>estimate.interval===null));
 const emptyClass={dataset:'edge',n:3,positive:0,negative:3,confusion:[[3,0],[0,0]],metrics:{},intervals:{recall:null,precision:null},calibration:[{n:3,lower:0,upper:1,mean_probability:0,observed_rate:0}]};
 const estimates=dashboardUncertainty(emptyClass);
 assert.equal(estimates[0].value,null);assert.equal(estimates[1].value,null);
 assert.equal(estimates[2].value,1);assert.ok(estimates.every(estimate=>estimate.interval===null));
});
test('empty classes and unavailable metrics stay undefined, not fabricated zero scores',()=>{
 const record={dataset:'edge',n:3,positive:0,negative:3,confusion:[[3,0],[0,0]],metrics:{average_precision:null},calibration:[{n:3,lower:0,upper:1,mean_probability:0,observed_rate:0}]};
 const result=dashboardSummary(record,'edge');
 assert.equal(result.detectedShare,null);assert.equal(result.missedShare,null);
 assert.equal(result.ap,null);assert.equal(result.apDifference,null);assert.equal(result.correctNegativeShare,1);
 for(const value of [null,undefined,NaN,Infinity,'0.9'])assert.equal(dashboardMetric(value),null);
 assert.equal(dashboardMetric(0),0);
});
test('calibration only plots observed finite bins and preserves their original coordinates',()=>{
 for(const ds of ['brfss','uci']){
  const bins=reports[ds].calibration,points=dashboardCalibration(bins);
  assert.equal(points.length,8);
  assert.equal(points.reduce((n,p)=>n+p.n,0),reports[ds].n);
  for(const point of points){assert.equal(point.x,bins[point.index].mean_probability);assert.equal(point.y,bins[point.index].observed_rate);}
 }
 assert.deepEqual(dashboardCalibration([{n:0,mean_probability:null,observed_rate:null},{n:2,mean_probability:NaN,observed_rate:.5},{n:1,mean_probability:.3,observed_rate:1.2}]),[]);
});
