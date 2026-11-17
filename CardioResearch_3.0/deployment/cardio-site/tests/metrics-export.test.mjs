import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import fs from 'node:fs';
import {build} from 'esbuild';
import {BASE_METRICS,METRICS,FIELDS,exportRows,metricsFromConfusion,metricsCSV} from '../src/metrics-export.js';

const reports=JSON.parse(fs.readFileSync(new URL('../data/reports.json',import.meta.url)));
const parse=text=>JSON.parse(execFileSync('python',['-X','utf8','-c','import csv,io,json,sys;print(json.dumps(list(csv.DictReader(io.StringIO(sys.stdin.read().lstrip("\\ufeff"))))))'],{input:text,encoding:'utf8'}));
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-12,`${a} != ${b}`);

test('derived metrics respect negative MCC, null denominators and fold-first aggregation',()=>{
 assert.equal(METRICS.length,13);assert.equal(BASE_METRICS.length,8);
 assert.deepEqual(metricsFromConfusion([[0,50],[50,0]]),{balanced_accuracy:0,mcc:-1,npv:0,fpr:1,fnr:1});
 for(const matrix of [null,[[0,0],[0,0]],[[true,1],[1,1]],[[-1,2],[1,2]]])assert.ok(Object.values(metricsFromConfusion(matrix)).every(value=>value===null));
 const source={benchmark:[{name:'Two folds',metrics:{roc_auc:.83},folds:[{confusion:[[9,1],[1,9]]},{confusion:[[20,80],[80,20]]}]}]};
 const before=structuredClone(source),row=exportRows(source,'uci','benchmark')[0];
 close(row.mcc,.1);close(row.mcc_fold_sd,Math.sqrt(.98));close(row.balanced_accuracy,.55);
 assert.equal(row.fold_count,2);assert.equal(row.derived_metrics_method,'mean_of_fold_metrics');assert.deepEqual(source,before);
 const missing=exportRows({benchmark:[{folds:[{confusion:[[5,0],[0,5]]},{confusion:[[0,5],[0,5]]}]}]},'uci','benchmark')[0];
 assert.equal(missing.mcc,null);assert.equal(missing.mcc_fold_sd,null);assert.equal(missing.npv,null);assert.equal(missing.balanced_accuracy,.75);
});

test('CSV neutralizes formula text while preserving numeric negatives, Unicode and absent metadata',()=>{
 const input={protocol:{test:85748},benchmark:[{name:' \t=HYPERLINK("bad")',metrics:{confusion:[[0,50],[50,0]]}},{name:'Модель, "екі"\nжол',metrics:{}}]};
 const csv=metricsCSV(input,'brfss','benchmark');assert.ok(csv.startsWith('\uFEFF'));assert.ok(csv.endsWith('\r\n'));
 const rows=parse(csv);assert.deepEqual(Object.keys(rows[0]),FIELDS);
 assert.equal(rows[0].model,'\' \t=HYPERLINK("bad")');assert.equal(Number(rows[0].mcc),-1);
 for(const key of ['training_n','test_n','threshold','fold_count'])assert.equal(rows[0][key],'');
 assert.equal(rows[0].threshold_source,'not_recorded_for_row');assert.equal(rows[1].model,'Модель, "екі"\nжол');
 assert.equal(rows[1].mcc,'');assert.equal(rows[1].mcc_fold_sd,'');
});

test('all real research CSVs agree with Python and frontend values and aggregation provenance',async()=>{
 const bundle=await build({entryPoints:['client/src/modelMetrics.ts'],bundle:true,format:'esm',write:false});
 const {enrichMetricsRows}=await import('data:text/javascript;base64,'+Buffer.from(bundle.outputFiles[0].text).toString('base64'));
 for(const [dataset,experiment,n]of [['brfss','benchmark',8],['brfss','full',2],['uci','benchmark',8]]){
  const report=reports.research[dataset];
  const python=JSON.parse(execFileSync('python',['-c','import sys,json;sys.path.insert(0,"../..");from cardio.metrics_export import export_rows;p=json.load(sys.stdin);print(json.dumps(export_rows(p["report"],p["dataset"],p["experiment"])))'],{input:JSON.stringify({report,dataset,experiment}),encoding:'utf8'}));
  const rows=exportRows(report,dataset,experiment);assert.equal(rows.length,n);
  const frontend=enrichMetricsRows(report[experiment],{dataset,experiment,evaluation:dataset==='uci'?'mean_outer_cv_6_folds':'held_out_test',weighting:'unweighted'});
  for(let i=0;i<rows.length;i++)for(const key of FIELDS){
   if(typeof rows[i][key]==='number')close(rows[i][key],python[i][key]);else assert.equal(rows[i][key],python[i][key],key);
  }
  for(let i=0;i<rows.length;i++)for(const key of METRICS){
   if(rows[i][key]===null)assert.ok(frontend[i].metrics[key]==null);else close(rows[i][key],frontend[i].metrics[key]);
   if(dataset==='uci'){if(rows[i][key+'_fold_sd']===null)assert.ok(frontend[i].std[key]==null);else close(rows[i][key+'_fold_sd'],frontend[i].std[key]);}
  }
 }
});

test('Worker route serves the complete CSV and retains endpoint validation',async()=>{
 const built=await build({entryPoints:['src/worker.js'],bundle:true,format:'esm',platform:'browser',write:false});
 const {default:worker}=await import('data:text/javascript;base64,'+Buffer.from(built.outputFiles[0].text).toString('base64'));
 for(const [dataset,experiment]of [['brfss','benchmark'],['brfss','full'],['uci','benchmark']]){
  const response=await worker.fetch(new Request(`https://cardio.example/api/research-export/${dataset}?experiment=${experiment}`),{});
  assert.equal(response.status,200);assert.equal(response.headers.get('Cache-Control'),'no-store');
  const bytes=Buffer.from(await response.arrayBuffer());assert.deepEqual([...bytes.subarray(0,3)],[239,187,191]);
  assert.equal(bytes.toString('utf8'),metricsCSV(reports.research[dataset],dataset,experiment));
 }
 assert.equal((await worker.fetch(new Request('https://cardio.example/api/research-export/uci?experiment=full'),{})).status,404);
 assert.equal((await worker.fetch(new Request('https://cardio.example/api/research-export/brfss?experiment=invalid'),{})).status,422);
});
