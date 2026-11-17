"""Regression tests for typed input, bounded CSV inspection and research provenance."""
import csv
from io import StringIO
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

import cardio.api as api
from cardio.history import record_results, list_results, get_result

client=TestClient(api.app)
VALUES={'age_group':7,'sex':1,'bmi':27,'smoking':4,'activity':1,'diabetes':3,
        'hypertension':3,'cholesterol':2,'general_health':3,'physical_days':2,'mental_days':1}


@pytest.mark.parametrize('bad',[True,False,'27',[],{},[27]])
def test_json_numbers_are_not_coerced(bad):
    response=client.post('/api/predict',json={'values':{**VALUES,'bmi':bad},'explain':False})
    assert response.status_code==422
    detail=response.json()['detail']
    assert detail['errors'][0]['field']=='bmi'
    assert 'input' not in str(detail)


@pytest.mark.parametrize('bad',['NaN','Infinity','-Infinity','1e9999'])
def test_nonfinite_json_is_rejected(bad):
    content=json.dumps({'values':VALUES,'explain':False}).replace('"bmi": 27','"bmi": '+bad)
    response=client.post('/api/predict',content=content,headers={'content-type':'application/json'})
    assert response.status_code==422
    assert response.json()['detail']['errors'][0]['field']=='bmi'


def test_framework_error_does_not_echo_health_values():
    response=client.post('/api/predict',json={'values':VALUES,'explain':'yes'})
    assert response.status_code==422
    assert 'input' not in str(response.json())
    assert response.json()['detail']['errors'][0]['field']=='explain'


def make_csv(rows):
    out=StringIO();writer=csv.DictWriter(out,fieldnames=list(VALUES));writer.writeheader();writer.writerows(rows)
    return out.getvalue()


def test_preflight_accepts_csv_numeric_text_and_reports_all_bad_rows():
    content=make_csv([VALUES,{**VALUES,'bmi':'oops'},{**VALUES,'age_group':100},{**VALUES,'bmi':''}])
    response=client.post('/api/batch/validate/brfss',content=content)
    assert response.status_code==200
    result=response.json()
    assert result['rows']==4 and result['valid_rows']==2 and result['invalid_rows']==2
    assert [e['line'] for e in result['errors']]==[3,4]
    assert result['errors'][0]['errors'][0]['field']=='bmi'
    assert not result['errors_truncated']
    assert client.post('/api/batch/brfss',content=content).status_code==422
    assert client.post('/api/batch/brfss',content=make_csv([VALUES])).status_code==200


def test_csv_preflight_is_bounded_and_rejects_bad_shape():
    content=make_csv([{**VALUES,'bmi':'wrong'}]*55)
    result=client.post('/api/batch/validate/brfss',content=content).json()
    assert result['invalid_rows']==55 and len(result['errors'])==50 and result['errors_truncated']
    assert client.post('/api/batch/validate/brfss',content=b'x'*(api.BATCH_MAX_BYTES+1)).status_code==413
    assert client.post('/api/batch/validate/brfss',content=make_csv([VALUES]*1001)).status_code==422
    truncated=','.join(VALUES)+'\n7,1,27\n'
    malformed=client.post('/api/batch/validate/brfss',content=truncated).json()
    assert malformed['invalid_rows']==1
    assert malformed['errors'][0]['errors'][0]['field']=='row'


def test_history_deduplicates_and_preserves_old_snapshot(tmp_path):
    reports=tmp_path/'reports';models=tmp_path/'models';reports.mkdir();models.mkdir()
    result={'selection':{'deployed_model':'Logistic Regression'},'full':[{'name':'Logistic Regression','metrics':{'average_precision':.32,'roc_auc':.84}}]}
    report=reports/'brfss_results.json';report.write_text(json.dumps(result),encoding='utf-8')
    (reports/'environment.json').write_text(json.dumps({'started':'2026-11-07T00:00:00Z','seed':42}),encoding='utf-8')
    (models/'brfss.joblib').write_bytes(b'model-v1')
    database=reports/'experiments.sqlite'
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE runs (dataset TEXT PRIMARY KEY, result_json TEXT)')
        connection.execute('INSERT INTO runs VALUES (?,?)',('brfss','legacy remains'))
    old_id=record_results(reports,models,database)[0]
    assert record_results(reports,models,database)[0]==old_id
    assert len(list_results(database))==1
    old=get_result(old_id,database)
    assert old['training_created']=='2026-11-07T00:00:00Z'
    result['full'][0]['metrics']['average_precision']=.33
    report.write_text(json.dumps(result),encoding='utf-8')
    new_id=record_results(reports,models,database)[0]
    assert new_id!=old_id and len(list_results(database))==2
    assert get_result(old_id,database)['result']['full'][0]['metrics']['average_precision']==.32
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT result_json FROM runs').fetchone()[0]=='legacy remains'
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute('UPDATE experiment_snapshots SET model=? WHERE id=?',('altered',old_id))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute('DELETE FROM experiment_snapshots WHERE id=?',(old_id,))
        connection.execute('''INSERT OR REPLACE INTO experiment_snapshots
            SELECT id,dataset,created,training_created,source,?,model_version,
                average_precision,roc_auc,result_json,environment_json
            FROM experiment_snapshots WHERE id=?''',('replaced',old_id))
        assert connection.execute('SELECT model FROM experiment_snapshots WHERE id=?',(old_id,)).fetchone()[0]=='Logistic Regression'


def test_metadata_endpoints_and_metric_export():
    response=client.get('/api/quality');assert response.status_code==200
    q=response.json()
    assert q['datasets']['brfss']['raw_columns']==350
    assert q['privacy']['answers_saved'] is False and q['tests']['measured_now'] is False
    for dataset in ['brfss','uci']:
        r=client.get('/api/research-export/'+dataset)
        assert r.status_code==200
        rows=list(csv.DictReader(StringIO(r.content.decode('utf-8-sig'))))
        assert len(rows)==8 and all(row['dataset']==dataset for row in rows)
        assert 'procedure_definition' in rows[0]
    assert client.get('/api/research-export/uci?experiment=full').status_code==404
    assert client.get('/api/research-export/brfss?experiment=other').status_code==422
    assert client.get('/api/nonexistent').status_code==404
    literature=client.get('/api/library').json()
    murphy=next(book for book in literature['books'] if book['id']=='murphy2022pml')
    assert '2021' in murphy['pagination_warning'] and murphy['verified_sections']


def test_library_empty_is_graceful_and_private_paths_are_not_served(monkeypatch,tmp_path):
    monkeypatch.setattr(api,'REPORTS',tmp_path)
    empty=client.get('/api/library').json()
    assert empty['counts']=={'books':0,'papers':0,'software':0,'atherosclerosis':0}
    assert empty['atherosclerosis'] is None
    payload={'archive':{'file':'C:/private/download.pdf','pdf_count':12,'sha256':'abc'},
             'records':[{'id':'A01','title':'Example','url':'file:///private/secret','local_path':'C:/private/secret','reason_ru':'Read context'}]}
    (tmp_path/'atherosclerosis_library.json').write_text(json.dumps(payload),encoding='utf-8')
    result=client.get('/api/library').json()
    assert 'private' not in json.dumps(result)
    assert result['atherosclerosis']['archive']['pdf_count']==12
    assert result['atherosclerosis']['records'][0]['title']=='Example'
    assert client.get('/api/experiments').json()['runs']==[]
    assert client.get('/api/reliability').status_code==503


def test_bilingual_report_vocabulary_and_dataset_scope():
    from cardio.i18n import REPORT_TEXT,FIELD_KK,field_label,displayed_value,disclaimer
    assert set(FIELD_KK)>={field['name'] for fields in api.SCHEMAS.values() for field in fields}
    field=next(field for field in api.SCHEMAS['brfss'] if field['name']=='sex')
    assert field_label(field,'kk')=='Жынысы'
    assert displayed_value(field,2,'kk')=='Әйел'
    assert displayed_value(field,None,'kk')=='Көрсетілмеген'
    assert 'клиникалық' in disclaimer('uci','kk') and 'анкеты' not in disclaimer('uci','ru')
    for lang in ['ru','kk']:
        response=client.post('/api/report',json={'values':VALUES,'explain':False,'lang':lang})
        assert response.status_code==200 and response.content.startswith(b'%PDF')
        result=client.post('/api/predict',json={'values':VALUES,'explain':False,'lang':lang}).json()
        assert result['disclaimer']==disclaimer('brfss',lang)
    assert client.post('/api/report',json={'values':VALUES,'lang':'en'}).status_code==422


def test_batch_export_identifies_actual_model_version():
    sample=client.get('/api/template/brfss').content
    result=client.post('/api/batch/brfss',content=sample)
    assert result.status_code==200
    row=list(csv.DictReader(StringIO(result.content.decode('utf-8-sig'))))[0]
    prediction=client.post('/api/predict',json={'values':VALUES,'explain':False}).json()
    assert row['dataset']=='brfss'
    assert row['model_name']==prediction['model']
    assert row['model_version']==prediction['version']
