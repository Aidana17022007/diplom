"""Reproduce three paper-informed analyses without changing production models."""
import hashlib,json,time,platform
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import average_precision_score,roc_auc_score,brier_score_loss
from threadpoolctl import threadpool_limits
from cardio.learning import preprocessing
from cardio.config import SCHEMAS
from cardio.calibration_audit import calibration_diagnostics,prior_scenario

ROOT=Path(__file__).resolve().parents[1]
def read(name):return json.loads((ROOT/'reports'/name).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    protocol=read('literature_experiments_protocol.json')
    watched=[ROOT/'models/brfss.joblib',ROOT/'models/uci.joblib',ROOT/'reports/brfss_results.json',ROOT/'reports/uci_results.json',ROOT/'data/processed/brfss.pkl',ROOT/'reports/brfss_splits.json',ROOT/'reports/brfss_test_predictions.csv']
    before={str(p.relative_to(ROOT)):sha(p) for p in watched}
    df=pd.read_pickle(ROOT/'data/processed/brfss.pkl').copy()
    df.index=df.row_id.astype(str)
    assert df.index.is_unique
    split=read('brfss_splits.json')
    train=df.loc[list(map(str,split['benchmark_train']))]
    assert len(train)==12000 and train.split.eq('train').all()
    assert not set(train.index)&set(map(str,split['test']))
    features=[f['name'] for f in SCHEMAS['brfss']]
    cv=list(StratifiedKFold(3,shuffle=True,random_state=20261107).split(train,train.target))
    records=[]
    for indicators in [False,True]:
        folds=[]
        for fold,(fit,validation) in enumerate(cv,1):
            pre=preprocessing('brfss').set_params(num__impute__add_indicator=indicators)
            model=Pipeline([('pre',pre),('model',LogisticRegression(C=1,max_iter=1500,random_state=20261107))])
            start=time.perf_counter();model.fit(train.iloc[fit][features],train.iloc[fit].target)
            p=model.predict_proba(train.iloc[validation][features])[:,1];y=train.iloc[validation].target
            folds.append({'fold':fold,'n_fit':len(fit),'n_validation':len(validation),'average_precision':float(average_precision_score(y,p)),
                          'roc_auc':float(roc_auc_score(y,p)),'brier':float(brier_score_loss(y,p)),'fit_and_score_seconds':time.perf_counter()-start,
                          'transformed_features':int(model.named_steps['pre'].transform(train.iloc[:1][features]).shape[1])})
        records.append({'numeric_missing_indicators':indicators,'folds':folds,'mean':{k:float(np.mean([r[k] for r in folds])) for k in ['average_precision','roc_auc','brier']}})
        print('Missing indicators',indicators,records[-1]['mean'],flush=True)
    stored=pd.read_csv(ROOT/'reports/brfss_test_predictions.csv',dtype={'row_id':str})
    test=df.loc[stored.row_id]
    assert test.split.eq('test').all() and np.array_equal(test.target.to_numpy(),stored.target.to_numpy())
    bundle=joblib.load(ROOT/'models/brfss.joblib')
    raw=bundle.raw_probability(test[features]);p=bundle.predict_proba(test[features])[:,1]
    parity=float(np.max(np.abs(p-stored.probability.to_numpy())))
    assert parity < 1e-10
    y=stored.target.to_numpy()
    calibration=[]
    for label,scores in [('raw',raw),('deployed_sigmoid',p)]:
        calibration.append({'version':label,**calibration_diagnostics(y,scores),'brier':float(brier_score_loss(y,scores)),
                            'roc_auc':float(roc_auc_score(y,scores)),'average_precision':float(average_precision_score(y,scores))})
    scenarios=[prior_scenario(y,p,x,bundle.threshold) for x in [0.01,0.05,float(y.mean()),0.1,0.2]]
    report={'created_utc':datetime.now(timezone.utc).isoformat(),'python':platform.python_version(),'protocol':protocol,'protocol_sha256':sha(ROOT/'reports/literature_experiments_protocol.json'),
            'missingness':records,'calibration':calibration,'prevalence_scenarios':scenarios,
            'test_prediction_max_delta':parity,'threshold':bundle.threshold,
            'input_sha256':before,'inputs_unchanged':all(sha(ROOT/n)==h for n,h in before.items())}
    assert report['inputs_unchanged']
    (ROOT/'reports/literature_experiments.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Saved literature_experiments.json',flush=True)


if __name__=='__main__':
    with threadpool_limits(limits=2):run()
