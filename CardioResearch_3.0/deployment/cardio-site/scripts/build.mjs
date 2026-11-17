import fs from 'node:fs/promises';
import path from 'node:path';
import {build} from 'esbuild';
import './build-client.mjs';

const manifest=JSON.parse(await fs.readFile('.openai/hosting.json','utf8'));
if(!manifest.project_id || manifest.static) throw new Error('Expected a Worker Site manifest');
const assets={};
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.ico':'image/x-icon'};
async function collect(dir, prefix='') {
  for(const entry of await fs.readdir(dir,{withFileTypes:true})) {
    const full=path.join(dir,entry.name),key=prefix+'/'+entry.name;
    if(entry.isDirectory()) await collect(full,key);
    else {
      if(!(path.extname(entry.name) in mime)) throw new Error('Unexpected public asset: '+key);
      assets[key]={type:mime[path.extname(entry.name)],body:(await fs.readFile(full)).toString('base64')};
    }
  }
}
await collect('public');
if(!assets['/index.html']) throw new Error('Frontend has not been prepared');
await fs.mkdir('src/generated',{recursive:true});
await fs.writeFile('src/generated/assets.js','export default '+JSON.stringify(assets)+';\n');
await fs.writeFile('src/generated/font.js','export default '+JSON.stringify((await fs.readFile('assets/DejaVuSans.ttf')).toString('base64'))+';\n');
await fs.mkdir('dist/server',{recursive:true});
await fs.mkdir('dist/.openai',{recursive:true});
await fs.copyFile('.openai/hosting.json','dist/.openai/hosting.json');
await build({entryPoints:['src/worker.js'],bundle:true,format:'esm',platform:'browser',target:'es2022',outfile:'dist/server/index.js',minify:true,legalComments:'eof',metafile:true}).then(r=>fs.writeFile('dist/build-meta.json',JSON.stringify(r.metafile)));
const bytes=(await fs.stat('dist/server/index.js')).size;
console.log('Built Worker:',bytes,'bytes;',Object.keys(assets).length,'public frontend files. Models and backgrounds remain server-side.');
