import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {withLiteratureAdditions} from '../src/literature.js';

const load=name=>JSON.parse(readFileSync(new URL('../data/'+name,import.meta.url)));
const library=load('reports.json').library, additions=load('literature-additions.json');
const expectedPaperCount=library.papers.length+additions.records.length;

test('supplementary review is merged without mutating frozen reports or archive counts',()=>{
 const original=JSON.stringify(library), extra=JSON.stringify(additions);
 const result=withLiteratureAdditions(library,additions);
 assert.equal(result.papers.length,expectedPaperCount);
 assert.equal(result.counts.papers,expectedPaperCount);
 assert.deepEqual(result.counts,{books:10,papers:expectedPaperCount,software:8,atherosclerosis:12});
 assert.equal(JSON.stringify(library),original);assert.equal(JSON.stringify(additions),extra);
 assert.equal(result.atherosclerosis.archive.pdf_count,library.atherosclerosis.archive.pdf_count);
 result.papers[0].title='Changed result only';
 assert.equal(JSON.stringify(library),original);
});

test('DOI normalization deduplicates repeated additions and duplicates across categories',()=>{
 const once=withLiteratureAdditions(library,additions);
 const twice=withLiteratureAdditions(once,{records:[{...additions.records[0],id:'different-id',doi:' HTTPS://DOI.ORG/10.1016/J.ATHEROSCLEROSIS.2026.120745 '}]});
 assert.deepEqual(twice,once);
 const archiveDOI=library.atherosclerosis.records.find(record=>record.doi).doi;
 assert.deepEqual(withLiteratureAdditions(library,{records:[{id:'duplicate-archive',title:'Duplicate',doi:archiveDOI}]}).papers,library.papers);
 assert.equal(withLiteratureAdditions(once,{records:[{id:additions.records[0].id,title:'Another title'}]}).papers.length,expectedPaperCount);
});

test('optional archive and absent paper lists do not prevent a supplementary reference',()=>{
 const result=withLiteratureAdditions({atherosclerosis:null,papers:null,books:null,software:null,counts:null},additions);
 assert.equal(result.papers.length,additions.records.length);
 assert.deepEqual(result.counts,{books:0,papers:additions.records.length,software:0,atherosclerosis:0});
 assert.equal(result.atherosclerosis,null);
});

test('source record distinguishes abstract verification and background-review scope',()=>{
 const record=additions.records[0];
 assert.equal(record.type,'review');assert.equal(record.verification_scope,'abstract');
 assert.equal(record.pmid,'42177119');assert.equal(record.doi,'10.1016/j.atherosclerosis.2026.120745');
 assert.equal(record.pubmed_url,'https://pubmed.ncbi.nlm.nih.gov/42177119/');
 for(const language of ['ru','kk']){
  assert.ok(record['summary_'+language]);assert.ok(record['verification_'+language].includes('403'));
  assert.ok(record['limitations_'+language].includes('CardioResearch'));
 }
 assert.equal(record.source_checked_at,'2026-11-09');
});

test('Python and Worker literature merges return identical aggregate catalogs',()=>{
 const code=`import importlib.util,json,sys\nfrom pathlib import Path\nroot=Path(sys.argv[1])\nspec=importlib.util.spec_from_file_location('literature',root/'python/cardio/literature.py')\nmodule=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)\nlibrary=json.loads((root/'data/reports.json').read_text(encoding='utf-8'))['library']\naddition=json.loads((root/'data/literature-additions.json').read_text(encoding='utf-8'))\nprint(json.dumps(module.with_literature_additions(library,addition),ensure_ascii=True))`;
 const root=new URL('..',import.meta.url);
 const result=spawnSync(process.env.CARDIO_PYTHON||'python',['-c',code,fileURLToPath(root)],{encoding:'utf8',windowsHide:true,maxBuffer:2*1024*1024});
 assert.equal(result.status,0,result.stderr||result.error?.message);
 assert.deepEqual(JSON.parse(result.stdout),withLiteratureAdditions(library,additions));
});
