"""Local FastAPI application. No patient history is persisted."""
from functools import lru_cache
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Literal
import csv, hashlib, json, math, os
import joblib, numpy as np, pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from .config import ROOT,REPORTS,MODELS,SCHEMAS,DISCLAIMER

app=FastAPI(title='CardioResearch',version='3.3.0',description=DISCLAIMER)
BATCH_MAX_BYTES=1024*1024
BATCH_MAX_ROWS=1000
BATCH_MAX_ERRORS=50

class PredictionRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    dataset:str='brfss'
    # Keep original JSON scalar types until per-field validation: a boolean or
    # numeric string must never silently become a medical measurement.
    values:dict[str,Any]
    explain:bool=True
    lang:Literal['ru','kk']='ru'


@app.exception_handler(RequestValidationError)
async def request_validation_error(request,exc):
    errors=[]
    for error in exc.errors():
        field='.'.join(str(part) for part in error['loc'] if part!='body') or 'request'
        errors.append({'field':field,'label':field,'message':'Неверная структура или тип данных запроса'})
    # Avoid reflecting submitted medical values in framework error details.
    return JSONResponse(status_code=422,content={'detail':{'message':'Проверьте формат запроса','errors':errors}})

def dataset_name(ds):
    if ds not in SCHEMAS: raise HTTPException(400,'Неизвестный набор данных')
    return ds

@lru_cache(maxsize=2)
def bundle(ds):
    dataset_name(ds); p=MODELS/f'{ds}.joblib'
    if not p.exists():raise HTTPException(503,'Модель ещё не обучена. Запустите обучение.')
    return joblib.load(p)

def read_report(name):
    path=REPORTS/name
    if not path.exists():raise HTTPException(503,'Результаты эксперимента ещё не готовы.')
    return json.loads(path.read_text(encoding='utf-8'))

def validate_values(ds,values,allow_strings=False):
    fields=SCHEMAS[dataset_name(ds)]; names={f['name'] for f in fields}
    unknown=set(values)-names
    clean={}; errors=[{'field':name,'label':name,'message':'Неизвестное поле'} for name in sorted(unknown)]
    for f in fields:
        value=values.get(f['name'])
        if value is None:clean[f['name']]=np.nan;continue
        def invalid(message):errors.append({'field':f['name'],'label':f['label'],'message':message})
        if isinstance(value,bool) or not isinstance(value,(int,float)) and not (allow_strings and isinstance(value,str)):
            invalid('Требуется число, а не текст или логическое значение');continue
        try: v=float(value)
        except (TypeError,ValueError,OverflowError):invalid('Не удалось прочитать конечное число');continue
        if not math.isfinite(v):invalid('Требуется конечное число');continue
        if f['kind']=='category' and v not in [o['value'] for o in f['options']]:invalid('Выберите допустимую категорию')
        elif f['kind']=='number' and not f['min']<=v<=f['max']:invalid(f"Допустимый диапазон: {f['min']}–{f['max']}")
        elif f['kind']=='number' and f['step']==1 and v!=int(v):invalid('Требуется целое число')
        clean[f['name']]=v
    if errors:raise HTTPException(422,{'message':'Проверьте введённые показатели','errors':errors})
    if sum(pd.notna(v) for v in clean.values())<3:raise HTTPException(422,{'message':'Заполните минимум три показателя. Остальные можно оставить неизвестными.','errors':[{'field':'values','label':'Анкета','message':'Заполнено меньше трёх показателей'}]})
    return pd.DataFrame([clean])

def explain_prediction(ds,model,frame):
    """Permutation SHAP in raw probability units with an explicit background."""
    from .explain import permutation_shap
    background=joblib.load(MODELS/f'{ds}_background.joblib')[model.features].iloc[:30]
    def predict(a):return model.raw_probability(pd.DataFrame(a,columns=model.features))
    contributions,baseline=permutation_shap(predict,background.to_numpy(),frame[model.features].to_numpy()[0])
    items=[{'feature':name,'value':float(value)} for name,value in zip(model.features,contributions)]
    return {'method':'Permutation SHAP — interventional Shapley sampling','units':'raw_model_probability','baseline':baseline,'raw_probability':float(model.raw_probability(frame)[0]),'contributions':sorted(items,key=lambda t:abs(t['value']),reverse=True),'note':'Вклад в вероятность базовой модели до дополнительной калибровки; не причинный эффект. Собственная реализация оценки Шепли: 48 перестановок и 30 обучающих наблюдений.'}

def predict_payload(req):
    from .i18n import disclaimer
    ds=dataset_name(req.dataset); frame=validate_values(ds,req.values); model=bundle(ds); p=float(model.predict_proba(frame)[0,1])
    result={'dataset':ds,'model':model.name,'probability':p,'threshold':model.threshold,'positive':p>=model.threshold,'missing_fields':[c for c in frame if frame[c].isna().any()],'disclaimer':disclaimer(ds,req.lang),'version':hashlib.sha256((MODELS/f'{ds}.joblib').read_bytes()).hexdigest()[:12]}
    if req.explain:result['explanation']=explain_prediction(ds,model,frame)
    return result

@app.get('/api/health')
def health():return {'status':'ok','models':{ds:(MODELS/f'{ds}.joblib').exists() for ds in SCHEMAS},'runtime':'python-local','version':app.version}

@app.get('/api/metrics-insights')
def metrics_insights():return read_report('metrics-insights.json')

@app.get('/api/development-study')
def development_study():return read_report('development-study.json')

@app.get('/api/scientific-audit')
def scientific_audit():return read_report('scientific-audit.json')

@app.get('/api/auth/session')
def local_session():
    # The local application is bound to loopback by START.cmd. Internet hosting
    # uses the separate Worker auth implementation and never this local shortcut.
    return {'authenticated':True,'mode':'full','username':'local','local':True}

@app.get('/api/schema/{ds}')
def schema(ds:str):return {'fields':SCHEMAS[dataset_name(ds)],'disclaimer':DISCLAIMER}

@app.get('/api/research/{ds}')
def research(ds:str):return read_report(dataset_name(ds)+'_results.json')

@app.get('/api/data/{ds}')
def data(ds:str):return read_report(dataset_name(ds)+'_data.json')

@app.get('/api/environment')
def environment():return read_report('environment.json')


@app.get('/api/reliability')
def reliability():return read_report('reliability.json')


@app.get('/api/experiments')
def experiments():
    from .history import list_results
    runs=list_results(database=REPORTS/'experiments.sqlite')
    return {'runs':runs,'count':len(runs),'note':'Дата записи снимка и сохранённая дата обучения показаны отдельно. История содержит метаданные экспериментов, а не анкеты пользователей.'}


@app.get('/api/experiments/{run_id}')
def experiment(run_id:str):
    from .history import get_result
    result=get_result(run_id,database=REPORTS/'experiments.sqlite')
    if result is None:raise HTTPException(404,'Эксперимент не найден')
    return result


def optional_report(name):
    path=REPORTS/name
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


@app.get('/api/release-checks')
def release_checks():
    from .release_checks import build_release_checks
    return build_release_checks(REPORTS,app.version)


@app.get('/api/quality')
def quality():
    datasets={}
    for ds in SCHEMAS:
        report=optional_report(ds+'_data.json') or {}; training=report.get('training',{})
        row={key:report.get(key) for key in ['raw_rows','raw_columns','retained','unknown_target_removed','train_n','test_n']}
        row.update({'positive_fraction':training.get('prevalence'),'eda_n':training.get('n'),
            'eda_scope':report.get('eda_scope','Cleveland: full dataset descriptive summary'),
            'model_available':(MODELS/f'{ds}.joblib').exists(),
            'missing_fields':[{'name':f['name'],'label':f['label'],'count':training.get('missing',{}).get(f['name']),
                'fraction':training.get('missing',{}).get(f['name'],0)/training['n'] if training.get('n') else None} for f in SCHEMAS[ds]]})
        datasets[ds]=row
    from .release_checks import docker_quality_limit
    release=release_checks(); py=release['checks']['python']
    counts=[py.get(key) for key in ('passed','failed','errors','skipped')]
    tests={**py,'tests':sum(counts) if all(isinstance(v,int) for v in counts) else None,
        'source':release['report_file'],'checked_release':release['checked_release'],
        'version_match':release['version_match'],'measured_now':False}
    limits=[
      {'id':'purpose','title':'Область задачи','detail':'Классификация сообщённого или диагностированного заболевания; не прогноз события на 5 или 10 лет.','status':'limitation'},
      {'id':'population','title':'Переносимость','detail':'Нет независимой клинической проверки или проверки на населении Казахстана.','status':'not_validated'},
      {'id':'survey','title':'План обследования','detail':'Основные интервалы BRFSS не учитывают полностью сложный план обследования.','status':'limitation'},
      {'id':'uci_protocol','title':'UCI и финальное обучение','detail':'Внешняя CV оценила поиск по двум конфигурациям; финальный артефакт повторно настраивался по трём. Среднее CV не является независимым тестом именно финального артефакта.','status':'limitation'},
      {'id':'uci_sd','title':'Неопределённость','detail':'SD шести зависимых folds не является 95% доверительным интервалом. Дополнительные интервалы, если доступны, имеют отдельные условия в разделе надёжности.','status':'limitation'},
      docker_quality_limit(release)]
    return {'datasets':datasets,'tests':tests,'release':release,'environment':optional_report('environment.json') or {},'limits':limits,
        'privacy':{'answers_saved':False,'experiment_metadata_only':True,'batch_max_rows':BATCH_MAX_ROWS,'batch_max_bytes':BATCH_MAX_BYTES}}


def _public_source(item,allowed):
    result={key:item[key] for key in allowed if key in item}
    for key in list(result):
        if key.endswith('url') and result[key] and not str(result[key]).startswith(('https://','http://')):
            result.pop(key)
    if 'verified_sections' in result:
        result['verified_sections']=[_public_source(section,['chapter','section','title','printed_pages','printed_start_page','content_read_pages','draft_start_page','verified','evidence_url']) for section in result['verified_sections']]
    return result


@app.get('/api/library')
def library():
    from .literature import with_literature_additions
    books=(optional_report('literature_books.json') or {}).get('books',[])
    papers=(optional_report('literature_papers.json') or {}).get('sources',[])
    software=(optional_report('literature_software.json') or {}).get('sources',[])
    atherosclerosis=optional_report('atherosclerosis_library.json')
    public_books=[_public_source(row,['id','title','authors','year','citation','doi','official_url','publisher_url','legal_access','project_use','limitations','pagination_warning','verified_sections','student_reading_questions']) for row in books]
    public_papers=[_public_source(row,['id','title','authors','year','year_note','venue','doi','url','full_text_url','type','summary_kz','supports','limitation','verification','suggested_section']) for row in papers]
    public_software=[_public_source(row,['id','title','publisher','version','url','use_kz']) for row in software]
    if atherosclerosis:
        archive=atherosclerosis.get('archive',{})
        atherosclerosis={key:atherosclerosis[key] for key in ['summary_ru','summary_kk','recommendation'] if key in atherosclerosis} | {
            'archive':{key:archive[key] for key in ['sha256','bytes','pdf_count','tabular_files'] if key in archive},
            'records':[_public_source(row,['id','title','authors','year','doi','url','type','relevance','reason_ru','reason_kk','note_ru','note_kk','limitations_ru','limitations_kk']) for row in atherosclerosis.get('records',[])]}
    result = {'books':public_books,'papers':public_papers,'software':public_software,'atherosclerosis':atherosclerosis,
        'counts':{'books':len(public_books),'papers':len(public_papers),'software':len(public_software),'atherosclerosis':len((atherosclerosis or {}).get('records',[]))}}
    return with_literature_additions(result, optional_report('literature-additions.json') or {})


@app.get('/api/research-export/{ds}')
def research_export(ds:str,experiment:str='benchmark'):
    from .metrics_export import metrics_csv
    dataset_name(ds)
    if experiment not in ['benchmark','full']:raise HTTPException(422,'Выберите benchmark или full')
    result=read_report(ds+'_results.json')
    if not result.get(experiment):raise HTTPException(404,'Такой эксперимент для набора данных отсутствует')
    content=metrics_csv(result,ds,experiment).encode('utf-8')
    return Response(content,media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="{ds}_{experiment}_metrics.csv"','Cache-Control':'no-store'})

@app.post('/api/predict')
def predict(req:PredictionRequest):return predict_payload(req)


async def read_scenario_body(request):
    from .scenarios import MAX_SCENARIO_BYTES
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>MAX_SCENARIO_BYTES:raise HTTPException(413,'Максимальный размер JSON — 32 КБ')
    try:return json.loads(body.decode('utf-8-sig'))
    except (ValueError,UnicodeDecodeError):raise HTTPException(422,'Нужен корректный JSON')


def scenario_prediction(dataset,values,lang):
    return predict_payload(PredictionRequest(dataset=dataset,values=values,lang=lang,explain=False))


@app.post('/api/scenarios')
async def scenarios(request:Request):
    from .scenarios import run_scenarios,ScenarioError
    try:return run_scenarios(await read_scenario_body(request),SCHEMAS,scenario_prediction)
    except ScenarioError as exc:raise HTTPException(exc.status,exc.detail)


@app.get('/api/scenario-demo/{ds}')
def scenario_demo(ds:str,request:Request):
    from .scenarios import run_scenarios,demo_request,ScenarioError
    if any(key!='lang' for key in request.query_params) or len(request.query_params.getlist('lang'))>1:
        raise HTTPException(422,'Демонстрация принимает только параметр lang')
    dataset_name(ds)
    try:return run_scenarios(demo_request(ds,request.query_params.get('lang','ru')),SCHEMAS,scenario_prediction,synthetic=True)
    except ScenarioError as exc:raise HTTPException(exc.status,exc.detail)


@app.get('/api/reproducibility/{ds}')
def reproducibility(ds:str):
    from .scenarios import reproducibility_metadata
    ds=dataset_name(ds);model=bundle(ds)
    result=reproducibility_metadata(ds,read_report(ds+'_results.json'),schema(ds),read_report('environment.json'),
        model.name,hashlib.sha256((MODELS/f'{ds}.joblib').read_bytes()).hexdigest()[:12],model.threshold)
    return Response(json.dumps(result,ensure_ascii=False,indent=2).encode('utf-8'),media_type='application/json',
        headers={'Content-Disposition':f'attachment; filename="{ds}_reproducibility.json"','Cache-Control':'no-store'})

@app.get('/api/template/{ds}')
def template(ds:str):
    dataset_name(ds)
    if ds=='brfss':row=[7,1,27,4,1,3,3,2,3,2,1]
    else:row=[55,1,3,130,240,0,0,150,0,1,2,0,3]
    buff=StringIO(); writer=csv.writer(buff); writer.writerow([f['name'] for f in SCHEMAS[ds]]); writer.writerow(row)
    return Response(buff.getvalue().encode('utf-8-sig'),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="{ds}_example.csv"'})

async def read_batch(ds,request):
    dataset_name(ds); buf=bytearray()
    async for chunk in request.stream():
        buf.extend(chunk)
        if len(buf)>BATCH_MAX_BYTES:raise HTTPException(413,'Максимальный размер CSV — 1 МБ')
    try:
        text=buf.decode('utf-8-sig'); reader=csv.DictReader(StringIO(text),strict=True)
        expected={f['name'] for f in SCHEMAS[ds]}
        if set(reader.fieldnames or [])!=expected or len(reader.fieldnames or [])!=len(expected):raise HTTPException(422,'Названия столбцов должны совпадать с шаблоном')
        rows=[]
        while True:
            line=reader.line_num+1
            try:row=next(reader)
            except StopIteration:break
            rows.append((line,row))
            if len(rows)>BATCH_MAX_ROWS:raise HTTPException(422,'CSV должен содержать от 1 до 1000 строк')
    except (UnicodeDecodeError,csv.Error):raise HTTPException(422,'Нужен корректный CSV UTF-8 с запятой в качестве разделителя')
    if not rows:raise HTTPException(422,'CSV должен содержать от 1 до 1000 строк')
    return rows


def check_batch(ds,rows):
    frames=[];errors=[];invalid_rows=0
    for line,row in rows:
        try:
            if None in row or any(value is None for value in row.values()):
                raise HTTPException(422,{'errors':[{'field':'row','label':'Строка','message':'Число значений не соответствует заголовку CSV'}]})
            frames.append(validate_values(ds,{key:None if value.strip()=='' else value for key,value in row.items()},allow_strings=True))
        except HTTPException as exc:
            invalid_rows+=1
            if len(errors)<BATCH_MAX_ERRORS:
                errors.append({'line':line,'errors':exc.detail.get('errors',[]) if isinstance(exc.detail,dict) else [{'field':'row','label':'Строка','message':str(exc.detail)}]})
    return frames,{'rows':len(rows),'valid_rows':len(frames),'invalid_rows':invalid_rows,'errors':errors,'errors_truncated':invalid_rows>len(errors),'max_rows':BATCH_MAX_ROWS,'max_bytes':BATCH_MAX_BYTES}


@app.post('/api/batch/validate/{ds}')
async def batch_validate(ds:str,request:Request):
    _,result=check_batch(ds,await read_batch(ds,request))
    return result


@app.post('/api/batch/{ds}')
async def batch(ds:str,request:Request):
    frames,validation=check_batch(ds,await read_batch(ds,request))
    if validation['invalid_rows']:raise HTTPException(422,{'message':'Исправьте строки CSV перед прогнозом',**validation})
    frame=pd.concat(frames,ignore_index=True); m=bundle(ds); p=m.predict_proba(frame)[:,1]
    # Export only numeric validated fields; no spreadsheet formulas from the input.
    frame['model_probability']=p; frame['decision_threshold']=m.threshold; frame['predicted_class']=(p>=m.threshold).astype(int)
    frame['dataset']=ds
    frame['model_name']=m.name
    frame['model_version']=hashlib.sha256((MODELS/f'{ds}.joblib').read_bytes()).hexdigest()[:12]
    return Response(frame.to_csv(index=False).encode('utf-8-sig'),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="predictions.csv"'})

@app.post('/api/report')
def report(req:PredictionRequest):
    from .i18n import REPORT_TEXT,field_label,displayed_value
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.utils import simpleSplit
    result=predict_payload(req); stream=BytesIO(); font=ROOT/'assets'/'DejaVuSans.ttf'
    pdfmetrics.registerFont(TTFont('DejaVu',str(font)))
    words=REPORT_TEXT[req.lang]
    pdf=canvas.Canvas(stream,pagesize=(595,842));pdf.setTitle(words['document_title']);pdf.setFont('DejaVu',10);y=790
    def line(text,size=10):
        nonlocal y
        for part in simpleSplit(str(text),'DejaVu',size,490):
            if y<55:pdf.showPage();y=790
            pdf.setFont('DejaVu',size);pdf.drawString(50,y,part);y-=size+6
    line('CardioResearch',22);line(words['heading'],14);y-=8
    line(words['dataset']+': '+req.dataset.upper());line(words['model']+': '+result['model']+' / '+words['version']+' '+result['version'])
    line(f"{words['estimate']}: {result['probability']:.1%}. {words['threshold']}: {result['threshold']:.3f}.")
    line(words['class']+': '+words['positive' if result['positive'] else 'negative'])
    y-=10;line(words['inputs'],13)
    for f in SCHEMAS[req.dataset]:
        line(field_label(f,req.lang)+': '+displayed_value(f,req.values.get(f['name']),req.lang))
    if 'explanation' in result:
        y-=10;line(words['explanation'],13);line(words['explanation_note'])
        labels={f['name']:field_label(f,req.lang) for f in SCHEMAS[req.dataset]}
        for item in result['explanation']['contributions'][:7]:line(f"{labels[item['feature']]}: {item['value']*100:+.2f} {words['units']}")
    y-=10;line(result['disclaimer']);pdf.save()
    return Response(stream.getvalue(),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="cardio_report.pdf"'})

from .evaluation import register_evaluation_routes
from .experiment_lab import register_experiment_lab_routes
register_evaluation_routes(app, REPORTS)
register_experiment_lab_routes(app, ROOT)

dist=ROOT/'frontend'/'dist'
@app.get('/api/{path:path}')
def missing_api(path:str):raise HTTPException(404,'Маршрут API не найден')

if dist.exists():
    app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
    @app.get('/{path:path}')
    def index(path:str):return FileResponse(dist/'index.html')
