import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';

async function load(entry){
 const bundle=await build({entryPoints:[entry],bundle:true,format:'esm',write:false});
 return import('data:text/javascript;base64,'+Buffer.from(bundle.outputFiles[0].text).toString('base64'));
}
const {arteryViewports}=await load('client/src/arteryComparison.ts');
const {arterySnapshot,arteryDiagramSnapshot}=await load('client/src/arterySnapshot.ts');

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

function diagram(details){
 const old=globalThis.document,canvases=[];
 globalThis.document={createElement(tag){
  assert.equal(tag,'canvas');
  const calls={arcs:[],draws:[],texts:[]};
  const context={fillRect(){},fillText(...args){calls.texts.push(args)},drawImage(...args){calls.draws.push(args)},beginPath(){},moveTo(){},lineTo(){},stroke(){},arc(...args){calls.arcs.push(args)},fill(){}};
  const canvas={width:0,height:0,getContext(kind){assert.equal(kind,'2d','the fallback must not require WebGL');return context},calls};
  canvases.push(canvas);return canvas;
 }};
 try{return {output:arteryDiagramSnapshot(details),canvases}}finally{if(old===undefined)delete globalThis.document;else globalThis.document=old}
}

test('2D export works without WebGL and draws reference and narrowed sections to the same scale',()=>{
 const {output,canvases:[source]}=diagram({lang:'ru',narrowing:50,sectionPosition:0,cutaway:true,compare:true});
 assert.equal(source.width,1600);assert.equal(source.height,800);
 const radii=source.calls.arcs.map(([, ,radius])=>radius);
 assert.deepEqual(radii,[306,255,255,330,306,255,127.5,330]);
 assert.equal(output.width,1600);assert.equal(output.height,1280);
 assert.equal(output.calls.draws.length,2);
 assert.deepEqual(output.calls.draws[0].slice(1,5),[0,0,800,800]);
 assert.deepEqual(output.calls.draws[1].slice(1,5),[800,0,800,800]);
 assert.equal(output.calls.draws[0][7],output.calls.draws[1][7]);
 const texts=output.calls.texts.map(([text])=>text);
 assert.match(texts[0],/2D/);assert.ok(texts.some(text=>text.includes('25.0%')));
 assert.ok(!texts.some(text=>text.includes('Частицы')),'static sections must not imply particle simulation');
 assert.ok(!texts.some(text=>text.includes('Разрез включён')),'longitudinal cutaway is not applicable to a 2D slice');
});

test('2D export uses the selected slice rather than central narrowing in both languages',()=>{
 for(const lang of ['ru','kk']){
  const {output,canvases:[source]}=diagram({lang,narrowing:80,sectionPosition:3.6,cutaway:false,compare:false});
  assert.equal(source.width,800);assert.equal(source.calls.arcs[2][2],255,'end slice remains fully open');
  assert.equal(output.calls.draws.length,1);
  const texts=output.calls.texts.map(([text])=>text);
  assert.match(texts[0],/2D/);assert.ok(texts.some(text=>text.includes('100.0%')));
  assert.ok(texts.some(text=>text.includes('ML')));
 }
});
