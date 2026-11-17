// Production smoke test. Supply {username,password} through hidden stdin only.
// The script never saves credentials, cookies, form values or request bodies.
import {writeFile} from 'node:fs/promises';
const base='https://cardioresearch-aidana-2027.happyburr1.chatgpt.site';
const checks=[];
const check=(name,ok)=>{checks.push({name,passed:!!ok});if(!ok)throw new Error(name);};
function hiddenInput(){return new Promise(resolve=>{let value='';if(process.stdin.isTTY)process.stdin.setRawMode(true);process.stdin.setEncoding('utf8');process.stdin.resume();process.stdin.on('data',chunk=>{for(const char of chunk){if(char==='\u0003')process.exit(130);if(char==='\r'||char==='\n'){if(process.stdin.isTTY)process.stdin.setRawMode(false);process.stdin.pause();resolve(JSON.parse(value));return;}value+=char;}});});}
console.log('Ready for owner test credentials on hidden stdin.');
const auth=await hiddenInput();
try{
 const status=await fetch(base+'/api/auth/session');check('anonymous session is JSON',status.status===200&&status.headers.get('content-type')?.includes('application/json'));
 check('anonymous visitor is a demo guest',(await status.json()).mode==='demo');
 for(const path of ['/api/predict','/api/report','/api/batch/brfss','/api/batch/validate/brfss','/api/scenarios']){
  const r=await fetch(base+path,{method:'POST',headers:{Origin:base},body:'{}'});check('guest denied '+path,r.status===401);
 }
 const demo=await(await fetch(base+'/api/demo/brfss?lang=kk')).json();check('fixed real-model demonstration',demo.synthetic&&Math.abs(demo.prediction.probability-0.026823487279290383)<1e-12);
 for(const dataset of ['brfss','uci']){
  const fixed=await(await fetch(base+'/api/scenario-demo/'+dataset+'?lang=kk')).json();check(dataset+' public scenario demo',fixed.synthetic===true&&fixed.dataset===dataset&&fixed.points.length===4);
  const same=fixed.points.find(p=>p.value===fixed.baseline.values[fixed.feature]);check(dataset+' baseline scenario delta is zero',same&&Math.abs(same.delta)<1e-12);
  const meta=await(await fetch(base+'/api/reproducibility/'+dataset)).json();check(dataset+' reproducibility metadata',meta.model_version===fixed.version&&!!meta.protocol.primary_metric&&!!meta.environment.python);
 }
 const login=await fetch(base+'/api/auth/login',{method:'POST',headers:{Origin:base,'Content-Type':'application/json'},body:JSON.stringify(auth)});
 check('owner login succeeds',login.status===200);const cookieHeader=login.headers.get('set-cookie')||'';check('secure session cookie',cookieHeader.includes('HttpOnly')&&cookieHeader.includes('Secure')&&cookieHeader.includes('SameSite=Strict'));
 const cookie=cookieHeader.split(';')[0];const headers={Origin:base,Cookie:cookie,'Content-Type':'application/json'};
 const session=await(await fetch(base+'/api/auth/session',{headers:{Cookie:cookie}})).json();check('owner session is full',session.authenticated===true&&session.mode==='full');
 const values={...demo.values,bmi:28};const payload=JSON.stringify({dataset:'brfss',values,lang:'kk',explain:true});
 const pred=await fetch(base+'/api/predict',{method:'POST',headers,body:payload});check('custom owner prediction',pred.status===200);const result=await pred.json();check('loaded model version',result.version==='b40179c28ed8'&&result.probability!==demo.prediction.probability);
 const scenario=await fetch(base+'/api/scenarios',{method:'POST',headers,body:JSON.stringify({dataset:'brfss',values,vary:{feature:'bmi',values:[22,28,35]},lang:'kk'})});check('owner custom scenarios',scenario.status===200);const varied=await scenario.json();check('scenarios preserve original pipeline probability',Math.abs(varied.baseline.probability-result.probability)<1e-12&&Math.abs(varied.points[1].delta)<1e-12);
 const oversized=await fetch(base+'/api/scenarios',{method:'POST',headers,body:JSON.stringify({dataset:'brfss',values,vary:{feature:'bmi',values:Array.from({length:10},(_,i)=>20+i)}})});check('scenario point budget enforced',oversized.status===422);
 const pdf=await fetch(base+'/api/report',{method:'POST',headers,body:payload});check('owner PDF export',pdf.status===200&&pdf.headers.get('content-type')==='application/pdf'&&(await pdf.arrayBuffer()).byteLength>10000);
 const csv=await(await fetch(base+'/api/template/brfss')).text();const batch=await fetch(base+'/api/batch/brfss',{method:'POST',headers:{Origin:base,Cookie:cookie},body:csv});check('owner CSV export',batch.status===200&&(await batch.text()).includes('b40179c28ed8'));
 const out=await fetch(base+'/api/auth/logout',{method:'POST',headers,body:'{}'});check('logout clears cookie',out.status===200&&out.headers.get('set-cookie')?.includes('Max-Age=0'));
}catch(error){checks.push({name:'test stopped',passed:false,reason:String(error.message).slice(0,180)});}
auth.password='';
const report={url:base,checked_at:new Date().toISOString(),checks,passed:checks.every(c=>c.passed)};
await writeFile(new URL('../reports/hosting_auth_http_qa.json',import.meta.url),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report));process.exitCode=report.passed?0:1;
