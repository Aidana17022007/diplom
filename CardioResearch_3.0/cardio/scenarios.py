"""Bounded one-feature model scenarios; no causal or medical-risk inference."""
import math

MAX_SCENARIO_BYTES=32768
MAX_SCENARIO_POINTS=9
NOTES={
    'ru':'Это изменение оценки модели при подстановке одного показателя. Разность вероятностей не означает причинный эффект, результат лечения или изменение будущего риска заболевания.',
    'kk':'Бір көрсеткішті өзгерткенде модель бағасының қалай өзгеретінін көрсетеді. Ықтималдықтар айырмасы себептік әсерді, емдеу нәтижесін немесе болашақтағы ауру қаупінің өзгеруін білдірмейді.',
}
DEMO={
    'brfss':{'values':{'age_group':7,'sex':1,'bmi':27,'smoking':4,'activity':1,'diabetes':3,'hypertension':3,'cholesterol':2,'general_health':3,'physical_days':2,'mental_days':1},'vary':{'feature':'bmi','values':[22,27,32,37]}},
    'uci':{'values':{'age':55,'sex':1,'cp':3,'trestbps':130,'chol':240,'fbs':0,'restecg':0,'thalach':150,'exang':0,'oldpeak':1,'slope':2,'ca':0,'thal':3},'vary':{'feature':'oldpeak','values':[0,1,2,3]}},
}
PROTOCOL_KEYS=['seed','primary_metric','benchmark_train','benchmark_test','fit','calibration','validation','test','cv','search_trials','full_candidates','selection','weighting','ci','feature_policy','outer','inner','selection_caveat']
SELECTION_KEYS=['benchmark_winner','deployed_model','threshold','calibration','locked_before_test','locked_at']
ENVIRONMENT_KEYS=['python','sklearn','pandas','numpy','lightgbm','seed','started']


class ScenarioError(ValueError):
    def __init__(self,status,detail):
        super().__init__(str(detail));self.status=status;self.detail=detail


def checked_request(payload,schemas):
    if not isinstance(payload,dict) or set(payload)-{'dataset','values','vary','lang'}:
        raise ScenarioError(422,'Проверьте структуру запроса сценария')
    dataset=payload.get('dataset','brfss');lang=payload.get('lang','ru')
    if not isinstance(dataset,str) or not isinstance(lang,str):raise ScenarioError(422,'Неверный тип набора данных или языка')
    if dataset not in schemas:raise ScenarioError(400,'Неизвестный набор данных')
    if lang not in NOTES:raise ScenarioError(422,'Неверный язык')
    values=payload.get('values');vary=payload.get('vary')
    if not isinstance(values,dict) or not isinstance(vary,dict) or set(vary)!={'feature','values'}:
        raise ScenarioError(422,'Укажите values и vary с полями feature и values')
    feature=vary['feature'];points=vary['values']
    if not isinstance(feature,str) or feature not in {field['name'] for field in schemas[dataset]}:
        raise ScenarioError(422,'Неизвестный показатель сценария')
    if not isinstance(points,list) or not 2<=len(points)<=MAX_SCENARIO_POINTS:
        raise ScenarioError(422,'Нужно от 2 до 9 различных значений показателя')
    for point in points:
        try:valid=not isinstance(point,bool) and isinstance(point,(int,float)) and math.isfinite(float(point))
        except (ValueError,OverflowError):valid=False
        if not valid:raise ScenarioError(422,'Значения сценария должны быть конечными числами')
    if len(set(points))!=len(points):raise ScenarioError(422,'Значения сценария не должны повторяться')
    return dataset,lang,values,feature,points


def run_scenarios(payload,schemas,predict,synthetic=False):
    """predict(dataset,values,lang) must call the ordinary real model pipeline."""
    dataset,lang,values,feature,points=checked_request(payload,schemas)
    baseline=predict(dataset,values,lang)
    normalized={field['name']:values.get(field['name']) for field in schemas[dataset]}
    results=[]
    for point in points:
        result=predict(dataset,{**normalized,feature:point},lang)
        results.append({'value':point,'probability':result['probability'],
            'delta':result['probability']-baseline['probability'],'positive':result['positive']})
    return {'dataset':dataset,'model':baseline['model'],'version':baseline['version'],'threshold':baseline['threshold'],
        'feature':feature,'baseline':{'values':normalized,'probability':baseline['probability'],
            'positive':baseline['positive'],'missing_fields':baseline['missing_fields']},
        'points':results,'note':NOTES[lang],'synthetic':synthetic}


def demo_request(dataset,lang='ru'):
    if dataset not in DEMO:raise ScenarioError(400,'Неизвестный набор данных')
    return {'dataset':dataset,'lang':lang,'values':dict(DEMO[dataset]['values']),
            'vary':{'feature':DEMO[dataset]['vary']['feature'],'values':list(DEMO[dataset]['vary']['values'])}}


def reproducibility_metadata(dataset,report,schema,environment,model,version,threshold):
    # Whitelists deliberately exclude observation IDs, fitted parameters,
    # backgrounds, local paths, session data and source-machine identity.
    return {'format_version':1,'dataset':dataset,'model':model,'model_version':version,'threshold':threshold,
        'protocol':{key:report.get('protocol',{})[key] for key in PROTOCOL_KEYS if key in report.get('protocol',{})},
        'selection':{key:report.get('selection',{})[key] for key in SELECTION_KEYS if key in report.get('selection',{})},
        'schema':schema,'environment':{key:environment[key] for key in ENVIRONMENT_KEYS if key in environment}}
