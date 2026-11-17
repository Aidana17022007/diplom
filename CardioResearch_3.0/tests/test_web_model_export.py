"""Numerical parity of exported fitted models with the Python source artifacts.

Requires Node.js (also needed to build the deployed frontend). Does not refit or
replace production models. All sample answers remain in the test subprocess.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import subprocess
import time

import joblib
import numpy as np
import pandas as pd
import pytest

from cardio.config import ROOT, MODELS, DATA, SCHEMAS, SEED
from cardio.explain import permutation_shap

EXPORT=ROOT/'deployment/cardio-site/data/models.json'
INFERENCE=ROOT/'deployment/cardio-site/src/inference.js'
DEMO={
    'brfss':{'age_group':7,'sex':1,'bmi':27,'smoking':4,'activity':1,'diabetes':3,'hypertension':3,'cholesterol':2,'general_health':3,'physical_days':2,'mental_days':1},
    'uci':{'age':55,'sex':1,'cp':3,'trestbps':130,'chol':240,'fbs':0,'restecg':0,'thalach':150,'exang':0,'oldpeak':1,'slope':2,'ca':0,'thal':3},
}


def records(frame):
    return json.loads(frame.to_json(orient='records',double_precision=15))


def node_run(payload):
    node=shutil.which('node')
    assert node,'Node.js is required for web inference verification'
    script=f'''
      import fs from 'node:fs';
      import {{rawProbability,predictProbability,predictPayload}} from {json.dumps(INFERENCE.as_uri())};
      const models=JSON.parse(fs.readFileSync({json.dumps(str(EXPORT))},'utf8'));
      const q=JSON.parse(fs.readFileSync(0,'utf8'));
      const began=performance.now();
      const results=q.map(item=>{{
        try {{
          if(item.mode==='raw')return {{raw:rawProbability(models,item.dataset,item.values),probability:predictProbability(models,item.dataset,item.values)}};
          return predictPayload(models,item.request);
        }}catch(error){{return {{error:{{status:error.status,detail:error.detail,message:error.message}}}}}}
      }});
      process.stdout.write(JSON.stringify({{results,elapsed_ms:performance.now()-began}}));
    '''
    completed=subprocess.run([node,'--input-type=module','-e',script],input=json.dumps(payload,allow_nan=False),text=True,encoding='utf-8',capture_output=True,timeout=120,check=True)
    return json.loads(completed.stdout)


@pytest.fixture(scope='module')
def export_data():
    assert EXPORT.exists(),'Run scripts/export_web_models.py first'
    return json.loads(EXPORT.read_text(encoding='utf-8'))


def test_export_is_exact_deterministic_and_uses_current_artifacts(tmp_path,export_data):
    spec=importlib.util.spec_from_file_location('web_export',ROOT/'scripts/export_web_models.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    copy=tmp_path/'models.json';module.export_all(copy)
    assert copy.read_bytes()==EXPORT.read_bytes()
    for dataset,model in export_data['datasets'].items():
        assert model['artifact_sha256']==hashlib.sha256((MODELS/f'{dataset}.joblib').read_bytes()).hexdigest()
        assert len(model['shap']['orders'])==48 and len(model['shap']['background'])==30
        assert all(sorted(order)==list(range(len(model['features']))) for order in model['shap']['orders'])
    assert not any(key in EXPORT.read_text(encoding='utf-8') for key in ['row_id','_PSU','_LLCPWT'])


@pytest.mark.parametrize('dataset',['brfss','uci'])
def test_javascript_probabilities_match_python_for_observed_missing_and_edge_rows(dataset,export_data):
    model=joblib.load(MODELS/f'{dataset}.joblib')
    frame=pd.read_pickle(DATA/'processed'/f'{dataset}.pkl')
    frame=frame[model.features].sample(min(1000,len(frame)),random_state=SEED).copy()
    extra=[DEMO[dataset],{name:None for name in model.features}]
    for field in SCHEMAS[dataset]:
        extra.append({**DEMO[dataset],field['name']:None})
        if field['kind']=='category':
            extra.extend({**DEMO[dataset],field['name']:option['value']} for option in field['options'])
            # Low-level pipeline parity for handle_unknown='ignore'; public API rejects this category.
            extra.append({**DEMO[dataset],field['name']:999})
        else:
            extra.extend([{**DEMO[dataset],field['name']:field['min']},{**DEMO[dataset],field['name']:field['max']}])
    if dataset=='uci':
        pre=export_data['datasets'][dataset]['preprocessing']['numeric']
        checked=0
        for tree in export_data['datasets'][dataset]['estimator']['trees']:
            for index,threshold in zip(tree['feature'],tree['threshold']):
                if 0<=index<len(pre['names']):
                    raw=threshold*pre['scale'][index]+pre['mean'][index]
                    for delta in [-1e-10,0,1e-10]:extra.append({**DEMO[dataset],pre['names'][index]:raw+delta})
                    checked+=1
                    if checked>=50:break
            if checked>=50:break
    frame=pd.concat([frame,pd.DataFrame(extra)],ignore_index=True)[model.features]
    inputs=records(frame)
    # Rebuild Python input from the same JSON precision sent to Node.
    exact_frame=pd.DataFrame(inputs,columns=model.features,dtype=float)
    expected_raw=model.raw_probability(exact_frame);expected=model.predict_proba(exact_frame)[:,1]
    output=node_run([{'mode':'raw','dataset':dataset,'values':row} for row in inputs])
    assert all('error' not in row for row in output['results'])
    actual=np.array([row['probability'] for row in output['results']])
    raw=np.array([row['raw'] for row in output['results']])
    assert np.max(np.abs(actual-expected))<1e-10
    assert np.max(np.abs(raw-expected_raw))<1e-10
    print(f'{dataset}: {len(inputs)} rows, max_probability_delta={np.max(np.abs(actual-expected)):.3g}, max_raw_delta={np.max(np.abs(raw-expected_raw)):.3g}, node_ms={output["elapsed_ms"]:.2f}')


@pytest.mark.parametrize('dataset',['brfss','uci'])
def test_javascript_explanations_match_original_python_estimator(dataset,export_data):
    model=joblib.load(MODELS/f'{dataset}.joblib')
    background=joblib.load(MODELS/f'{dataset}_background.joblib')[model.features].iloc[:30]
    inputs=[DEMO[dataset],{**DEMO[dataset],model.features[0]:None,model.features[-1]:None}]
    output=node_run([{'request':{'dataset':dataset,'values':row,'explain':True,'lang':'kk'}} for row in inputs])
    for values,result in zip(inputs,output['results']):
        assert 'error' not in result,result
        x=np.array([values[name] if values[name] is not None else np.nan for name in model.features])
        expected,baseline=permutation_shap(lambda a:model.raw_probability(pd.DataFrame(a,columns=model.features)),background.to_numpy(),x)
        explanation=result['explanation'];actual={row['feature']:row['value'] for row in explanation['contributions']}
        assert abs(explanation['baseline']-baseline)<1e-10
        assert np.max(np.abs(np.array([actual[name] for name in model.features])-expected))<1e-10
        assert abs(explanation['baseline']+sum(actual.values())-explanation['raw_probability'])<1e-10
        assert result['version']==export_data['datasets'][dataset]['version']
        assert 'Зерттеу' in result['disclaimer']
    print(f'{dataset}: 2 exact48-order explanations, Node_total_ms={output["elapsed_ms"]:.2f}')


def test_public_validation_rejects_wrong_categories_and_types_without_coercion():
    bad=[{**DEMO['brfss'],'age_group':99},{**DEMO['brfss'],'bmi':'27'},
         {**DEMO['brfss'],'bmi':True},{**DEMO['brfss'],'target':1},{}]
    output=node_run([{'request':{'values':row,'explain':False}} for row in bad]+[
        {'request':{'values':DEMO['brfss'],'lang':'en'}},
        {'request':{'values':DEMO['brfss'],'explain':'yes'}},
        {'request':{'values':DEMO['brfss'],'unexpected':True}},
        {'request':{'values':DEMO['brfss'],'dataset':None}},
        {'request':{'values':DEMO['brfss'],'lang':None}},
        {'request':{'values':DEMO['brfss'],'explain':None}},
    ])
    assert all(row.get('error',{}).get('status')==422 for row in output['results'])
