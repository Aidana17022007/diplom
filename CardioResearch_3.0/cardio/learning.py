"""Shared pipelines, metrics and version-stable model bundles."""
import numpy as np
import pandas as pd
from scipy.special import expit
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import roc_auc_score, average_precision_score, accuracy_score, precision_score, recall_score, f1_score, brier_score_loss, confusion_matrix, roc_curve, precision_recall_curve
from lightgbm import LGBMClassifier
from .config import SCHEMAS, SEED

def preprocessing(dataset,features=None,scale=True):
    fields=[f for f in SCHEMAS[dataset] if features is None or f['name'] in features]
    numeric=[f['name'] for f in fields if f['kind']=='number']
    cats=[f for f in fields if f['kind']=='category']
    numeric_pipe=Pipeline([('impute',SimpleImputer(strategy='median',keep_empty_features=True)),('scale',StandardScaler() if scale else 'passthrough')])
    # Fixed documented categories (including unknown=-1) are not learned from test rows.
    cat_pipe=Pipeline([('impute',SimpleImputer(strategy='constant',fill_value=-1)),('encode',OneHotEncoder(categories=[[-1]+[o['value'] for o in f['options']] for f in cats],handle_unknown='ignore',sparse_output=False))])
    return ColumnTransformer([('num',numeric_pipe,numeric),('cat',cat_pipe,[f['name'] for f in cats])])

def candidates(dataset):
    specs={
      'Dummy':(DummyClassifier(strategy='prior'),{}),
      'Logistic Regression':(LogisticRegression(max_iter=1500,random_state=SEED),{'model__C':[.1,1,10],'model__class_weight':[None,'balanced']}),
      'Decision Tree':(DecisionTreeClassifier(max_depth=5,min_samples_leaf=15,random_state=SEED),{'model__max_depth':[3,5,8],'model__min_samples_leaf':[5,20,50]}),
      'Random Forest':(RandomForestClassifier(n_estimators=100,max_depth=8,min_samples_leaf=5,n_jobs=2,random_state=SEED),{'model__max_depth':[5,10,None],'model__min_samples_leaf':[3,10,25]}),
      'Linear SVM':(CalibratedClassifierCV(LinearSVC(C=.1,dual='auto',max_iter=2500,random_state=SEED),cv=3),{'model__estimator__C':[.01,.1,1],'model__estimator__class_weight':[None,'balanced']}),
      'KNN':(KNeighborsClassifier(n_neighbors=31,n_jobs=2),{'model__n_neighbors':[15,31,61],'model__weights':['uniform','distance']}),
      'LightGBM':(LGBMClassifier(n_estimators=140,num_leaves=15,max_depth=-1,min_child_samples=25,learning_rate=.05,verbosity=-1,n_jobs=2,random_state=SEED,deterministic=True,force_col_wise=True),{'model__num_leaves':[7,15,31],'model__min_child_samples':[20,60],'model__reg_lambda':[0,2]}),
      'MLP':(MLPClassifier(hidden_layer_sizes=(32,),max_iter=140,early_stopping=True,n_iter_no_change=12,random_state=SEED),{'model__hidden_layer_sizes':[(24,),(48,24)],'model__alpha':[.001,.1,.5]})
    }
    result={name:(Pipeline([('pre',preprocessing(dataset)),('model',model)]),params) for name,(model,params) in specs.items()}
    # The calibration folds must also own their preprocessing parameters.
    svm=Pipeline([('pre',preprocessing(dataset)),('svm',LinearSVC(C=.1,dual='auto',max_iter=2500,random_state=SEED))])
    result['Linear SVM']=(Pipeline([('model',CalibratedClassifierCV(svm,cv=3))]),{'model__estimator__svm__C':[.01,.1,1],'model__estimator__svm__class_weight':[None,'balanced']})
    return result

def metrics(y,p,threshold=.5,weight=None):
    pred=np.asarray(p)>=threshold; tn,fp,fn,tp=confusion_matrix(y,pred,labels=[0,1],sample_weight=weight).ravel()
    return {'roc_auc':float(roc_auc_score(y,p,sample_weight=weight)),'average_precision':float(average_precision_score(y,p,sample_weight=weight)),
      'accuracy':float(accuracy_score(y,pred,sample_weight=weight)),'precision':float(precision_score(y,pred,sample_weight=weight,zero_division=0)),
      'recall':float(recall_score(y,pred,sample_weight=weight,zero_division=0)),'specificity':float(tn/(tn+fp)) if tn+fp else 0.,
      'f1':float(f1_score(y,pred,sample_weight=weight,zero_division=0)),'brier':float(brier_score_loss(y,p,sample_weight=weight)),
      'confusion':[[float(tn),float(fp)],[float(fn),float(tp)]]}

def curves(y,p):
    fpr,tpr,_=roc_curve(y,p); prec,rec,_=precision_recall_curve(y,p)
    def thin(a,b):
        idx=np.unique(np.linspace(0,len(a)-1,min(180,len(a))).astype(int)); return {'x':np.asarray(a)[idx].tolist(),'y':np.asarray(b)[idx].tolist()}
    frac,mean=calibration_curve(y,p,n_bins=10,strategy='quantile')
    return {'roc':thin(fpr,tpr),'pr':thin(rec,prec),'calibration':{'x':mean.tolist(),'y':frac.tolist()}}

class ModelBundle:
    def __init__(self,pipeline,features,dataset,name,threshold=.5,calibrator=None):
        self.pipeline=pipeline; self.features=features; self.dataset=dataset; self.name=name; self.threshold=threshold; self.calibrator=calibrator
    def raw_probability(self,X): return self.pipeline.predict_proba(X[self.features])[:,1]
    def predict_proba(self,X):
        p=self.raw_probability(X)
        if self.calibrator is not None: p=self.calibrator.predict_proba(logit(p).reshape(-1,1))[:,1]
        return np.c_[1-p,p]

def logit(p):
    p=np.clip(p,1e-6,1-1e-6); return np.log(p/(1-p))

def fit_calibrator(p,y): return LogisticRegression(C=1e6,max_iter=1000,random_state=SEED).fit(logit(p).reshape(-1,1),y)

def threshold_for_f1(y,p):
    prec,rec,thresholds=precision_recall_curve(y,p)
    f=2*prec[:-1]*rec[:-1]/np.maximum(prec[:-1]+rec[:-1],1e-12)
    return float(thresholds[np.argmax(f)])

def bootstrap(y,p,threshold=.5,other=None,repeats=200):
    """Conditional iid respondent bootstrap; not design-based survey inference."""
    y=np.asarray(y); p=np.asarray(p); rng=np.random.default_rng(SEED); values=[]; delta=[]
    for _ in range(repeats):
        idx=rng.integers(0,len(y),len(y))
        if len(np.unique(y[idx]))<2: continue
        m=metrics(y[idx],p[idx],threshold); values.append([m[k] for k in ['roc_auc','average_precision','recall','brier']])
        if other is not None: delta.append(average_precision_score(y[idx],p[idx])-average_precision_score(y[idx],np.asarray(other)[idx]))
    ci={k:np.quantile(np.array(values)[:,i],[.025,.975]).tolist() for i,k in enumerate(['roc_auc','average_precision','recall','brier'])}
    if delta: ci['paired_ap_difference']=np.quantile(delta,[.025,.975]).tolist()
    return ci
