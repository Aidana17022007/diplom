import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {build} from 'esbuild';

const compile=async file=>{const result=await build({entryPoints:[file],bundle:true,format:'esm',write:false});return import('data:text/javascript;base64,'+Buffer.from(result.outputFiles[0].text).toString('base64'))};
const {evaluateThresholdCosts,thresholdCostsCsv,DEFAULT_COST_ASSUMPTIONS}=await compile('client/src/thresholdCostModel.ts');
const {thresholdPoint,buildThresholdLab}=await compile('client/src/thresholdComparison.ts');
const reports=JSON.parse(await readFile(new URL('../data/reports.json',import.meta.url),'utf8'));
const point=(threshold,matrix,source='grid')=>thresholdPoint(threshold,matrix,source);
const reference=point(.5,[[84,6],[4,6]],'working');
const options=(extra={})=>({...DEFAULT_COST_ASSUMPTIONS,...extra});
const low=point(.2,[[70,20],[1,9]]), high=point(.8,[[88,2],[8,2]]);
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-10,`${a} != ${b}`);

test('real study uses only saved validation counts including the exact working threshold, without mutations',()=>{
 const research=reports.research.brfss,before=JSON.stringify(research);
 const {points,baseline}=buildThresholdLab(research), inputs=JSON.stringify([points,baseline]);
 const result=evaluateThresholdCosts(points,baseline,options());
 assert.equal(result.status,'ok');assert.equal(result.rows.length,36);
 assert.equal(result.baseline.point.n,51449);assert.equal(result.baseline.point.threshold,.19042448230963954);
 assert.equal(result.rows.filter(row=>row.point.source==='working').length,1);
 for(const row of result.rows){
  assert.equal(row.point.n,51449);assert.equal(row.point.positive,4358);
  close(row.lossPer1000,(row.point.counts.fp+5*row.point.counts.fn)/51449*1000);
  close(row.positiveFraction,(row.point.counts.tp+row.point.counts.fp)/51449);
 }
 assert.equal(result.selected.weightedErrors,Math.min(...result.rows.map(row=>row.weightedErrors)));
 assert.equal(JSON.stringify(research),before);assert.equal(JSON.stringify([points,baseline]),inputs);
});

test('relative FN penalty changes the measured minimum and the exact working point wins a tie',()=>{
 const inputs=[high,low,reference];
 const equal=evaluateThresholdCosts(inputs,reference,options({falseNegativeWeight:1}));
 assert.equal(equal.selected.point.threshold,.5);assert.deepEqual(equal.ties,[.5,.8]);
 const weighted=evaluateThresholdCosts(inputs,reference,options());
 assert.equal(weighted.selected.point.threshold,.2);assert.equal(weighted.selected.weightedErrors,25);
 close(weighted.selected.lossPer1000,250);
 const nonWorkingTie=point(.3,low.confusion);
 const tied=evaluateThresholdCosts([nonWorkingTie,high,low],reference,options());
 assert.deepEqual(tied.ties,[.2,.3]);assert.equal(tied.selected.point.threshold,.2);
 assert.deepEqual(tied.rows.map(row=>row.point.threshold),[.2,.3,.5,.8]);
});

test('recall and predicted-positive constraints filter full-precision counts and can yield no feasible point',()=>{
 const constrained=evaluateThresholdCosts([low,high],reference,options({minRecall:.6,maxPositiveFraction:.12}));
 assert.equal(constrained.feasibleCount,1);assert.equal(constrained.selected.point.threshold,.5);
 const none=evaluateThresholdCosts([low,high],reference,options({minRecall:.9,maxPositiveFraction:.12}));
 assert.equal(none.status,'ok');assert.equal(none.selected,null);assert.equal(none.feasibleCount,0);assert.deepEqual(none.ties,[]);
 assert.ok(none.baseline);assert.equal(none.baseline.feasible,false);
 const below=evaluateThresholdCosts([low,high],reference,options({minRecall:.6000001,maxPositiveFraction:.12}));
 assert.equal(below.selected,null);
});

test('undefined ratios remain unavailable and a disabled recall constraint is explicit',()=>{
 const negative=point(.5,[[100,0],[0,0]],'working');
 const free=evaluateThresholdCosts([negative],negative,options());
 assert.equal(free.status,'ok');assert.equal(free.selected.point.metrics.recall,null);
 assert.equal(free.selected.point.metrics.precision,null);assert.equal(free.selected.lossPer1000,0);
 const constrained=evaluateThresholdCosts([negative],negative,options({minRecall:.01}));
 assert.equal(constrained.selected,null);assert.equal(constrained.feasibleCount,0);
 assert.equal(evaluateThresholdCosts([],negative,options()).status,'unavailable');
 assert.equal(evaluateThresholdCosts([negative],null,options()).status,'unavailable');
});

test('invalid assumptions, mixed cohorts and contradictory duplicate counts do not produce an optimum',()=>{
 for(const settings of [{falseNegativeWeight:0},{falseNegativeWeight:21},{falseNegativeWeight:1.5},{falseNegativeWeight:NaN},{minRecall:-.1},{minRecall:1.1},{maxPositiveFraction:Infinity},{maxPositiveFraction:-.1}]){
  const result=evaluateThresholdCosts([reference],reference,options(settings));
  assert.equal(result.status,'invalid_assumptions');assert.equal(result.selected,null);
 }
 const different=point(.8,[[89,2],[8,1]]);
 assert.equal(evaluateThresholdCosts([different],reference,options()).status,'unavailable');
 const contradictory=point(.2,[[88,2],[8,2]]);
 assert.equal(evaluateThresholdCosts([low,contradictory],reference,options()).status,'unavailable');
 const forged={...low,counts:{tn:0,fp:0,fn:0,tp:0},metrics:{recall:1},n:1};
 const result=evaluateThresholdCosts([forged],reference,options());
 assert.equal(result.rows[0].point.n,100);assert.equal(result.rows[0].weightedErrors,25);
 const falseWorking={...low,source:'working'};
 assert.equal(evaluateThresholdCosts([falseWorking],reference,options()).rows.filter(row=>row.point.source==='working').length,1);
});

test('CSV retains every point, assumptions, nulls, no-feasible outcome and inert metadata',()=>{
 const result=evaluateThresholdCosts([low,high],reference,options({minRecall:.9,maxPositiveFraction:.12}));
 const csv=thresholdCostsCsv(result,'=HYPERLINK("x")');
 const [header,...lines]=csv.trimEnd().split('\r\n');
 assert.equal(lines.length,3);assert.match(header,/selected_threshold,feasible_points,minimum_tie_count/);
 assert.ok(lines.every(line=>line.includes('validation,unweighted,probability >= threshold,exploratory_hypothetical_penalty,1,5,0.9,true,0.12,0.5,,0,0,')));
 assert.ok(lines.every(line=>line.includes('"\'=HYPERLINK(""x"")"')));
 assert.ok(header.includes('penalty_delta_from_working_per_1000'));
 assert.ok(header.includes('working_reference'));assert.ok(header.includes('recall_constraint_enabled'));
 const negative=point(.5,[[100,0],[0,0]],'working');
 const undefinedCsv=thresholdCostsCsv(evaluateThresholdCosts([negative],negative,options()),'LR');
 assert.match(undefinedCsv,/100,0,100,100,0,0,0,,,0,0,0,0/);
 assert.equal(thresholdCostsCsv(evaluateThresholdCosts([],null,options()),'LR'),'');
});

test('a grid point conflicting with the exact working threshold is rejected rather than overwritten',()=>{
 const conflict=point(reference.threshold,[[85,5],[3,7]]);
 const rejected=evaluateThresholdCosts([low,conflict,high],reference,options());
 assert.equal(rejected.status,'unavailable');assert.equal(rejected.selected,null);assert.equal(rejected.baseline,null);
 assert.deepEqual(rejected.rows,[]);
 const matching=point(reference.threshold,reference.confusion);
 const accepted=evaluateThresholdCosts([low,matching,high],reference,options());
 assert.equal(accepted.status,'ok');assert.equal(accepted.rows.length,3);
 assert.deepEqual(accepted.baseline.point.confusion,reference.confusion);
 assert.equal(accepted.rows.filter(row=>row.point.source==='working').length,1);
});
