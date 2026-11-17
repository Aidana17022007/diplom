/** Owner authentication for the public demo Worker.
 *
 * Required secret environment bindings (never commit their values):
 * CARDIO_AUTH_USERNAME: the exact owner username,1–128 characters.
 * CARDIO_AUTH_PASSWORD_HASH:
 *   pbkdf2-sha256$100000$<unpadded-base64url salt16..64bytes>$<digest32bytes>
 *   digest = PBKDF2-HMAC-SHA256(UTF8(password), salt,100000,32bytes).
 * CARDIO_SESSION_SECRET: unpadded-base64url encoding of32..64 random bytes.
 *
 * Routes must enforce same-origin POST and a4KiB body limit before login().
 * A session is an8-hour, origin-bound HMAC token in a secure HttpOnly cookie.
 * Logout clears the browser cookie; this stateless design cannot revoke a copied
 * token individually. Rotating the session secret revokes all sessions. Changing
 * the username/password hash also invalidates sessions through credential binding.
 * Per-IP attempt limits are bounded and local to one Worker isolate, best effort:
 * resets/other isolates/distributed clients require platform-level rate limiting.
 * No passwords, usernames, tokens, or request bodies are logged here.
 */

const encoder = new TextEncoder();
const decoder = new TextDecoder('utf-8', {fatal:true});
export const AUTH_SETTINGS = Object.freeze({
  cookieName:'__Host-cardio_session', version:1, sessionSeconds:8*60*60,
  iterations:100000, attempts:8, windowSeconds:15*60, maxRateEntries:4096,
});

export class AuthError extends Error {
  constructor(status,detail) { super(detail); this.name='AuthError'; this.status=status; this.detail=detail; }
}

function encode64(bytes) {
  let binary='';for(const byte of new Uint8Array(bytes))binary+=String.fromCharCode(byte);
  return btoa(binary).replaceAll('+','-').replaceAll('/','_').replace(/=+$/,'');
}

function decode64(value) {
  if(typeof value!=='string'||!value.length||value.length>4096||!/^[A-Za-z0-9_-]+$/.test(value))throw new Error('Invalid encoding');
  const binary=atob(value.replaceAll('-','+').replaceAll('_','/')+'='.repeat((4-value.length%4)%4));
  const bytes=Uint8Array.from(binary,char=>char.charCodeAt(0));
  if(encode64(bytes)!==value)throw new Error('Noncanonical encoding');
  return bytes;
}

// Fixed-size digest comparisons have no data-dependent early return. HMAC token
// signatures use WebCrypto.verify, which avoids a JavaScript signature comparison.
function equalDigest(a,b) {
  let difference=a.length^b.length;
  for(let i=0;i<32;i++)difference|=a[i]^b[i];
  return difference===0;
}

async function configuration(env) {
  try {
    const username=env?.CARDIO_AUTH_USERNAME, stored=env?.CARDIO_AUTH_PASSWORD_HASH;
    if(typeof username!=='string'||username.length<1||username.length>128||typeof stored!=='string'||stored.length>300)throw new Error();
    const parts=stored.split('$');
    if(parts.length!==4||parts[0]!=='pbkdf2-sha256'||parts[1]!==String(AUTH_SETTINGS.iterations))throw new Error();
    const salt=decode64(parts[2]),digest=decode64(parts[3]),secret=decode64(env.CARDIO_SESSION_SECRET);
    if(salt.length<16||salt.length>64||digest.length!==32||secret.length<32||secret.length>64)throw new Error();
    const key=await crypto.subtle.importKey('raw',secret,{name:'HMAC',hash:'SHA-256'},false,['sign','verify']);
    const usernameDigest=new Uint8Array(await crypto.subtle.digest('SHA-256',encoder.encode(username)));
    const credential=encode64(await crypto.subtle.digest('SHA-256',encoder.encode(username+'\0'+stored)));
    return {username,usernameDigest,salt,digest,key,credential};
  } catch { throw new AuthError(503,'Авторизация временно недоступна'); }
}

function response(body,status=200,extra={}) {
  return new Response(JSON.stringify(body),{status,headers:{
    'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store, private',
    'Pragma':'no-cache','Vary':'Cookie','X-Content-Type-Options':'nosniff',...extra,
  }});
}

function sessionCookie(token,seconds) {
  return `${AUTH_SETTINGS.cookieName}=${token}; Path=/; Max-Age=${seconds}; HttpOnly; Secure; SameSite=Strict`+
    (seconds===0?'; Expires=Thu, 01 Jan 1970 00:00:00 GMT':'');
}

function readCookie(request) {
  const header=request.headers.get('Cookie')||'';
  if(header.length>4096)return null;
  const found=[];
  for(const part of header.split(';')) {
    const split=part.indexOf('=');
    if(split<0)continue;
    if(part.slice(0,split).trim()===AUTH_SETTINGS.cookieName)found.push(part.slice(split+1).trim());
  }
  return found.length===1?found[0]:null;
}

async function verifyToken(request,config,now) {
  const token=readCookie(request);
  if(!token||token.length>2048)return null;
  try {
    const parts=token.split('.');if(parts.length!==2)return null;
    const payloadBytes=decode64(parts[0]),signature=decode64(parts[1]);
    if(signature.length!==32)return null;
    const valid=await crypto.subtle.verify('HMAC',config.key,signature,encoder.encode(parts[0]));
    if(!valid)return null;
    const value=JSON.parse(decoder.decode(payloadBytes));
    if(!value||typeof value!=='object'||Array.isArray(value))return null;
    if(value.v!==AUTH_SETTINGS.version||value.aud!==new URL(request.url).origin||value.sub!==config.username||value.cred!==config.credential)return null;
    if(!Number.isInteger(value.iat)||!Number.isInteger(value.exp)||value.iat>now||value.exp<=now||value.exp-value.iat!==AUTH_SETTINGS.sessionSeconds)return null;
    if(typeof value.jti!=='string'||decode64(value.jti).length!==16)return null;
    return {authenticated:true,mode:'full',username:config.username,expiresAt:value.exp};
  } catch { return null; }
}

/** Injectable clock provides deterministic expiry/rate-limit tests. */
export function createAuthHandlers({clock=Date.now,maxRateEntries=AUTH_SETTINGS.maxRateEntries}={}) {
  const attempts=new Map();
  const requestedLimit=Number.isFinite(maxRateEntries)?maxRateEntries:AUTH_SETTINGS.maxRateEntries;
  const limit=Math.min(AUTH_SETTINGS.maxRateEntries,Math.max(1,Math.floor(requestedLimit)));
  const nowSeconds=()=>Math.floor(clock()/1000);

  function ipKey(request) {
    // Cloudflare supplies this header at the edge; do not trust X-Forwarded-For.
    const ip=request.headers.get('CF-Connecting-IP')||'unknown';
    return ip.length<=64&&/^[a-fA-F0-9:.]+$/.test(ip)?ip:'unknown';
  }

  function consumeAttempt(request,now) {
    for(const [key,bucket] of attempts)if(bucket.until<=now)attempts.delete(key);
    const key=ipKey(request),current=attempts.get(key);
    if(current&&current.count>=AUTH_SETTINGS.attempts)return {allowed:false,retryAfter:current.until-now};
    if(current)current.count++;
    else {
      if(attempts.size>=limit)attempts.delete(attempts.keys().next().value);
      attempts.set(key,{count:1,until:now+AUTH_SETTINGS.windowSeconds});
    }
    return {allowed:true,key};
  }

  async function requireSession(request,env) {
    const config=await configuration(env),session=await verifyToken(request,config,nowSeconds());
    if(!session)throw new AuthError(401,'Для этого действия войдите в аккаунт владельца');
    return session;
  }

  async function authStatus(request,env) {
    try {
      const config=await configuration(env),session=await verifyToken(request,config,nowSeconds());
      return response(session||{authenticated:false,mode:'demo'});
    } catch(error) { return response({detail:error.detail||'Авторизация временно недоступна'},503); }
  }

  async function login(request,env,body) {
    let config;
    try { config=await configuration(env); }
    catch { return response({detail:'Авторизация временно недоступна'},503); }
    const now=nowSeconds(),attempt=consumeAttempt(request,now);
    if(!attempt.allowed)return response({detail:'Слишком много попыток. Попробуйте позже.'},429,{'Retry-After':String(attempt.retryAfter)});
    if(!body||typeof body!=='object'||Array.isArray(body)||typeof body.username!=='string'||typeof body.password!=='string'||body.username.length>128||body.password.length<1||body.password.length>1024)
      return response({detail:'Неверное имя пользователя или пароль'},401);
    try {
      const input=await crypto.subtle.importKey('raw',encoder.encode(body.password),'PBKDF2',false,['deriveBits']);
      const derived=new Uint8Array(await crypto.subtle.deriveBits({name:'PBKDF2',salt:config.salt,iterations:AUTH_SETTINGS.iterations,hash:'SHA-256'},input,256));
      const submittedUsername=new Uint8Array(await crypto.subtle.digest('SHA-256',encoder.encode(body.username)));
      const passwordMatches=equalDigest(derived,config.digest),usernameMatches=equalDigest(submittedUsername,config.usernameDigest);
      if(!passwordMatches||!usernameMatches)return response({detail:'Неверное имя пользователя или пароль'},401);
      const value={v:AUTH_SETTINGS.version,aud:new URL(request.url).origin,sub:config.username,
        iat:now,exp:now+AUTH_SETTINGS.sessionSeconds,cred:config.credential,
        jti:encode64(crypto.getRandomValues(new Uint8Array(16)))};
      const encoded=encode64(encoder.encode(JSON.stringify(value)));
      const signature=encode64(await crypto.subtle.sign('HMAC',config.key,encoder.encode(encoded)));
      attempts.delete(attempt.key);
      return response({authenticated:true,mode:'full',username:config.username,expiresAt:value.exp},200,
        {'Set-Cookie':sessionCookie(encoded+'.'+signature,AUTH_SETTINGS.sessionSeconds)});
    } catch { return response({detail:'Авторизация временно недоступна'},503); }
  }

  async function logout(request,env) {
    try { await configuration(env); }
    catch { return response({detail:'Авторизация временно недоступна'},503,{'Set-Cookie':sessionCookie('',0)}); }
    return response({authenticated:false,mode:'demo'},200,{'Set-Cookie':sessionCookie('',0)});
  }

  return {authStatus,login,logout,requireSession};
}

const shared=createAuthHandlers();
export const authStatus=shared.authStatus;
export const login=shared.login;
export const logout=shared.logout;
export const requireSession=shared.requireSession;
