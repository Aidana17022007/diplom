"""Persist evidence and machine-readable verification status."""
from pathlib import Path
import json,xml.etree.ElementTree as ET,sys,importlib.metadata as md
ROOT=Path(__file__).resolve().parents[1];REPORTS=ROOT/'reports'
tree=ET.parse(REPORTS/'tests.xml');suite=tree.getroot()
counts={k:sum(int(e.attrib.get(k,0)) for e in suite.findall('testsuite')) for k in ['tests','failures','errors','skipped']}
def load(n):return json.loads((REPORTS/n).read_text(encoding='utf-8'))
model=load('brfss_results.json');schema=load('schema.json')
browser=load('browser_qa_v22.json') if (REPORTS/'browser_qa_v22.json').exists() else load('browser_qa_v2.json') if (REPORTS/'browser_qa_v2.json').exists() else {}
build=load('frontend_build_v2.json') if (REPORTS/'frontend_build_v2.json').exists() else {}
checks={'automated_tests':counts,'frontend_build':build.get('status','not recorded for current version'),'local_server':browser.get('status','browser verification not recorded for current version'),'browser_checks':browser.get('checks',[]),'docker':'not run: Docker Engine unavailable','data_sources':'SHA-256 fingerprints retained','independent_test_selection':model['selection']['locked_before_test'],'documents_language':'Kazakh auxiliary drafts; independent student writing pending','interface_language':'Russian and Kazakh','shap_implementation':'own interventional permutation Shapley estimator; 48 orders, 30 background rows','known_limits':['No external clinical validation','No Kazakhstan validation','Survey design not fully accounted for in intervals','UCI fixed-OOF bootstrap is descriptive; overlapping training sets and model selection uncertainty excluded','UCI final artifact search budget differs from outer CV; retained without retrospective model replacement','Finite hyperparameter budget; MLP performance unstable','University requirements read; final student-authored 100-page manuscript pending']}
(REPORTS/'verification.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
deps=['numpy','pandas','scipy','scikit-learn','lightgbm','joblib','threadpoolctl','beautifulsoup4','matplotlib','fastapi','uvicorn','pydantic','reportlab','httpx','pytest','Pillow','psutil']
(ROOT/'requirements-tested.txt').write_text('\n'.join(f'{p}=={md.version(p)}' for p in deps)+'\n',encoding='utf-8')
print(checks)
