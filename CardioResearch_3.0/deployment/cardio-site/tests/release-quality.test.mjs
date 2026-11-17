import test from 'node:test';
import assert from 'node:assert/strict';
import {dockerQualityLimit} from '../src/release-quality.js';

test('Docker limit confirms only matching saved evidence and preserves provenance',()=>{
 const result=dockerQualityLimit({version_match:true,checks:{docker:{status:'passed',report_file:'docker-audit.json',report_sha256:'a'.repeat(64)}}});
 assert.equal(result.status,'passed');
 assert.equal(result.report_file,'docker-audit.json');
 assert.equal(result.report_sha256,'a'.repeat(64));
 assert.ok(result.detail.includes('полный набор тестов внутри контейнера не запускался'));
});

test('absent, unknown and stale Docker evidence never confirms this application',()=>{
 for(const report of [null,{}, {version_match:true,checks:{}}, {version_match:true,checks:{docker:{status:'unknown'}}}, {version_match:false,checks:{docker:{status:'passed'}}}]){
  assert.equal(dockerQualityLimit(report).status,'not_verified');
 }
 assert.equal(dockerQualityLimit({version_match:true,checks:{docker:{status:'failed'}}}).status,'failed');
});
