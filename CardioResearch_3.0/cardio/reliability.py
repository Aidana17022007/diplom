"""Supplementary checks of fixed predictions; no deployment or model selection.

Recreate saved outer-fold predictions with their already selected parameters,
verify their metrics, then resample patients jointly across algorithms. These
intervals describe the fixed cross-fitted predictions, not uncertainty of the
whole training/selection process or independent validation of deployed models.
"""
import os
os.environ.setdefault('OMP_NUM_THREADS','2')
os.environ.setdefault('OPENBLAS_NUM_THREADS','2')
import hashlib
import json
import threading
import time
import warnings
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import psutil
from scipy.stats import binomtest
from sklearn.base import clone
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
from threadpoolctl import threadpool_limits
from .config import REPORTS, DATA, MODELS, SCHEMAS, SEED
from .learning import candidates, metrics
from .prepare import write_json

METRICS=('roc_auc','average_precision','recall','brier')

def exact_recall_interval(tp, positive, confidence=.95):
    if positive == 0: return None
    if not 0 <= tp <= positive: raise ValueError('Invalid success count')
    ci=binomtest(int(tp),int(positive)).proportion_ci(confidence_level=confidence,method='exact')
    return [float(ci.low),float(ci.high)]

def fixed_prediction_bootstrap(y, probabilities, repeats=500, seed=SEED):
    """Shared patient resamples, preserving pairing across fixed predictions."""
    y=np.asarray(y,dtype=int)
    if len(np.unique(y)) != 2: raise ValueError('Two outcome classes are required')
    if repeats < 20: raise ValueError('Use at least20 resamples')
    ps={k:np.asarray(v,dtype=float) for k,v in probabilities.items()}
    if any(p.shape != y.shape or not np.isfinite(p).all() or (p<0).any() or (p>1).any() for p in ps.values()):
        raise ValueError('Invalid prediction vector')
    samples={k:[] for k in ps};rng=np.random.default_rng(seed)
    for _ in range(repeats):
        ids=rng.integers(0,len(y),len(y));yb=y[ids]
        if len(np.unique(yb))<2: continue
        for name,p in ps.items():
            pb=p[ids]
            samples[name].append([roc_auc_score(yb,pb),average_precision_score(yb,pb),float(np.mean(pb[yb==1]>=.5)),brier_score_loss(yb,pb)])
    result={name:{key:np.quantile(np.asarray(vals)[:,i],[.025,.975]).tolist() for i,key in enumerate(METRICS)} for name,vals in samples.items()}
    return result,{k:np.asarray(v) for k,v in samples.items()}

def subgroup_intervals():
    result=json.loads((REPORTS/'brfss_results.json').read_text(encoding='utf-8'))
    rows=[]
    for group in result['subgroups']:
        field=next(f for f in SCHEMAS['brfss'] if f['name']==group['feature'])
        label=next(o['label'] for o in field['options'] if o['value']==group['value'])
        tp=int(group['metrics']['confusion'][1][1]);positive=int(group['positive'])
        rows.append({k:group[k] for k in ['feature','value','n','positive']}|{
            'label':label,'true_positive':tp,'recall':group['metrics']['recall'],
            'recall_ci':exact_recall_interval(tp,positive),'method':'Clopper–Pearson',
            'original_percentile_interval':group['ci']['recall']})
    test_n=result['protocol']['test']
    coverage={feature:{'accounted':sum(x['n'] for x in rows if x['feature']==feature),'missing':test_n-sum(x['n'] for x in rows if x['feature']==feature)} for feature in ['sex','age_group']}
    return {'subgroups':rows,'coverage':coverage,'confidence_level':.95,
        'note_ru':'95% интервалы чувствительности по биномиальной модели; при нуле обнаруженных случаев верхняя граница остаётся положительной.',
        'note_kk':'Сезімталдықтың биномиалдық модельдегі 95% аралықтары: анықталған жағдай саны нөл болса да, жоғарғы шек оң болып қалады.',
        'limitations':['Описательные невзвешенные интервалы; независимость респондентов предполагается.','Сложный план BRFSS и множественные сравнения не учтены.','Интервал не является доказательством справедливости модели или переносимости на Казахстан.']}

def run(repeats=500):
    started=time.perf_counter();process=psutil.Process();peak=[process.memory_info().rss];stop=threading.Event()
    def monitor():
        while not stop.wait(.05):peak[0]=max(peak[0],process.memory_info().rss)
    watcher=threading.Thread(target=monitor,daemon=True);watcher.start()
    original_hash={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in MODELS.glob('*.joblib')}
    source=json.loads((REPORTS/'uci_results.json').read_text(encoding='utf-8'))
    folds=json.loads((REPORTS/'uci_folds.json').read_text(encoding='utf-8'))
    data=pd.read_pickle(DATA/'processed'/'uci.pkl').set_index('row_id',drop=False)
    features=[f['name'] for f in SCHEMAS['uci']];X=data[features];y=data.target.to_numpy()
    position={rid:i for i,rid in enumerate(data.index)};probabilities={};models=[]
    try:
        with threadpool_limits(limits=2):
            for row in source['benchmark']:
                name=row['name'];print('Reproducing locked UCI folds:',name,flush=True)
                selected=sorted([f for f in folds if f['model']==name],key=lambda x:x['fold'])
                base,_=candidates('uci')[name];oof=np.full((2,len(data)),np.nan);max_delta=0.;fold_checks=[]
                for fold in selected:
                    i=fold['fold'];tr=fold['train_ids'];te=fold['test_ids']
                    assert not set(tr)&set(te)
                    params=row['params'][i] if row['params'] else {}
                    model=clone(base).set_params(**params).fit(X.loc[tr],data.target.loc[tr])
                    p=model.predict_proba(X.loc[te])[:,1];observed=metrics(data.target.loc[te],p)
                    delta=max(abs(observed[k]-fold['metrics'][k]) for k in observed if k!='confusion')
                    max_delta=max(max_delta,delta);fold_checks.append({'fold':i,'max_abs_metric_delta':delta,'test_n':len(te)})
                    oof[i//3,[position[rid] for rid in te]]=p
                if np.isnan(oof).any(): raise RuntimeError('Incomplete OOF coverage')
                if max_delta>1e-7: raise RuntimeError(f'{name}: saved fold mismatch {max_delta}')
                p=oof.mean(axis=0);probabilities[name]=p
                # Identical batch size and thread limits for timing only; not a new quality estimate.
                batch=X.loc[selected[-1]['test_ids']];model.predict_proba(batch);timings=[]
                for _ in range(7):
                    tick=time.perf_counter();model.predict_proba(batch);timings.append((time.perf_counter()-tick)*1000)
                models.append({'name':name,'metrics':metrics(y,p),'fold_match':True,'max_abs_metric_delta':max_delta,'fold_checks':fold_checks,
                    'predict_timing':{'n':len(batch),'repeats':7,'median_ms':float(np.median(timings)),'p95_ms':float(np.quantile(timings,.95)),
                    'scope':'last outer-fold estimator;101 rows; warm inference;2 native threads; not HTTP latency'}})
            print('Paired fixed-prediction bootstrap:',repeats,flush=True)
            cis,draws=fixed_prediction_bootstrap(y,probabilities,repeats)
            for item in models:item['ci']=cis[item['name']]
        winner=source['selection']['deployed_model'];paired=[]
        for other in ['Logistic Regression','Linear SVM']:
            if other==winner:continue
            paired.append({'a':winner,'b':other,'metric':'average_precision',
                'estimate':float(average_precision_score(y,probabilities[winner])-average_precision_score(y,probabilities[other])),
                'ci':np.quantile(draws[winner][:,1]-draws[other][:,1],[.025,.975]).tolist()})
        oof_table=pd.DataFrame({'row_id':data.row_id,'target':y,**probabilities})
        oof_table.to_csv(REPORTS/'uci_oof_predictions.csv',index=False)
        brfss=subgroup_intervals()
        unchanged=all(hashlib.sha256((MODELS/name).read_bytes()).hexdigest()==digest for name,digest in original_hash.items())
        if not unchanged:raise RuntimeError('Deployment model artifacts changed during reliability checks')
        report={'created':datetime.now(timezone.utc).isoformat(),
          'method':{'confidence_level':.95,'bootstrap_repeats':repeats,'seed':SEED,'selection_changed':False,
            'sources':['https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats._result_classes.BinomTestResult.proportion_ci.html','https://scikit-learn.org/1.7/modules/cross_validation.html']},
          'uci':{'n':len(y),'repeats':repeats,'models':models,'paired':paired,
            'note_ru':'Приближённые95% интервалы для фиксированных усреднённых OOF-прогнозов. Отдельная описательная оценка, не доверительные интервалы всей процедуры обучения.',
            'note_kk':'Орташаланған тұрақты OOF-болжамдардың жуық 95% аралықтары. Бұл толық оқыту рәсімінің сенімділік аралықтары емес, бөлек сипаттамалық бағалау.',
            'limitations':['Обучающие выборки CV пересекаются; их зависимость не учитывается повторной выборкой фиксированных прогнозов.','Модели и параметры при bootstrap не переобучаются; неопределённость настройки и выбора алгоритма не охвачена.','Метрики усреднённых OOF отличаются от среднего метрик6внешнихfold.','Финальный артефакт обучен с другим бюджетом настройки(3конфигурации вместо2); эти интервалы не являются его независимой валидацией.']},
          'brfss':brfss,'reproduction':{'elapsed_seconds':time.perf_counter()-started,'peak_rss_mb':peak[0]/1024**2,
            'original_models_preserved':unchanged,'fold_metrics_matched':True,'native_threads':2,
            'scope':'locked outer-fold estimators refitted for reproduction; original search not rerun;deployment models unchanged'}}
        write_json(REPORTS/'reliability.json',report)
        print('Reliability report saved',len(models),'models; peak MiB',round(peak[0]/1024**2),flush=True)
        return report
    finally:stop.set();watcher.join(timeout=1)

if __name__=='__main__': run()
