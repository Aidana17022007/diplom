import {useEffect,useRef,useState} from 'react';
import {ArrowRight,Calculator,Search,X} from 'lucide-react';
import {Lang,T} from './ui';
import './quick-tools.css';

export type NavigationCommand={id:string;ru:string;kk:string;keywords?:string};
export function QuickSearch({commands,lang,onNavigate,onClose}:{commands:NavigationCommand[];lang:Lang;onNavigate:(id:string)=>void;onClose:()=>void}){
 const t:T=(ru,kk)=>lang==='kk'?kk:ru;
 const ref=useRef<HTMLDialogElement>(null),input=useRef<HTMLInputElement>(null),results=useRef<HTMLDivElement>(null),navigated=useRef(false);
 const [query,setQuery]=useState(''),[selected,setSelected]=useState(0);
 const visible=commands.filter(c=>(c.ru+' '+c.kk+' '+c.id+' '+(c.keywords||'')).toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
 const active=visible[selected];
 useEffect(()=>{const dialog=ref.current,previous=document.activeElement as HTMLElement|null;dialog?.showModal();input.current?.focus();return()=>{dialog?.close();if(!navigated.current)previous?.focus()}},[]);
 useEffect(()=>{results.current?.querySelectorAll('button')[Math.max(0,selected)]?.scrollIntoView({block:'nearest'})},[selected,query]);
 const choose=(id:string)=>{navigated.current=true;onNavigate(id);onClose()};
 return <dialog className="quick-dialog" ref={ref} aria-labelledby="quick-title" onCancel={e=>{e.preventDefault();onClose()}}>
  <div className="quick-heading"><h2 id="quick-title">{t('Быстрый переход','Жылдам өту')}</h2><button className="icon-btn" onClick={onClose} aria-label={t('Закрыть поиск','Іздеуді жабу')}><X size={20}/></button></div>
  <label className="quick-search"><Search size={19}/><input ref={input} value={query} role="combobox" aria-autocomplete="list" aria-expanded="true" aria-controls="quick-results" aria-activedescendant={active?'quick-option-'+active.id:undefined} aria-describedby="quick-help" autoComplete="off" spellCheck={false} onChange={e=>{setQuery(e.target.value);setSelected(0)}} placeholder={t('Раздел, метрика или 3D…','Бөлім, метрика немесе 3D…')} aria-label={t('Поиск раздела','Бөлімді іздеу')} onKeyDown={e=>{if(e.key==='ArrowDown'){e.preventDefault();setSelected(i=>Math.min(i+1,Math.max(0,visible.length-1)))}if(e.key==='ArrowUp'){e.preventDefault();setSelected(i=>Math.max(i-1,0))}if(e.key==='Enter'&&active){e.preventDefault();choose(active.id)}}}/></label>
  <p className="quick-count" role="status">{t('Найдено разделов:','Табылған бөлімдер:')} {visible.length}</p>
  <div id="quick-results" className="quick-results" ref={results} role="listbox" aria-label={t('Разделы приложения','Қосымша бөлімдері')}>{visible.map((c,i)=><button role="option" aria-selected={i===selected} id={'quick-option-'+c.id} tabIndex={-1} key={c.id} className={i===selected?'highlighted':''} onMouseEnter={()=>setSelected(i)} onClick={()=>choose(c.id)}><span>{t(c.ru,c.kk)}</span><ArrowRight size={16}/></button>)}</div>
  {!visible.length&&<p className="quick-empty">{t('Раздел не найден. Попробуйте «метрики», «SHAP» или «3D».','Бөлім табылмады. «Метрикалар», «SHAP» немесе «3D» сөздерін енгізіңіз.')}</p>}
  <div className="quick-help" id="quick-help">↑ ↓ {t('выбор','таңдау')} · Enter {t('открыть','ашу')} · Esc {t('закрыть','жабу')}</div>
 </dialog>;
}

export function BMICalculator({lang,min,max,onApply,disabled=false}:{lang:Lang;min:number;max:number;onApply:(value:number)=>void;disabled?:boolean}){
 const t:T=(ru,kk)=>lang==='kk'?kk:ru;
 const [weight,setWeight]=useState(''),[height,setHeight]=useState(''),[applied,setApplied]=useState(false);
 const w=Number(weight),h=Number(height),validInput=weight!==''&&height!==''&&w>=25&&w<=300&&h>=120&&h<=220;
 const bmi=validInput?Math.round(w/(h/100)**2*10)/10:NaN;
 const validBmi=validInput&&bmi>=min&&bmi<=max;
 return <details className="bmi-tool"><summary><Calculator size={17}/>{t('Рассчитать ИМТ по росту и весу','Бой мен салмақ бойынша ДСИ есептеу')}</summary><div className="bmi-body"><p>{t('ИМТ = масса (кг) / рост² (м). Результат можно перенести в анкету.','ДСИ = салмақ (кг) / бой² (м). Нәтижені сауалнамаға көшіруге болады.')}</p><div className="bmi-inputs"><label>{t('Вес, кг','Салмақ, кг')}<input type="number" disabled={disabled} min="25" max="300" step="0.1" value={weight} onChange={e=>{setWeight(e.target.value);setApplied(false)}}/></label><label>{t('Рост, см','Бой, см')}<input type="number" disabled={disabled} min="120" max="220" step="0.1" value={height} onChange={e=>{setHeight(e.target.value);setApplied(false)}}/></label><output>{validInput?bmi.toFixed(1):'—'}<small>{t('кг/м²','кг/м²')}</small></output></div>{weight&&height&&!validBmi&&<p role="status">{t(`Проверьте единицы и диапазоны. Модель принимает ИМТ от ${min} до ${max}.`,`Өлшем бірлігі мен ауқымын тексеріңіз. Модель ${min}–${max} аралығындағы ДСИ қабылдайды.`)}</p>}<button type="button" className="secondary compact" disabled={disabled||!validBmi} onClick={()=>{if(!disabled){onApply(bmi);setApplied(true)}}}>{applied?t('Перенесено в анкету','Сауалнамаға көшірілді'):t('Использовать в анкете','Сауалнамада қолдану')}</button><small className="bmi-footnote">{t('Это арифметический помощник. Он не устанавливает диагноз или категорию риска. Рост и вес не сохраняются.','Бұл арифметикалық көмекші. Диагноз немесе қауіп санатын анықтамайды. Бой мен салмақ сақталмайды.')}</small></div></details>;
}
