"""Deterministic codebook-based cleaning. No learned preprocessing here."""
import hashlib, json, re, shutil, zipfile
import numpy as np
import pandas as pd
from bs4 import BeautifulSoup
from sklearn.model_selection import train_test_split
from .config import DATA, REPORTS, DOWNLOADS, SCHEMAS, SEED

def write_json(path, obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False,default=lambda x: x.item() if hasattr(x,'item') else str(x)),encoding='utf-8')

def target_brfss(a,b):
    """Any affirmative => 1; both explicit no => 0; otherwise unknown."""
    return pd.Series(np.where((a==1)|(b==1),1,np.where((a==2)&(b==2),0,np.nan)),index=a.index)

def clean_brfss(raw):
    out=pd.DataFrame(index=raw.index)
    for field in SCHEMAS['brfss']:
        name=field['name']; src=field['source'].split(' / ')[0]; s=raw[src].copy()
        if field['kind']=='category': s=s.where(s.isin([o['value'] for o in field['options']]))
        elif name=='bmi': s=(s/100).where(s.between(1,9999))
        else: s=s.replace(88,0).where(lambda v:v.between(0,30))
        out[name]=s
    out['target']=target_brfss(raw.CVDINFR4,raw.CVDCRHD4)
    out['weight']=raw['_LLCPWT']; out['state']=raw['_STATE']; out['psu']=raw['_PSU']; out['stratum']=raw['_STSTR']
    out['row_id']=raw.index.astype(str)
    return out

def summary(df,features):
    return {'n':len(df),'positive':int(df.target.sum()),'prevalence':float(df.target.mean()),
      'missing':{c:int(df[c].isna().sum()) for c in features},
      'distributions':{c:{str(k):int(v) for k,v in df[c].value_counts(dropna=False).head(20).items()} for c in features},
      'numeric':df[features].describe().replace({np.nan:None}).to_dict()}

def main():
    manifest=[]
    for name in ['LLCP2023XPT.zip','codebook23_llcp-v2-508 (1).zip','heart+disease.zip']:
        p=DOWNLOADS/name
        if not p.exists(): raise FileNotFoundError(f'Не найден {p}. Задайте CARDIO_DATA_SOURCE.')
        manifest.append({'file':name,'bytes':p.stat().st_size,'sha256':hashlib.file_digest(p.open('rb'),'sha256').hexdigest() if hasattr(hashlib,'file_digest') else hashlib.sha256(p.read_bytes()).hexdigest()})
    write_json(REPORTS/'sources.json',manifest)
    with zipfile.ZipFile(DOWNLOADS/'codebook23_llcp-v2-508 (1).zip') as z:
        html=z.read(z.namelist()[0]); (DATA/'raw'/'codebook.html').write_bytes(html)
        text=re.sub(r'\s+',' ',BeautifulSoup(html.decode('cp1252'),'html.parser').get_text(' ',strip=True))
        names=['CVDINFR4','CVDCRHD4','_MICHD','_LLCPWT','_PSU','_STSTR']+[f['source'].split(' / ')[0] for f in SCHEMAS['brfss']]
        excerpts={}
        for name in names:
            start=text.find('SAS Variable Name: '+name+' ')
            if start<0: raise ValueError('Missing codebook variable '+name)
            end=text.find(' Label:',start)
            excerpts[name]=text[start:end if end>start else start+2000]
        write_json(REPORTS/'codebook_excerpts.json',excerpts)
    rawpath=DATA/'raw'/'LLCP2023.xpt'
    if not rawpath.exists():
        with zipfile.ZipFile(DOWNLOADS/'LLCP2023XPT.zip') as z, z.open(z.namelist()[0]) as src, rawpath.open('wb') as dst: shutil.copyfileobj(src,dst)
    chunks=[]; raw_count=0; raw_columns=0; mismatches=0
    for chunk in pd.read_sas(rawpath,format='xport',chunksize=20000,encoding='utf-8'):
        chunk.index=np.arange(raw_count,raw_count+len(chunk)); raw_count+=len(chunk); raw_columns=len(chunk.columns)
        out=clean_brfss(chunk)
        expected=chunk['_MICHD'].map({1:1,2:0})
        mismatches+=int((out.target.fillna(-1)!=expected.fillna(-1)).sum())
        chunks.append(out)
        print(f'BRFSS read {raw_count}',flush=True)
    full=pd.concat(chunks,ignore_index=True)
    unknown=int(full.target.isna().sum()); full=full.dropna(subset=['target']).reset_index(drop=True)
    full['target']=full.target.astype(int)
    # PSU is a respondent identifier inside a state. Assert before individual splitting.
    duplicates=int(full.duplicated(['state','psu']).sum())
    if duplicates: raise ValueError('Repeated state/PSU: require group split')
    train,test=train_test_split(np.arange(len(full)),test_size=.2,stratify=full.target,random_state=SEED)
    full['split']='train'; full.loc[test,'split']='test'
    full.to_pickle(DATA/'processed'/'brfss.pkl')
    features=[f['name'] for f in SCHEMAS['brfss']]
    audit={'raw_rows':raw_count,'raw_columns':raw_columns,'unknown_target_removed':unknown,'retained':len(full),'target_formula_matches_MICHD':mismatches==0,'target_mismatches':mismatches,'duplicate_respondents':duplicates,'identical_feature_rows_retained':int(full.duplicated(features).sum()),'train_n':len(train),'test_n':len(test),'eda_scope':'training only','training':summary(full.iloc[train],features),'missing_rules':'Per-variable codebook; 88 days -> 0; unknown/refused -> NaN; BMI / 100','target':'Ever reported myocardial infarction OR angina/coronary heart disease; 0 only if both explicitly no'}
    write_json(REPORTS/'brfss_data.json',audit)
    with zipfile.ZipFile(DOWNLOADS/'heart+disease.zip') as z:
        (DATA/'raw'/'uci_description.txt').write_bytes(z.read('heart-disease.names'))
        columns=[f['name'] for f in SCHEMAS['uci']]+['severity']
        frames=[]
        for center,file in [('Cleveland','processed.cleveland.data'),('Hungary','processed.hungarian.data'),('Switzerland','processed.switzerland.data'),('VA','processed.va.data')]:
            a=pd.read_csv(z.open(file),header=None,names=columns,na_values='?'); a['center']=center; frames.append(a)
        all_uci=pd.concat(frames,ignore_index=True); all_uci.to_csv(DATA/'processed'/'uci_centers_audit.csv',index=False)
        uci=frames[0].copy(); uci['target']=(uci.severity>0).astype(int); uci['row_id']=['cleveland_'+str(i) for i in range(len(uci))]
        uci.to_pickle(DATA/'processed'/'uci.pkl')
        features=[f['name'] for f in SCHEMAS['uci']]
        write_json(REPORTS/'uci_data.json',{'raw_rows':len(uci),'retained':len(uci),'centers_audit':{c:{'n':len(g),'missing_fraction':float(g[features].isna().mean().mean())} for c,g in all_uci.groupby('center')},'choice':'Cleveland only: consistent 13 clinical features; other centers retained for missingness audit, not merged','training':summary(uci,features),'eda_scope':'descriptive full Cleveland; fixed a priori feature set; nested CV evaluation','target':'num 1–4 => 1; num 0 => 0'})
    write_json(REPORTS/'schema.json',SCHEMAS)
    print(json.dumps({'BRFSS':audit['retained'],'UCI':len(uci),'MICHD_mismatches':mismatches}),flush=True)

if __name__=='__main__': main()
