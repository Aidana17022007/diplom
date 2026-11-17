import {compareModels,ComparisonContext,enrichMetricsRows,finiteMetric,metricDefinitions,metricLabels,ModelRow} from './modelMetrics';
export type ModelView={sort:string;direction:'asc'|'desc';query:string;set:string;showSD:boolean;chosen:string[]};
export const defaultModelView:ModelView={sort:'',direction:'desc',query:'',set:'core',showSD:true,chosen:[]};
export function modelViewKey(rows:ModelRow[],context?:ComparisonContext){
  const source=JSON.stringify([context,rows.map(r=>[r.name,r.threshold,r.metrics,r.std,r.test_n,r.training_n])]);
  let hash=2166136261;for(let i=0;i<source.length;i++){hash^=source.charCodeAt(i);hash=Math.imul(hash,16777619);}
  return 'cardio-model-view-v1:'+JSON.stringify(context||{})+':'+(hash>>>0).toString(16);
}
export function restoreModelView(raw:unknown,rows:ModelRow[]):ModelView{
  const defaults={...defaultModelView,chosen:[]};
  if(!raw||typeof raw!=='object'||Array.isArray(raw))return defaults;
  const x=raw as Record<string,unknown>,names=new Set(rows.map(r=>r.name));
  const set=typeof x.set==='string'&&['core','classification','all'].includes(x.set)?x.set:'core';
  const allowed=set==='core'?['average_precision','roc_auc','recall','brier']:set==='classification'?['precision','recall','specificity','f1','accuracy','balanced_accuracy','mcc','npv','fpr','fnr']:Object.keys(metricLabels);
  return {sort:typeof x.sort==='string'&&allowed.includes(x.sort)?x.sort:'',direction:x.direction==='asc'?'asc':'desc',query:typeof x.query==='string'?x.query.slice(0,100):'',set,showSD:typeof x.showSD==='boolean'?x.showSD:true,chosen:Array.isArray(x.chosen)?[...new Set(x.chosen.filter((n):n is string=>typeof n==='string'&&names.has(n)))].slice(0,2):[]};
}
const memories=new Map<string,ModelView>();
export function readModelView(key:string,rows:ModelRow[]):ModelView{
  try{const raw=sessionStorage.getItem(key);if(raw)return restoreModelView(JSON.parse(raw),rows);}catch{}
  return restoreModelView(memories.get(key),rows);
}
export function saveModelView(key:string,view:ModelView){
  memories.set(key,view);if(memories.size>30)memories.delete(memories.keys().next().value!);
  try{sessionStorage.setItem(key,JSON.stringify(view));}catch{}
}
function csvCell(value:unknown){
  if(value===null||value===undefined||typeof value==='number'&&!Number.isFinite(value))return '';
  let text=String(value);if(typeof value==='string'&&/^[=+\-@\t\r]/.test(text))text="'"+text;
  return /[",\n\r]/.test(text)?'"'+text.replace(/"/g,'""')+'"':text;
}
export function comparisonCsv(a:ModelRow,b:ModelRow,context?:ComparisonContext){
  [a,b]=enrichMetricsRows([a,b],context);
  const keys=Object.keys(metricLabels),comparison=compareModels(a,b,keys);
  const header=['dataset','experiment','evaluation','weighting','role','model','training_n','evaluation_n','threshold','derived_metric_method','derived_metric_folds','derived_metric_sd',...keys,...keys.map(k=>k+'_fold_sd'),...keys.map(k=>'delta_B_minus_A_'+k)];
  const rows=[a,b].map((r,i)=>[context?.dataset||'unspecified',context?.experiment||'unspecified',context?.evaluation||'unspecified',context?.weighting||'unspecified',i?'B':'A',r.name,r.training_n,r.test_n,r.threshold,r.derived_metrics?.method,r.derived_metrics?.folds,r.derived_metrics?.sd,...keys.map(k=>r.metrics?.[k]),...keys.map(k=>r.std?.[k]),...comparison.map(x=>i?x.delta:null)]);
  return [header,...rows].map(row=>row.map(csvCell).join(',')).join('\r\n')+'\r\n';
}
export const xmlEscape=(v:unknown)=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]!));
const number=(v:unknown,d=3)=>finiteMetric(v)?v.toFixed(d):'—';
export function comparisonSvg(a:ModelRow,b:ModelRow,context?:ComparisonContext,lang:'ru'|'kk'='ru'){
  [a,b]=enrichMetricsRows([a,b],context);
  const t=(ru:string,kk:string)=>lang==='kk'?kk:ru;
  const footerY=290+Object.keys(metricLabels).length*78+33,height=footerY+83;
  const evaluation=context?.evaluation==='mean_outer_cv_6_folds'?t('Среднее 6 внешних фолдов CV','CV 6 сыртқы бөлігінің орташа мәні'):context?.evaluation==='held_out_test'?t('Отложенный тест','Бөлек тест'):context?.evaluation==='validation'?t('Валидация','Валидация'):t('Схема не указана','Бағалау сызбасы көрсетілмеген');
  const metricRows=compareModels(a,b,Object.keys(metricLabels)).map((row,i)=>{
    const y=290+i*78,delta=row.delta===null?'—':Math.abs(row.delta)>0&&Math.abs(row.delta)<.00005?(row.delta<0?'−<0.0001':'+<0.0001'):(row.delta>0?'+':'')+row.delta.toFixed(4);
    const bar=(v:number|null,offset:number,color:string)=>{const signed=row.key==='mcc',start=signed?450+Math.min(0,v??0)*180:270,width=v===null?0:signed?Math.min(1,Math.abs(v))*180:Math.min(1,Math.max(0,v))*360;return `<rect x="270" y="${y+offset}" width="360" height="9" rx="4" fill="#edf2ef"/>${v===null?'':`<rect x="${start}" y="${y+offset}" width="${width}" height="9" rx="4" fill="${color}"/>`}${signed?`<line x1="450" x2="450" y1="${y+offset-2}" y2="${y+offset+11}" stroke="#617c70"/>`:''}`;};
    return `<g><text x="44" y="${y+14}" font-size="18" font-weight="600">${xmlEscape(metricLabels[row.key])}${metricDefinitions[row.key]?.direction==='lower'?' ↓':' ↑'}${row.key==='mcc'?' [−1…1]':''}</text>${bar(row.first,0,'#288d74')}${bar(row.second,26,'#628ab5')}<text x="650" y="${y+9}" font-size="18">A ${number(row.first)}${finiteMetric(a.std?.[row.key])?' ± '+number(a.std?.[row.key]):''}</text><text x="650" y="${y+35}" font-size="18">B ${number(row.second)}${finiteMetric(b.std?.[row.key])?' ± '+number(b.std?.[row.key]):''}</text><text x="885" y="${y+24}" font-size="18">${xmlEscape(delta)}</text><line x1="44" x2="1056" y1="${y+56}" y2="${y+56}" stroke="#e5ede8"/></g>`;
  }).join('');
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="${height}" viewBox="0 0 1100 ${height}" role="img"><title>${xmlEscape(t('Сравнение моделей CardioResearch','CardioResearch модельдерін салыстыру'))}</title><desc>${xmlEscape([a.name,b.name,context?.dataset,evaluation].join(' · '))}</desc><rect width="1100" height="${height}" fill="white"/><g font-family="Segoe UI, Arial, sans-serif" fill="#294e43"><text x="44" y="49" font-size="15" fill="#607c70">CARDIORESEARCH · ${xmlEscape(t('ИССЛЕДОВАТЕЛЬСКИЕ РЕЗУЛЬТАТЫ','ЗЕРТТЕУ НӘТИЖЕЛЕРІ'))}</text><text x="44" y="91" font-size="31" font-weight="600">${xmlEscape(t('Сравнение двух моделей','Екі модельді салыстыру'))}</text><text x="44" y="123" font-size="17">${xmlEscape((context?.dataset||'—').toUpperCase()+' · '+evaluation+' · '+(context?.weighting==='survey_weighted'?t('с весами обследования','сауалнама салмақтарымен'):context?.weighting==='unweighted'?t('без весов','салмақсыз'):t('взвешивание не указано','салмақтау көрсетілмеген')))}</text><text x="44" y="149" font-size="16">${xmlEscape(t('Эксперимент: ','Эксперимент: ')+(context?.experiment||t('не указан','көрсетілмеген')))}</text><text x="44" y="190" font-size="18" fill="#288d74">A · ${xmlEscape(a.name)}</text><text x="560" y="190" font-size="18" fill="#628ab5">B · ${xmlEscape(b.name)}</text>${[a,b].map((r,i)=>`<text x="${i?560:44}" y="218" font-size="14">${xmlEscape(t('n обучения / оценки: ','Оқыту / бағалау n: ')+(r.training_n??'—')+' / '+(r.test_n??'—'))}</text><text x="${i?560:44}" y="241" font-size="14">${xmlEscape(t('Порог: ','Шек: ')+(finiteMetric(r.threshold)?String(r.threshold):'—'))}</text>`).join('')}<text x="270" y="265" font-size="14" fill="#6b8277">${xmlEscape(t('Шкала 0–1; MCC: −1…1','Шкала 0–1; MCC: −1…1'))}</text><text x="885" y="265" font-size="14">Δ B − A</text>${metricRows}<text x="44" y="${footerY}" font-size="15">${xmlEscape(t('Разность оценок не доказывает превосходство. Для Brier, FPR и FNR меньше — лучше.','Бағалар айырмасы басымдықты дәлелдемейді. Brier, FPR және FNR үшін төмен мән жақсы.'))}</text><text x="44" y="${footerY+33}" font-size="15">${xmlEscape(t('± показывает SD по фолдам, если он доступен; это не доверительный интервал.','± қолжетімді болса, бөліктер бойынша SD көрсетеді; бұл сенімділік аралығы емес.'))}</text></g></svg>`;
}
