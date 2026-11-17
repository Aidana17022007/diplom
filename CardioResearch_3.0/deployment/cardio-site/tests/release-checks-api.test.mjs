import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import worker from '../dist/server/index.js';

test('public passport and quality expose the same versioned evidence',async()=>{
 const get=path=>worker.fetch(new Request('https://cardio.example/api/'+path),{});
 const response=await get('release-checks');
 assert.equal(response.status,200);
 assert.equal(response.headers.get('Cache-Control'),'no-store');
 const report=await response.json(),quality=await(await get('quality')).json(),health=await(await get('health')).json();
 assert.deepEqual(report,JSON.parse(fs.readFileSync(new URL('../data/release-checks.json',import.meta.url))));
 assert.equal(report.application_version,health.version);
 assert.deepEqual(quality.release,report);
 assert.equal(quality.tests.source,report.report_file);
 assert.notEqual(quality.tests.source,'verification.json');
 assert.equal(quality.tests.passed,report.checks.python.passed);
 assert.equal(report.measured_now,false);
 assert.equal(quality.tests.measured_now,false);
 assert.equal(quality.privacy.answers_saved,false);
 assert.equal((await worker.fetch(new Request('https://cardio.example/data/release-checks.json'),{})).status,404);
});
