"""Run a locked comparison protocol and persist actual outputs."""
import os
os.environ.setdefault('OMP_NUM_THREADS','2')
os.environ.setdefault('OPENBLAS_NUM_THREADS','2')
import json, time, warnings, sqlite3, platform
from datetime import datetime,timezone
import joblib, numpy as np, pandas as pd, sklearn, lightgbm
from sklearn.base import clone
from sklearn.model_selection import train_test_split, StratifiedKFold, RepeatedStratifiedKFold, RandomizedSearchCV, cross_val_score
from sklearn.inspection import permutation_importance
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits
from .config import DATA,REPORTS,MODELS,SEED,SCHEMAS
from .prepare import write_json
from .learning import candidates,metrics,curves,ModelBundle,fit_calibrator,threshold_for_f1,bootstrap,preprocessing

def log(msg): print(datetime.now().strftime('%H:%M:%S'),msg,flush=True)
def sample(df,n):
    if len(df)<=n:return df.copy()
    idx,_=train_test_split(np.arange(len(df)),train_size=n,stratify=df.target,random_state=SEED)
    return df.iloc[idx].copy()
def search(pipe,space,X,y,folds=3,n_iter=3):
    cv=StratifiedKFold(folds,shuffle=True,random_state=SEED)
    base=cross_val_score(clone(pipe),X,y,cv=cv,scoring='average_precision',n_jobs=1)
    if not space:
        pipe.fit(X,y); return pipe,{'base_ap':base.tolist(),'tuned_ap':float(base.mean()),'best_params':{},'trials':[]}
    run=RandomizedSearchCV(pipe,space,n_iter=n_iter,cv=cv,scoring='average_precision',random_state=SEED,n_jobs=1,error_score='raise',return_train_score=True).fit(X,y)
    table=pd.DataFrame(run.cv_results_)[['params','mean_test_score','std_test_score','mean_fit_time','mean_train_score']].to_dict('records')
    return run.best_estimator_,{'base_ap':base.tolist(),'tuned_ap':float(run.best_score_),'best_params':run.best_params_,'trials':table}

def brfss():
    df=pd.read_pickle(DATA/'processed'/'brfss.pkl'); features=[f['name'] for f in SCHEMAS['brfss']]
    dev=df[df.split=='train']; test=df[df.split=='test']
    fit,rest=train_test_split(dev,test_size=.3,stratify=dev.target,random_state=SEED)
    cal,val=train_test_split(rest,test_size=.5,stratify=rest.target,random_state=SEED)
    bench=sample(fit,12000); bench_test=sample(test,12000)
    splits={k:v.row_id.tolist() for k,v in [('fit',fit),('calibration',cal),('validation',val),('test',test),('benchmark_train',bench),('benchmark_test',bench_test)]}
    write_json(REPORTS/'brfss_splits.json',splits)
    protocol={'seed':SEED,'primary_metric':'average_precision','benchmark_train':len(bench),'benchmark_test':len(bench_test),'fit':len(fit),'calibration':len(cal),'validation':len(val),'test':len(test),'cv':'3-fold stratified','search_trials':3,'full_candidates':['Logistic Regression','LightGBM'],'selection':'benchmark: mean inner CV AP; full: validation AP; sigmoid selected by validation Brier; threshold max validation F1','weighting':'primary training and selection unweighted respondent-level; weighted test metrics and separate weighted logistic sensitivity','ci':'200 iid respondent bootstrap, fixed fitted model, not survey-design based','feature_policy':'11 fixed codebook-defined predictors; reduced set excludes subjective health measures and cholesterol'}
    write_json(REPORTS/'protocol.json',protocol)
    fitted={}; compare=[]
    for name,(pipe,space) in candidates('brfss').items():
        log('BRFSS benchmark '+name); start=time.perf_counter()
        model,info=search(pipe,space,bench[features],bench.target)
        elapsed=time.perf_counter()-start; fitted[name]=model
        compare.append({'name':name,'training_n':len(bench),'search_seconds':elapsed,**info})
        write_json(REPORTS/'brfss_search.json',compare)
    benchmark_winner=max([r for r in compare if r['name']!='Dummy'],key=lambda r:r['tuned_ap'])['name']
    full={}; full_rows=[]
    for name in ['Logistic Regression','LightGBM']:
        log('BRFSS full '+name); start=time.perf_counter(); pipe=clone(fitted[name]).fit(fit[features],fit.target)
        cal_model=fit_calibrator(pipe.predict_proba(cal[features])[:,1],cal.target)
        raw=ModelBundle(pipe,features,'brfss',name); calibrated=ModelBundle(pipe,features,'brfss',name,calibrator=cal_model)
        pr=raw.predict_proba(val)[:,1]; pc=calibrated.predict_proba(val)[:,1]
        use=metrics(val.target,pc)['brier']<metrics(val.target,pr)['brier']
        bundle=calibrated if use else raw; pv=pc if use else pr
        bundle.threshold=threshold_for_f1(val.target,pv); full[name]=bundle
        full_rows.append({'name':name,'training_n':len(fit),'fit_seconds':time.perf_counter()-start,'calibrated':bool(use),'threshold':bundle.threshold,'validation':metrics(val.target,pv,bundle.threshold),'raw_validation':metrics(val.target,pr),'sigmoid_validation':metrics(val.target,pc)})
    winner=max(full_rows,key=lambda r:r['validation']['average_precision'])['name']; final=full[winner]
    # Ablations are validation experiments, never chosen after looking at test metrics.
    ablations=[]
    for tag,scale,balanced,weighted,reduced in [('Logistic standard',True,False,False,False),('Logistic balanced',True,True,False,False),('Logistic survey weighted',True,False,True,False),('Logistic without scaling',False,False,False,False),('Logistic reduced features',True,False,False,True)]:
        log('Ablation '+tag); cols=[c for c in features if c not in ['physical_days','mental_days','general_health','cholesterol']] if reduced else features
        pipe=clone(candidates('brfss')['Logistic Regression'][0]); pipe.set_params(pre=preprocessing('brfss',cols,scale),model__class_weight='balanced' if balanced else None)
        kw={'model__sample_weight':fit.weight.to_numpy()/fit.weight.mean()} if weighted else {}
        pipe.fit(fit[cols],fit.target,**kw); p=pipe.predict_proba(val[cols])[:,1]
        ablations.append({'name':tag,'features':len(cols),'training_n':len(fit),**metrics(val.target,p)})
    write_json(REPORTS/'ablations.json',ablations)
    selection={'benchmark_winner':benchmark_winner,'deployed_model':winner,'threshold':final.threshold,'calibration':final.calibrator is not None,'locked_before_test':True,'locked_at':datetime.now(timezone.utc).isoformat()}
    write_json(REPORTS/'selection_lock.json',selection)
    joblib.dump(final,MODELS/'brfss.joblib',compress=3)
    for row in compare:
        log('Benchmark test '+row['name']); model=fitted[row['name']]; start=time.perf_counter(); p=model.predict_proba(bench_test[features])[:,1]
        row.update({'predict_seconds':time.perf_counter()-start,'test_n':len(bench_test),'threshold':.5,'metrics':metrics(bench_test.target,p),'curves':curves(bench_test.target,p)})
    preds={}
    for row in full_rows:
        b=full[row['name']]; start=time.perf_counter(); p=b.predict_proba(test)[:,1]; preds[row['name']]=p
        row.update({'predict_seconds':time.perf_counter()-start,'test_n':len(test),'metrics':metrics(test.target,p,b.threshold),'metrics_at_05':metrics(test.target,p,.5),'survey_weighted':metrics(test.target,p,b.threshold,test.weight),'curves':curves(test.target,p)})
        joblib.dump(b,MODELS/('full_'+row['name'].replace(' ','_')+'.joblib'),compress=3)
    p=preds[winner]; other=preds['LightGBM' if winner=='Logistic Regression' else 'Logistic Regression']
    log('Bootstrap confidence intervals')
    confidence=bootstrap(test.target,p,final.threshold,other)
    subgroups=[]
    for col in ['sex','age_group']:
        for value,g in test.groupby(col):
            ix=test.index.get_indexer(g.index); pp=p[ix]
            if len(g)<100 or g.target.nunique()<2:continue
            subgroups.append({'feature':col,'value':float(value),'n':len(g),'positive':int(g.target.sum()),'metrics':metrics(g.target,pp,final.threshold),'ci':bootstrap(g.target,pp,final.threshold,repeats=100)})
    log('Permutation importance')
    importance_sample=sample(val,2000)
    # scoring callable avoids classifier tags on the deployment wrapper.
    from sklearn.metrics import average_precision_score
    baseline=average_precision_score(importance_sample.target,final.predict_proba(importance_sample)[:,1]); rng=np.random.default_rng(SEED); importance=[]
    for c in features:
        drops=[]
        for _ in range(5):
            changed=importance_sample.copy(); changed[c]=rng.permutation(changed[c].to_numpy()); drops.append(baseline-average_precision_score(changed.target,final.predict_proba(changed)[:,1]))
        importance.append({'feature':c,'mean':float(np.mean(drops)),'std':float(np.std(drops))})
    importance.sort(key=lambda x:x['mean'],reverse=True)
    # Only aggregate results are exposed through the application.
    pd.DataFrame({'row_id':test.row_id,'target':test.target,'probability':p,'weight':test.weight}).to_csv(REPORTS/'brfss_test_predictions.csv',index=False)
    error_examples=[]
    for kind,mask in [('false_positive',(p>=final.threshold)&(test.target.to_numpy()==0)),('false_negative',(p<final.threshold)&(test.target.to_numpy()==1))]:
        ix=np.flatnonzero(mask)
        error_examples.append({'kind':kind,'n':int(len(ix)),'mean_probability':float(p[ix].mean()),'note':'Aggregate error analysis; respondent-level records not displayed'})
    bundle={'dataset':'brfss','benchmark':compare,'full':full_rows,'selection':selection,'confidence':confidence,'subgroups':subgroups,'importance':importance,'ablations':ablations,'protocol':protocol,'errors':error_examples,'threshold_curve':[{'threshold':float(t),**metrics(val.target,final.predict_proba(val)[:,1],float(t))} for t in np.linspace(.02,.6,35)]}
    write_json(REPORTS/'brfss_results.json',bundle)
    background=sample(fit,100)[features]; joblib.dump(background,MODELS/'brfss_background.joblib')
    log('BRFSS complete '+winner)

def uci():
    data=pd.read_pickle(DATA/'processed'/'uci.pkl'); features=[f['name'] for f in SCHEMAS['uci']]; X=data[features]; y=data.target
    outer=RepeatedStratifiedKFold(n_splits=3,n_repeats=2,random_state=SEED)
    fold_indices=list(outer.split(X,y)); rows=[]; all_folds=[]
    for name,(base,space) in candidates('uci').items():
        log('UCI nested CV '+name); fold_metrics=[]; oof=np.zeros((2,len(data))); timings=[]; selected_params=[]
        for i,(tr,te) in enumerate(fold_indices):
            start=time.perf_counter()
            if space:
                run=RandomizedSearchCV(clone(base),space,n_iter=2,cv=StratifiedKFold(3,shuffle=True,random_state=SEED+i),scoring='average_precision',random_state=SEED,n_jobs=1,error_score='raise').fit(X.iloc[tr],y.iloc[tr]); model=run.best_estimator_; selected_params.append(run.best_params_)
            else:model=clone(base).fit(X.iloc[tr],y.iloc[tr])
            p=model.predict_proba(X.iloc[te])[:,1]; oof[i//3,te]=p; m=metrics(y.iloc[te],p); timings.append(time.perf_counter()-start); fold_metrics.append(m)
            all_folds.append({'model':name,'fold':i,'train_ids':data.row_id.iloc[tr].tolist(),'test_ids':data.row_id.iloc[te].tolist(),'metrics':m})
        keys=[k for k in fold_metrics[0] if k!='confusion']
        avg={k:float(np.mean([m[k] for m in fold_metrics])) for k in keys}; std={k:float(np.std([m[k] for m in fold_metrics],ddof=1)) for k in keys}
        mean_p=oof.mean(axis=0)
        row={'name':name,'training_n':'202 per outer fold','test_n':'101 per outer fold','metrics':avg,'std':std,'folds':fold_metrics,'oof_metrics':metrics(y,mean_p),'curves':curves(y,mean_p),'search_seconds':sum(timings),'params':selected_params}
        rows.append(row); write_json(REPORTS/'uci_progress.json',rows)
    winner=max([r for r in rows if r['name']!='Dummy'],key=lambda r:r['metrics']['average_precision'])['name']
    base,space=candidates('uci')[winner]; model,info=search(base,space,X,y,n_iter=3)
    final=ModelBundle(model,features,'uci',winner); joblib.dump(final,MODELS/'uci.joblib',compress=3); joblib.dump(X.sample(80,random_state=SEED),MODELS/'uci_background.joblib')
    write_json(REPORTS/'uci_folds.json',all_folds)
    write_json(REPORTS/'uci_results.json',{'dataset':'uci','benchmark':rows,'selection':{'deployed_model':winner,'threshold':.5,'calibration':'native model or internal SVM sigmoid; no extra calibration'},'protocol':{'outer':'3 folds x 2 repeats','inner':'3 folds, 2 random configurations','primary_metric':'average_precision','ci':'Report fold SD; dependent folds are not independent confidence intervals','selection_caveat':'Each algorithm evaluated by nested CV; selecting winner among algorithms introduces additional selection uncertainty. No independent external test.'},'final_training':info})
    log('UCI complete '+winner)

def main():
    start=time.perf_counter()
    versions={'python':platform.python_version(),'sklearn':sklearn.__version__,'pandas':pd.__version__,'numpy':np.__version__,'lightgbm':lightgbm.__version__,'seed':SEED,'started':datetime.now(timezone.utc).isoformat()}
    write_json(REPORTS/'environment.json',versions)
    with threadpool_limits(limits=2):
        brfss(); uci()
    conn=sqlite3.connect(REPORTS/'experiments.sqlite')
    conn.execute('CREATE TABLE IF NOT EXISTS runs (dataset TEXT PRIMARY KEY, created TEXT, result_json TEXT)')
    for ds in ['brfss','uci']:
        conn.execute('INSERT OR REPLACE INTO runs VALUES (?,?,?)',(ds,datetime.now(timezone.utc).isoformat(),(REPORTS/f'{ds}_results.json').read_text(encoding='utf-8')))
    conn.commit();conn.close()
    from .history import record_results
    record_results(source='training_completion')
    log(f'ALL COMPLETE {time.perf_counter()-start:.1f}s')

if __name__=='__main__': main()
