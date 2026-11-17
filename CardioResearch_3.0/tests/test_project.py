import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from cardio.config import REPORTS,SCHEMAS,DATA
from cardio.prepare import target_brfss,clean_brfss
from cardio.api import app,bundle,validate_values
from cardio.explain import permutation_shap

client=TestClient(app)
BRFSS={'age_group':7,'sex':1,'bmi':27,'smoking':4,'activity':1,'diabetes':3,'hypertension':3,'cholesterol':2,'general_health':3,'physical_days':2,'mental_days':1}
UCI={'age':55,'sex':1,'cp':3,'trestbps':130,'chol':240,'fbs':0,'restecg':0,'thalach':150,'exang':0,'oldpeak':1,'slope':2,'ca':0,'thal':3}

def test_target_truth_table():
    cases=[1,2,7,9,np.nan]
    pairs=[(a,b) for a in cases for b in cases]
    result=target_brfss(pd.Series([p[0] for p in pairs]),pd.Series([p[1] for p in pairs]))
    for (a,b),v in zip(pairs,result):
        if a==1 or b==1:assert v==1
        elif a==2 and b==2:assert v==0
        else:assert pd.isna(v)

def test_special_codes():
    raw=pd.DataFrame({f['source'].split(' / ')[0]:[np.nan,np.nan] for f in SCHEMAS['brfss']})
    for c in ['CVDINFR4','CVDCRHD4','_LLCPWT','_STATE','_PSU','_STSTR']:raw[c]=[2,2]
    raw.PHYSHLTH=[88,77];raw.MENTHLTH=[30,99];raw['_BMI5']=[2700,9999];raw.DIABETE4=[2,7];raw['_AGEG5YR']=[13,14]
    out=clean_brfss(raw)
    assert out.physical_days.iloc[0]==0 and pd.isna(out.physical_days.iloc[1])
    assert out.mental_days.iloc[0]==30 and pd.isna(out.mental_days.iloc[1])
    assert out.bmi.iloc[0]==27 and out.diabetes.iloc[0]==2
    assert pd.isna(out.diabetes.iloc[1]) and pd.isna(out.age_group.iloc[1])

def test_split_and_leakage():
    split=json.loads((REPORTS/'brfss_splits.json').read_text())
    sets=[set(split[k]) for k in ['fit','calibration','validation','test']]
    for i,a in enumerate(sets):
        for b in sets[i+1:]:assert not a&b
    assert set(split['benchmark_train'])<=sets[0]
    assert set(split['benchmark_test'])<=sets[3]
    assert not {'CVDINFR4','CVDCRHD4','_MICHD','target'}&set(bundle('brfss').features)
    assert json.loads((REPORTS/'brfss_data.json').read_text())['target_formula_matches_MICHD']

@pytest.mark.parametrize('ds,values',[('brfss',BRFSS),('uci',UCI)])
def test_prediction_consistency_and_explanation(ds,values):
    payload={'dataset':ds,'values':values,'explain':True}
    r=client.post('/api/predict',json=payload);assert r.status_code==200,r.text
    data=r.json();direct=bundle(ds).predict_proba(validate_values(ds,values))[0,1]
    assert abs(data['probability']-direct)<1e-12
    ex=data['explanation'];assert abs(ex['baseline']+sum(c['value'] for c in ex['contributions'])-ex['raw_probability'])<1e-8

def test_shap_additive_and_dummy():
    background=np.array([[0.,1.,3.],[2.,3.,1.]])
    coef=np.array([.2,.3,0]);x=np.array([3.,5.,9.])
    vals,base=permutation_shap(lambda a:a@coef,background,x)
    assert np.allclose(vals,(x-background.mean(axis=0))*coef)
    assert vals[2]==0

@pytest.mark.parametrize('values',[{**BRFSS,'age_group':14},{**BRFSS,'physical_days':31},{**BRFSS,'mental_days':2.5},{**BRFSS,'target':1},{}])
def test_invalid_values(values):assert client.post('/api/predict',json={'values':values,'explain':False}).status_code==422

def test_unknown_category_missing_and_dataset():
    assert client.post('/api/predict',json={'values':{**BRFSS,'bmi':None},'explain':False}).status_code==200
    assert client.get('/api/schema/unknown').status_code==400

def test_batch_and_pdf():
    template=client.get('/api/template/brfss')
    batch=client.post('/api/batch/brfss',content=template.content,headers={'content-type':'text/csv'})
    assert batch.status_code==200,batch.text
    from io import StringIO
    tab=pd.read_csv(StringIO(batch.content.decode('utf-8-sig')))
    assert abs(tab.model_probability.iloc[0]-bundle('brfss').predict_proba(validate_values('brfss',BRFSS))[0,1])<1e-12
    assert client.post('/api/batch/brfss',content='bad\n1').status_code==422
    malformed=template.content.decode('utf-8-sig').rstrip()+',extra\n'
    assert client.post('/api/batch/brfss',content=malformed).status_code==422
    assert client.post('/api/batch/brfss',content=b'x'*(1024*1024+1)).status_code==413
    r=client.post('/api/report',json={'values':BRFSS,'explain':True});assert r.status_code==200,r.text;assert r.content.startswith(b'%PDF')
    (REPORTS/'sample_prediction.pdf').write_bytes(r.content)

def test_unavailable_model(monkeypatch,tmp_path):
    import cardio.api as module
    module.bundle.cache_clear();monkeypatch.setattr(module,'MODELS',tmp_path)
    assert client.post('/api/predict',json={'values':BRFSS,'explain':False}).status_code==503
    module.bundle.cache_clear()
