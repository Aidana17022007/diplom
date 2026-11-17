import test from 'node:test';
import assert from 'node:assert/strict';
import {pbkdf2Sync,createHmac,createHash} from 'node:crypto';
import {createAuthHandlers,AUTH_SETTINGS,AuthError} from '../src/auth.js';

// Synthetic fixtures only. These are never deployment credentials.
const PASSWORD='synthetic-test-password';
const salt=Buffer.alloc(16,7),secret=Buffer.alloc(32,11);
const encodedHash='pbkdf2-sha256$100000$'+salt.toString('base64url')+'$'+pbkdf2Sync(PASSWORD,salt,100000,32,'sha256').toString('base64url');
const env={CARDIO_AUTH_USERNAME:'test-owner',CARDIO_AUTH_PASSWORD_HASH:encodedHash,CARDIO_SESSION_SECRET:secret.toString('base64url')};
const start=Date.UTC(2026,10,7,12,0,0);
function request(path='/api/auth/session',{cookie,origin='https://cardio.example',ip='192.0.2.1'}={}) {
  const headers={'CF-Connecting-IP':ip};if(cookie)headers.Cookie=cookie;
  return new Request(origin+path,{headers});
}
function cookie(response){return response.headers.get('Set-Cookie').split(';')[0];}
function tokenOf(value){return value.slice(value.indexOf('=')+1);}
function signedToken(claims){const encoded=Buffer.from(JSON.stringify(claims)).toString('base64url');return encoded+'.'+createHmac('sha256',secret).update(encoded).digest('base64url');}
function claimsOf(value){return JSON.parse(Buffer.from(tokenOf(value).split('.')[0],'base64url').toString('utf8'));}
const credentials={username:env.CARDIO_AUTH_USERNAME,password:PASSWORD};

test('guest status, valid owner login, secure cookie, session and logout',async()=>{
  const auth=createAuthHandlers({clock:()=>start});
  const guest=await auth.authStatus(request(),env);assert.equal(guest.status,200);
  assert.deepEqual(await guest.json(),{authenticated:false,mode:'demo'});
  await assert.rejects(auth.requireSession(request(),env),error=>error instanceof AuthError&&error.status===401);
  const response=await auth.login(request('/api/auth/login'),env,credentials);
  assert.equal(response.status,200);assert.match(response.headers.get('Cache-Control'),/no-store/);
  const header=response.headers.get('Set-Cookie');
  for(const term of ['__Host-cardio_session=','Path=/','Max-Age=28800','HttpOnly','Secure','SameSite=Strict'])assert.ok(header.includes(term),term);
  assert.ok(!header.includes('Domain='));assert.ok(!header.includes(PASSWORD));
  const session=await auth.requireSession(request(undefined,{cookie:cookie(response)}),env);
  assert.equal(session.username,'test-owner');assert.equal(session.mode,'full');
  const status=await auth.authStatus(request(undefined,{cookie:cookie(response)}),env);assert.equal((await status.json()).authenticated,true);
  const end=await auth.logout(request('/api/auth/logout'),env);assert.equal(end.status,200);
  assert.match(end.headers.get('Set-Cookie'),/Max-Age=0/);assert.match(end.headers.get('Set-Cookie'),/HttpOnly; Secure; SameSite=Strict/);
});

test('password and username failures are generic; values are never reflected',async()=>{
  const auth=createAuthHandlers({clock:()=>start});
  const badPassword=await auth.login(request(),env,{...credentials,password:'incorrect-private-value'});
  const badUsername=await auth.login(request(),env,{...credentials,username:'unknown-private-user'});
  assert.equal(badPassword.status,401);assert.equal(badUsername.status,401);
  assert.deepEqual(await badPassword.json(),await badUsername.json());
  for(const body of [null,[],{username:true,password:[]},{username:'x',password:'x'.repeat(1025)}]){
    const result=await auth.login(request(),env,body);assert.equal(result.status,401);assert.equal(result.headers.get('Set-Cookie'),null);
  }
});

test('expired, future, foreign-audience, wrong-version and tampered sessions fail',async()=>{
  let now=start;const auth=createAuthHandlers({clock:()=>now});
  const valid=await auth.login(request(),env,credentials);const original=cookie(valid),claims=claimsOf(original);
  now=start+AUTH_SETTINGS.sessionSeconds*1000;
  assert.equal((await (await auth.authStatus(request(undefined,{cookie:original}),env)).json()).authenticated,false);
  now=start;
  for(const changes of [{v:2},{aud:'https://attacker.example'},{sub:'another-owner'},{iat:claims.iat+60,exp:claims.exp+60},{exp:claims.exp+1},{cred:'wrong'},{jti:'x'}]) {
    const fake=AUTH_SETTINGS.cookieName+'='+signedToken({...claims,...changes});
    await assert.rejects(auth.requireSession(request(undefined,{cookie:fake}),env),error=>error.status===401);
  }
  const tampered=AUTH_SETTINGS.cookieName+'='+tokenOf(original).replace(/.$/,c=>c==='a'?'b':'a');
  await assert.rejects(auth.requireSession(request(undefined,{cookie:tampered}),env),error=>error.status===401);
  await assert.rejects(auth.requireSession(request(undefined,{cookie:original,origin:'https://different.example'}),env),error=>error.status===401);
});

test('malformed/duplicate/oversized cookies and arbitrary signatures fail closed',async()=>{
  const auth=createAuthHandlers({clock:()=>start}),valid=cookie(await auth.login(request(),env,credentials));
  for(const value of [AUTH_SETTINGS.cookieName+'=not.a.token',AUTH_SETTINGS.cookieName+'=%ZZ',valid+'; '+valid,AUTH_SETTINGS.cookieName+'='+'a'.repeat(5000),AUTH_SETTINGS.cookieName+'='+Buffer.from('{}').toString('base64url')+'.'+Buffer.alloc(32).toString('base64url')]){
    const response=await auth.authStatus(request(undefined,{cookie:value}),env);
    assert.equal(response.status,200);assert.deepEqual(await response.json(),{authenticated:false,mode:'demo'});
  }
});

test('missing or malformed environment returns503 and never authenticates',async()=>{
  const auth=createAuthHandlers({clock:()=>start});
  const badEnvs=[{}, {...env,CARDIO_AUTH_USERNAME:''},{...env,CARDIO_AUTH_PASSWORD_HASH:encodedHash.replace('$100000$','$1000$')},{...env,CARDIO_SESSION_SECRET:'short'},{...env,CARDIO_AUTH_PASSWORD_HASH:'plaintext-password'}];
  for(const badEnv of badEnvs){
    assert.equal((await auth.authStatus(request(),badEnv)).status,503);
    assert.equal((await auth.login(request(),badEnv,credentials)).status,503);
    await assert.rejects(auth.requireSession(request(),badEnv),error=>error.status===503);
  }
});

test('credential and signing-secret rotation invalidate existing sessions',async()=>{
  const auth=createAuthHandlers({clock:()=>start}),valid=cookie(await auth.login(request(),env,credentials));
  for(const changed of [{...env,CARDIO_AUTH_USERNAME:'new-owner'},{...env,CARDIO_AUTH_PASSWORD_HASH:encodedHash.replace(salt.toString('base64url'),Buffer.alloc(16,8).toString('base64url'))},{...env,CARDIO_SESSION_SECRET:Buffer.alloc(32,12).toString('base64url')}]){
    await assert.rejects(auth.requireSession(request(undefined,{cookie:valid}),changed),error=>error.status===401);
  }
});

test('best-effort rate limit isolates CF-IP, expires and bounds retained entries',async()=>{
  let now=start;const auth=createAuthHandlers({clock:()=>now,maxRateEntries:2});
  for(let i=0;i<AUTH_SETTINGS.attempts;i++)assert.equal((await auth.login(request(),env,{...credentials,password:'wrong'})).status,401);
  const limited=await auth.login(request(),env,credentials);assert.equal(limited.status,429);assert.equal(limited.headers.get('Retry-After'),'900');
  assert.equal((await auth.login(request(undefined,{ip:'192.0.2.2'}),env,credentials)).status,200);
  now+=AUTH_SETTINGS.windowSeconds*1000;
  assert.equal((await auth.login(request(),env,credentials)).status,200);
  // With a two-entry cap, introducing a third IP evicts the oldest bucket.
  for(const ip of ['192.0.2.10','192.0.2.11','192.0.2.12'])assert.equal((await auth.login(request(undefined,{ip}),env,{...credentials,password:'wrong'})).status,401);
  for(let i=0;i<AUTH_SETTINGS.attempts;i++)assert.equal((await auth.login(request(undefined,{ip:'192.0.2.10'}),env,{...credentials,password:'wrong'})).status,401);
});
