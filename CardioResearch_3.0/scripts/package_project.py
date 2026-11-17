from pathlib import Path
import json,zipfile,os

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output'/'CardioResearch_project.zip'
folders=['cardio','frontend/src','frontend/dist','models','reports','assets','tests','scripts','deployment/cardio-site']
files=['README.md','requirements.txt','requirements-tested.txt','run.ps1','setup.ps1','START.cmd','CHECK.cmd','Dockerfile','compose.yaml','.dockerignore','.gitignore','frontend/package.json','frontend/package-lock.json','frontend/tsconfig.json','frontend/vite.config.ts','frontend/index.html']
files.append('OPEN_SITE.url')
for folder in folders:
    for directory, children, names in os.walk(ROOT/folder):
        children[:]=[name for name in children if name not in {'__pycache__','node_modules','.git','.sites-runtime','tmp'} and not (folder.startswith('deployment/') and name in {'dist','generated'})]
        files.extend(str((Path(directory)/name).relative_to(ROOT)) for name in names if not name.endswith('.log'))
files.extend(str(p.relative_to(ROOT)) for p in (ROOT/'output').rglob('*') if p.is_file() and p.suffix in ['.pdf','.html','.txt'])
files.extend(['data/raw/codebook.html','data/raw/uci_description.txt','data/processed/uci_centers_audit.csv'])
with zipfile.ZipFile(OUT,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for name in sorted(set(files)):
        p=ROOT/name
        if p.exists():z.write(p,arcname='CardioResearch/'+str(Path(name)).replace('\\','/'))
with zipfile.ZipFile(OUT) as z:
    assert z.testzip() is None
    names=z.namelist()
    assert 'CardioResearch/frontend/dist/index.html' in names
    assert 'CardioResearch/models/brfss.joblib' in names
    assert 'CardioResearch/output/Diplom_CardioResearch_KZ.pdf' in names
print('Archive verified:',OUT,'bytes',OUT.stat().st_size,'files',len(names))
