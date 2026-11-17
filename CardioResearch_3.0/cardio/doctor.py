"""Local pre-demonstration checks, without training or saving health answers."""
import argparse
import importlib.metadata as metadata
import json
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET
from .config import ROOT, REPORTS, MODELS, SCHEMAS

def check_project():
    checks=[]
    def add(name,ok,detail):checks.append({'name':name,'ok':bool(ok),'detail':str(detail)})
    for package in ['numpy','pandas','scikit-learn','lightgbm','fastapi','uvicorn','reportlab','psutil']:
        try:add(package,True,metadata.version(package))
        except metadata.PackageNotFoundError:add(package,False,'Тәуелділік орнатылмаған')
    add('Интерфейс',(ROOT/'frontend/dist/index.html').exists(),'frontend/dist/index.html')
    add('PDF қарпі',(ROOT/'assets/DejaVuSans.ttf').exists(),'assets/DejaVuSans.ttf')
    import joblib
    import numpy as np
    import pandas as pd
    for ds in SCHEMAS:
        try:
            model=joblib.load(MODELS/f'{ds}.joblib')
            fields=SCHEMAS[ds]
            expected=[f['name'] for f in fields]
            assert expected==model.features,'Белгілер реті сәйкес емес'
            row={f['name']:f['options'][0]['value'] if f['kind']=='category' else (f['min']+f['max'])/2 for f in fields}
            frame=pd.DataFrame([row],dtype=float);p=model.predict_proba(frame)
            assert p.shape==(1,2) and np.isfinite(p).all() and ((p>=0)&(p<=1)).all()
            assert abs(p.sum()-1)<1e-8
            add(ds.upper()+' моделі',True,model.name+'; жүктелді; техникалық болжам есептелді')
        except Exception as exc:add(ds.upper()+' моделі',False,str(exc))
        try:
            report=json.loads((REPORTS/f'{ds}_results.json').read_text(encoding='utf-8'))
            add(ds.upper()+' нәтижелері',bool(report.get('benchmark')),f"{len(report.get('benchmark',[]))} модель жазбасы")
        except Exception as exc:add(ds.upper()+' нәтижелері',False,str(exc))
    for file in ['reliability.json','atherosclerosis_library.json']:
        try:
            data=json.loads((REPORTS/file).read_text(encoding='utf-8'));add(file,isinstance(data,dict),'JSON оқылды')
        except Exception as exc:add(file,False,str(exc))
    saved_tests=None
    if (REPORTS/'tests.xml').exists():
        root=ET.parse(REPORTS/'tests.xml').getroot()
        suites=[root] if root.tag=='testsuite' else list(root.iter('testsuite'))
        saved_tests={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ['tests','failures','errors','skipped']}
    return {'checked_at':datetime.now(timezone.utc).isoformat(),'ok':all(c['ok'] for c in checks),
        'checks':checks,'last_saved_test_report':saved_tests,
        'scope':'Файлдар, кітапханалар және модельді жүктеп техникалық болжам есептеу тексерілді. Бұл толық тесттерді немесе клиникалық валидацияны алмастырмайды. Пайдаланушы жауаптары сақталмайды.'}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--json',action='store_true');args=parser.parse_args()
    result=check_project()
    if args.json:print(json.dumps(result,ensure_ascii=False,indent=2))
    else:
        print('CardioResearch | Қорғау алдындағы техникалық тексеру\n')
        for c in result['checks']:print(('OK' if c['ok'] else 'ҚАТЕ')+' | '+c['name']+' | '+c['detail'])
        print('\n'+result['scope'])
        print('\nДайын. START.cmd арқылы қосымшаны ашыңыз.' if result['ok'] else '\nЖоғарыда көрсетілген мәселелерді түзету қажет.')
    return 0 if result['ok'] else 1

if __name__=='__main__':raise SystemExit(main())
