import {useEffect,useRef,useState,ReactNode} from 'react';
import {Info,LoaderCircle,AlertCircle,ArrowUpRight,Download} from 'lucide-react';
import MetricsExplorer from './MetricsExplorer';
import {metricLabels} from './modelMetrics';
import {loadChartRuntime,chartFileName,ChartRuntime} from './chart-runtime';

export type Lang='ru'|'kk';
export type T=(ru:string,kk:string)=>string;
export type Field={name:string;label:string;kind:string;group:string;source?:string;options?:{value:number;label:string}[];min?:number;max?:number;step?:number};
export type Values=Record<string,number|null>;
export const colors=['#138f81','#537eac','#d29b47','#9b75ad','#65a799','#bf7780','#849d4b','#8d9aa8'];
export const metricNames=metricLabels;
export const fmt=(n:number,d=3)=>Number.isFinite(n)?n.toFixed(d):'—';
export const count=(n:number)=>Number(n||0).toLocaleString('ru-RU');
export function errorText(value:any):string{
  if(typeof value==='string')return value;
  if(Array.isArray(value))return value.map(errorText).join('; ');
  if(value?.message)return value.message+(value.errors?.length?' · '+value.errors.map((e:any)=>`${e.label||e.field||''}: ${e.message||errorText(e)}`).join('; '):'');
  if(value?.errors)return errorText(value.errors);
  if(value?.msg)return `${value.loc?.slice(-1).join('')||''}: ${value.msg}`;
  return 'Не удалось выполнить запрос / Сұрау орындалмады';
}
export async function api(path:string,init?:RequestInit){const r=await fetch('/api'+path,init);if(!r.ok){let e;try{e=await r.json()}catch{e={detail:r.statusText}}throw Error(errorText(e.detail||e))}return r.json()}
export function post(values:Values,dataset:string,explain=true,lang:Lang='ru'){return {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dataset,values,explain,lang})}}
export async function downloadResponse(response:Response,name:string){if(!response.ok){let e;try{e=await response.json()}catch{e={detail:response.statusText}}throw Error(errorText(e.detail||e))}const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
export function Card({title,subtitle,children,className='',action}:{title?:string;subtitle?:string;children:ReactNode;className?:string;action?:ReactNode}){return <section className={'card '+className}>{title&&<div className="card-heading"><div><h2>{title}</h2>{subtitle&&<p>{subtitle}</p>}</div>{action}</div>}{children}</section>}
export function Note({children,tone='neutral'}:{children:ReactNode;tone?:'neutral'|'amber'|'teal'}){return <div className={'note '+tone}><Info size={17}/><div>{children}</div></div>}
export function Loading({text}:{text:string}){return <div className="loading" role="status"><LoaderCircle className="spin" size={23}/><span>{text}</span></div>}
export function Empty({title,body,children}:{title:string;body:string;children?:ReactNode}){return <div className="empty"><div className="empty-icon"><Info size={27}/></div><h3>{title}</h3><p>{body}</p>{children}</div>}
export function Chart({data,layout={},height=330,label='График / График',lang}:{data:any[];layout?:any;height?:number;label?:string;lang?:Lang}){
  const ref=useRef<HTMLDivElement>(null),runtime=useRef<ChartRuntime|null>(null),mounted=useRef(false);
  const [error,setError]=useState(false),[loading,setLoading]=useState(true),[attempt,setAttempt]=useState(0),[exporting,setExporting]=useState(false),[exportError,setExportError]=useState(false);
  const text=(ru:string,kk:string)=>lang==='ru'?ru:lang==='kk'?kk:`${ru} / ${kk}`;
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[]);
  useEffect(()=>{let canceled=false;let plot:any;const node=ref.current;let observer:ResizeObserver|undefined;
    setError(false);setLoading(true);setExportError(false);runtime.current=null;
    loadChartRuntime().then(async P=>{
      plot=P;if(canceled||!node)return;
      await P.react(node,data,{height,paper_bgcolor:'transparent',plot_bgcolor:'transparent',font:{family:'Segoe UI, sans-serif',size:12,color:'#506973'},margin:{t:20,r:18,b:48,l:55},colorway:colors,xaxis:{gridcolor:'#e5ece9',zeroline:false},yaxis:{gridcolor:'#e5ece9',zeroline:false},legend:{orientation:'h',y:-.22,font:{size:12}},...layout},{responsive:true,displayModeBar:false});
      if(canceled)return;runtime.current=P;setLoading(false);
      observer=new ResizeObserver(()=>{if(!canceled)Promise.resolve(P.Plots.resize(node)).catch(()=>{if(!canceled)setError(true)})});observer.observe(node);
    }).catch(()=>{if(!canceled){setError(true);setLoading(false)}});
    return()=>{canceled=true;observer?.disconnect();runtime.current=null;if(plot&&node)plot.purge(node)};
  },[JSON.stringify(data),JSON.stringify(layout),height,attempt]);
  const exportPng=async()=>{
    const node=ref.current,P=runtime.current;
    if(!node||!P||loading||error||exporting)return;
    setExporting(true);setExportError(false);
    // Existing charts without a custom label inherit their visible card heading for the filename.
    const context=label==='График / График'?node.closest('.card')?.querySelector('h2')?.textContent||label:label;
    try{await P.downloadImage(node,{format:'png',filename:chartFileName(context),width:Math.max(1,Math.round(node.clientWidth)),height,scale:2})}
    catch{if(mounted.current)setExportError(true)}
    finally{if(mounted.current)setExporting(false)}
  };
  return <div className="chart-shell" style={{position:'relative',minHeight:height}} aria-busy={loading&&!error}>
    <div className="chart" ref={ref} role="img" aria-label={label} style={{minHeight:height,visibility:error?'hidden':undefined}}/>
    {loading&&!error&&<div className="chart-loading-overlay" role="status"><LoaderCircle className="spin" size={21}/><span>{text('Загрузка графика','График жүктелуде')}</span></div>}
    {error&&<div className="chart-error-overlay" role="alert"><AlertCircle size={21}/><span>{text('График недоступен','График қолжетімсіз')}</span><button type="button" className="secondary compact" onClick={()=>setAttempt(x=>x+1)}>{text('Повторить','Қайталау')}</button></div>}
    {!loading&&!error&&<div style={{display:'flex',justifyContent:'flex-end',alignItems:'center',flexWrap:'wrap',gap:10,marginTop:8}}>
      {exportError&&<span role="alert" style={{fontSize:12,color:'#955c42'}}>{text('Не удалось сохранить PNG. Повторите попытку.','PNG сақтау мүмкін болмады. Қайталап көріңіз.')}</span>}
      <button type="button" className="secondary compact" disabled={exporting} onClick={exportPng} aria-label={`${text('Скачать график в PNG','Графикті PNG түрінде жүктеу')}: ${label}`} title={text('PNG с двойным разрешением','Екі еселенген ажыратымдылықтағы PNG')}>{exporting?<LoaderCircle size={15} className="spin"/>:<Download size={15}/>}<span>{exporting?text('Сохранение…','Сақталуда…'):'PNG'}</span></button>
    </div>}
  </div>;
}
export function MetricsTable({rows,selected,t,sd=true,context}:{rows:any[];selected?:string;t:T;sd?:boolean;context?:{dataset:string;experiment:string;evaluation:string;weighting:string}}){
 return <MetricsExplorer rows={rows} selected={selected} t={t} sd={sd} context={context}/>;
}
export function ExternalLink({url,children}:{url?:string;children:ReactNode}){return url?<a className="inline-link" href={url} target="_blank" rel="noreferrer noopener">{children}<ArrowUpRight size={15}/></a>:<span>{children}</span>}
