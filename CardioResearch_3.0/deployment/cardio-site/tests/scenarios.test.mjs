import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {pbkdf2Sync} from 'node:crypto';
import worker from '../dist/server/index.js';
import {runScenarios,scenarioDemo,reproducibilityMetadata} from '../src/scenarios.js';
import {predictPayload} from '../src/inference.js';

const models=JSON.parse(fs.readFileSync(new URL('../data/models.json',import.meta.url),'utf8'));
const reports=JSON.parse(fs.readFileSync(new URL('../data/reports.json',import.meta.url),'utf8'));
const origin='https://scenarios.example';
const demo=scenarioDemo(models,'brfss','ru');
const payload={dataset:'brfss',values:demo.baseline.values,vary:{feature:'bmi',values:[22,27,32,37]},lang:'kk'};
const salt=Buffer.alloc(16,19),password='synthetic-scenarios-password';
const env={CARDIO_AUTH_USERNAME:'scenario-test-owner',CARDIO_AUTH_PASSWORD_HASH:'pbkdf2-sha256$100000$'+salt.toString('base64url')+'$'+pbkdf2Sync(password,salt,100000,32,'sha256').toString('base64url'),CARDIO_SESSION_SECRET:Buffer.alloc(32,23).toString('base64url')};
const raw=(path,options={},bindings=env)=>worker.fetch(new Request(origin+path,options),bindings);
const login=await raw('/api/auth/login',{method:'POST',headers:{origin},body:JSON.stringify({username:env.CARDIO_AUTH_USERNAME,password})});
assert.equal(login.status,200);const cookie=login.headers.get('set-cookie').split(';')[0];
const post=(body)=>raw('/api/scenarios',{method:'POST',headers:{origin,cookie},body:JSON.stringify(body)});

test('scenario points use the actual model and preserve baseline/input/model data',()=>{
  const requestBefore=structuredClone(payload),modelBefore=JSON.stringify(models);
  const result=runScenarios(models,payload);
  assert.equal(result.synthetic,false);assert.equal(result.points.length,4);
  const baseline=predictPayload(models,{dataset:'brfss',values:payload.values,explain:false});
  assert.equal(result.baseline.probability,baseline.probability);assert.equal(result.version,baseline.version);
  for(const point of result.points){
    const expected=predictPayload(models,{dataset:'brfss',values:{...payload.values,bmi:point.value},explain:false});
    assert.equal(point.probability,expected.probability);
    assert.equal(point.delta,expected.probability-baseline.probability);
    assert.equal(point.positive,expected.positive);
  }
  assert.equal(result.points.find(point=>point.value===27).delta,0);
  assert.deepEqual(payload,requestBefore);assert.equal(JSON.stringify(models),modelBefore);
  assert.ok(result.note.includes('себептік'));
});

test('both public scenario demos are fixed synthetic profiles without custom arguments',async()=>{
  for(const dataset of ['brfss','uci']){
    const response=await raw('/api/scenario-demo/'+dataset+'?lang=kk');assert.equal(response.status,200);
    const result=await response.json();assert.equal(result.synthetic,true);assert.equal(result.points.length,4);
    assert.equal(result.feature,dataset==='brfss'?'bmi':'oldpeak');
    assert.ok(!Object.hasOwn(result.baseline,'explanation'));
    assert.deepEqual(result,scenarioDemo(models,dataset,'kk'));
    assert.equal((await raw('/api/scenario-demo/'+dataset+'?lang=kk&bmi=99')).status,422);
    assert.equal((await raw('/api/scenario-demo/'+dataset+'?lang=ru&lang=kk')).status,422);
  }
  assert.equal((await raw('/api/scenario-demo/brfss?lang=en')).status,422);
});

test('scenario owner gate precedes body reading; authorized requests enforce32KiB',async()=>{
  const protectedRequest={url:origin+'/api/scenarios',method:'POST',headers:new Headers({origin}),
    get body(){throw new Error('Body must not be read before authentication');}};
  assert.equal((await worker.fetch(protectedRequest,env)).status,401);
  assert.equal((await raw('/api/scenarios',{method:'POST',headers:{origin},body:'x'.repeat(32769)})).status,401);
  assert.equal((await raw('/api/scenarios',{method:'POST',headers:{origin,cookie},body:'x'.repeat(32769)})).status,413);
  assert.equal((await raw('/api/scenarios',{method:'POST',headers:{origin:'https://other.example',cookie},body:JSON.stringify(payload)})).status,403);
  assert.equal((await raw('/api/scenarios',{method:'POST',headers:{origin},body:'{}'},{})).status,503);
  const response=await post(payload);assert.equal(response.status,200);assert.equal(response.headers.get('cache-control'),'no-store');
});

test('scenario keys, point counts/types/uniqueness and clinical schema are strict',async()=>{
  const bad=[null,[],{...payload,extra:true},{...payload,vary:{...payload.vary,extra:true}},
    {...payload,vary:{feature:'bmi',values:[22]}},
    {...payload,vary:{feature:'bmi',values:Array.from({length:10},(_,i)=>20+i)}},
    {...payload,vary:{feature:'bmi',values:[22,22]}},
    {...payload,vary:{feature:'bmi',values:[22,null]}},
    {...payload,vary:{feature:'bmi',values:[22,'27']}},
    {...payload,vary:{feature:'bmi',values:[22,true]}},
    {...payload,vary:{feature:'bmi',values:[22,100]}},
    {...payload,vary:{feature:'physical_days',values:[0,1.5]}},
    {...payload,vary:{feature:'sex',values:[1,3]}},
    {...payload,vary:{feature:'target',values:[0,1]}},
    {...payload,values:{sex:1}},{...payload,lang:null}];
  for(const body of bad)assert.equal((await post(body)).status,422,JSON.stringify(body));
  assert.throws(()=>runScenarios(models,{...payload,vary:{feature:'bmi',values:[22,Infinity]}}),error=>error.status===422);
  const allowed=await post({...payload,vary:{feature:'bmi',values:Array.from({length:9},(_,i)=>20+i)}});
  assert.equal(allowed.status,200);assert.equal((await allowed.json()).points.length,9);
});

test('reproducibility download contains only aggregate protocol and public schema',async()=>{
  for(const dataset of ['brfss','uci']){
    const response=await raw('/api/reproducibility/'+dataset,{},{});assert.equal(response.status,200);
    assert.match(response.headers.get('content-disposition'),/attachment.*reproducibility.json/);
    const result=await response.json();assert.deepEqual(result,reproducibilityMetadata(models,reports,dataset));
    assert.equal(result.model_version,models.datasets[dataset].version);
    assert.equal(result.schema.fields.length,models.datasets[dataset].features.length);
    const serialized=JSON.stringify(result);
    for(const forbidden of ['row_id','train_ids','test_ids','background','CARDIO_SESSION_SECRET','student_profile','C:\\Users'])assert.ok(!serialized.includes(forbidden),forbidden);
  }
  const hostile=structuredClone(reports);hostile.environment.password='private';hostile.research.brfss.protocol.train_ids=[1,2];hostile.research.brfss.selection.private_file='secret';
  const cleaned=reproducibilityMetadata(models,hostile,'brfss');
  assert.ok(!JSON.stringify(cleaned).includes('private'));assert.ok(!Object.hasOwn(cleaned.protocol,'train_ids'));
});
