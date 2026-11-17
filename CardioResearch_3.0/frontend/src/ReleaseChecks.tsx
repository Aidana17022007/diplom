import {useEffect,useState} from 'react';
import {ArrowDownToLine,CheckCircle2,Clock3,Info,RotateCcw,ShieldCheck} from 'lucide-react';
import {api,Card,count,Empty,Lang,Loading,Note,T} from './ui';
import './release-checks.css';

type Check={status:'passed'|'failed'|'not_verified'|'unknown';passed?:number|null;failed?:number|null;errors?:number|null;skipped?:number|null;detail?:string};
type Passport={schema_version:number;application_version:string;checked_release:string|null;checked_date:string|null;report_file:string|null;report_sha256:string|null;version_match:boolean;status:'current'|'stale'|'unknown';scope:string;measured_now:false;checks:{python:Check;worker:Check;builds:Check;browser:Check;startup:Check};frozen_artifact_count:number;frozen_artifacts_sha256:Record<string,string>;issues:string[]};

export default function ReleaseChecks({lang}:{lang:Lang}){
 const t:T=(ru,kk)=>lang==='kk'?kk:ru;
 const [report,setReport]=useState<Passport|null>(null),[error,setError]=useState(false),[attempt,setAttempt]=useState(0);
 useEffect(()=>{const controller=new AbortController();setError(false);api('/release-checks',{signal:controller.signal,cache:'no-store'}).then(value=>{
  if(value?.schema_version!==1||value.measured_now!==false||!['current','stale','unknown'].includes(value.status)||!['python','worker','builds','browser','startup'].every(key=>value.checks?.[key]?.status)||!Array.isArray(value.issues)||!value.frozen_artifacts_sha256)throw Error('schema');
  if(!controller.signal.aborted)setReport(value);
 }).catch(()=>{if(!controller.signal.aborted)setError(true)});return()=>controller.abort()},[attempt]);
 const refresh=<button type="button" className="secondary compact" onClick={()=>setAttempt(n=>n+1)} aria-label={t('Обновить паспорт проверок','Тексеру паспортын жаңарту')}><RotateCcw size={15}/></button>;
 if(error)return <Card title={t('Проверки выпуска','Шығарылым тексерулері')} action={refresh}><Empty title={t('Отчёт недоступен','Есеп қолжетімсіз')} body={t('Статус проверок не подтверждён. Повторите загрузку.','Тексеру мәртебесі расталмаған. Қайта жүктеңіз.')}/></Card>;
 if(!report)return <Card title={t('Проверки выпуска','Шығарылым тексерулері')}><Loading text={t('Сверяем версии приложения и отчёта…','Қолданба мен есеп нұсқаларын салыстырудамыз…')}/></Card>;
 const label=(status:Check['status'])=>status==='passed'?t('Пройдена','Өтілген'):status==='failed'?t('Есть ошибки','Қателер бар'):status==='not_verified'?t('Не проверено','Тексерілмеген'):t('Нет подтверждения','Расталмаған');
 const format=(value:number|null|undefined)=>typeof value==='number'&&Number.isFinite(value)?count(value):'—';
 const exportReport=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)+'\n'],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`cardioresearch-${report.application_version}-checks.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
 const rows:[string,Check,string][]=[
  ['Python',report.checks.python,t('API, расчёты и воспроизводимость','API, есептеулер және қайта өндіру')],
  ['Worker',report.checks.worker,t('Веб-API и логика интерфейса','Веб-API және интерфейс логикасы')],
  [t('Сборки','Құрастырулар'),report.checks.builds,t('TypeScript и готовые интерфейсы','TypeScript және дайын интерфейстер')],
  [t('Локальный запуск','Жергілікті іске қосу'),report.checks.startup,t('Проверка окружения и запуска из отчёта','Есептегі орта мен іске қосу тексеруі')],
  [t('Проверка в браузере','Браузердегі тексеру'),report.checks.browser,t('Отдельная визуальная проверка экранов','Экрандардың жеке визуалды тексеруі')],
 ];
 return <Card title={t('Проверки выпуска','Шығарылым тексерулері')} subtitle={t('Версия приложения и происхождение результатов','Қолданба нұсқасы және нәтижелердің шығу тегі')} action={refresh} className="release-checks">
  <div className="release-versions"><div><span>{t('Приложение','Қолданба')}</span><strong>{report.application_version}</strong></div><div><span>{t('Проверенный выпуск','Тексерілген шығарылым')}</span><strong>{report.checked_release||'—'}</strong></div><div><span>{t('Дата отчёта','Есеп күні')}</span><strong>{report.checked_date||'—'}</strong></div></div>
  <div className={`release-match ${report.status}`} role="status">{report.status==='current'?<ShieldCheck size={17}/>:<Clock3 size={17}/>}<span>{report.status==='current'?t('Отчёт относится к этой версии приложения','Есеп қолданбаның осы нұсқасына қатысты'):report.status==='stale'?t('Отчёт от предыдущей версии: текущая проверка не подтверждена','Есеп алдыңғы нұсқадан: қазіргі тексеру расталмаған'):t('Нет подходящего подтверждённого отчёта','Сәйкес расталған есеп жоқ')}</span></div>
  <div className="release-test-counts">{(['python','worker'] as const).map(key=><div key={key}><span>{key==='python'?'Python':'Worker'}</span><strong>{format(report.checks[key].passed)}</strong><small>{t('пройдено','өтілген')} · {t('ошибок','қателер')}: {format(typeof report.checks[key].failed==='number'&&typeof report.checks[key].errors==='number'?report.checks[key].failed!+report.checks[key].errors!:null)} · {t('пропущено','өткізілген')}: {format(report.checks[key].skipped)}</small></div>)}</div>
  <ul className="release-check-list">{rows.map(([name,check,description])=><li key={name}>{check.status==='passed'&&report.version_match?<CheckCircle2 size={18}/>:<Info size={18}/>}<div><strong>{name}</strong><small>{description}</small></div><span className={`release-check-status ${report.version_match?check.status:'historical'}`}>{label(check.status)}</span></li>)}</ul>
  <p className="release-saved-note">{t('Сохранённые результаты. Открытие этой страницы не запускает тесты; совпадение версий не означает, что все виды проверки выполнены.','Сақталған нәтижелер. Бұл бетті ашу тесттерді іске қоспайды; нұсқалардың сәйкес келуі тексерудің барлық түрі орындалды дегенді білдірмейді.')}</p>
  <details className="release-provenance"><summary>{t('Источник и контрольные суммы','Дереккөз және бақылау қосындылары')}</summary><dl><dt>{t('Отчёт','Есеп')}</dt><dd>{report.report_file||'—'}</dd><dt>SHA-256</dt><dd><code>{report.report_sha256||'—'}</code></dd></dl><p>{t('Контрольные суммы из сохранённого отчёта','Сақталған есептен алынған бақылау қосындылары')}: {count(report.frozen_artifact_count)}</p>{Object.entries(report.frozen_artifacts_sha256).map(([file,hash])=><div key={file}><span>{file}</span><code>{hash}</code></div>)}{report.issues.length>0&&<Note tone="amber">{report.issues.join(' · ')}</Note>}</details>
  <button type="button" className="secondary compact" onClick={exportReport}><ArrowDownToLine size={15}/>{t('Скачать паспорт JSON','Паспортты JSON жүктеу')}</button>
 </Card>;
}
