import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';

// Exercise the response merge without mounting the UI or importing the chart runtime.
const bundle=await build({stdin:{contents:"export {mergeExperimentJob,reconcileExperimentJob} from './client/src/ExperimentRuns';",resolveDir:process.cwd()},bundle:true,format:'esm',write:false,jsx:'transform',tsconfigRaw:{compilerOptions:{jsx:'react'}},plugins:[{name:'unused-ui-imports',setup(build){build.onResolve({filter:/^(react(?:\/.*)?|lucide-react|\.\/ui)$/},args=>({path:args.path,external:true,sideEffects:false}))}}]});
const {mergeExperimentJob,reconcileExperimentJob}=await import('data:text/javascript;base64,'+Buffer.from(bundle.outputFiles[0].text).toString('base64'));
const job=(status,progress=0)=>({id:'run-a',status,progress,stage:status,config:{dataset:'uci',algorithm:'logistic_regression',seed:42}});

test('late poll and report responses cannot undo cancellation or terminal job status',()=>{
 for(const status of ['cancel_requested','cancelled','succeeded','failed']){
  const previous=job(status,80);
  for(const next of [job('queued'),job('running',60)])assert.equal(mergeExperimentJob(previous,next),previous);
 }
 const running=job('running',25);
 assert.equal(mergeExperimentJob(running,job('queued')),running);
 assert.equal(mergeExperimentJob(running,job('running',20)).progress,25);
 assert.equal(mergeExperimentJob(job('cancel_requested',80),job('cancelled',80)).status,'cancelled');
});

test('completed result survives summary-only refresh, while a different active job is adopted',()=>{
 const result={id:'run-a',baseline:{roc_auc:{mean:.8,sd:.02}}};
 const completed={...job('succeeded',100),result};
 assert.equal(mergeExperimentJob(completed,job('succeeded',100)).result,result);
 const next={...job('queued'),id:'run-b'};
 assert.equal(mergeExperimentJob(completed,next),next);
 assert.equal(mergeExperimentJob(null,next),next);
});

test('returning to the runner after completion restores the latest job and its exact saved result',()=>{
 const latest=job('succeeded',100),older={...job('succeeded',100),id:'run-older'};
 const result={id:latest.id,config:latest.config,baseline:{roc_auc:{mean:.8,sd:.02}}};
 const report={runs:[{...result,id:older.id},result],runner:{active_job:null,recent_jobs:[latest,older]}};
 for(const previous of [null,older]){
  const restored=reconcileExperimentJob(previous,report);
  assert.equal(restored.id,latest.id);assert.equal(restored.status,'succeeded');assert.equal(restored.result,result);
 }
 const stillRunning={...job('running',10),id:'new-active'};
 assert.equal(reconcileExperimentJob(null,{...report,runner:{...report.runner,active_job:stillRunning}}),stillRunning);
 assert.equal(reconcileExperimentJob(stillRunning,report),stillRunning,'a stale history must not hide an in-flight local job');
});

test('restoring an unsuccessful recent job never borrows another run result',()=>{
 for(const status of ['cancelled','failed']){
  const latest=job(status,60);
  const restored=reconcileExperimentJob(null,{runs:[{id:'unrelated-result'}],runner:{recent_jobs:[latest]}});
  assert.equal(restored,latest);assert.equal(restored.result,undefined);
 }
 assert.equal(reconcileExperimentJob(null,{runs:[],runner:{recent_jobs:[]}}),null);
});
