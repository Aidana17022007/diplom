import {ModelInputError,predictPayload} from './inference.js';

export const SCENARIO_MAX_BYTES=32768,SCENARIO_MAX_POINTS=9;
const notes={
  ru:'Это изменение оценки модели при подстановке одного показателя. Разность вероятностей не означает причинный эффект, результат лечения или изменение будущего риска заболевания.',
  kk:'Бір көрсеткішті өзгерткенде модель бағасының қалай өзгеретінін көрсетеді. Ықтималдықтар айырмасы себептік әсерді, емдеу нәтижесін немесе болашақтағы ауру қаупінің өзгеруін білдірмейді.',
};
const demos={
  brfss:{values:{age_group:7,sex:1,bmi:27,smoking:4,activity:1,diabetes:3,hypertension:3,cholesterol:2,general_health:3,physical_days:2,mental_days:1},vary:{feature:'bmi',values:[22,27,32,37]}},
  uci:{values:{age:55,sex:1,cp:3,trestbps:130,chol:240,fbs:0,restecg:0,thalach:150,exang:0,oldpeak:1,slope:2,ca:0,thal:3},vary:{feature:'oldpeak',values:[0,1,2,3]}},
};
const object=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
const fail=(status,message)=>{throw new ModelInputError(status,message);};

export function runScenarios(models,payload,{synthetic=false}={}) {
  if(!object(payload)||Object.keys(payload).some(key=>!['dataset','values','vary','lang'].includes(key)))fail(422,'Проверьте структуру запроса сценария');
  const dataset=payload.dataset===undefined?'brfss':payload.dataset,lang=payload.lang===undefined?'ru':payload.lang;
  if(typeof dataset!=='string'||typeof lang!=='string')fail(422,'Неверный тип набора данных или языка');
  if(!['brfss','uci'].includes(dataset)||!models.datasets[dataset])fail(400,'Неизвестный набор данных');
  if(!Object.hasOwn(notes,lang))fail(422,'Неверный язык');
  const {values,vary}=payload;
  if(!object(values)||!object(vary)||Object.keys(vary).length!==2||!Object.hasOwn(vary,'feature')||!Object.hasOwn(vary,'values'))fail(422,'Укажите values и vary с полями feature и values');
  const {feature,values:points}=vary,model=models.datasets[dataset];
  if(typeof feature!=='string'||!model.features.includes(feature))fail(422,'Неизвестный показатель сценария');
  if(!Array.isArray(points)||points.length<2||points.length>SCENARIO_MAX_POINTS)fail(422,'Нужно от 2 до 9 различных значений показателя');
  if(points.some(point=>typeof point!=='number'||!Number.isFinite(point)))fail(422,'Значения сценария должны быть конечными числами');
  if(new Set(points).size!==points.length)fail(422,'Значения сценария не должны повторяться');
  const baseline=predictPayload(models,{dataset,values,lang,explain:false});
  const normalized=Object.fromEntries(model.features.map(name=>[name,values[name]??null]));
  const results=points.map(value=>{
    const result=predictPayload(models,{dataset,values:{...normalized,[feature]:value},lang,explain:false});
    return {value,probability:result.probability,delta:result.probability-baseline.probability,positive:result.positive};
  });
  return {dataset,model:baseline.model,version:baseline.version,threshold:baseline.threshold,feature,
    baseline:{values:normalized,probability:baseline.probability,positive:baseline.positive,missing_fields:baseline.missing_fields},
    points:results,note:notes[lang],synthetic};
}

export function scenarioDemo(models,dataset,lang='ru') {
  if(!Object.hasOwn(demos,dataset))fail(400,'Неизвестный набор данных');
  return runScenarios(models,{dataset,lang,values:{...demos[dataset].values},vary:{feature:demos[dataset].vary.feature,values:[...demos[dataset].vary.values]}},{synthetic:true});
}

export function reproducibilityMetadata(models,reports,dataset) {
  const report=reports.research[dataset],model=models.datasets[dataset];
  if(!['brfss','uci'].includes(dataset)||!model||!report)fail(400,'Неизвестный набор данных');
  const pick=(value,keys)=>Object.fromEntries(keys.filter(key=>Object.hasOwn(value||{},key)).map(key=>[key,value[key]]));
  return {format_version:1,dataset,model:model.name,model_version:model.version,threshold:model.threshold,
    protocol:pick(report.protocol,['seed','primary_metric','benchmark_train','benchmark_test','fit','calibration','validation','test','cv','search_trials','full_candidates','selection','weighting','ci','feature_policy','outer','inner','selection_caveat']),
    selection:pick(report.selection,['benchmark_winner','deployed_model','threshold','calibration','locked_before_test','locked_at']),
    schema:reports.schema[dataset],environment:pick(reports.environment,['python','sklearn','pandas','numpy','lightgbm','seed','started'])};
}
