import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';

async function load(entry){
 const bundle=await build({entryPoints:[entry],bundle:true,format:'esm',write:false});
 return import('data:text/javascript;base64,'+Buffer.from(bundle.outputFiles[0].text).toString('base64'));
}
const {arteryViewports}=await load('client/src/arteryComparison.ts');
const {arterySnapshot}=await load('client/src/arterySnapshot.ts');

test('comparison panes cover both edges with equal scale, a small gutter and no overlap',()=>{
 for(const width of [2,17,320,390,559,560,561,801,1440])for(const height of [2,3,17,301,620,1001]){
  const [a,b]=arteryViewports(width,height,true);
  assert.equal(a.kind,'reference');assert.equal(b.kind,'altered');
  assert.equal(a.width,b.width);assert.equal(a.height,b.height);
  for(const view of [a,b]){
   assert.ok(view.width>0&&view.height>0);
   assert.ok(view.left>=0&&view.top>=0&&view.left+view.width<=width&&view.top+view.height<=height);
  }
  const vertical=width<560;
  const gap=vertical?b.top-a.height:b.left-a.width;
  assert.ok(gap>=0&&gap<=13,`unexpected blank region ${width}x${height}: ${gap}`);
  if(vertical){assert.equal(a.left,0);assert.equal(b.left,0);assert.equal(a.width,width);assert.equal(a.top,0);assert.equal(b.top+b.height,height)}
  else {assert.equal(a.top,0);assert.equal(b.top,0);assert.equal(a.height,height);assert.equal(a.left,0);assert.equal(b.left+b.width,width)}
 }
});

test('single mode and collapsed canvases have one bounded altered view',()=>{
 assert.deepEqual(arteryViewports(839.9,617.7,false),[{kind:'altered',left:0,top:0,width:839,height:617}]);
 for(const [width,height] of [[0,0],[1,620],[900,1],[-4,200],[NaN,Infinity]]){
  const views=arteryViewports(width,height,true);
  assert.equal(views.length,1);assert.equal(views[0].kind,'altered');
  for(const n of Object.values(views[0]).filter(v=>typeof v==='number'))assert.ok(Number.isFinite(n)&&n>=0);
  assert.ok(views[0].width>=1&&views[0].height>=1);
 }
});

function capture(frame,details){
 const old=globalThis.document,draws=[],texts=[];
 const context={fillRect(){},fillText(...args){texts.push(args)},drawImage(...args){draws.push(args)},beginPath(){},moveTo(){},lineTo(){},stroke(){},arc(){},fill(){}};
 const canvas={width:0,height:0,getContext(kind){assert.equal(kind,'2d');return context}};
 globalThis.document={createElement(tag){assert.equal(tag,'canvas');return canvas}};
 try{return {output:arterySnapshot(frame,details),draws,texts}}finally{if(old===undefined)delete globalThis.document;else globalThis.document=old}
}

test('PNG uses both fresh source crops at identical scale on desktop and high-DPI mobile',()=>{
 for(const [width,height,ratio] of [[1201,620,1],[390,701,2]]){
  const canvas={width:width*ratio,height:height*ratio};
  const views=arteryViewports(width,height,true).map(v=>({...v,left:v.left*ratio,top:v.top*ratio,width:v.width*ratio,height:v.height*ratio}));
  const {output,draws}=capture({canvas,views},{lang:'ru',narrowing:50,sectionPosition:0,cutaway:true});
  assert.equal(output.width,1600);assert.equal(output.height,1280);assert.equal(draws.length,2);
  for(let i=0;i<2;i++){
   const view=views[i],[source,sx,sy,sw,sh,dx,dy,dw,dh]=draws[i];
   assert.equal(source,canvas);assert.deepEqual([sx,sy,sw,sh],[view.left,view.top,view.width,view.height]);
   assert.ok(dx>=0&&dy>=222&&dx+dw<=1600&&dy+dh<=1002);
   assert.ok(Math.abs(dw/dh-sw/sh)<1e-10,'the source crop must keep its aspect ratio');
  }
  assert.equal(draws[0][7],draws[1][7]);assert.equal(draws[0][8],draws[1][8]);
  assert.ok(draws[0][5]+draws[0][7]<draws[1][5],'mobile source is composed into distinct left and right export panels');
 }
});

test('PNG distinguishes reference area from local altered area in both interface languages',()=>{
 const canvas={width:1000,height:620},views=arteryViewports(1000,620,true);
 for(const lang of ['ru','kk']){
  const {texts}=capture({canvas,views},{lang,narrowing:50,sectionPosition:0,cutaway:false});
  const headings=texts.filter(([, ,y])=>y===210).map(([text])=>text);
  assert.equal(headings.length,2);assert.match(headings[0],/100%/);assert.match(headings[1],/25\.0%/);
  assert.ok(texts.some(([text])=>text.includes('ML')));
 }
 const {texts}=capture({canvas,views},{lang:'ru',narrowing:50,sectionPosition:3.6,cutaway:true});
 assert.match(texts.filter(([, ,y])=>y===210)[1][0],/100\.0%/,'the selected end section is open despite maximum 50% central narrowing');
});

test('single-view export uses the entire current frame and never labels a second vessel',()=>{
 const canvas={width:1024,height:600},views=arteryViewports(1024,600,false);
 const {draws,texts}=capture({canvas,views},{lang:'ru',narrowing:80,sectionPosition:0,cutaway:true});
 assert.equal(draws.length,1);assert.deepEqual(draws[0].slice(1,5),[0,0,1024,600]);
 assert.equal(texts.filter(([, ,y])=>y===210).length,0);
 assert.throws(()=>capture({canvas:{width:0,height:600},views},{lang:'ru',narrowing:0,sectionPosition:0,cutaway:true}),/dimensions/);
});
