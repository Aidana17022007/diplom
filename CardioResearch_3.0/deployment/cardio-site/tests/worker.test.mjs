import test from 'node:test';
import assert from 'node:assert/strict';
import worker,{parseCSV} from '../dist/server/index.js';
import {PDFDocument} from 'pdf-lib';
import {pbkdf2Sync} from 'node:crypto';

const origin='https://cardioresearch.example';
const values={age_group:7,sex:1,bmi:27,smoking:4,activity:1,diabetes:3,hypertension:3,cholesterol:2,general_health:3,physical_days:2,mental_days:1};
// Synthetic test credentials only; production values live in hosting secrets.
const salt=Buffer.alloc(16,13), password='test-only-owner-password';
const env={CARDIO_AUTH_USERNAME:'test-owner',CARDIO_AUTH_PASSWORD_HASH:'pbkdf2-sha256$100000$'+salt.toString('base64url')+'$'+pbkdf2Sync(password,salt,100000,32,'sha256').toString('base64url'),CARDIO_SESSION_SECRET:Buffer.alloc(32,17).toString('base64url')};
const rawCall=(path,options={},bindings=env)=>worker.fetch(new Request(origin+path,options),bindings);
const loginResponse=await rawCall('/api/auth/login',{method:'POST',headers:{origin,'Content-Type':'application/json'},body:JSON.stringify({username:'test-owner',password})});
assert.equal(loginResponse.status,200);
const cookie=loginResponse.headers.get('set-cookie').split(';')[0];
const call=(path,options={})=>rawCall(path,{...options,headers:{origin,cookie,...options.headers}});
const post=(path,input)=>call(path,{method:'POST',headers:{'Content-Type':'application/json',origin},body:JSON.stringify(input)});

test('frontend and aggregate routes are available while private artifacts are inaccessible',async()=>{
 for(const path of ['/','/api/health','/api/schema/brfss','/api/schema/uci','/api/research/brfss','/api/data/uci','/api/environment','/api/reliability','/api/quality','/api/library','/api/experiments'])assert.equal((await call(path)).status,200,path);
 for(const path of ['/data/models.json','/reports/student_profile.json','/models/uci.joblib','/api/missing'])assert.equal((await call(path)).status,404,path);
 const html=await(await call('/')).text();assert.ok(html.includes('CardioResearch'));const asset=html.match(/src="([^"]+\.js)"/)[1];assert.equal((await call(asset)).status,200);
 const library=await(await call('/api/library')).json();assert.equal(library.counts.atherosclerosis,12);
 assert.equal(library.counts.papers,library.papers.length);
 assert.ok(library.papers.some(row=>row.doi==='10.1186/s12916-019-1466-7'));
 const suggested=library.papers.find(row=>row.doi==='10.1016/j.atherosclerosis.2026.120745');
 assert.equal(suggested?.verification_scope,'abstract');assert.equal(suggested?.pubmed_url,'https://pubmed.ncbi.nlm.nih.gov/42177119/');
});
test('guests receive fixed demo predictions and cannot invoke protected actions',async()=>{
 const session=await(await rawCall('/api/auth/session')).json();assert.deepEqual(session,{authenticated:false,mode:'demo'});
 for(const ds of ['brfss','uci']){
  const a=await(await rawCall('/api/demo/'+ds+'?lang=kk')).json();
  const b=await(await rawCall('/api/demo/'+ds+'?lang=kk&bmi=99&age_group=14')).json();
  assert.equal(a.synthetic,true);assert.equal(a.prediction.dataset,ds);assert.deepEqual(a,b);
 }
 for(const path of ['/api/predict','/api/report','/api/batch/brfss','/api/batch/validate/uci'])assert.equal((await rawCall(path,{method:'POST',headers:{origin},body:'{}'})).status,401,path);
 assert.equal((await rawCall('/api/predict',{method:'POST',headers:{origin,cookie:'__Host-cardio_session=forged'},body:'{}'})).status,401);
 assert.equal((await rawCall('/api/predict',{method:'POST',headers:{origin},body:'{}'},{})).status,503);
 assert.equal((await rawCall('/api/auth/session',{},{})).status,503);
 assert.equal((await rawCall('/api/auth/login',{method:'POST',body:'{}'})).status,403);
 assert.equal((await rawCall('/api/auth/login',{method:'POST',headers:{origin:'https://other.example'},body:'{}'})).status,403);
 assert.equal((await rawCall('/api/auth/login',{method:'POST',headers:{origin},body:'x'.repeat(4097)})).status,413);
 const signedIn=await(await call('/api/auth/session')).json();assert.equal(signedIn.authenticated,true);
 const signedOut=await call('/api/auth/logout',{method:'POST',body:'{}'});assert.match(signedOut.headers.get('set-cookie'),/Max-Age=0/);
});
test('BRFSS deployed artifact reproduces Python result including explanations',async()=>{
 const response=await post('/api/predict',{dataset:'brfss',values,explain:true,lang:'kk'});assert.equal(response.status,200);
 const result=await response.json();assert.ok(Math.abs(result.probability-0.026823487279290383)<1e-12);assert.equal(result.version,'b40179c28ed8');
 const e=result.explanation;assert.equal(e.units,'raw_model_probability');assert.ok(Math.abs(e.baseline+e.contributions.reduce((s,c)=>s+c.value,0)-e.raw_probability)<1e-12);
 assert.equal(response.headers.get('cache-control'),'no-store');
});
test('strict JSON types, category range, minimum fields and size limit',async()=>{
 for(const input of [{values:{...values,bmi:'27'}},{values:{...values,bmi:true}},{values:{...values,age_group:14}},{values:{sex:1}},{values,explain:null},{values,lang:'en'},{values,secret:'bad'}])assert.equal((await post('/api/predict',input)).status,422);
 assert.equal((await call('/api/predict',{method:'POST',body:'x'.repeat(32769)})).status,413);
 assert.equal((await call('/api/predict',{method:'POST',headers:{origin:'https://other.example'},body:JSON.stringify({values})})).status,403);
});
test('CSV validation identifies line3, blocks errors and exports the real model version',async()=>{
 const template=await(await call('/api/template/brfss')).text();
 const response=await call('/api/batch/validate/brfss',{method:'POST',body:template});assert.equal((await response.json()).valid_rows,1);
 const bad=template+'14,1,27,4,1,3,3,2,3,2,1\r\n';
 const validation=await(await call('/api/batch/validate/brfss',{method:'POST',body:bad})).json();assert.equal(validation.invalid_rows,1);assert.equal(validation.errors[0].line,3);
 assert.equal((await call('/api/batch/brfss',{method:'POST',body:bad})).status,422);
 const output=await(await call('/api/batch/brfss',{method:'POST',body:template})).text();assert.ok(output.includes('b40179c28ed8'));assert.ok(output.includes('model_probability'));
 const header=template.trim().split('\r\n')[0],line=template.trim().split('\r\n')[1];
 assert.equal((await call('/api/batch/brfss',{method:'POST',body:header+'\r\n'+(line+'\r\n').repeat(1001)})).status,422);
 assert.equal((await call('/api/batch/brfss',{method:'POST',body:'x'.repeat(1024*1024+1)})).status,413);
});
test('CSV parser supports quoted commas, escaped quotes and physical line numbers',()=>{
 const rows=parseCSV('a,b\r\n"x,y","a""b"\r\n"line\nwrap",z\r\n1,2');
 assert.deepEqual(rows.map(r=>r.line),[1,2,3,5]);assert.deepEqual(rows[1].cells,['x,y','a"b']);
 assert.throws(()=>parseCSV('a\n"unfinished'));
});
test('metrics export retains comparable sample sizes and weighting',async()=>{
 const text=await(await call('/api/research-export/brfss?experiment=benchmark')).text();assert.equal(text.trim().split('\r\n').length,9);assert.ok(text.includes('12000,12000,0.5,unweighted'));
 assert.equal((await call('/api/research-export/uci?experiment=full')).status,404);
});
test('hosted PDF embeds a Cyrillic-capable font and returns a valid document',async()=>{
 const response=await post('/api/report',{dataset:'brfss',values,explain:true,lang:'kk'});assert.equal(response.status,200);assert.equal(response.headers.get('content-type'),'application/pdf');
 const bytes=new Uint8Array(await response.arrayBuffer());assert.ok(bytes.length>10000);const pdf=await PDFDocument.load(bytes);assert.ok(pdf.getPageCount()>=1);assert.ok(pdf.getPageCount()<=3);
});
