import {useEffect,useState,KeyboardEvent} from 'react';
import {ArrowDownToLine,CheckCircle2,RotateCcw} from 'lucide-react';
import {api,Card,Chart,count,Empty,fmt,Lang,Loading,Note,T} from './ui';
import './scientific-audit.css';

type Score={average_precision:number;roc_auc:number;brier:number};
type Budget={permutations:number;profile_seed_pairs:number;mean_mae_pp:number;p95_max_error_pp:number;worst_error_pp:number;mean_top3_overlap:number;mean_sign_agreement:number};
type Audit={
 schema_version:number;created_utc:string;scope:string;production_model_replaced:boolean;
 sources:{file:string;sha256:string}[];threshold:number;
 missingness:{numeric_missing_indicators:boolean;mean:Score;folds:(Score&{fold:number;n_fit:number;n_validation:number;transformed_features:number})[]}[];
 calibration:(Score&{version:string;n:number;observed_fraction:number;mean_probability:number;mean_error_pp:number;intercept_slope_fixed_1:number;joint_intercept:number;slope:number})[];
 prevalence_scenarios:{assumed_prevalence:number;roc_auc:number;average_precision:number;precision_fixed_threshold:number}[];
 explanation:{protocol:{background_size:number;seeds_per_budget:number};datasets:{dataset:string;model:string;features:number;profiles:number;coalitions_per_profile:number;summary:Budget[];background_change_mean_mae_pp:number}[]};
};
const signed=(v:number,d=6)=>(v>0?'+':'')+fmt(v,d);

export default function ScientificAudit({lang}:{lang:Lang}){
 const t:T=(ru,kk)=>lang==='kk'?kk:ru;
 const [report,setReport]=useState<Audit|null>(null),[error,setError]=useState(false),[attempt,setAttempt]=useState(0);
 const [panel,setPanel]=useState('explanation'),[dataset,setDataset]=useState('brfss'),[scenario,setScenario]=useState(2);
 useEffect(()=>{
  const controller=new AbortController();setError(false);
  api('/scientific-audit',{signal:controller.signal}).then(value=>{
   if(value.schema_version!==1||value.scope!=='saved_exploratory_diagnostics'||!value.explanation?.datasets?.length||!value.prevalence_scenarios?.length||!value.missingness?.length||!value.calibration?.length)throw Error('report schema');
   if(!controller.signal.aborted)setReport(value);
  }).catch(()=>{if(!controller.signal.aborted)setError(true)});
  return()=>controller.abort();
 },[attempt]);
 if(error)return <Card><Empty title={t('Аудит не загрузился','Аудит жүктелмеді')} body={t('Основные модели и остальные эксперименты доступны отдельно.','Негізгі модельдер мен басқа эксперименттер бөлек қолжетімді.')}><button className="secondary" onClick={()=>setAttempt(n=>n+1)}><RotateCcw size={16}/>{t('Повторить','Қайталау')}</button></Empty></Card>;
 if(!report)return <Loading text={t('Загрузка сохранённого аудита…','Сақталған аудит жүктелуде…')}/>;
 const tabs=[['explanation',t('Точность SHAP','SHAP дәлдігі')],['prevalence',t('Доля класса','Сынып үлесі')],['calibration',t('Калибровка','Калибрлеу')],['missingness',t('Пропуски','Бос мәндер')]];
 const keys=(event:KeyboardEvent<HTMLDivElement>)=>{
  const current=tabs.findIndex(row=>row[0]===panel);
  const next=event.key==='ArrowRight'?(current+1)%tabs.length:event.key==='ArrowLeft'?(current+tabs.length-1)%tabs.length:event.key==='Home'?0:event.key==='End'?tabs.length-1:-1;
  if(next<0)return;event.preventDefault();setPanel(tabs[next][0]);event.currentTarget.querySelectorAll<HTMLButtonElement>('[role=tab]')[next]?.focus();
 };
 const audit=report.explanation.datasets.find(row=>row.dataset===dataset)??report.explanation.datasets[0];
 const production=audit.summary.find(row=>row.permutations===48);
 const point=report.prevalence_scenarios[scenario]??report.prevalence_scenarios[0];
 const baseline=report.missingness.find(row=>!row.numeric_missing_indicators),indicators=report.missingness.find(row=>row.numeric_missing_indicators);
 const exportReport=()=>{
  const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)+'\n'],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download='cardioresearch-scientific-audit.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 };
 const table=(label:string,headers:string[],rows:(string|number)[][])=><div className="table-scroll" role="region" tabIndex={0} aria-label={label}><table><thead><tr>{headers.map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{rows.map((row,i)=><tr key={i}>{row.map((cell,j)=><td key={j}>{cell}</td>)}</tr>)}</tbody></table></div>;
 return <div className="science-audit">
  <Card title={t('Что проверено у модели','Модельде не тексерілді')} subtitle={t('Четыре дополнительных анализа из сохранённых расчётов от 17.11.2026','17.11.2026 күнгі сақталған есептерден төрт қосымша талдау')} action={<button className="secondary compact" onClick={exportReport}><ArrowDownToLine size={15}/>JSON</button>}>
   <div className="science-context"><span><CheckCircle2 size={16}/>{t('Результаты рассчитаны','Нәтижелер есептелген')}</span><span>{t('Модели и порог сохранены','Модельдер мен шек сақталған')}</span></div>
   <p>{t('Здесь можно проверить точность объяснений, чувствительность метрик к составу выборки и качество вероятностей. Дополнительные опыты не заменяют основной benchmark.','Мұнда түсіндірмелер дәлдігін, метрикалардың іріктеме құрамына сезімталдығын және ықтималдықтар сапасын тексеруге болады. Қосымша тәжірибелер негізгі benchmark-ті алмастырмайды.')}</p>
  </Card>
  <div className="tabs science-tabs" role="tablist" aria-label={t('Анализы надёжности','Сенімділік талдаулары')} onKeyDown={keys}>{tabs.map(([id,label])=><button key={id} id={`science-tab-${id}`} role="tab" aria-selected={panel===id} aria-controls="science-panel" tabIndex={panel===id?0:-1} className={panel===id?'selected':''} onClick={()=>setPanel(id)}>{label}</button>)}</div>
  <section id="science-panel" role="tabpanel" aria-labelledby={`science-tab-${panel}`} tabIndex={0}>
   {panel==='explanation'&&<>
    <div className="section-tools"><div><h2>{t('Насколько точен расчёт вкладов?','Үлестерді есептеу қаншалықты дәл?')}</h2><p>{t('Сравнение перестановочного SHAP с полным перебором коалиций','Пермутациялық SHAP-ты коалицияларды толық санаумен салыстыру')}</p></div><div className="segmented" role="group" aria-label={t('Набор данных аудита SHAP','SHAP аудитінің деректер жиыны')}>{report.explanation.datasets.map(row=><button key={row.dataset} aria-pressed={dataset===row.dataset} className={dataset===row.dataset?'active':''} onClick={()=>setDataset(row.dataset)}>{row.dataset==='brfss'?'BRFSS':'UCI'}</button>)}</div></div>
    <div className="science-kpis"><div><span>{t('MAE при 48 перестановках','48 пермутациядағы MAE')}</span><strong>{fmt(production?.mean_mae_pp??NaN,4)} <small>{t('п.п.','п.т.')}</small></strong><small>{t('Бюджет приложения · среднее 20 seed','Қосымша бюджеті · 20 seed орташа мәні')}</small></div><div><span>{t('Проверено профилей','Тексерілген профильдер')}</span><strong>{audit.profiles}</strong><small>{t('Из обучающего фона; не клиническая апробация','Оқыту фонынан; клиникалық апробация емес')}</small></div><div><span>{t('Коалиций на профиль','Бір профильдегі коалициялар')}</span><strong>{count(audit.coalitions_per_profile)}</strong><small>{audit.features} {t('признаков · фон','белгі · фон')}: {report.explanation.protocol.background_size}</small></div></div>
    <Card title={t('Ошибка снижается с числом перестановок','Пермутация саны артқанда қате азаяды')} subtitle={`${audit.model} · ${t('меньше MAE — точнее численное приближение','MAE аз болған сайын сандық жуықтау дәлірек')}`}>
     <Chart lang={lang} label={t('MAE объяснений при 12, 48 и 192 перестановках','12, 48 және 192 пермутациядағы түсіндірме MAE')} data={[{type:'bar',x:audit.summary.map(row=>String(row.permutations)),y:audit.summary.map(row=>row.mean_mae_pp),marker:{color:audit.summary.map(row=>row.permutations===48?'#138f81':'#91bdb3')},hovertemplate:'%{x}<br>MAE %{y:.4f}<extra></extra>'}]} layout={{xaxis:{title:{text:t('Перестановки','Пермутациялар')},type:'category'},yaxis:{title:{text:t('MAE вклада, п.п.','Үлес MAE, п.т.')},rangemode:'tozero'},showlegend:false}} height={280}/>
     {table(t('Численная точность SHAP','SHAP сандық дәлдігі'),[t('Перестановки','Пермутациялар'),'MAE, '+t('п.п.','п.т.'),t('Макс. ошибка, п.п.','Ең үлкен қате, п.т.'),t('Совпадение top-3','Top-3 сәйкестігі')],audit.summary.map(row=>[row.permutations+(row.permutations===48?' · '+t('в приложении','қосымшада'):''),fmt(row.mean_mae_pp,4),fmt(row.worst_error_pp,4),fmt(row.mean_top3_overlap*100,1)+'%']))}
     <p className="science-caption">{t('Вклады измерены в вероятности базовой модели до дополнительной sigmoid-калибровки. Для каждого бюджета: 6 профилей × 20 seed = 120 зависимых прогонов. Это не 120 независимых пациентов и не доверительный интервал.','Үлестер қосымша sigmoid-калибрлеуге дейінгі базалық модель ықтималдығында өлшенген. Әр бюджет үшін: 6 профиль × 20 seed = 120 тәуелді есептеу. Бұл 120 тәуелсіз пациент те, сенімділік аралығы да емес.')}</p>
    </Card>
    <Note tone="teal">{t('При замене фоновой выборки средний абсолютный сдвиг точных вкладов составляет','Фондық іріктеме ауысқанда дәл үлестердің орташа абсолют ығысуы')} <strong>{fmt(audit.background_change_mean_mae_pp,4)} {t('п.п.','п.т.')}</strong>. {t('Это изменение точки сравнения, а не ошибка алгоритма SHAP. Точный перебор относится к выбранному фону и не доказывает причинность.','Бұл SHAP алгоритмінің қатесі емес, салыстыру негізінің өзгеруі. Толық санау таңдалған фонға қатысты және себептілікті дәлелдемейді.')}</Note>
   </>}
   {panel==='prevalence'&&<>
    <Card title={t('Та же модель, другая доля положительного класса','Сол модель, оң сыныптың басқа үлесі')} subtitle={t('Гипотетическое перевзвешивание замороженных BRFSS test-прогнозов','Бекітілген BRFSS test болжамдарын гипотетикалық қайта салмақтау')}>
     <div className="science-scenarios" role="group" aria-label={t('Доля положительного класса','Оң сынып үлесі')}>{report.prevalence_scenarios.map((row,i)=><button key={row.assumed_prevalence} className={scenario===i?'active':''} aria-pressed={scenario===i} onClick={()=>setScenario(i)}>{fmt(row.assumed_prevalence*100,i===2?2:0)}%{i===2&&<small>{t('в исходном тесте','бастапқы тестте')}</small>}</button>)}</div>
     <div className="science-kpis" aria-live="polite"><div><span>Average Precision</span><strong>{fmt(point.average_precision,4)}</strong><small>{t('Меняется с долей класса','Сынып үлесіне қарай өзгереді')}</small></div><div><span>Precision</span><strong>{fmt(point.precision_fixed_threshold,4)}</strong><small>{t('Порог','Шек')}: {fmt(report.threshold,6)}</small></div><div><span>ROC-AUC</span><strong>{fmt(point.roc_auc,4)}</strong><small>{t('Сохраняется при этом сценарии','Осы сценарийде сақталады')}</small></div></div>
     <Chart lang={lang} label={t('Зависимость метрик от доли положительного класса','Метрикалардың оң сынып үлесіне тәуелділігі')} data={(['average_precision','precision_fixed_threshold','roc_auc'] as const).map((key,i)=>({type:'scatter',mode:'lines+markers',name:['AP','Precision','ROC-AUC'][i],x:report.prevalence_scenarios.map(row=>row.assumed_prevalence*100),y:report.prevalence_scenarios.map(row=>row[key]),line:{dash:i===2?'dot':'solid'},marker:{size:7}}))} layout={{xaxis:{title:{text:t('Доля положительного класса, %','Оң сынып үлесі, %')}},yaxis:{title:{text:t('Значение','Мәні')},range:[0,1]}}} height={310}/>
     {table(t('Сценарии доли класса','Сынып үлесінің сценарийлері'),[t('Доля класса','Сынып үлесі'),'AP','Precision','ROC-AUC'],report.prevalence_scenarios.map(row=>[fmt(row.assumed_prevalence*100,2)+'%',fmt(row.average_precision,4),fmt(row.precision_fixed_threshold,4),fmt(row.roc_auc,4)]))}
    </Card><Note>{t('Внутри каждого класса распределение оценок сохранено. Это не новые наблюдения, не веса обследования и не проверка на населении Казахстана. Линии соединяют рассчитанные сценарии; промежуточные значения не оценивались.','Әр сынып ішіндегі бағалар үлестірімі сақталған. Бұл жаңа бақылаулар, сауалнама салмақтары немесе Қазақстан тұрғындарындағы тексеру емес. Сызықтар есептелген сценарийлерді қосады; аралық мәндер бағаланбаған.')}</Note>
   </>}
   {panel==='calibration'&&<>
    <Card title={t('Согласуются ли вероятности с наблюдениями?','Ықтималдықтар бақылауларға сәйкес пе?')} subtitle={t('BRFSS · один и тот же test, n = 85 748 · без весов обследования','BRFSS · бір test, n = 85 748 · сауалнама салмақтарынсыз')}>
     {table(t('Диагностика калибровки','Калибрлеу диагностикасы'),[t('Метрика','Метрика'),t('До sigmoid','Sigmoid дейін'),t('В приложении','Қосымшада')],[
      ['Brier ↓',...report.calibration.map(row=>fmt(row.brier,6))],
      [t('Средняя вероятность','Орташа ықтималдық'),...report.calibration.map(row=>fmt(row.mean_probability*100,3)+'%')],
      [t('Наблюдаемая доля','Бақыланған үлес'),...report.calibration.map(row=>fmt(row.observed_fraction*100,3)+'%')],
      [t('Разница средних, п.п.','Орташа айырма, п.т.'),...report.calibration.map(row=>signed(row.mean_error_pp,4))],
      [t('Offset intercept (slope = 1)','Offset intercept (slope = 1)'),...report.calibration.map(row=>fmt(row.intercept_slope_fixed_1,4))],
      [t('Совместный intercept','Бірге бағаланған intercept'),...report.calibration.map(row=>fmt(row.joint_intercept,4))],
      [t('Совместный slope','Бірге бағаланған slope'),...report.calibration.map(row=>fmt(row.slope,4))],
     ])}
     <div className="science-reading"><h3>{t('Как читать','Қалай оқу керек')}</h3><p>{t('Brier оценивает ошибку вероятностей: меньше — лучше. Для диагностической логистической калибровки ориентиры: intercept = 0, slope = 1. Каждый показатель описывает отдельный аспект; улучшение Brier не означает улучшение всех остальных.','Brier ықтималдықтар қатесін бағалайды: аз болғаны жақсы. Диагностикалық логистикалық калибрлеудің бағдарлары: intercept = 0, slope = 1. Әр көрсеткіш бөлек қырды сипаттайды; Brier жақсаруы басқа көрсеткіштердің бәрі жақсарды дегенді білдірмейді.')}</p></div>
    </Card><Note tone="amber">{t('Диагностические коэффициенты оценены на test для анализа; к рабочей модели они не применяются. Sigmoid выбран ранее на validation. Доверительные интервалы этих коэффициентов не рассчитаны.','Диагностикалық коэффициенттер талдау үшін test жиынында бағаланған; жұмыс моделіне қолданылмайды. Sigmoid бұрын validation жиынында таңдалған. Бұл коэффициенттердің сенімділік аралықтары есептелмеген.')}</Note>
   </>}
   {panel==='missingness'&&baseline&&indicators&&<>
    <Card title={t('Помогают ли индикаторы пропусков?','Бос мән индикаторлары көмектесе ме?')} subtitle={t('Logistic Regression · 12 000 строк исходного train · одинаковые 3 folds','Logistic Regression · бастапқы train-нің 12 000 жолы · бірдей 3 fold')}>
     <div className="science-kpis"><div><span>{t('AP без индикаторов','Индикаторсыз AP')}</span><strong>{fmt(baseline.mean.average_precision,6)}</strong><small>{t('Среднее 3 folds','3 fold орташа мәні')}</small></div><div><span>{t('AP с индикаторами','Индикаторлармен AP')}</span><strong>{fmt(indicators.mean.average_precision,6)}</strong><small>{t('Добавлены только числовые индикаторы','Тек сандық индикаторлар қосылды')}</small></div><div><span>Δ AP</span><strong>{signed(indicators.mean.average_precision-baseline.mean.average_precision)}</strong><small>{t('Различие очень мало','Айырма өте аз')}</small></div></div>
     {table(t('Парные результаты folds','Fold бойынша жұпталған нәтижелер'),['Fold',t('Train / validation','Train / validation'),t('AP без','Индикаторсыз AP'),t('AP с','Индикаторлармен AP'),'Δ AP'],baseline.folds.map(row=>{const other=indicators.folds.find(f=>f.fold===row.fold);return [row.fold,`${count(row.n_fit)} / ${count(row.n_validation)}`,fmt(row.average_precision,6),fmt(other?.average_precision??NaN,6),signed((other?.average_precision??NaN)-row.average_precision)]}))}
    </Card><Note>{t('Устойчивое улучшение не установлено: изменения AP различаются по знаку между folds. Test не использовался; рабочая модель не заменена. Среднее по трём folds не является доверительным интервалом.','Тұрақты жақсару анықталмаған: folds арасында AP өзгерісінің таңбасы әртүрлі. Test қолданылмаған; жұмыс моделі ауыстырылмаған. Үш fold бойынша орташа мән сенімділік аралығы емес.')}</Note>
   </>}
  </section>
  <details className="science-provenance"><summary>{t('Источники расчётов и воспроизводимость','Есептеу көздері және қайталанымдылық')}</summary><p>{t('JSON содержит агрегаты и протоколы, без индивидуальных анкет. SHA-256 связывает отображаемый результат с исходным отчётом в репозитории.','JSON жеке сауалнамаларды емес, агрегаттар мен хаттамаларды қамтиды. SHA-256 көрсетілген нәтижені репозиторийдегі бастапқы есеппен байланыстырады.')}</p>{report.sources.map(source=><div key={source.file}><strong>{source.file}</strong><code>{source.sha256}</code></div>)}<p>{t('Время сохранённого расчёта','Сақталған есеп уақыты')}: <time dateTime={report.created_utc}>{report.created_utc}</time></p></details>
 </div>;
}
