"""Export the existing fitted estimators for exact JavaScript inference.

No fitting or hyperparameter search occurs here. The export includes all fitted
preprocessing, model parameters, calibration, schemas, and the original SHAP
background and NumPy-generated permutation orders. Re-export is deterministic.
"""
from pathlib import Path
import hashlib
import json
import sys

import joblib
import numpy as np
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cardio.config import MODELS, SCHEMAS, SEED
from cardio.i18n import REPORT_TEXT, FIELD_KK, OPTION_KK, DISCLAIMERS

OUTPUT=ROOT/'deployment/cardio-site/data/models.json'


def numbers(value):
    """Only JSON-native numbers; NaN in an input background means missing."""
    if isinstance(value,np.ndarray):return numbers(value.tolist())
    if isinstance(value,list):return [numbers(item) for item in value]
    if isinstance(value,dict):return {key:numbers(item) for key,item in value.items()}
    if isinstance(value,(np.integer,)):return int(value)
    if isinstance(value,(float,np.floating)):return float(value) if np.isfinite(value) else None
    return value


def export_preprocessing(pre):
    num=pre.named_transformers_['num'];cat=pre.named_transformers_['cat']
    names={name:list(columns) for name,_,columns in pre.transformers_ if name in ['num','cat']}
    scale=num.named_steps['scale'];encoder=cat.named_steps['encode']
    if encoder.drop is not None or encoder.handle_unknown!='ignore':raise ValueError('Unsupported category encoding')
    mean=scale.mean_ if scale.with_mean else np.zeros(len(names['num']))
    scales=scale.scale_ if scale.with_std else np.ones(len(names['num']))
    result={'numeric':{'names':names['num'],'fill':num.named_steps['impute'].statistics_,
                       'mean':mean,'scale':scales},
            'categorical':{'names':names['cat'],'fill':cat.named_steps['impute'].statistics_,
                           'categories':[array.tolist() for array in encoder.categories_]},
            'output_width':len(pre.get_feature_names_out())}
    return numbers(result)


def export_estimator(estimator):
    if list(estimator.classes_)!=[0,1]:raise ValueError('Only the existing binary0/1 models are supported')
    if isinstance(estimator,LogisticRegression):
        return {'type':'logistic_regression','coef':numbers(estimator.coef_[0]),'intercept':float(estimator.intercept_[0])}
    if isinstance(estimator,RandomForestClassifier):
        trees=[]
        for fitted_tree in estimator.estimators_:
            tree=fitted_tree.tree_
            values=tree.value[:,0,:]
            # sklearn stores class proportions in1.7; normalization also supports counts.
            positive=values[:,1]/values.sum(axis=1)
            trees.append(numbers({'left':tree.children_left,'right':tree.children_right,
                'feature':tree.feature,'threshold':tree.threshold,'positive':positive,
                'missing_go_to_left':tree.missing_go_to_left}))
        return {'type':'random_forest','feature_dtype':'float32','trees':trees}
    raise ValueError(f'Unsupported fitted estimator: {type(estimator).__name__}')


def export_model(dataset):
    path=MODELS/f'{dataset}.joblib';bundle=joblib.load(path)
    if list(bundle.pipeline.named_steps)!=['pre','model']:raise ValueError('Unexpected pipeline structure')
    background=joblib.load(MODELS/f'{dataset}_background.joblib')[bundle.features].iloc[:30]
    rng=np.random.default_rng(SEED);orders=[]
    for _ in range(24):
        order=rng.permutation(len(bundle.features));orders.extend([order.tolist(),order[::-1].tolist()])
    calibration=None
    if bundle.calibrator is not None:
        calibration=export_estimator(bundle.calibrator)
        calibration['input']='logit_raw_probability'
        calibration['clip']=[1e-6,1-1e-6]
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    return {'dataset':dataset,'name':bundle.name,'features':bundle.features,'threshold':bundle.threshold,
        'version':sha[:12],'artifact_sha256':sha,'schema':SCHEMAS[dataset],
        'preprocessing':export_preprocessing(bundle.pipeline.named_steps['pre']),
        'estimator':export_estimator(bundle.pipeline.named_steps['model']),'calibrator':calibration,
        'shap':{'seed':SEED,'permutations':48,'orders':orders,'background':numbers(background.to_numpy()),
                'units':'raw_model_probability','method':'Permutation SHAP — interventional Shapley sampling',
                'reproducibility':'Identical30-row background and48 NumPy-generated permutation orders as the Python API'}}


def export_all(output=OUTPUT):
    export={'format_version':1,'source':'Existing fitted joblib artifacts; no retraining',
        'sklearn_version':sklearn.__version__,
        'datasets':{dataset:export_model(dataset) for dataset in ['brfss','uci']},
        'localization':{'report_text':REPORT_TEXT,'field_kk':FIELD_KK,'option_kk':OPTION_KK,'disclaimers':DISCLAIMERS}}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(export,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
    return export


if __name__=='__main__':
    data=export_all()
    print(f'Exported {OUTPUT.stat().st_size} bytes; BRFSS logistic + calibration; UCI {len(data["datasets"]["uci"]["estimator"]["trees"])} trees')
