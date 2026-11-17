import {useCallback,useEffect,useRef,useState,KeyboardEvent} from 'react';
import {BarChart3,CalendarDays,FlaskConical,GitCompareArrows,RotateCcw,ShieldCheck} from 'lucide-react';
import {api,Card,Empty,Lang,Loading,T} from './ui';
import DisagreementLab,{AgreementReport} from './DisagreementLab';
import ExperimentRuns,{ExperimentReport} from './ExperimentRuns';
import TemporalLab,{TemporalReport} from './TemporalLab';
import './experiments.css';

export default function ExperimentsHub({lang}:{lang:Lang}){
 const t:T=(ru,kk)=>lang==='kk'?kk:ru;
 const [tab,setTab]=useState('agreement'),[agreement,setAgreement]=useState<AgreementReport|null>(null),[experiments,setExperiments]=useState<ExperimentReport|null>(null),[temporal,setTemporal]=useState<TemporalReport|null>(null),[errors,setErrors]=useState<Record<string,boolean>>({}),[attempt,setAttempt]=useState(0);
 const experimentRequest=useRef<AbortController|null>(null);
 const refresh=useCallback(()=>{
  experimentRequest.current?.abort();const controller=new AbortController();experimentRequest.current=controller;
  api('/experiment-lab',{signal:controller.signal,cache:'no-store'}).then(data=>{if(!controller.signal.aborted){setExperiments(data);setErrors(e=>({...e,experiments:false}))}}).catch(()=>{if(!controller.signal.aborted)setErrors(e=>({...e,experiments:true}))});
 },[]);
 useEffect(()=>{
  let live=true;const controller=new AbortController();setErrors({});
  refresh();
  const requests:[string,string,(value:any)=>void][]=[['agreement','/disagreement/uci',setAgreement],['temporal','/temporal/brfss',setTemporal]];
  requests.forEach(([key,path,set])=>{api(path,{signal:controller.signal}).then(data=>{if(live)set(data)}).catch(()=>{if(live)setErrors(e=>({...e,[key]:true}))})});
  return()=>{live=false;controller.abort();experimentRequest.current?.abort()};
 },[attempt,refresh]);
 useEffect(()=>{if(['learning','stress','run'].includes(tab))refresh()},[tab,refresh]);
 const tabs=[['agreement',t('Разногласия моделей','Модельдер келіспеушілігі'),GitCompareArrows],['learning',t('Кривые обучения','Оқыту қисықтары'),BarChart3],['stress',t('Устойчивость','Тұрақтылық'),ShieldCheck],['temporal',t('Перенос на 2024','2024 жылға тасымал'),CalendarDays],['run',t('Новый эксперимент','Жаңа эксперимент'),FlaskConical]] as const;
 const keys=(event:KeyboardEvent<HTMLDivElement>)=>{const i=tabs.findIndex(x=>x[0]===tab),next=event.key==='ArrowRight'?(i+1)%tabs.length:event.key==='ArrowLeft'?(i+tabs.length-1)%tabs.length:event.key==='Home'?0:event.key==='End'?tabs.length-1:-1;if(next<0)return;event.preventDefault();setTab(tabs[next][0]);event.currentTarget.querySelectorAll<HTMLButtonElement>('[role=tab]')[next]?.focus()};
 const key=tab==='agreement'?'agreement':tab==='temporal'?'temporal':'experiments';
 const ready=key==='agreement'?agreement:key==='temporal'?temporal:experiments;
 return <div className="experiments-hub"><div className="tabs experiment-tabs" role="tablist" aria-label={t('Новые исследовательские эксперименты','Жаңа зерттеу эксперименттері')} onKeyDown={keys}>{tabs.map(([id,label,Icon])=><button key={id} id={`experiment-tab-${id}`} role="tab" aria-selected={tab===id} aria-controls="experiment-panel" tabIndex={tab===id?0:-1} className={tab===id?'selected':''} onClick={()=>setTab(id)}><Icon size={16}/>{label}</button>)}</div><section id="experiment-panel" role="tabpanel" aria-labelledby={`experiment-tab-${tab}`} tabIndex={0}>
  {errors[key]&&ready&&<div className="error" role="alert">{t('Не удалось обновить данные. Показаны последние загруженные результаты.','Деректер жаңартылмады. Соңғы жүктелген нәтижелер көрсетілген.')} <button className="secondary compact" onClick={()=>setAttempt(n=>n+1)}>{t('Повторить','Қайталау')}</button></div>}
  {errors[key]&&!ready?<Card><Empty title={t('Не удалось загрузить опыт','Тәжірибе жүктелмеді')} body={t('Повторите запрос. Результаты других разделов остаются доступны.','Сұрауды қайталаңыз. Басқа бөлімдердің нәтижелері қолжетімді.')}><button className="secondary" onClick={()=>setAttempt(n=>n+1)}><RotateCcw size={16}/>{t('Повторить','Қайталау')}</button></Empty></Card>:!ready?<Loading text={t('Загрузка рассчитанных экспериментов…','Есептелген эксперименттер жүктелуде…')}/>:tab==='agreement'?<DisagreementLab report={agreement!} lang={lang}/>:tab==='temporal'?<TemporalLab report={temporal!} lang={lang}/>:<ExperimentRuns report={experiments!} lang={lang} pane={tab} onRefresh={refresh} onPane={setTab}/>}
 </section></div>;
}
