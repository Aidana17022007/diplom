import models from '../data/models.json';
import reports from '../data/reports.json';
import evaluation from '../data/evaluation.json';
import transfer from '../data/transfer.json';
import disagreement from '../data/disagreement.json';
import experimentLab from '../data/experiment-lab.json';
import temporal from '../data/temporal.json';
import release from '../package.json';
import literatureAdditions from '../data/literature-additions.json';
import {withLiteratureAdditions} from './literature.js';
import assets from './generated/assets.js';
import fontBase64 from './generated/font.js';
import {ModelInputError, predictPayload, predictProbability, validateValues} from './inference.js';
import {buildPdf} from './pdf.js';
import {AuthError, authStatus, login, logout, requireSession} from './auth.js';
import {runScenarios,scenarioDemo,reproducibilityMetadata,SCENARIO_MAX_BYTES} from './scenarios.js';

const BATCH_BYTES=1024*1024, BATCH_ROWS=1000, MAX_ERRORS=50;
const secureHeaders={'X-Content-Type-Options':'nosniff','Referrer-Policy':'strict-origin-when-cross-origin'};
const encoder=new TextEncoder();
function json(data,status=200){return new Response(JSON.stringify(data),{status,headers:{...secureHeaders,'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'}});}
function fail(status,detail){throw new ModelInputError(status,detail);}
function dataset(ds){if(!['brfss','uci'].includes(ds))fail(400,'Неизвестный набор данных');return ds;}
function decode64(value){const raw=atob(value),bytes=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);return bytes;}
let fontBytes;
const demoCache=new Map();
const demoRows={brfss:[7,1,27,4,1,3,3,2,3,2,1],uci:[55,1,3,130,240,0,0,150,0,1,2,0,3]};
function csvCell(value){const s=value==null?'':String(value);return /[",\r\n]/.test(s)?'"'+s.replaceAll('"','""')+'"':s;}
function csvText(rows){return '\uFEFF'+rows.map(row=>row.map(csvCell).join(',')).join('\r\n')+'\r\n';}
function download(body,type,name){return new Response(body,{headers:{...secureHeaders,'Content-Type':type,'Content-Disposition':`attachment; filename="${name}"`,'Cache-Control':'no-store'}});}
async function readBody(request,max){
  const declared=Number(request.headers.get('content-length'));
  if(declared>max)fail(413,'Превышен допустимый размер запроса');
  if(!request.body)return '';
  const reader=request.body.getReader(),parts=[];let size=0;
  while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>max){await reader.cancel();fail(413,max===BATCH_BYTES?'Максимальный размер CSV — 1 МБ':'Максимальный размер JSON — 32 КБ');}parts.push(value);}
  const bytes=new Uint8Array(size);let offset=0;for(const part of parts){bytes.set(part,offset);offset+=part.length;}
  try{return new TextDecoder('utf-8',{fatal:true}).decode(bytes).replace(/^\uFEFF/,'');}catch{fail(422,'Нужен корректный текст UTF-8');}
}

/** CSV parser with quoted fields, physical line numbers and a bounded row count. */
export function parseCSV(text){
  const rows=[];let row=[],value='',quoted=false,closed=false,atStart=true,line=1,start=1;
  const field=()=>{row.push(value);value='';closed=false;atStart=true;};
  const record=()=>{field();if(row.length>1||row[0]!=='')rows.push({line:start,cells:row});row=[];if(rows.length>BATCH_ROWS+1)fail(422,'CSV должен содержать от 1 до 1000 строк');};
  for(let i=0;i<text.length;i++){
    const ch=text[i];
    if(quoted){if(ch==='"'){if(text[i+1]==='"'){value+='"';i++;}else{quoted=false;closed=true;}}else{value+=ch;if(ch==='\n')line++;}continue;}
    if(ch==='"'){if(!atStart)fail(422,'Некорректные кавычки CSV');quoted=true;atStart=false;continue;}
    if(ch===','){field();continue;}
    if(ch==='\r'||ch==='\n'){if(ch==='\r'&&text[i+1]==='\n')i++;record();line++;start=line;continue;}
    if(closed)fail(422,'Некорректный символ после кавычек CSV');
    value+=ch;atStart=false;
  }
  if(quoted)fail(422,'Незакрытые кавычки CSV');
  if(row.length||value!==''||closed)record();
  return rows;
}
function checkedBatch(ds,text){
  const parsed=parseCSV(text),header=parsed.shift()?.cells||[],expected=models.datasets[ds].features;
  if(header.length!==expected.length||new Set(header).size!==expected.length||header.some(name=>!expected.includes(name)))fail(422,'Названия столбцов должны совпадать с шаблоном');
  if(!parsed.length||parsed.length>BATCH_ROWS)fail(422,'CSV должен содержать от 1 до 1000 строк');
  const frames=[],errors=[];let invalid=0;
  for(const row of parsed){
    try{
      if(row.cells.length!==header.length)fail(422,{errors:[{field:'row',label:'Строка',message:'Число значений не соответствует заголовку CSV'}]});
      const values=Object.fromEntries(header.map((name,i)=>{
        const raw=row.cells[i].trim();
        // Decimal numeric text only: reject JS hexadecimal coercion and formulas.
        return [name,raw===''?null:/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(raw)?Number(raw):NaN];
      }));
      frames.push(validateValues(models,ds,values));
    }catch(error){if(!(error instanceof ModelInputError))throw error;invalid++;if(errors.length<MAX_ERRORS)errors.push({line:row.line,errors:typeof error.detail==='object'?error.detail.errors:[{field:'row',label:'Строка',message:error.detail}]});}
  }
  return {frames,validation:{rows:parsed.length,valid_rows:frames.length,invalid_rows:invalid,errors,errors_truncated:invalid>errors.length,max_rows:BATCH_ROWS,max_bytes:BATCH_BYTES}};
}
function metricsCSV(ds,experiment){
  if(!['benchmark','full'].includes(experiment))fail(422,'Выберите benchmark или full');
  const report=reports.research[ds],records=report[experiment];
  if(!records?.length)fail(404,'Такой эксперимент для набора данных отсутствует');
  const metricNames=['roc_auc','average_precision','accuracy','precision','recall','specificity','f1','brier'];
  const rows=[['dataset','experiment','model','evaluation','training_n','test_n','threshold','weighting',...metricNames,...metricNames.map(m=>m+'_fold_sd'),'procedure_seconds','procedure_definition','predict_seconds']];
  for(const row of records){
    const evaluation=ds==='uci'?'Mean of 6 outer CV folds; fold SD is not a confidence interval':experiment==='full'?'Locked independent test':'Fixed common benchmark test subset';
    const procedure=ds==='uci'?'Total outer CV procedure including search, prediction and scoring':experiment==='full'?'Full fit plus calibration and validation procedure':'Base CV plus randomized search and refit';
    rows.push([ds,experiment,row.name,evaluation,row.training_n,row.test_n??report.protocol?.test,row.threshold??.5,'unweighted',...metricNames.map(m=>row.metrics?.[m]),...metricNames.map(m=>row.std?.[m]),row.search_seconds??row.fit_seconds,procedure,row.predict_seconds]);
  }
  return download(csvText(rows),'text/csv; charset=utf-8',`${ds}_${experiment}_metrics.csv`);
}
function evaluationPayload(ds){
  return {...evaluation.datasets[ds],schema_version:evaluation.schema_version,created:evaluation.created,sources:evaluation.sources,methods:evaluation.methods};
}
function evaluationExport(ds,format){
  const payload=evaluationPayload(ds);
  if(format==='json')return download(JSON.stringify(payload,null,2),'application/json; charset=utf-8',`${ds}_evaluation.json`);
  if(format!=='csv')fail(422,'Выберите json или csv');
  const rows=[['dataset','model','evaluation','n','threshold','weighting','metric','value','ci_lower','ci_upper','interval_method']];
  for(const [metric,value] of Object.entries(payload.metrics)){
    const ci=payload.intervals?.[metric];
    rows.push([ds,payload.model,payload.evaluation,payload.n,payload.threshold,'unweighted',metric,value,ci?.[0],ci?.[1],ci?'Wilson 95%; fixed predictions; sampling/design limitations apply':'']);
  }
  rows.push([ds,payload.model,payload.evaluation,payload.n,payload.threshold,'unweighted','TN',payload.confusion[0][0]],
    [ds,payload.model,payload.evaluation,payload.n,payload.threshold,'unweighted','FP',payload.confusion[0][1]],
    [ds,payload.model,payload.evaluation,payload.n,payload.threshold,'unweighted','FN',payload.confusion[1][0]],
    [ds,payload.model,payload.evaluation,payload.n,payload.threshold,'unweighted','TP',payload.confusion[1][1]]);
  return download(csvText(rows),'text/csv; charset=utf-8',`${ds}_evaluation.csv`);
}
async function route(request,env){
  const url=new URL(request.url),pathname=url.pathname;
  if(request.method==='POST'){
    const origin=request.headers.get('origin');
    if(origin!==url.origin)fail(403,'Запрос должен исходить с этого сайта');
  }
  if(pathname.startsWith('/api/')){
    if(request.method==='POST'&&pathname.startsWith('/api/experiment-lab/'))fail(405,'Запуск обучения доступен только в локальной Python-версии проекта.');
    if(request.method==='GET'){
      if(pathname==='/api/auth/session')return authStatus(request,env);
      const scenarioMatch=pathname.match(/^\/api\/scenario-demo\/([^/]+)$/);
      if(scenarioMatch){
        if([...url.searchParams.keys()].some(key=>key!=='lang')||url.searchParams.getAll('lang').length>1)fail(422,'Демонстрация принимает только параметр lang');
        const ds=dataset(scenarioMatch[1]),lang=url.searchParams.get('lang')??'ru';
        return json(scenarioDemo(models,ds,lang));
      }
      const reproducibilityMatch=pathname.match(/^\/api\/reproducibility\/([^/]+)$/);
      if(reproducibilityMatch){
        const ds=dataset(reproducibilityMatch[1]);
        return download(JSON.stringify(reproducibilityMetadata(models,reports,ds),null,2),'application/json; charset=utf-8',`${ds}_reproducibility.json`);
      }
      const demoMatch=pathname.match(/^\/api\/demo\/([^/]+)$/);
      if(demoMatch){
        const ds=dataset(demoMatch[1]),lang=url.searchParams.get('lang')||'ru';
        if(!['ru','kk'].includes(lang))fail(422,'Неверный язык');
        const key=ds+':'+lang;
        if(!demoCache.has(key)){
          const values=Object.fromEntries(models.datasets[ds].features.map((f,i)=>[f,demoRows[ds][i]]));
          demoCache.set(key,{values,prediction:predictPayload(models,{dataset:ds,values,explain:true,lang}),synthetic:true});
        }
        return json(demoCache.get(key));
      }
      if(pathname==='/api/disagreement/uci')return json(disagreement);
      if(pathname==='/api/temporal/brfss')return json(temporal);
      if(pathname==='/api/experiment-lab')return json({...experimentLab,runner:{available:false,available_datasets:[],algorithms:['logistic_regression','random_forest'],active_job:null,recent_jobs:[],reason:'Обучение доступно в локальной Python-версии проекта.'}});
      if(pathname==='/api/health')return json({status:'ok',models:{brfss:!!models.datasets.brfss,uci:!!models.datasets.uci},runtime:'cloudflare-worker',version:release.version});
      const evaluationMatch=pathname.match(/^\/api\/(evaluation|evaluation-export)\/([^/]+)$/);
      if(evaluationMatch){
        const ds=dataset(evaluationMatch[2]);
        return evaluationMatch[1]==='evaluation'?json(evaluationPayload(ds)):evaluationExport(ds,url.searchParams.get('format')||'json');
      }
      if(pathname==='/api/transfer/uci')return json(transfer);
      if(pathname==='/api/transfer-export/uci')return download(JSON.stringify(transfer,null,2),'application/json; charset=utf-8','uci_transfer.json');
      if(pathname==='/api/library')return json(withLiteratureAdditions(reports.library,literatureAdditions));
      const fixed={'/api/environment':'environment','/api/reliability':'reliability','/api/experiments':'experiments','/api/quality':'quality'};
      if(fixed[pathname])return json(reports[fixed[pathname]]);
      let match=pathname.match(/^\/api\/(schema|research|data)\/([^/]+)$/);
      if(match)return json(reports[match[1]][dataset(match[2])]);
      match=pathname.match(/^\/api\/experiments\/([^/]+)$/);
      if(match){const detail=reports.experiment_details[match[1]];if(!detail)fail(404,'Эксперимент не найден');return json(detail);}
      match=pathname.match(/^\/api\/template\/([^/]+)$/);
      if(match){const ds=dataset(match[1]);return download(csvText([models.datasets[ds].features,ds==='brfss'?[7,1,27,4,1,3,3,2,3,2,1]:[55,1,3,130,240,0,0,150,0,1,2,0,3]]),'text/csv; charset=utf-8',`${ds}_example.csv`);}
      match=pathname.match(/^\/api\/research-export\/([^/]+)$/);
      if(match)return metricsCSV(dataset(match[1]),url.searchParams.get('experiment')||'benchmark');
    }
    if(request.method==='POST'){
      if(pathname==='/api/auth/login'){
        const text=await readBody(request,4096);let input;
        try{input=JSON.parse(text);}catch{fail(422,'Нужен корректный JSON');}
        return login(request,env,input);
      }
      if(pathname==='/api/auth/logout'){
        await readBody(request,4096);
        return logout(request,env);
      }
      if(pathname==='/api/predict'||pathname==='/api/report'||pathname==='/api/scenarios'||pathname.startsWith('/api/batch/'))await requireSession(request,env);
      if(pathname==='/api/scenarios'){
        const text=await readBody(request,SCENARIO_MAX_BYTES);let input;
        try{input=JSON.parse(text);}catch{fail(422,'Нужен корректный JSON');}
        return json(runScenarios(models,input));
      }
      if(pathname==='/api/predict'||pathname==='/api/report'){
        const text=await readBody(request,32768);let input;
        try{input=JSON.parse(text);}catch{fail(422,'Нужен корректный JSON');}
        const result=predictPayload(models,input);
        if(pathname==='/api/predict')return json(result);
        fontBytes??=decode64(fontBase64);
        const pdf=await buildPdf({dataset:result.dataset,values:input.values,lang:input.lang??'ru',result,schema:reports.schema[result.dataset],fontBytes});
        return download(pdf,'application/pdf',`CardioResearch_${result.dataset}_${input.lang??'ru'}.pdf`);
      }
      const match=pathname.match(/^\/api\/batch\/(validate\/)?([^/]+)$/);
      if(match){
        const ds=dataset(match[2]),{frames,validation}=checkedBatch(ds,await readBody(request,BATCH_BYTES));
        if(match[1])return json(validation);
        if(validation.invalid_rows)fail(422,{message:'Исправьте строки CSV перед прогнозом',...validation});
        const model=models.datasets[ds],rows=[[...model.features,'model_probability','decision_threshold','predicted_class','dataset','model_name','model_version']];
        for(const frame of frames){const p=predictProbability(models,ds,frame);rows.push([...model.features.map(f=>frame[f]),p,model.threshold,p>=model.threshold?1:0,ds,model.name,model.version]);}
        return download(csvText(rows),'text/csv; charset=utf-8',`${ds}_predictions.csv`);
      }
    }
    fail(404,'Маршрут API не найден');
  }
  if(request.method!=='GET'&&request.method!=='HEAD')fail(405,'Метод не поддерживается');
  // No filesystem fallback: private datasets, backgrounds and source never route.
  const key=pathname==='/'?'/index.html':pathname,asset=Object.hasOwn(assets,key)?assets[key]:null;
  if(!asset)return new Response('Not found',{status:404,headers:secureHeaders});
  return new Response(request.method==='HEAD'?null:decode64(asset.body),{headers:{...secureHeaders,'Content-Type':asset.type,'Cache-Control':key==='/index.html'?'no-cache':'public, max-age=31536000, immutable'}});
}
export default {async fetch(request,env={}){try{return await route(request,env);}catch(error){if(error instanceof ModelInputError||error instanceof AuthError)return json({detail:error.detail},error.status);return json({detail:'Ошибка обработки запроса. Повторите попытку.'},500);}}};
