import {useEffect,useRef,useState} from 'react';
import {CheckCircle2,Eye,EyeOff,KeyRound,LoaderCircle,LockKeyhole,LogIn,X} from 'lucide-react';
import {Lang,T} from './ui';

export type AuthSession={authenticated:boolean;mode:'demo'|'full';username?:string;local?:boolean};
export const GUEST_SESSION:AuthSession={authenticated:false,mode:'demo'};

export function AccessNotice({t,onLogin,compact=false}:{t:T;onLogin:()=>void;compact?:boolean}){
 return <div className={'access-notice '+(compact?'compact':'')}><span className="access-icon"><LockKeyhole size={21}/></span><div><strong>{t('Открытый деморежим','Ашық деморежим')}</strong><p>{t('Исследование и фиксированные примеры доступны всем. Свои данные, PDF и пакетный расчёт доступны владельцу после входа.','Зерттеу мен бекітілген мысалдар бәріне ашық. Жеке деректер, PDF және топтап есептеу иесіне кіргеннен кейін қолжетімді.')}</p></div><button type="button" className="secondary compact" onClick={onLogin}><LogIn size={16}/>{t('Войти владельцу','Иесі ретінде кіру')}</button></div>;
}

export default function AuthGate({lang,onClose,onAuthenticated}:{lang:Lang;onClose:()=>void;onAuthenticated:(session:AuthSession)=>void}){
 const t:T=(ru,kk)=>lang==='kk'?kk:ru;
 const dialog=useRef<HTMLDialogElement>(null);const usernameRef=useRef<HTMLInputElement>(null);
 const active=useRef(true);const controller=useRef<AbortController|null>(null);
 const [username,setUsername]=useState('');const [password,setPassword]=useState('');
 const [visible,setVisible]=useState(false);const [busy,setBusy]=useState(false);const [error,setError]=useState<'credentials'|'limited'|'unavailable'|null>(null);
 useEffect(()=>{active.current=true;dialog.current?.showModal();usernameRef.current?.focus();return()=>{active.current=false;controller.current?.abort();dialog.current?.close()}},[]);
 const submit=async(e:React.FormEvent)=>{
  e.preventDefault();if(busy||!username.trim()||!password)return;
  setBusy(true);setError(null);controller.current=new AbortController();
  try{
   const response=await fetch('/api/auth/login',{method:'POST',credentials:'same-origin',cache:'no-store',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({username:username.trim(),password}),signal:controller.current.signal});
   if(!active.current)return;
   if(!response.ok){setError(response.status===401?'credentials':response.status===429?'limited':'unavailable');return}
   const session=await response.json();
   if(!active.current)return;
   if(session.authenticated!==true||session.mode!=='full'){setError('unavailable');return}
   setPassword('');onAuthenticated({authenticated:true,mode:'full',username:typeof session.username==='string'?session.username.slice(0,80):undefined});
  }catch(e){if(active.current&&(e as Error).name!=='AbortError')setError('unavailable')}
  finally{if(active.current){setPassword('');setBusy(false)}}
 };
 return <dialog ref={dialog} className="auth-dialog" aria-labelledby="auth-title" aria-describedby="auth-description" onCancel={e=>{e.preventDefault();if(!busy)onClose()}}>
  <button className="icon-btn auth-close" type="button" onClick={onClose} disabled={busy} aria-label={t('Закрыть вход','Кіру терезесін жабу')}><X size={20}/></button>
  <div className="auth-emblem"><KeyRound size={30}/></div><div className="eyebrow">CARDIORESEARCH</div>
  <h2 id="auth-title">{t('Рабочее пространство владельца','Иесінің жұмыс кеңістігі')}</h2>
  <p id="auth-description">{t('Войдите для индивидуальных расчётов, PDF-отчётов и обработки CSV. Для просмотра исследования вход не нужен.','Жеке есептеулер, PDF есептер және CSV өңдеу үшін кіріңіз. Зерттеуді көру үшін кіру қажет емес.')}</p>
  <form onSubmit={submit} className="auth-form">
   <label htmlFor="owner-username">{t('Имя пользователя','Пайдаланушы аты')}<input ref={usernameRef} id="owner-username" name="username" autoComplete="username" autoCapitalize="none" spellCheck={false} maxLength={80} value={username} onChange={e=>setUsername(e.target.value)} disabled={busy} required/></label>
   <label htmlFor="owner-password">{t('Пароль','Құпиясөз')}<div className="password-field"><input id="owner-password" name="password" type={visible?'text':'password'} autoComplete="current-password" maxLength={256} value={password} onChange={e=>setPassword(e.target.value)} disabled={busy} required/><button type="button" className="icon-btn" onClick={()=>setVisible(!visible)} disabled={busy} aria-label={visible?t('Скрыть пароль','Құпиясөзді жасыру'):t('Показать пароль','Құпиясөзді көрсету')} aria-pressed={visible}>{visible?<EyeOff size={18}/>:<Eye size={18}/>}</button></div></label>
   {error&&<p className="auth-error" role="alert">{error==='credentials'?t('Не удалось войти. Проверьте имя пользователя и пароль.','Кіру мүмкін болмады. Аты мен құпиясөзін тексеріңіз.'):error==='limited'?t('Слишком много попыток. Подождите и повторите позже.','Әрекет саны тым көп. Біраз күтіп, қайталаңыз.'):t('Вход временно недоступен. Попробуйте ещё раз.','Кіру уақытша қолжетімсіз. Қайта көріңіз.')}</p>}
   <button type="submit" className="primary full-width" disabled={busy||!username.trim()||!password}>{busy?<LoaderCircle size={18} className="spin"/>:<LogIn size={18}/>} {busy?t('Выполняем вход…','Кіру орындалуда…'):t('Войти','Кіру')}</button>
  </form>
  <div className="auth-benefits"><span><CheckCircle2 size={15}/>{t('Свои показатели','Жеке көрсеткіштер')}</span><span><CheckCircle2 size={15}/>PDF / CSV</span></div>
  <button className="text-btn auth-guest" type="button" onClick={onClose} disabled={busy}>{t('Продолжить в деморежиме','Деморежимде жалғастыру')}</button>
 </dialog>;
}
