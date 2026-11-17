import {useMemo,useState} from 'react';
import {BookOpen,Search,ArrowUpRight,Copy,Check,FileText,Archive,Code2} from 'lucide-react';
import {Card,Empty,ExternalLink,Lang,Note,T} from './ui';

export default function Library({library,lang,t}:{library:any;lang:Lang;t:T}){
 const [filter,setFilter]=useState('all');const [query,setQuery]=useState('');const [copied,setCopied]=useState('');
 const entries=useMemo(()=>library?[...(library.books||[]).map((x:any)=>({...x,category:'books'})),...(library.papers||[]).map((x:any)=>({...x,category:'papers'})),...(library.software||[]).map((x:any)=>({...x,category:'software'})),...(library.atherosclerosis?.records||[]).map((x:any)=>({...x,category:'archive'}))]:[],[library]);
 const shown=entries.filter((e:any)=>(filter==='all'||e.category===filter)&&`${e.title} ${JSON.stringify(e.authors||'')} ${e.doi||''} ${e.summary_ru||''} ${e.summary_kk||''}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
 const categories=[['all',t('Все источники','Барлық дереккөз')],['books',t('Книги','Кітаптар')],['papers',t('Статьи и данные','Мақалалар мен деректер')],['archive',t('Архив Atherosclerosis','Atherosclerosis архиві')],['software',t('Документация','Құжаттама')]];
 const copy=async(e:any)=>{const text=e.citation||`${Array.isArray(e.authors)?e.authors.join(', '):e.authors||e.publisher||''}. ${e.title}. ${e.year||''}. ${e.doi?'https://doi.org/'+e.doi:e.url||e.official_url||''}`;try{await navigator.clipboard.writeText(text);setCopied(e.category+e.id);setTimeout(()=>setCopied(''),2000)}catch{setCopied('unavailable')}};
 if(!library)return <Card><Empty title={t('Библиотека пока недоступна','Кітапхана әзірге қолжетімсіз')} body={t('Источники загружаются из проверенного локального каталога. Повторите загрузку страницы.','Дереккөздер тексерілген жергілікті каталогтан жүктеледі. Бетті қайта жүктеңіз.')}/></Card>;
 return <>
  <div className="library-banner"><div className="library-banner-icon"><BookOpen size={31}/></div><div><span className="eyebrow">{t('НАУЧНАЯ ОСНОВА','ҒЫЛЫМИ НЕГІЗ')}</span><h2>{t('От источника к обоснованному решению','Дереккөзден негізделген шешімге')}</h2><p>{t('Книги, обзоры, первичные исследования и официальная документация. Ссылки и заметки помогают проверить методику и подготовиться к защите.','Кітаптар, шолулар, түпнұсқа зерттеулер және ресми құжаттама. Сілтемелер мен жазбалар әдістемені тексеруге және қорғауға дайындалуға көмектеседі.')}</p></div><strong>{entries.length}<small>{t('записей в каталоге','каталогтағы жазба')}</small></strong></div>
  {library.atherosclerosis&&<Note tone="teal"><strong>Atherosclerosis · {library.atherosclerosis.archive?.pdf_count||12} PDF. </strong>{t('Архив содержит научные публикации, а не таблицу пациентов. Он дополняет литературную основу; третья обучающая выборка из него не создавалась.','Архивте пациенттер кестесі емес, ғылыми жарияланымдар бар. Ол әдеби негізді толықтырады; одан үшінші оқыту іріктемесі жасалған жоқ.')}</Note>}
  <div className="library-controls"><div className="tabs">{categories.map(([key,title])=><button className={filter===key?'selected':''} key={key} onClick={()=>setFilter(key)}>{title}<span>{key==='all'?entries.length:entries.filter((e:any)=>e.category===key).length}</span></button>)}</div><label className="search"><Search size={18}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder={t('Название, автор или DOI','Атауы, авторы немесе DOI')} aria-label={t('Поиск по библиотеке','Кітапханадан іздеу')}/></label></div>
  {copied==='unavailable'&&<Note>{t('Буфер обмена недоступен. Ссылку можно скопировать из карточки.','Алмасу буфері қолжетімсіз. Сілтемені карточкадан көшіріңіз.')}</Note>}
  <div className="source-grid">{shown.map((e:any)=>{const Icon=e.category==='books'?BookOpen:e.category==='archive'?Archive:e.category==='software'?Code2:FileText;const url=e.url||e.official_url||e.publisher_url||(e.doi?'https://doi.org/'+e.doi:undefined);const authors=Array.isArray(e.authors)?e.authors.join(', '):e.authors||e.publisher||'';return <article className="source-card" key={e.category+e.id}>
   <div className="source-meta"><span><Icon size={16}/>{e.category==='books'?t('Книга','Кітап'):e.category==='archive'?'Atherosclerosis':e.category==='software'?t('Документация','Құжаттама'):e.type==='review'?t('Обзор','Шолу'):t('Исследование / данные','Зерттеу / деректер')}</span><span>{e.year||''}</span></div>
   <h3><ExternalLink url={url}>{e.title}</ExternalLink></h3><p className="source-authors">{authors}</p>
   {e.category==='archive'&&<div className={'relevance '+e.relevance}>{e.relevance==='high'?t('Непосредственно связано с темой','Тақырыпқа тікелей қатысты'):e.relevance==='exclude'?t('Не использовать как исследовательское доказательство','Зерттеу дәлелі ретінде қолданбау'):t('Клинический контекст','Клиникалық контекст')}</div>}
   {e.category==='archive'&&<p className="source-note">{lang==='kk'?e.reason_kk||e.note_kk:e.reason_ru||e.note_ru}</p>}
   {e.verification_scope==='abstract'&&<div className="relevance context">{t('Проверена аннотация','Аннотация тексерілді')}</div>}
   {(e.summary_ru||e.summary_kk)&&<p className="source-note">{lang==='kk'?e.summary_kk:e.summary_ru}</p>}
   {e.doi&&<p className="doi">DOI: {e.doi}</p>}
   <details><summary>{t('Что проверить при чтении','Оқығанда нені тексеру керек')}</summary><div className="source-details">
    {e.category==='archive'?<><p>{lang==='kk'?e.note_kk:e.note_ru}</p><p>{lang==='kk'?e.limitations_kk||e.limitations_ru:e.limitations_ru}</p></>:(e.project_use_ru||e.project_use_kk)?<>
     <p>{lang==='kk'?e.project_use_kk:e.project_use_ru}</p>
     <p>{lang==='kk'?e.verification_kk:e.verification_ru}</p>
     <p>{lang==='kk'?e.limitations_kk:e.limitations_ru}</p>
     {e.source_checked_at&&<small>{t('Дата проверки источника','Дереккөз тексерілген күн')}: {e.source_checked_at}</small>}
    </>:<>
     {lang==='ru'&&<small>{t('Исходные заметки каталога на казахском языке.','Каталогтың бастапқы жазбалары қазақ тілінде.')}</small>}
     <p>{e.project_use||e.supports?.join('; ')||e.use_kz||e.summary_kz}</p>
     <p>{e.legal_access||e.verification}</p><p>{e.limitations||e.limitation}</p>
     {e.pagination_warning&&<p>{e.pagination_warning}</p>}
    </>}
   </div></details>
   {e.pubmed_url&&<p className="source-note"><ExternalLink url={e.pubmed_url}>{t('Проверенная аннотация · PubMed','Тексерілген аннотация · PubMed')}</ExternalLink></p>}
   <div className="source-actions"><a href={url} target="_blank" rel="noreferrer noopener" className="inline-link">{t('Первоисточник','Түпнұсқа')}<ArrowUpRight size={16}/></a><button className="icon-btn" onClick={()=>copy(e)} aria-label={t('Скопировать библиографическую запись','Библиографиялық жазбаны көшіру')}>{copied===e.category+e.id?<Check size={17}/>:<Copy size={17}/>}</button></div>
  </article>})}</div>
  {!shown.length&&<Card><Empty title={t('Источники не найдены','Дереккөз табылмады')} body={t('Попробуйте другое слово или выберите все категории.','Басқа сөз енгізіңіз немесе барлық санатты таңдаңыз.')}/></Card>}
  <Note>{t('Публикации не подтверждают клиническую пригодность этой модели. Липопротеин(а), генетические и молекулярные показатели из статей отсутствуют в используемой анкете и не добавлялись как вымышленные признаки.','Жарияланымдар осы модельдің клиникалық жарамдылығын растамайды. Мақалалардағы липопротеин(а), генетикалық және молекулалық көрсеткіштер қолданылған сауалнамада жоқ және ойдан шығарылған белгі ретінде қосылған жоқ.')}</Note>
 </>;
}
