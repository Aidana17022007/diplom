import {Component, lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, KeyboardEvent as ReactKeyboardEvent, ReactNode} from 'react';
import {ArrowUpRight, Box, Download, Maximize2, Minimize2, Move, Pause, Play, RotateCcw, Scissors, SplitSquareHorizontal} from 'lucide-react';
import {Card, Lang, Note, T} from './ui';
import {clampNarrowing, clampSectionPosition, HALF_ARTERY_LENGTH, sectionMetrics} from './arteryGeometry';
import ArteryProfile from './ArteryProfile';
import {arteryDiagramSnapshot, arterySnapshot} from './arterySnapshot';
import type {ArteryCapture} from './ArteryScene';
import './artery.css';
import './artery-resilience.css';

/** Keep an unavailable 3D module from taking down the working geometry controls. */
class SceneBoundary extends Component<{children:ReactNode;onUnavailable:()=>void},{failed:boolean}> {
  state={failed:false};
  static getDerivedStateFromError(){return {failed:true};}
  componentDidCatch(){this.props.onUnavailable();}
  render(){return this.state.failed?null:this.props.children;}
}

export default function ArteryLab({lang}: {lang: Lang}) {
  const t: T = (ru, kk) => lang === 'kk' ? kk : ru;
  const [narrowing, setNarrowing] = useState(40);
  const [sectionPosition, setSectionPosition] = useState(0);
  const [cutaway, setCutaway] = useState(true);
  const [moving, setMoving] = useState(false);
  const [compare,setCompare]=useState(false);
  const [reset, setReset] = useState(0);
  const [view, setView] = useState<'side' | 'end' | 'top'>('side');
  const [topic, setTopic] = useState(1);
  const [displayMode,setDisplayMode]=useState<'3d'|'2d'>('3d');
  const [sceneAttempt,setSceneAttempt]=useState(0);
  const [sceneUnavailable,setSceneUnavailable]=useState(false);
  // A failed lazy import is cached by React; a deliberate retry needs a fresh wrapper.
  const ArteryScene=useMemo(()=>lazy(()=>import('./ArteryScene')),[sceneAttempt]);
  const workbench=useRef<HTMLDivElement>(null),fullscreenButton=useRef<HTMLButtonElement>(null),capture=useRef<ArteryCapture|null>(null);
  const [screenMode,setScreenMode]=useState<'native'|'expanded'|null>(null),[screenBusy,setScreenBusy]=useState(false);
  const [sceneReady,setSceneReady]=useState(false),[exportBusy,setExportBusy]=useState(false),[exportStatus,setExportStatus]=useState<'saved'|'failed'|null>(null);
  const useDiagram=useCallback(()=>{setSceneReady(false);setMoving(false);setDisplayMode('2d');setExportStatus(null);},[]);
  const unavailable=useCallback(()=>{setSceneUnavailable(true);useDiagram();},[useDiagram]);
  const retryScene=()=>{setSceneUnavailable(false);setSceneReady(false);setMoving(false);setExportStatus(null);setSceneAttempt(value=>value+1);setDisplayMode('3d');};
  const [screenError,setScreenError]=useState(false);
  const modeRef=useRef(screenMode),alive=useRef(true);modeRef.current=screenMode;
  const restoreScreenFocus=()=>requestAnimationFrame(()=>fullscreenButton.current?.focus({preventScroll:true}));
  useEffect(()=>{
    alive.current=true;
    const target=workbench.current;
    const change=()=>{
      if(document.fullscreenElement===workbench.current)setScreenMode('native');
      else if(modeRef.current==='native'){setScreenMode(null);restoreScreenFocus();}
    };
    document.addEventListener('fullscreenchange',change);
    return()=>{alive.current=false;document.removeEventListener('fullscreenchange',change);if(target&&document.fullscreenElement===target&&document.exitFullscreen)void document.exitFullscreen().catch(()=>{});};
  },[]);
  useEffect(()=>{
    if(!screenMode)return;
    const previousOverflow=document.body.style.overflow;document.body.style.overflow='hidden';
    const background=new Map<HTMLElement,boolean>();
    // Isolate siblings at every level, never the workbench or its ancestors.
    let branch:HTMLElement|null=workbench.current;
    while(branch&&branch!==document.body){
      const parent=branch.parentElement;if(!parent)break;
      for(const sibling of Array.from(parent.children)){
        if(sibling!==branch&&sibling instanceof HTMLElement){background.set(sibling,sibling.inert);sibling.inert=true;}
      }
      branch=parent;
    }
    const frame=requestAnimationFrame(()=>fullscreenButton.current?.focus({preventScroll:true}));
    return()=>{cancelAnimationFrame(frame);background.forEach((wasInert,element)=>{element.inert=wasInert;});document.body.style.overflow=previousOverflow;};
  },[screenMode]);
  const exitScreen=async()=>{
    setScreenError(false);
    if(document.fullscreenElement===workbench.current){
      try{await document.exitFullscreen();}catch{if(alive.current)setScreenError(true);return;}
    }
    if(alive.current){setScreenMode(null);restoreScreenFocus();}
  };
  const toggleScreen=async()=>{
    if(screenBusy)return;
    if(screenMode){await exitScreen();return;}
    const target=workbench.current;if(!target)return;
    setScreenBusy(true);setScreenError(false);
    try{
      if(document.fullscreenEnabled&&target.requestFullscreen){
        try{await target.requestFullscreen();if(alive.current)setScreenMode(document.fullscreenElement===target?'native':'expanded');}
        catch{if(alive.current)setScreenMode('expanded');}
      }else setScreenMode('expanded');
    }finally{if(alive.current)setScreenBusy(false);}
  };
  const screenKeys=(event:ReactKeyboardEvent<HTMLDivElement>)=>{
    if(!screenMode)return;
    if(event.key==='Escape'){event.preventDefault();event.stopPropagation();void exitScreen();return;}
    // Keep a background command palette from competing with this expanded view.
    if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();event.stopPropagation();return;}
    if(event.key!=='Tab')return;
    const items=Array.from(workbench.current?.querySelectorAll<HTMLElement>('button:not([disabled]),input:not([disabled]),select:not([disabled]),a[href],[tabindex]:not([tabindex="-1"])')||[]).filter(item=>item.getClientRects().length>0);
    const first=items[0],last=items[items.length-1];
    if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
  };
  const saveSnapshot=async()=>{
    if((displayMode==='3d'&&!sceneReady)||exportBusy)return;setExportBusy(true);setExportStatus(null);
    try{
      const details={lang,narrowing,sectionPosition,cutaway};
      let output:HTMLCanvasElement;
      if(displayMode==='2d')output=arteryDiagramSnapshot({...details,compare});
      else{const source=capture.current?.capture();if(!source)throw new Error('Scene unavailable');output=arterySnapshot(source,details);}
      const blob=await new Promise<Blob>((resolve,reject)=>output.toBlob(value=>value?resolve(value):reject(new Error('PNG export failed')),'image/png'));
      if(!alive.current)return;
      const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`CardioResearch_artery_${displayMode}_${compare?'comparison_':''}${lang}.png`;link.click();setTimeout(()=>URL.revokeObjectURL(url),30000);setExportStatus('saved');
    }catch{if(alive.current)setExportStatus('failed');}
    finally{if(alive.current)setExportBusy(false);}
  };
  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const stop = () => {if (query.matches) setMoving(false);};
    query.addEventListener('change', stop); return () => query.removeEventListener('change', stop);
  }, []);
  const resetAll = () => {setNarrowing(40); setSectionPosition(0); setCutaway(true); setMoving(false); setView('side'); setTopic(1); setReset(n => n + 1);};
  const topics = [
    {name: t('Стенка артерии','Артерия қабырғасы'), text: t('Розовая оболочка показывает стенку сосуда. Её слои и размеры здесь упрощены для наглядности.','Қызғылт қабық тамыр қабырғасын көрсетеді. Қабаттары мен өлшемдері көрнекілік үшін жеңілдетілген.'), color: 'wall'},
    {name: t('Бляшка','Түйіндақ'), text: t('При атеросклерозе в стенке артерии накапливается бляшка. Здесь она выделена золотым и условно расположена по окружности.','Атеросклероз кезінде артерия қабырғасында түйіндақ жиналады. Мұнда ол алтын түспен көрсетіліп, шартты түрде шеңбер бойымен орналасқан.'), color: 'plaque'},
    {name: t('Просвет','Тамыр қуысы'), text: t('Просвет — внутреннее пространство сосуда. Перемещайте ползунок и сравнивайте, как меняются диаметр и площадь условного круглого сечения.','Қуыс — тамырдың ішкі кеңістігі. Жүгірткіні жылжытып, шартты дөңгелек қиманың диаметрі мен ауданы қалай өзгеретінін салыстырыңыз.'), color: 'lumen'}
  ];
  const section = sectionMetrics(sectionPosition, narrowing);
  return <div className="artery-lab">
    <div className="artery-intro"><span className="artery-kicker"><Box size={15}/> {t('ИНТЕРАКТИВНЫЙ АТЛАС','ИНТЕРАКТИВТІ АТЛАС')}</span><h2>{t('Загляните внутрь артерии','Артерияның ішіне үңіліңіз')}</h2><p>{t('Исследуйте стенку, бляшку и просвет в объёме. Меняйте геометрию и сравнивайте поперечное сечение.','Қабырға, түйіндақ және қуысты көлемді түрде зерттеңіз. Геометрияны өзгертіп, көлденең қиманы салыстырыңыз.')}</p></div>
    <Note tone="teal">{t('Учебная схема атеросклероза. Это не снимок пациента: сужение задаётся вручную и не связано с вероятностью, рассчитанной ML-моделью.','Атеросклероздың оқу сызбасы. Бұл пациенттің суреті емес: тарылу қолмен беріледі және ML моделі есептеген ықтималдықпен байланысты емес.')}</Note>
    <div ref={workbench} id="artery-workbench" className={'artery-workbench'+(screenMode?' artery-expanded':'')+(compare?' artery-comparing':'')} role={screenMode?'dialog':undefined} aria-modal={screenMode?true:undefined} aria-label={screenMode?t('Учебный 3D-атлас артерии','Артерияның оқу 3D атласы'):undefined} onKeyDownCapture={screenKeys}>
      <section className="artery-stage" aria-label={displayMode==='3d'?t('Объёмная модель','Көлемді модель'):t('Схема поперечного сечения','Көлденең қима сызбасы')}>
        <div className="artery-stage-top"><span><span className="status-dot"/> {t('Артерия · условная геометрия','Артерия · шартты геометрия')}</span><div className="artery-stage-actions"><button type="button" onClick={saveSnapshot} disabled={(displayMode==='3d'&&!sceneReady)||exportBusy} aria-label={displayMode==='3d'?t('Скачать снимок 3D в PNG','3D суретін PNG түрінде жүктеу'):t('Скачать схему 2D в PNG','2D сызбасын PNG түрінде жүктеу')}><Download size={15}/><span>{exportBusy?t('Сохранение…','Сақталуда…'):'PNG'}</span></button><button type="button" className="artery-fullscreen-toggle" ref={fullscreenButton} onClick={toggleScreen} disabled={screenBusy} aria-expanded={!!screenMode} aria-controls="artery-workbench" aria-label={screenMode?t('Выйти из полного экрана','Толық экраннан шығу'):t('Развернуть атлас на весь экран','Атласты толық экранға ашу')}>{screenMode?<Minimize2 size={16}/>:<Maximize2 size={16}/>}<span>{screenMode?t('Свернуть','Жабу'):t('Развернуть','Ашу')}</span></button></div></div>
        <div className="artery-compare-toolbar"><button type="button" aria-pressed={compare} onClick={()=>{setCompare(value=>!value);setExportStatus(null)}}><SplitSquareHorizontal size={16}/>{t('Сравнить два сосуда','Екі тамырды салыстыру')}</button><span>{compare?t('Общий ракурс, масштаб и положение среза','Ортақ ракурс, масштаб және қима орны'):t('Исходная и изменённая геометрия рядом','Бастапқы және өзгерген геометрия қатар')}</span></div>
        <div className="artery-mode-toolbar"><div role="group" aria-label={t('Режим отображения атласа','Атласты көрсету режимі')}><button type="button" aria-pressed={displayMode==='3d'} onClick={()=>{if(displayMode!=='3d')retryScene();}}>3D</button><button type="button" aria-pressed={displayMode==='2d'} onClick={useDiagram}>{t('2D · без WebGL','2D · WebGL жоқ')}</button></div><span>{t('Геометрия и выбранный срез сохраняются при переключении','Ауысқанда геометрия мен таңдалған қима сақталады')}</span></div>
        {screenMode&&<p className="artery-screen-note">{t('Учебная схема, не изображение пациента. Esc — вернуться к странице.','Оқу сызбасы, пациенттің суреті емес. Esc — бетке оралу.')}</p>}
        {screenError&&<p className="artery-export-message" role="alert">{t('Используйте Esc или системную кнопку выхода из полного экрана.','Esc немесе жүйенің толық экраннан шығу батырмасын пайдаланыңыз.')}</p>}
        {exportStatus&&<p className={'artery-export-message '+exportStatus} role={exportStatus==='failed'?'alert':'status'}>{exportStatus==='saved'?t('PNG подготовлен к скачиванию. В изображение включены параметры и легенда.','PNG жүктеуге дайын. Суретке параметрлер мен шартты белгілер қосылған.'):t('Не удалось сохранить PNG. Повторите попытку или выберите схему 2D.','PNG сақтау мүмкін болмады. Қайталап көріңіз немесе 2D сызбасын таңдаңыз.')}</p>}
        {sceneUnavailable&&<div className="artery-recovery" role="status"><div><strong>{t('Продолжаем в 2D','2D режимінде жалғастырамыз')}</strong><p>{t('3D-модуль или графический контекст недоступен. Срез, сравнение и PNG работают; параметры сохранены.','3D модулі немесе графикалық контекст қолжетімсіз. Қима, салыстыру және PNG жұмыс істейді; параметрлер сақталған.')}</p></div><button type="button" onClick={retryScene}><RotateCcw size={14}/>{t('Повторить 3D','3D қайта қосу')}</button></div>}
        {displayMode==='3d'?<SceneBoundary key={sceneAttempt} onUnavailable={unavailable}><Suspense fallback={<div className="artery-loading" role="status">{t('Загрузка 3D…','3D жүктелуде…')}</div>}><ArteryScene compare={compare} narrowing={narrowing} sectionPosition={sectionPosition} cutaway={cutaway} moving={moving} reset={reset} view={view} highlight={topics[topic].color as 'wall'|'plaque'|'lumen'} t={t} captureRef={capture} onReady={setSceneReady} onUnavailable={unavailable}/></Suspense></SceneBoundary>:<div className={'artery-diagram'+(compare?' artery-diagram-comparison':'')} aria-label={t('Учебная схема поперечного сечения','Көлденең қиманың оқу сызбасы')}>
          {(compare?[true,false]:[false]).map(reference=><figure key={String(reference)}><svg viewBox="0 0 240 240" role="img" aria-label={reference?t('Исходное сечение: диаметр и площадь 100%.','Бастапқы қима: диаметрі мен ауданы 100%.'):t(`Срез x=${sectionPosition.toFixed(1)}: диаметр ${section.diameterPercent.toFixed(1)}%, площадь просвета ${section.areaPercent.toFixed(1)}% исходной.`,`Қима x=${sectionPosition.toFixed(1)}: диаметр бастапқының ${section.diameterPercent.toFixed(1)}%, қуыс ауданы ${section.areaPercent.toFixed(1)}%.`)}><circle cx="120" cy="120" r="102" fill="#cf7b87"/><circle cx="120" cy="120" r="85" fill={reference?'#173d48':'#e7b961'}/>{!reference&&<circle cx="120" cy="120" r={85*section.radius} fill="#173d48"/>}<circle cx="120" cy="120" r="85" fill="none" stroke="#f4efe0" strokeWidth="1" strokeDasharray="3 5"/><path d={`M${120-85*(reference?1:section.radius)} 120H${120+85*(reference?1:section.radius)}`} stroke="#a5eff5" strokeWidth="2"/><circle cx="120" cy="120" r="110" fill="none" stroke="#9de6ee" strokeOpacity=".6" strokeWidth="1"/></svg><figcaption><strong>{reference?t('Без сужения','Тарылусыз'):t('Выбранное сечение','Таңдалған қима')}</strong><span>{reference?t('Диаметр 100% · площадь 100%','Диаметр 100% · аудан 100%'):t(`Диаметр ${section.diameterPercent.toFixed(1)}% · площадь ${section.areaPercent.toFixed(1)}%`,`Диаметр ${section.diameterPercent.toFixed(1)}% · аудан ${section.areaPercent.toFixed(1)}%`)}</span><small>x = {sectionPosition.toFixed(1)}</small></figcaption></figure>)}
        </div>}
        <div className="artery-legend" role="group" aria-label={t('Выделить часть модели','Модель бөлігін ерекшелеу')}>{topics.map((x,i) => <button key={x.color} aria-pressed={topic===i} onClick={()=>setTopic(i)}><i className={x.color}/>{x.name}</button>)}{displayMode==='3d'&&<span><i className="blood"/>{t('Условные частицы','Шартты бөлшектер')}</span>}<span><i className="section-marker"/>{t('Выбранное сечение','Таңдалған қима')}</span></div>
        <ArteryProfile narrowing={narrowing} position={sectionPosition} onChange={setSectionPosition} t={t}/>
        <div className="artery-scene-tools"><button disabled={!sceneReady} className={cutaway ? 'selected' : ''} aria-pressed={cutaway} onClick={() => setCutaway(x => !x)}><Scissors size={15}/>{t('Разрез','Қима')}</button><button disabled={!sceneReady} aria-pressed={moving} onClick={() => setMoving(x => !x)}>{moving ? <Pause size={15}/> : <Play size={15}/>} {moving ? t('Пауза','Кідірту') : t('Движение частиц','Бөлшектер қозғалысы')}</button><button onClick={resetAll}><RotateCcw size={15}/>{t('Сбросить','Қалпына келтіру')}</button></div>
        <p className="artery-hint"><Move size={14}/>{displayMode==='3d'?t('Перетащите для вращения · кнопки + / − для масштаба · доступны клавиши со стрелками','Айналдыру үшін сүйреңіз · масштаб үшін + / − батырмалары · бағыттау пернелері де жұмыс істейді'):t('2D: выберите срез на продольном профиле или ползунком · масштаб двух сечений одинаков','2D: қиманы бойлық профильден немесе жүгірткімен таңдаңыз · екі қиманың масштабы бірдей')}</p>
      </section>
      <Card className="artery-controls" title={t('Геометрия сужения','Тарылу геометриясы')}>
        <label className="artery-slider-label" htmlFor="artery-narrowing"><span>{t('Максимальное сужение диаметра','Диаметрдің ең үлкен тарылуы')}</span><output htmlFor="artery-narrowing">{narrowing}<small>%</small></output></label>
        <input id="artery-narrowing" type="range" min="0" max="80" step="1" value={narrowing} onChange={e => setNarrowing(clampNarrowing(Number(e.target.value)))}/>
        <div className="artery-range-labels"><span>0%</span><span>80%</span></div>
        <div className="artery-presets" role="group" aria-label={t('Примеры геометрии','Геометрия мысалдары')}>{[0, 25, 50, 75].map(n => <button key={n} aria-pressed={narrowing === n} className={narrowing === n ? 'selected' : ''} onClick={() => setNarrowing(n)}>{n}%</button>)}</div>
        <p className="artery-control-note">{t('Примеры формы, а не клинические стадии. Ползунок изменяет диаметр в самом узком месте.','Клиникалық сатылар емес, пішін мысалдары. Жүгірткі ең тар жердегі диаметрді өзгертеді.')}</p>
        <div className="artery-section-position">
          <label htmlFor="artery-section-position"><span>{t('Положение сечения','Қима орны')}</span><output htmlFor="artery-section-position">x = {sectionPosition.toFixed(1)}</output></label>
          <input id="artery-section-position" type="range" min={-HALF_ARTERY_LENGTH} max={HALF_ARTERY_LENGTH} step="0.1" value={sectionPosition} onChange={e=>setSectionPosition(clampSectionPosition(Number(e.target.value)))} aria-valuetext={t(`Положение ${sectionPosition.toFixed(1)}, условные единицы; местное сужение ${section.narrowingPercent.toFixed(1)}%.`,`Орны ${sectionPosition.toFixed(1)}, шартты бірлік; жергілікті тарылу ${section.narrowingPercent.toFixed(1)}%.`)}/>
          <div className="artery-range-labels"><span>−3.6</span><span>{t('Центр: 0','Ортасы: 0')}</span><span>+3.6</span></div>
          <button className="artery-center-reset" onClick={()=>setSectionPosition(0)}><RotateCcw size={13}/>{narrowing>0?t('Самое узкое место','Ең тар жер'):t('К центру','Ортасына')}</button>
          <p>{t('Голубое кольцо в 3D отмечает этот срез. Координата условная, не миллиметры.','3D-дегі көгілдір сақина осы қиманы белгілейді. Координата шартты, миллиметр емес.')}</p>
        </div>
        <div className="artery-section-comparison">
          <figure><svg viewBox="0 0 180 180" role="img" aria-label={t('Исходное сечение без сужения: диаметр и площадь 100%.','Тарылусыз бастапқы қима: диаметрі мен ауданы 100%.')}><circle cx="90" cy="90" r="76" fill="#cf7b87"/><circle cx="90" cy="90" r="63" fill="#173d48"/><path d="M27 90H153" stroke="#fff9" strokeWidth="1" strokeDasharray="3 4"/></svg><figcaption>{t('Без сужения','Тарылусыз')}<small>{t('Исходная геометрия','Бастапқы геометрия')}</small></figcaption></figure>
          <figure><svg viewBox="0 0 180 180" role="img" aria-label={t(`Выбранное сечение x=${sectionPosition.toFixed(1)}: местное сужение ${section.narrowingPercent.toFixed(1)}%, площадь просвета ${section.areaPercent.toFixed(1)}% от исходной.`,`Таңдалған қима x=${sectionPosition.toFixed(1)}: жергілікті тарылу ${section.narrowingPercent.toFixed(1)}%, қуыс ауданы бастапқының ${section.areaPercent.toFixed(1)}%.`)}><circle cx="90" cy="90" r="76" fill="#cf7b87"/><circle cx="90" cy="90" r="63" fill="#e7b961"/><circle cx="90" cy="90" r={63*section.radius} fill="#173d48"/><path d="M27 90H153" stroke="#fff9" strokeWidth="1" strokeDasharray="3 4"/><circle cx="90" cy="90" r="63" fill="none" stroke="#fff9" strokeWidth="1" strokeDasharray="3 4"/></svg><figcaption>{t('Выбранное сечение','Таңдалған қима')}<small>x = {sectionPosition.toFixed(1)}</small></figcaption></figure>
        </div>
        <div className="artery-local-metrics" aria-live="polite"><div><span>{t('Диаметр среза','Қима диаметрі')}</span><strong>{section.diameterPercent.toFixed(1)}<small>%</small></strong></div><div><span>{t('Площадь просвета','Қуыс ауданы')}</span><strong>{section.areaPercent.toFixed(1)}<small>%</small></strong></div><div><span>{t('Потеря площади','Ауданның азаюы')}</span><strong>{section.areaLossPercent.toFixed(1)}<small>%</small></strong></div></div>
        <p className="artery-formula">A(x) / A₀ = [d(x) / d₀]²<br/>{t('Диаметр и площадь — относительно исходного сечения. Потеря площади = 100% − оставшаяся площадь. Эти числа относятся к выбранному срезу; ползунок сверху задаёт максимальное сужение в центре.','Диаметр мен аудан бастапқы қимаға қатысты. Ауданның азаюы = 100% − қалған аудан. Бұл сандар таңдалған қимаға қатысты; жоғарғы жүгірткі ортасындағы ең үлкен тарылуды белгілейді.')}</p>
        <div className="artery-view-switch" role="group" aria-label={t('Ракурс камеры · только в 3D','Камера көрінісі · тек 3D режимінде')}><button disabled={!sceneReady} aria-pressed={view === 'side'} onClick={() => {setView('side'); setReset(n => n + 1);}}>{t('Сбоку','Бүйірінен')}</button><button disabled={!sceneReady} aria-pressed={view === 'top'} onClick={() => {setView('top'); setReset(n => n + 1);}}>{t('Сверху','Үстінен')}</button><button disabled={!sceneReady} aria-pressed={view === 'end'} onClick={() => {setView('end'); setReset(n => n + 1);}}>{t('С торца','Ұшынан')}</button></div>
      </Card>
    </div>
    <section className="artery-explainer" id="artery-description"><div role="group" aria-label={t('Что показано на модели','Модельде не көрсетілген')}>{topics.map((x, i) => <button key={x.color} className={topic === i ? 'selected' : ''} aria-pressed={topic === i} onClick={() => setTopic(i)}><i className={x.color}/>{x.name}</button>)}</div><h3>{topics[topic].name}</h3><p>{topics[topic].text}</p></section>
    <div className="artery-footnote"><p>{t('Масштаб и форма упрощены. Движение частиц — иллюстрация: скорость, давление и объёмный кровоток не рассчитываются. Процент сужения не означает вероятность инфаркта.','Масштаб пен пішін жеңілдетілген. Бөлшектер қозғалысы — иллюстрация: жылдамдық, қысым және қан ағынының көлемі есептелмейді. Тарылу пайызы инфаркт ықтималдығын білдірмейді.')}</p><a href="https://www.nhlbi.nih.gov/health/atherosclerosis" target="_blank" rel="noreferrer noopener">{t('Об атеросклерозе · NHLBI / NIH','Атеросклероз туралы · NHLBI / NIH')}<ArrowUpRight size={15}/></a></div>
  </div>;
}
