import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile,readdir} from 'node:fs/promises';
import {build} from 'esbuild';
import ts from '../client/node_modules/typescript/lib/typescript.js';

const bundle=await build({entryPoints:['client/src/chart-runtime.ts'],bundle:true,format:'esm',write:false,external:['plotly.js-cartesian-dist-min']});
const {createChartRuntimeLoader,chartFileName}=await import('data:text/javascript;base64,'+Buffer.from(bundle.outputFiles[0].text).toString('base64'));

test('concurrent charts share one import and can retry a rejected import',async()=>{
  let calls=0,resolve;
  const runtime={react(){},purge(){},Plots:{resize(){}},downloadImage(){}};
  const load=createChartRuntimeLoader(()=>{calls++;return new Promise(done=>{resolve=done})});
  const first=load(),second=load();
  assert.equal(first,second);
  assert.equal(calls,1);
  resolve(runtime);
  assert.equal(await first,runtime);
  assert.equal(await load(),runtime);
  assert.equal(calls,1);

  let retries=0;
  const retry=createChartRuntimeLoader(()=>++retries===1?Promise.reject(Error('chunk unavailable')):Promise.resolve(runtime));
  await assert.rejects(retry(),/chunk unavailable/);
  assert.equal(await retry(),runtime);
  assert.equal(retries,2);
});

test('PNG filenames preserve readable Cyrillic context and remove path syntax',()=>{
  assert.equal(chartFileName('Ошибки выбранной модели'),'CardioResearch-Ошибки-выбранной-модели');
  assert.equal(chartFileName('Қателер: BRFSS / validation'),'CardioResearch-Қателер-BRFSS-validation');
  assert.equal(chartFileName('../../<script>"\\:*?|'),'CardioResearch-script');
  assert.equal(chartFileName('... / '),'CardioResearch-chart');
  assert.ok(chartFileName('a'.repeat(200)).length<100);
  assert.ok(!/[./\\:*?"<>|]/.test(chartFileName('../Диаграмма / ROC-AUC')));
});

test('every actual chart trace remains supported by the pinned cartesian distribution',async()=>{
  const directory=new URL('../client/src/',import.meta.url);
  const used=new Set();let errorBars=0;
  for(const name of await readdir(directory)){
    if(!name.endsWith('.tsx'))continue;
    const source=ts.createSourceFile(name,await readFile(new URL(name,directory),'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
    const visit=node=>{
      if(ts.isObjectLiteralExpression(node)){
        const props=new Map(node.properties.filter(ts.isPropertyAssignment).map(prop=>[prop.name.getText(source).replace(/['"]/g,''),prop.initializer]));
        if(['x','y','z','values'].some(key=>props.has(key))){
          const type=props.get('type');
          if(type&&ts.isStringLiteral(type))used.add(type.text);
          if(props.has('error_x')||props.has('error_y'))errorBars++;
        }
      }
      ts.forEachChild(node,visit);
    };
    visit(source);
  }
  // Official 3.7.0 dist README: basic would lose heatmap; cartesian retains these modules.
  const supported=new Set(['bar','box','contour','heatmap','histogram','histogram2d','histogram2dcontour','image','pie','scatter','scatterternary','violin']);
  assert.deepEqual([...used].filter(type=>!supported.has(type)),[]);
  for(const type of ['scatter','bar','pie','heatmap'])assert.ok(used.has(type),type);
  assert.ok(errorBars>=2,'asymmetric calibration/subgroup and importance error bars remain in use');
  const manifest=JSON.parse(await readFile(new URL('../client/package.json',import.meta.url),'utf8'));
  const installed=JSON.parse(await readFile(new URL('../client/node_modules/plotly.js-cartesian-dist-min/package.json',import.meta.url),'utf8'));
  assert.equal(manifest.dependencies['plotly.js-cartesian-dist-min'],'3.7.0');
  assert.equal(installed.version,'3.7.0');
  assert.equal(manifest.dependencies['plotly.js-dist-min'],undefined);
});
