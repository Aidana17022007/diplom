import copy
import json
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from cardio.api import app,PredictionRequest,predict_payload
from cardio.config import ROOT
from cardio.scenarios import demo_request

client=TestClient(app)


@pytest.mark.parametrize('dataset',['brfss','uci'])
def test_local_scenario_deltas_are_real_and_input_is_unchanged(dataset):
    payload=demo_request(dataset,'kk');before=copy.deepcopy(payload)
    response=client.post('/api/scenarios',json=payload);assert response.status_code==200,response.text
    result=response.json();baseline=predict_payload(PredictionRequest(dataset=dataset,values=payload['values'],explain=False))
    # Parallel tree reductions can differ by a few machine-precision bits.
    assert result['baseline']['probability']==pytest.approx(baseline['probability'],rel=0,abs=1e-12)
    assert result['version']==baseline['version'] and result['synthetic'] is False
    for point in result['points']:
        expected=predict_payload(PredictionRequest(dataset=dataset,values={**payload['values'],payload['vary']['feature']:point['value']},explain=False))
        assert point['probability']==pytest.approx(expected['probability'],rel=0,abs=1e-12)
        assert point['delta']==pytest.approx(expected['probability']-baseline['probability'],rel=0,abs=1e-12)
        assert point['positive']==expected['positive']
    assert payload==before
    assert 'себептік' in result['note']


def test_scenario_bounds_and_strict_fields():
    payload=demo_request('brfss')
    for values in [[22],[22]*2,list(range(20,30)),[22,None],[22,True],[22,'27'],[22,100]]:
        response=client.post('/api/scenarios',json={**payload,'vary':{'feature':'bmi','values':values}})
        assert response.status_code==422
    for bad in [{**payload,'extra':1},{**payload,'vary':{'feature':'target','values':[0,1]}},
                {**payload,'vary':{'feature':'sex','values':[1,3]}},
                {**payload,'vary':{'feature':'physical_days','values':[1,2.5]}},
                {**payload,'values':{'sex':1}},{**payload,'lang':None}]:
        assert client.post('/api/scenarios',json=bad).status_code==422
    assert client.post('/api/scenarios',content=b'x'*32769).status_code==413
    assert client.post('/api/scenarios',content=b'{bad').status_code==422
    assert client.post('/api/scenarios',json={**payload,'vary':{'feature':'bmi','values':list(range(20,29))}}).status_code==200
    raw=json.dumps(payload).replace('[22, 27, 32, 37]','[22, NaN]')
    assert client.post('/api/scenarios',content=raw).status_code==422


def test_fixed_demo_and_reproducibility_export():
    for dataset in ['brfss','uci']:
        response=client.get(f'/api/scenario-demo/{dataset}?lang=kk');assert response.status_code==200
        result=response.json();assert result['synthetic'] is True and len(result['points'])==4
        assert client.get(f'/api/scenario-demo/{dataset}?values=custom').status_code==422
        assert client.get(f'/api/scenario-demo/{dataset}?lang=ru&lang=kk').status_code==422
        export=client.get('/api/reproducibility/'+dataset);assert export.status_code==200
        data=export.json();assert data['model_version']==result['version']
        assert data['schema']['fields'] and data['protocol'] and data['selection']
        assert 'attachment' in export.headers['content-disposition']
        for forbidden in ['row_id','train_ids','test_ids','background','student_profile','C:\\Users']:
            assert forbidden not in export.text


def test_local_and_worker_scenario_schemas_and_numbers_match():
    node=shutil.which('node');assert node
    module=(ROOT/'deployment/cardio-site/src/scenarios.js').as_uri()
    model_path=ROOT/'deployment/cardio-site/data/models.json'
    report_path=ROOT/'deployment/cardio-site/data/reports.json'
    script=f"""import fs from 'node:fs';import {{scenarioDemo,reproducibilityMetadata}} from {json.dumps(module)};
      const models=JSON.parse(fs.readFileSync({json.dumps(str(model_path))},'utf8'));
      const reports=JSON.parse(fs.readFileSync({json.dumps(str(report_path))},'utf8'));
      const out={{}};for(const ds of ['brfss','uci'])out[ds]={{scenario:scenarioDemo(models,ds,'kk'),metadata:reproducibilityMetadata(models,reports,ds)}};
      process.stdout.write(JSON.stringify(out));"""
    process=subprocess.run([node,'--input-type=module','-e',script],text=True,encoding='utf-8',capture_output=True,check=True,timeout=30)
    worker=json.loads(process.stdout)
    for dataset in ['brfss','uci']:
        local=client.get(f'/api/scenario-demo/{dataset}?lang=kk').json();remote=worker[dataset]['scenario']
        assert local.keys()==remote.keys() and local['baseline'].keys()==remote['baseline'].keys()
        assert local['baseline']['values']==remote['baseline']['values']
        assert local['note']==remote['note']
        assert abs(local['baseline']['probability']-remote['baseline']['probability'])<1e-10
        for left,right in zip(local['points'],remote['points']):
            assert left.keys()==right.keys() and abs(left['probability']-right['probability'])<1e-10
            assert abs(left['delta']-right['delta'])<1e-10
        assert client.get('/api/reproducibility/'+dataset).json()==worker[dataset]['metadata']
