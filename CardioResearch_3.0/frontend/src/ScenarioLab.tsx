import {useEffect,useRef,useState} from 'react';
import {ArrowDownToLine,ArrowRight,Check,FlaskConical,Info,LoaderCircle,LockKeyhole,Pin,RotateCcw,SlidersHorizontal,Trash2,X} from 'lucide-react';
import {Card,Chart,Empty,errorText,Field,fmt,Lang,Note,T,Values} from './ui';
import {fieldLabel,groupLabel,optionLabel} from './locale';
import './scenarios.css';

export type ScenarioLabProps={
 ds:string; fields:Field[]; lang:Lang; fullAccess:boolean;
 onLogin:()=>void; onSessionExpired:()=>void; initialValues?:Values;
};
type ScenarioPoint={value:number;probability:number;delta:number;positive:boolean};
type ScenarioResponse={
 dataset:string;model:string;version:string;threshold:number;feature:string;
 baseline:{values:Values;probability:number;positive:boolean;missing_fields:string[]};
 points:ScenarioPoint[];note:string;synthetic:boolean;
};
type PinnedScenario={id:number;response:ScenarioResponse;signature:string};

function subset(values:Values|undefined,fields:Field[]):Values{
 return Object.fromEntries(fields.map(field=>[field.name,typeof values?.[field.name]==='number'&&Number.isFinite(values[field.name])?values[field.name]:null]));
}
function validScalar(field:Field,value:number){
 if(!Number.isFinite(value))return false;
 if(field.kind==='category')return !!field.options?.some(option=>option.value===value);
 return (field.min===undefined||value>=field.min)&&(field.max===undefined||value<=field.max)
  &&(field.step!==1||Number.isInteger(value));
}
function preferredFeature(ds:string,fields:Field[]){return fields.find(field=>field.name===(ds==='brfss'?'bmi':'oldpeak'))||fields[0]}
function suggestedPoints(field:Field|undefined,baseline:Values):number[]{
 if(!field)return [];
 if(field.kind==='category')return (field.options?.length||0)<=9?(field.options||[]).map(option=>option.value):[];
 if(field.name==='bmi')return [22,27,32,37];
 if(field.name==='oldpeak')return [0,1,2,3];
 const low=field.min??0,high=field.max??100,center=baseline[field.name]??(low+high)/2;
 const step=field.step||1;const offset=Math.max(step,(high-low)/10);
 return Array.from(new Set([-1,0,1].map(k=>Math.min(high,Math.max(low,Number((Math.round((center+k*offset)/step)*step).toFixed(4)))))));
}
function fingerprint(response:ScenarioResponse){return JSON.stringify([response.dataset,response.version,response.feature,response.baseline.values,response.points.map(point=>point.value)])}
function chartLabel(value:string){
 const lines:string[]=[];let line='';
 for(const word of value.split(' ')){if(line&&(line+' '+word).length>22){lines.push(line);line=word}else line=line?line+' '+word:word}
 if(line)lines.push(line);return lines.join('<br>');
}

export default function ScenarioLab({ds,fields,lang,fullAccess,onLogin,onSessionExpired,initialValues}:ScenarioLabProps){
 const t:T=(ru,kk)=>lang==='kk'?kk:ru;
 const first=preferredFeature(ds,fields);
 const [values,setValues]=useState<Values>(()=>fullAccess?subset(initialValues,fields):{});
 const [feature,setFeature]=useState(first?.name||'');
 const [numericText,setNumericText]=useState(()=>suggestedPoints(first,initialValues||{}).join(', '));
 const [categories,setCategories]=useState<number[]>(()=>first?.kind==='category'?suggestedPoints(first,initialValues||{}):[]);
 const [result,setResult]=useState<ScenarioResponse|null>(null);
 const [pins,setPins]=useState<PinnedScenario[]>([]);
 const [busy,setBusy]=useState(false);const [error,setError]=useState('');
 const [syntheticInput,setSyntheticInput]=useState(false);
 const epoch=useRef(0);const controller=useRef<AbortController|null>(null);const pinId=useRef(0);
 const activeScope=useRef({ds,fullAccess});
 activeScope.current={ds,fullAccess};
 const currentField=fields.find(field=>field.name===feature);
 const complete=fields.filter(field=>values[field.name]!=null&&Number.isFinite(values[field.name])).length;
 const inheritedCount=fields.filter(field=>initialValues?.[field.name]!=null&&Number.isFinite(initialValues[field.name])).length;

 useEffect(()=>{
  epoch.current++;controller.current?.abort();setBusy(false);setError('');setResult(null);setPins([]);setSyntheticInput(false);
  const field=preferredFeature(ds,fields);const start=fullAccess?subset(initialValues,fields):{};
  setValues(start);setFeature(field?.name||'');setNumericText(suggestedPoints(field,start).join(', '));
  setCategories(field?.kind==='category'?suggestedPoints(field,start):[]);
  return()=>{epoch.current++;controller.current?.abort()};
  // Inputs are intentionally copied only at a dataset/access boundary or by the explicit button below.
  // A language change or a parent's unrelated render must never overwrite an edited baseline.
 },[ds,fullAccess]);

 const invalidate=()=>{epoch.current++;controller.current?.abort();controller.current=null;setBusy(false);setResult(null);setError('')};
 const reset=()=>{invalidate();setValues({});setSyntheticInput(false);const field=preferredFeature(ds,fields);setFeature(field?.name||'');setNumericText(suggestedPoints(field,{}).join(', '));setCategories(field?.kind==='category'?suggestedPoints(field,{}):[])};
 const chooseFeature=(name:string)=>{if(!fullAccess||busy)return;invalidate();const field=fields.find(item=>item.name===name);setFeature(name);setNumericText(suggestedPoints(field,values).join(', '));setCategories(field?.kind==='category'?suggestedPoints(field,values):[])};
 const updateValue=(name:string,value:string)=>{if(!fullAccess||busy)return;invalidate();setValues(previous=>({...previous,[name]:value===''?null:Number(value)}));setSyntheticInput(false)};
 const copyInitial=()=>{if(!fullAccess||busy)return;invalidate();setValues(subset(initialValues,fields));setSyntheticInput(false)};
 const labelValue=(field:Field|undefined,value:number|null|undefined)=>{
  if(value==null)return t('Не указано','Көрсетілмеген');
  const option=field?.options?.find(item=>item.value===value);
  return option?optionLabel(option.label,lang):String(value);
 };
 const parsePoints=():{points:number[];message:string}=>{
  if(!currentField)return {points:[],message:t('Выберите показатель.','Көрсеткішті таңдаңыз.')};
  const tokens=numericText.split(/[,;\n]/).map(part=>part.trim());
  const points=currentField.kind==='category'?categories:tokens.map(token=>token===''?NaN:Number(token));
  if(points.length<2||points.length>9)return {points:[],message:t('Укажите от 2 до 9 значений.','2-ден 9-ға дейін мән көрсетіңіз.')};
  if(points.some(value=>!validScalar(currentField,value)))return {points:[],message:t('Проверьте значения, диапазон и целочисленный формат показателя.','Мәндерді, ауқымды және көрсеткіштің бүтін сан пішімін тексеріңіз.')};
  if(new Set(points).size!==points.length)return {points:[],message:t('Каждое значение должно встречаться один раз.','Әр мән бір рет қана кездесуі керек.')};
  return {points,message:''};
 };
 const sweep=parsePoints();
 const baselineInvalid=fields.some(field=>values[field.name]!=null&&!validScalar(field,values[field.name] as number));
 const request=async(demo:boolean)=>{
  if(busy||!fields.length)return;
  if(!demo&&!fullAccess){onLogin();return}
  if(!demo&&(complete<3||baselineInvalid||sweep.message)){setError(sweep.message||t('Заполните хотя бы три корректных показателя.','Кемінде үш дұрыс көрсеткішті толтырыңыз.'));return}
  controller.current?.abort();const abort=new AbortController();controller.current=abort;
  const ticket=++epoch.current;const scope={ds,fullAccess};setBusy(true);setError('');
  const isCurrent=()=>ticket===epoch.current&&scope.ds===activeScope.current.ds&&scope.fullAccess===activeScope.current.fullAccess;
  try{
   const response=await fetch(demo?`/api/scenario-demo/${ds}?lang=${lang}`:'/api/scenarios',demo?
    {credentials:'same-origin',cache:'no-store',signal:abort.signal}:
    {method:'POST',credentials:'same-origin',cache:'no-store',signal:abort.signal,headers:{'Content-Type':'application/json'},
     body:JSON.stringify({dataset:ds,values:subset(values,fields),vary:{feature,values:sweep.points},lang})});
   if(!isCurrent())return;
   if(response.status===401){invalidate();setValues({});setPins([]);setSyntheticInput(false);onSessionExpired();return}
   const data=await response.json();if(!isCurrent())return;
   if(!response.ok)throw Error(errorText(data.detail||data));
   const resultField=fields.find(field=>field.name===data.feature);
   const probability=(value:unknown):value is number=>typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=1;
   if(data.dataset!==ds||!resultField||!probability(data.baseline?.probability)||!probability(data.threshold)
      ||typeof data.model!=='string'||typeof data.version!=='string'||!Array.isArray(data.points)||data.points.length<2||data.points.length>9
      ||!data.baseline.values||typeof data.baseline.positive!=='boolean'||data.baseline.positive!==(data.baseline.probability>=data.threshold)
      ||new Set(data.points.map((point:ScenarioPoint)=>point.value)).size!==data.points.length
      ||fields.some(field=>data.baseline.values[field.name]!=null&&!validScalar(field,data.baseline.values[field.name]))
      ||data.points.some((point:ScenarioPoint)=>!validScalar(resultField,point.value)||!probability(point.probability)
       ||typeof point.positive!=='boolean'||point.positive!==(point.probability>=data.threshold)
       ||!Number.isFinite(point.delta)||Math.abs(point.delta-(point.probability-data.baseline.probability))>1e-8)){
    throw Error(t('Сервер вернул несовместимый результат. Повторите расчёт.','Сервер үйлесімсіз нәтиже қайтарды. Есептеуді қайталаңыз.'));
   }
   const saved:ScenarioResponse={...data,synthetic:demo||data.synthetic===true||syntheticInput,baseline:{...data.baseline,values:subset(data.baseline.values,fields)}};
   setResult(saved);setValues({...saved.baseline.values});setFeature(saved.feature);setSyntheticInput(demo||saved.synthetic===true);
   setNumericText(saved.points.map(point=>point.value).join(', '));setCategories(saved.points.map(point=>point.value));
  }catch(e){if(isCurrent()&&(e as Error).name!=='AbortError')setError((e as Error).message.slice(0,700))}
  finally{if(isCurrent()){setBusy(false);controller.current=null}}
 };
 const pin=()=>{if(!result||pins.length>=4)return;const signature=fingerprint(result);if(pins.some(item=>item.signature===signature))return;setPins(previous=>[...previous,{id:++pinId.current,response:structuredClone(result),signature}])};
 const exportCsv=()=>{
  if(!fullAccess){onLogin();return}if(!result)return;
  const headers=['dataset','model','model_version','feature','baseline_feature_value','scenario_value','baseline_probability','scenario_probability','delta_percentage_points','threshold','predicted_class','synthetic',...fields.map(field=>'baseline_'+field.name)];
  const rows=result.points.map(point=>[result.dataset,result.model,result.version,result.feature,result.baseline.values[result.feature]??'',point.value,result.baseline.probability,point.probability,point.delta*100,result.threshold,Number(point.positive),result.synthetic,...fields.map(field=>result.baseline.values[field.name]??'')]);
  const cell=(value:unknown)=>{const safe=typeof value==='string'&&/^[=+\-@\t\r]/.test(value)?"'"+value:String(value);return '"'+safe.replace(/"/g,'""')+'"'};
  const csv='\uFEFF'+[headers,...rows].map(row=>row.map(cell).join(',')).join('\r\n');
  const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download=`CardioResearch_${ds}_scenarios.csv`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 };
 const resultField=result?fields.find(field=>field.name===result.feature):undefined;
 const plotted=result?[...result.points].sort((a,b)=>resultField?.kind==='number'?a.value-b.value:0):[];
 const signed=(value:number)=>`${value>=0?'+':''}${fmt(value,2)}`;
 const alreadyPinned=!!result&&pins.some(item=>item.signature===fingerprint(result));

 return <div className="scenario-lab">
  <section className="scenario-intro"><span className="scenario-emblem"><SlidersHorizontal size={27}/></span><div><div className="eyebrow">{t('ЧУВСТВИТЕЛЬНОСТЬ МОДЕЛИ','МОДЕЛЬ СЕЗІМТАЛДЫҒЫ')}</div><h2>{t('Один показатель. Несколько сценариев.','Бір көрсеткіш. Бірнеше сценарий.')}</h2><p>{t('Зафиксируйте исходную анкету и сравните оценки модели при разных значениях одного признака.','Бастапқы сауалнаманы бекітіп, бір белгінің түрлі мәндеріндегі модель бағаларын салыстырыңыз.')}</p></div></section>
  <Note tone="amber">{t('Это проверка статистической чувствительности модели. Разница оценок не означает эффект лечения, причинное влияние или изменение будущего риска. Некоторые сочетания признаков могут быть редкими или нереалистичными.','Бұл модельдің статистикалық сезімталдығын тексеру. Бағалар айырмасы емдеу әсерін, себептік ықпалды немесе болашақ қауіптің өзгеруін білдірмейді. Белгілердің кейбір үйлесімдері сирек немесе шынайы болмауы мүмкін.')}</Note>
  {!fullAccess&&<div className="scenario-guest"><LockKeyhole size={21}/><div><strong>{t('Фиксированный пример открыт всем','Бекітілген мысал бәріне ашық')}</strong><p>{t('В деморежиме используются только синтетические значения сервера. Для своей анкеты и экспорта CSV войдите как владелец.','Деморежимде тек сервердің синтетикалық мәндері қолданылады. Жеке сауалнама мен CSV экспорты үшін иесі ретінде кіріңіз.')}</p></div><button className="secondary compact" onClick={onLogin}>{t('Войти','Кіру')}<ArrowRight size={16}/></button></div>}
  {error&&<div className="error" role="alert"><Info size={18}/><div>{error}</div><button className="icon-btn" onClick={()=>setError('')} aria-label={t('Закрыть сообщение','Хабарды жабу')}><X size={16}/></button></div>}
  <div className="scenario-setup">
   <Card className="scenario-baseline" title={t('01 · Исходная анкета','01 · Бастапқы сауалнама')} subtitle={t('Остальные признаки остаются одинаковыми во всех сценариях','Қалған белгілер барлық сценарийде бірдей қалады')}>
    <div className="scenario-input-tools"><button className="secondary compact" disabled={busy||!fields.length} onClick={()=>request(true)}><FlaskConical size={15}/>{t('Загрузить демопример','Демомысалды жүктеу')}</button>{fullAccess&&inheritedCount>0&&<button className="text-btn" disabled={busy} onClick={copyInitial}>{t('Из индивидуальной оценки','Жеке бағалаудан алу')}</button>}</div>
    {syntheticInput&&<div className="scenario-synthetic"><FlaskConical size={14}/>{t('Синтетическая анкета, не данные пациента','Синтетикалық сауалнама, пациент деректері емес')}</div>}
    <div className="scenario-completeness"><div><span>{t('Указано показателей','Көрсетілген көрсеткіштер')}</span><strong>{complete} / {fields.length}</strong></div><span className="scenario-completeness-track"><i style={{width:`${fields.length?complete/fields.length*100:0}%`}}/></span><small>{t('Пропуски обрабатывает сохранённый Pipeline. Минимум 3 поля — ограничение приложения.','Бос мәндерді сақталған Pipeline өңдейді. Кемінде 3 өріс — қосымша шектеуі.')}</small></div>
    <details className="scenario-baseline-details"><summary>{t('Посмотреть и изменить исходные показатели','Бастапқы көрсеткіштерді көру және өзгерту')}<span>{fullAccess?t('редактирование доступно','өзгертуге болады'):t('только просмотр','тек көру')}</span></summary><div className="scenario-baseline-fields">{Array.from(new Set(fields.map(field=>field.group))).map(group=><fieldset key={group} disabled={busy||!fullAccess}><legend>{groupLabel(group,lang)}</legend><div className="field-grid">{fields.filter(field=>field.group===group).map(field=><label key={field.name} htmlFor={'scenario-'+field.name}><span>{fieldLabel(field,lang)}</span>{field.kind==='category'?<select id={'scenario-'+field.name} value={values[field.name]??''} onChange={e=>updateValue(field.name,e.target.value)}><option value="">{t('Не указано','Көрсетілмеген')}</option>{field.options?.map(option=><option key={option.value} value={option.value}>{optionLabel(option.label,lang)}</option>)}</select>:<input id={'scenario-'+field.name} type="number" min={field.min} max={field.max} step={field.step} value={values[field.name]??''} placeholder={t('Не указано','Көрсетілмеген')} onChange={e=>updateValue(field.name,e.target.value)}/>}</label>)}</div></fieldset>)}</div></details>
   </Card>
   <Card className="scenario-sweep" title={t('02 · Изменяемый показатель','02 · Өзгертілетін көрсеткіш')} subtitle={t('Меняется только один признак за один расчёт','Бір есептеуде тек бір белгі өзгереді')}>
    <label className="scenario-control" htmlFor="scenario-feature"><span>{t('Показатель','Көрсеткіш')}</span><select id="scenario-feature" value={feature} disabled={busy||!fullAccess} onChange={e=>chooseFeature(e.target.value)}>{fields.map(field=><option key={field.name} value={field.name}>{fieldLabel(field,lang)}</option>)}</select></label>
    <div className="scenario-baseline-value"><span>{t('Исходное значение','Бастапқы мән')}</span><strong>{labelValue(currentField,values[feature])}</strong></div>
    {currentField?.kind==='category'?<div className="scenario-category-control"><div className="scenario-points-heading"><span>{t('Значения для сравнения','Салыстыру мәндері')}</span><strong>{categories.length} / 9</strong></div><div className="scenario-option-grid">{currentField.options?.map(option=>{const checked=categories.includes(option.value);return <label key={option.value} className={checked?'selected':''}><input type="checkbox" checked={checked} disabled={busy||!fullAccess||(!checked&&categories.length>=9)} onChange={()=>{if(!fullAccess||busy)return;invalidate();setCategories(previous=>checked?previous.filter(value=>value!==option.value):[...previous,option.value])}}/><span>{optionLabel(option.label,lang)}</span>{checked&&<Check size={13}/>}</label>})}</div><small>{t('Выберите от 2 до 9 категорий.','2-ден 9-ға дейін санат таңдаңыз.')}</small></div>:<label className="scenario-control" htmlFor="scenario-points"><span>{t('Значения через запятую','Үтірмен бөлінген мәндер')}</span><input id="scenario-points" type="text" inputMode="text" maxLength={180} value={numericText} disabled={busy||!fullAccess} onChange={e=>{if(!fullAccess)return;invalidate();setNumericText(e.target.value)}} aria-describedby="scenario-points-hint"/><small id="scenario-points-hint">{t('От 2 до 9 разных чисел; десятичный разделитель — точка.','2-ден 9-ға дейін әртүрлі сан; ондық бөлгіш — нүкте.')} {currentField&&`${currentField.min}–${currentField.max}`}</small></label>}
    {fullAccess&&sweep.message&&<p className="scenario-validation" role="status">{sweep.message}</p>}
    <div className="scenario-run"><button className="primary" onClick={()=>request(!fullAccess)} disabled={busy||!fields.length||(fullAccess&&(complete<3||baselineInvalid||!!sweep.message))}>{busy?<LoaderCircle size={17} className="spin"/>:<SlidersHorizontal size={17}/>} {fullAccess?t('Сравнить сценарии','Сценарийлерді салыстыру'):t('Показать демосценарии','Демосценарийлерді көрсету')}</button><button className="text-btn" onClick={reset} disabled={busy}><RotateCcw size={15}/>{t('Сбросить','Тазалау')}</button></div>
   </Card>
  </div>
  {result?<Card className="scenario-result" title={t('03 · Результаты сравнения','03 · Салыстыру нәтижелері')} subtitle={resultField?fieldLabel(resultField,lang):result.feature} action={<div className="scenario-result-actions"><button className="secondary compact" onClick={pin} disabled={pins.length>=4||alreadyPinned}><Pin size={15}/>{alreadyPinned?t('В сравнении','Салыстыруда'):t('Закрепить','Бекіту')}</button><button className="secondary compact" onClick={exportCsv} disabled={!fullAccess}><ArrowDownToLine size={15}/>CSV</button></div>}>
   <div className="scenario-model-line"><span>{result.model}</span><code>{result.version}</code><span>{t('Порог','Шек')}: {fmt(result.threshold*100,1)}%</span>{result.synthetic&&<span className="mini-tag">{t('Синтетический пример','Синтетикалық мысал')}</span>}</div>
   <div className="scenario-metrics"><div><span>{t('Исходная оценка','Бастапқы баға')}</span><strong>{fmt(result.baseline.probability*100,1)}<small>%</small></strong><p>{labelValue(resultField,result.baseline.values[result.feature])}</p></div><div><span>{t('Диапазон оценок сценариев','Сценарий бағаларының ауқымы')}</span><strong>{fmt(Math.min(...result.points.map(point=>point.probability))*100,1)}–{fmt(Math.max(...result.points.map(point=>point.probability))*100,1)}<small>%</small></strong><p>{result.points.length} {t('рассчитанных точек','есептелген нүкте')}</p></div><div><span>{t('Изменение относительно исходной','Бастапқы бағамен салыстырғандағы өзгеріс')}</span><strong>{signed(Math.min(...result.points.map(point=>point.delta))*100)}…{signed(Math.max(...result.points.map(point=>point.delta))*100)}</strong><p>{t('процентных пунктов, не процентов','пайыздық тармақ, пайыз емес')}</p></div></div>
   <div className="scenario-chart-key"><span><i className="point"/>{t('Сценарий','Сценарий')}</span><span><i className="baseline"/>{t('Исходная оценка','Бастапқы баға')}</span><span><i className="threshold"/>{t('Порог классификации','Жіктеу шегі')}</span></div>
   <Chart label={t('Вероятность положительного класса по сценариям','Сценарийлердегі оң сынып ықтималдығы')} height={320} data={[{type:'scatter',mode:'markers',x:plotted.map(point=>resultField?.kind==='category'?chartLabel(labelValue(resultField,point.value)):point.value),y:plotted.map(point=>point.probability*100),text:plotted.map(point=>`${labelValue(resultField,point.value)}<br>${t('Изменение','Өзгеріс')}: ${signed(point.delta*100)} ${t('п.п.','пайыздық тармақ')}`),hovertemplate:'%{text}<br>%{y:.2f}%<extra></extra>',marker:{color:'#138f81',size:13,line:{color:'#ffffff',width:2}},showlegend:false}]} layout={{margin:{l:55,r:24,t:15,b:resultField?.kind==='category'?90:55},xaxis:{title:{text:t('Значение показателя','Көрсеткіш мәні')},automargin:true,tickangle:0,type:resultField?.kind==='category'?'category':'linear'},yaxis:{range:[0,100],title:{text:t('Оценка модели, %','Модель бағасы, %')},ticksuffix:'%',gridcolor:'#edf1f2'},shapes:[{type:'line',xref:'paper',x0:0,x1:1,y0:result.baseline.probability*100,y1:result.baseline.probability*100,line:{color:'#537eac',dash:'dash',width:1.5}},{type:'line',xref:'paper',x0:0,x1:1,y0:result.threshold*100,y1:result.threshold*100,line:{color:'#c49b60',dash:'dot',width:1.5}}]}}/>
   <p className="scenario-chart-note">{t('Показаны только рассчитанные точки; промежуточные значения и доверительные интервалы не оценивались. Остальные введённые признаки зафиксированы.','Тек есептелген нүктелер көрсетілген; аралық мәндер мен сенімділік аралықтары бағаланған жоқ. Қалған енгізілген белгілер бекітілген.')}</p>
   <div className="table-scroll" tabIndex={0}><table className="scenario-table"><thead><tr><th>{t('Значение признака','Белгінің мәні')}</th><th>{t('Оценка модели','Модель бағасы')}</th><th>{t('Разница, п.п.','Айырма, пайыздық тармақ')}</th><th>{t('Относительно порога','Шекке қатысты')}</th></tr></thead><tbody><tr className="scenario-origin-row"><td>{labelValue(resultField,result.baseline.values[result.feature])}<small>{t('Исходная анкета','Бастапқы сауалнама')}</small></td><td>{fmt(result.baseline.probability*100,2)}%</td><td>0.00</td><td>{result.baseline.positive?t('Выше или равно','Жоғары немесе тең'):t('Ниже','Төмен')}</td></tr>{result.points.map(point=><tr key={point.value}><td>{labelValue(resultField,point.value)}</td><td>{fmt(point.probability*100,2)}%</td><td>{signed(point.delta*100)}</td><td>{point.positive?t('Выше или равно','Жоғары немесе тең'):t('Ниже','Төмен')}</td></tr>)}</tbody></table></div>
   {!fullAccess&&<button className="text-btn scenario-export-login" onClick={onLogin}><LockKeyhole size={14}/>{t('Войти для экспорта текущих точек в CSV','Ағымдағы нүктелерді CSV-ге экспорттау үшін кіру')}</button>}
  </Card>:<Card className="scenario-empty"><Empty title={t('Сравнение появится после расчёта','Салыстыру есептеуден кейін пайда болады')} body={t('Загрузите открытый пример или задайте исходные показатели и значения одного признака.','Ашық мысалды жүктеңіз немесе бастапқы көрсеткіштер мен бір белгінің мәндерін беріңіз.')}/></Card>}
  <Card className="scenario-pins" title={t('Временные сравнения','Уақытша салыстырулар')} subtitle={t('До 4 расчётов в памяти этой страницы. Они удаляются при выходе со страницы или из учётной записи.','Осы беттің жадында 4 есепке дейін. Олар беттен немесе есептік жазбадан шыққанда өшіріледі.')} action={<div className="scenario-pin-tools"><span>{pins.length} / 4</span><button className="text-btn" onClick={()=>setPins([])} disabled={!pins.length}><Trash2 size={14}/>{t('Очистить','Тазалау')}</button></div>}>
   {pins.length?<div className="scenario-pin-grid">{pins.map(item=>{const saved=item.response;const field=fields.find(field=>field.name===saved.feature);return <article className="scenario-pin" key={item.id}><div className="scenario-pin-head"><span>#{item.id} · {t('Сценарий','Сценарий')}</span><button className="icon-btn" onClick={()=>setPins(previous=>previous.filter(pin=>pin.id!==item.id))} aria-label={t('Удалить сравнение','Салыстыруды жою')+' '+item.id}><X size={15}/></button></div><h3>{field?fieldLabel(field,lang):saved.feature}</h3><p>{saved.model} · <code>{saved.version}</code></p><div className="scenario-pin-numbers"><div><span>{t('Исходная','Бастапқы')}</span><strong>{fmt(saved.baseline.probability*100,1)}%</strong></div><ArrowRight size={16}/><div><span>{t('Сценарии','Сценарийлер')}</span><strong>{fmt(Math.min(...saved.points.map(point=>point.probability))*100,1)}–{fmt(Math.max(...saved.points.map(point=>point.probability))*100,1)}%</strong></div></div><div className="scenario-pin-values">{saved.points.map(point=><span key={point.value}>{labelValue(field,point.value)}</span>)}</div><details><summary>{t('Исходные показатели','Бастапқы көрсеткіштер')}</summary><dl>{fields.map(field=><div key={field.name}><dt>{fieldLabel(field,lang)}</dt><dd>{labelValue(field,saved.baseline.values[field.name])}</dd></div>)}</dl></details>{saved.synthetic&&<span className="mini-tag">{t('Синтетический пример','Синтетикалық мысал')}</span>}</article>})}</div>:<p className="scenario-pins-empty"><Pin size={18}/>{t('Закрепите рассчитанный сценарий, чтобы сопоставить несколько исходных анкет.','Бірнеше бастапқы сауалнаманы салыстыру үшін есептелген сценарийді бекітіңіз.')}</p>}
   {pins.length>1&&<p className="scenario-chart-note">{t('У закреплённых расчётов могут различаться исходные анкеты. Сравнивайте их контекст; это не экспериментальное доказательство причинности.','Бекітілген есептердің бастапқы сауалнамалары әртүрлі болуы мүмкін. Олардың мәнмәтінін салыстырыңыз; бұл себептіліктің эксперименттік дәлелі емес.')}</p>}
  </Card>
 </div>;
}
