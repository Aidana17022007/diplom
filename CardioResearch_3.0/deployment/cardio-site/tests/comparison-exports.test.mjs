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
  assert.equal(restoreModelView({sort:'fnr',set:'classification',direction:'asc'},[a,b]).sort,'fnr');
});
test('CSV exports derived fold metrics with provenance and never substitutes pooled counts',()=>{
  const cv={...context,dataset:'uci',evaluation:'mean_outer_cv_6_folds'};
  const first={name:'Fold average',folds:[{confusion:[[9,1],[1,9]]},{confusion:[[20,80],[80,20]]}],metrics:{confusion:[[29,81],[81,29]]}};
  const second={name:'Undefined fold',folds:[{confusion:[[9,1],[1,9]]},{confusion:[[0,4],[0,6]]}]};
  const records=JSON.parse(execFileSync('python',['-c','import csv,json,sys;print(json.dumps(list(csv.DictReader(sys.stdin))))'],{input:comparisonCsv(first,second,cv),encoding:'utf8'}));
  assert.equal(records[0].derived_metric_method,'mean_of_fold_metrics');
  assert.equal(records[0].derived_metric_folds,'2');
  assert.equal(records[0].derived_metric_sd,'sample_ddof_1');
  assert.ok(Math.abs(Number(records[0].balanced_accuracy)-.55)<1e-12);
  assert.ok(Math.abs(Number(records[0].mcc)-.1)<1e-12);
  assert.ok(Math.abs(Number(records[0].mcc_fold_sd)-Math.sqrt(.98))<1e-12);
  assert.equal(records[1].mcc,'');assert.equal(records[1].mcc_fold_sd,'');
  assert.equal(records[1].npv,'');assert.equal(records[1].delta_B_minus_A_mcc,'');
  assert.equal(records[0].evaluation,'mean_outer_cv_6_folds');
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
test('SVG fits all 13 metrics and draws negative MCC to the left of zero with correct direction labels',()=>{
  const svg=comparisonSvg({name:'Inverse',metrics:{confusion:[[0,50],[50,0]]}},{name:'Perfect',metrics:{confusion:[[50,0],[0,50]]}},context);
  const parsed=JSON.parse(execFileSync('python',['-c',[
    'import xml.etree.ElementTree as E,json,sys',
    'r=E.fromstring(sys.stdin.buffer.read().decode("utf-8")); ns={"s":"http://www.w3.org/2000/svg"}',
    'texts=r.findall(".//s:text",ns)',
    'mcc=next(g for g in r.findall(".//s:g",ns) if (g.find("s:text",ns) is not None and (g.find("s:text",ns).text or "").startswith("MCC")))',
    'print(json.dumps({"height":float(r.attrib["height"]),"maxTextY":max(float(t.attrib["y"]) for t in texts),"labels":[t.text for t in texts],"mccRects":[x.attrib for x in mcc.findall("s:rect",ns)],"zeroLines":[x.attrib for x in mcc.findall("s:line",ns)]}))',
  ].join('\n')],{input:svg,encoding:'utf8'}));
  assert.ok(parsed.height>1300);assert.ok(parsed.maxTextY+20<parsed.height);
  for(const label of ['Balanced accuracy ↑','MCC ↑ [−1…1]','NPV ↑','FPR ↓','FNR ↓','Brier score ↓'])assert.ok(parsed.labels.includes(label),label);
  const bars=parsed.mccRects.filter(rect=>['#288d74','#628ab5'].includes(rect.fill));
  assert.equal(bars.length,2);
  assert.equal(Number(bars[0].x),270);assert.equal(Number(bars[0].width),180);
  assert.equal(Number(bars[1].x),450);assert.equal(Number(bars[1].width),180);
  assert.equal(parsed.zeroLines.filter(line=>line.x1==='450'&&line.x2==='450').length,2);
});
