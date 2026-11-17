import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {build} from 'esbuild';
const bundle=await build({entryPoints:['client/src/comparisonExports.ts'],bundle:true,format:'esm',write:false});
const {modelViewKey,restoreModelView,comparisonCsv,comparisonSvg}=await import('data:text/javascript;base64,'+Buffer.from(bundle.outputFiles[0].text).toString('base64'));
const context={dataset:'brfss',experiment:'benchmark',evaluation:'held_out_test',weighting:'unweighted'};
const a={name:'A',threshold:.19042448230963954,training_n:12000,test_n:12000,metrics:{roc_auc:.8,brier:.2,recall:null}};
const b={name:'B',threshold:.5,training_n:12000,test_n:12000,metrics:{roc_auc:.9,brier:.1,recall:.5},std:{roc_auc:.02}};
test('saved views are isolated by dataset, protocol and exact metric snapshot',()=>{
  const key=modelViewKey([a,b],context);
  assert.equal(key,modelViewKey(structuredClone([a,b]),{...context}));
  assert.notEqual(key,modelViewKey([a,b],{...context,dataset:'uci'}));
  assert.notEqual(key,modelViewKey([a,b],{...context,weighting:'survey_weighted'}));
  assert.notEqual(key,modelViewKey([a,{...b,metrics:{...b.metrics,roc_auc:.9001}}],context));
});
test('malformed or stale saved controls cannot choose missing or more than two models',()=>{
  const view=restoreModelView({sort:'recall',direction:'anything',query:'RF',set:'core',showSD:false,chosen:['A','A','missing','B','C']},[a,b,{name:'C'}]);
  assert.deepEqual(view.chosen,['A','B']);assert.equal(view.direction,'desc');assert.equal(view.showSD,false);
  assert.equal(restoreModelView({sort:'precision',set:'core'},[a,b]).sort,'');
  assert.deepEqual(restoreModelView(null,[a,b]).chosen,[]);
});
test('CSV round-trips context, full precision, undefined metrics, fold SD and signed differences',()=>{
  const csv=comparisonCsv({...a,name:'=HYPERLINK("x")'},b,context);
  const records=JSON.parse(execFileSync('python',['-c','import csv,json,sys;print(json.dumps(list(csv.DictReader(sys.stdin))))'],{input:csv,encoding:'utf8'}));
  assert.equal(records[0].model,'\'=HYPERLINK("x")');assert.equal(records[0].threshold,String(a.threshold));
  assert.equal(records[0].recall,'');assert.equal(records[1].roc_auc_fold_sd,'0.02');
  assert.equal(records[1].evaluation_n,'12000');assert.equal(records[1].experiment,'benchmark');
  assert.ok(Math.abs(Number(records[1].delta_B_minus_A_roc_auc)-.1)<1e-12);
  assert.equal(records[1].delta_B_minus_A_brier,'-0.1');assert.equal(records[1].delta_B_minus_A_recall,'');
});
test('SVG is parseable, escapes labels and retains experiment sample and threshold context',()=>{
  const svg=comparisonSvg({...a,name:'A <script> & "quote"'},b,context,'ru');
  const parsed=JSON.parse(execFileSync('python',['-c','import xml.etree.ElementTree as E,json,sys;r=E.fromstring(sys.stdin.buffer.read().decode("utf-8"));print(json.dumps({"text":" ".join(r.itertext()),"scripts":len(r.findall(".//{http://www.w3.org/2000/svg}script"))}))'],{input:svg,encoding:'utf8'}));
  assert.equal(parsed.scripts,0);assert.ok(parsed.text.includes('benchmark'));assert.ok(parsed.text.includes('12000 / 12000'));
  assert.ok(parsed.text.includes(String(a.threshold)));assert.ok(parsed.text.includes('A <script> & "quote"'));
  assert.ok(comparisonSvg(a,b).includes('взвешивание не указано'));
});
