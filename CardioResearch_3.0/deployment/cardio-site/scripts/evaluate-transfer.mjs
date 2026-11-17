/** Exploratory, frozen-model transfer audit. Never fits or selects a model.
 * node scripts/evaluate-transfer.mjs --archive C:\diplom\CardioResearch_project.zip
 * Python's standard library reads the archive; no patient-level file is published.
 */
import {readFileSync, writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {basename, dirname, resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {predictProbability} from '../src/inference.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const features = ['age','sex','cp','trestbps','chol','fbs','restecg','thalach','exang','oldpeak','slope','ca','thal'];
const externalCenters = ['Hungary','Switzerland','VA'];
const digest = value => createHash('sha256').update(value).digest('hex');
const ratio = (a,b) => b ? a/b : null;

/** Tied scores are grouped; AP is the non-interpolated, recall-weighted precision. */
export function transferMetrics(targets, probabilities, threshold = 0.5) {
  if (!targets.length || targets.length !== probabilities.length) throw new Error('Non-empty, aligned prediction arrays required');
  if (!Number.isFinite(threshold) || threshold < 0 || threshold > 1) throw new Error('Invalid threshold');
  const rows = targets.map((y,i) => {
    const p = probabilities[i];
    if (![0,1].includes(y) || !Number.isFinite(p) || p < 0 || p > 1) throw new Error('Invalid binary target or probability');
    return {y,p};
  });
  const n = rows.length, positive = targets.reduce((a,b) => a+b,0), negative = n-positive;
  let tn=0,fp=0,fn=0,tp=0,brier=0,probabilitySum=0;
  for (const {y,p} of rows) {
    if (p >= threshold) { if (y) tp++; else fp++; } else { if (y) fn++; else tn++; }
    brier += (p-y)**2; probabilitySum += p;
  }
  rows.sort((a,b) => a.p-b.p);
  let negativesBelow=0, concordance=0, cumulativePositive=0, cumulativeTotal=0, ap=0;
  for (let start=0; start<n;) {
    let end=start, groupPositive=0;
    while (end<n && rows[end].p === rows[start].p) groupPositive += rows[end++].y;
    const groupNegative=end-start-groupPositive;
    concordance += groupPositive*(negativesBelow+groupNegative/2);
    negativesBelow += groupNegative; start=end;
  }
  for (let end=n; end>0;) {
    let start=end-1, groupPositive=0;
    while (start>=0 && rows[start].p === rows[end-1].p) groupPositive += rows[start--].y;
    cumulativeTotal += end-start-1; cumulativePositive += groupPositive;
    if (positive) ap += groupPositive/positive*cumulativePositive/cumulativeTotal;
    end=start+1;
  }
  const recall=ratio(tp,positive), specificity=ratio(tn,negative);
  const mccDenominator=Math.sqrt((tp+fp)*(tp+fn)*(tn+fp)*(tn+fn));
  return {
    n,positive,negative,threshold,prevalence:positive/n,
    roc_auc:positive && negative ? concordance/(positive*negative) : null,
    average_precision:positive ? ap : null,
    brier:brier/n,mean_probability:probabilitySum/n,
    accuracy:(tp+tn)/n,precision:ratio(tp,tp+fp),recall,specificity,
    f1:ratio(2*tp,2*tp+fp+fn),
    balanced_accuracy:recall !== null && specificity !== null ? (recall+specificity)/2 : null,
    mcc:ratio(tp*tn-fp*fn,mccDenominator),
    confusion:[[tn,fp],[fn,tp]],
  };
}

export function parseTransferRows(rawRows) {
  if (!Array.isArray(rawRows) || !rawRows.length) throw new Error('Empty center audit');
  return rawRows.map((raw,index) => {
    if (!['Cleveland',...externalCenters].includes(raw.center)) throw new Error('Unexpected center');
    const severity=Number(raw.severity);
    if (raw.severity === '' || !Number.isInteger(severity) || severity<0 || severity>4) throw new Error('Invalid severity');
    const values=Object.fromEntries(features.map(name => {
      if (!(name in raw)) throw new Error('Missing source feature '+name);
      const text=raw[name], value=text === '' || text === '?' ? null : Number(text);
      if (value !== null && !Number.isFinite(value)) throw new Error('Invalid numeric source value');
      return [name,value];
    }));
    return {center:raw.center,values,target:Number(severity>0),sourceRow:index};
  });
}

const rowSignature = row => JSON.stringify([...features.map(name=>row.values[name]),row.target]);

export function evaluateTransfer(rawRows, models) {
  const model=models.datasets?.uci;
  if (!model || model.name !== 'Random Forest' || model.threshold !== 0.5 || JSON.stringify(model.features)!==JSON.stringify(features)) throw new Error('Expected frozen Cleveland Random Forest and fixed 13-feature schema');
  const rows=parseTransferRows(rawRows);
  const cleveland=rows.filter(row=>row.center==='Cleveland');
  if (cleveland.length!==303) throw new Error('Expected 303 Cleveland training records');
  const trainingSignatures=new Set(cleveland.map(rowSignature));
  const cohorts=externalCenters.map(center => {
    const cohort=rows.filter(row=>row.center===center);
    if (!cohort.length) throw new Error('Missing transfer center');
    const observed=cohort.map(row=>features.filter(name=>row.values[name]!==null).length);
    const probabilities=cohort.map(row=>predictProbability(models,'uci',row.values));
    const targets=cohort.map(row=>row.target);
    const missingness=Object.fromEntries(features.map(name=>{
      const missing=cohort.filter(row=>row.values[name]===null).length;
      return [name,{missing,fraction:missing/cohort.length}];
    }));
    const outsideFormRange=Object.fromEntries(model.schema.filter(field=>field.kind==='number').map(field=>[
      field.name,cohort.filter(row=>row.values[field.name]!==null && (row.values[field.name]<field.min || row.values[field.name]>field.max)).length,
    ]));
    const unknownCategories=Object.fromEntries(model.schema.filter(field=>field.kind==='category').map(field=>[
      field.name,cohort.filter(row=>row.values[field.name]!==null && !field.options.some(option=>option.value===row.values[field.name])).length,
    ]));
    // This fixed completeness cutoff is descriptive; it is not a model/threshold selection rule.
    const eligibleIndices=observed.map((count,index)=>count>=10 ? index : -1).filter(index=>index>=0);
    const metrics=transferMetrics(targets,probabilities,model.threshold);
    return {
      center,n:cohort.length,positive:metrics.positive,prevalence:metrics.prevalence,
      missing_fraction:Object.values(missingness).reduce((sum,item)=>sum+item.missing,0)/(cohort.length*features.length),
      missingness,
      quality:{
        all_features_missing:observed.filter(count=>count===0).length,
        fewer_than_three_observed:observed.filter(count=>count<3).length,
        complete_records:observed.filter(count=>count===features.length).length,
        observed_features_min:Math.min(...observed),observed_features_max:Math.max(...observed),
        outside_interactive_form_ranges:outsideFormRange,unknown_categories:unknownCategories,
        zero_values:{chol:cohort.filter(row=>row.values.chol===0).length,trestbps:cohort.filter(row=>row.values.trestbps===0).length},
        duplicate_feature_target_rows:cohort.length-new Set(cohort.map(rowSignature)).size,
        exact_matches_to_cleveland:cohort.filter(row=>trainingSignatures.has(rowSignature(row))).length,
      },
      metrics,
      eligible_subset:{
        definition:'At least 10 of 13 source features observed; zeros remain observed. Descriptive subset, not a new validation sample.',
        minimum_observed_features:10,n:eligibleIndices.length,excluded:cohort.length-eligibleIndices.length,
        metrics:eligibleIndices.length ? transferMetrics(eligibleIndices.map(i=>targets[i]),eligibleIndices.map(i=>probabilities[i]),model.threshold) : null,
      },
    };
  });
  return {cohorts,training_reference:{center:'Cleveland',n:cleveland.length,positive:cleveland.reduce((sum,row)=>sum+row.target,0),role:'Training only; no in-sample quality score is presented'}};
}

function readSourceArchive(archive, python) {
  const code = `import csv,hashlib,io,json,sys,zipfile
archive=sys.argv[1]
member='CardioResearch/data/processed/uci_centers_audit.csv'
with zipfile.ZipFile(archive) as source:
 raw=source.read(member)
 rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
archive_hasher=hashlib.sha256()
with open(archive,'rb') as handle:
 for chunk in iter(lambda:handle.read(1024*1024),b''): archive_hasher.update(chunk)
archive_sha256=archive_hasher.hexdigest()
print(json.dumps({'rows':rows,'csv_sha256':hashlib.sha256(raw).hexdigest(),'archive_sha256':archive_sha256,'member':member}))`;
  const result=spawnSync(python,['-c',code,archive],{encoding:'utf8',maxBuffer:4*1024*1024,windowsHide:true});
  if (result.error || result.status!==0) throw new Error('Cannot read source archive using Python standard library: '+(result.error?.message || result.stderr));
  return JSON.parse(result.stdout);
}

export function runTransferEvaluation({archive=resolve(root,'../../CardioResearch_project.zip'),python=process.env.CARDIO_PYTHON || 'python',output=resolve(root,'data/transfer.json')}={}) {
  archive=resolve(archive);
  const source=readSourceArchive(archive,python);
  const modelBytes=readFileSync(resolve(root,'data/models.json'));
  const models=JSON.parse(modelBytes), frozenModelHash=digest(modelBytes);
  const evaluation=evaluateTransfer(source.rows,models);
  const report={
    schema_version:1,created:new Date().toISOString(),
    stage:'exploratory_retrospective_cross_center_transfer',
    protocol:{
      frozen_before_evaluation:true,fit_performed:false,selection_changed:false,threshold:0.5,
      task:'Historical UCI heart-disease severity > 0; not prediction of future cardiovascular events.',
      training_center:'Cleveland',evaluation_centers:externalCenters,all_external_records:true,
      preprocessing:'Exactly the fitted Cleveland preprocessing in the exported model. Empty CSV fields become null; numeric medians, category handling and scales are frozen.',
      source_value_policy:'All recorded numeric values, including zeros and values outside interactive form ranges, are preserved and separately counted. No silent recoding or test-driven cleaning.',
      inference_path:'Low-level predictProbability, intentionally bypassing interactive form validation; all source rows are included.',
      weighting:'Unweighted records, reported separately by center. No pooled headline score.',
      intervals:'Not calculated. Small center samples and repeated or unidentified records limit precision.',
      metric_definitions:{roc_auc:'Mann–Whitney pair concordance, half-credit for ties',average_precision:'Non-interpolated precision weighted by positive-recall increments, grouping tied scores',balanced_accuracy:'Mean sensitivity and specificity',undefined_metric:'null when a required class or denominator is absent',confusion:'[[true negative,false positive],[false negative,true positive]]'},
    },
    provenance:{
      source_archive:basename(archive),source_archive_sha256:source.archive_sha256,
      source_member:source.member,source_csv_sha256:source.csv_sha256,
      model_file:'data/models.json',model_file_sha256:frozenModelHash,
      model_version:models.datasets.uci.version,
      reproduction_command:'node scripts/evaluate-transfer.mjs --archive "../../'+basename(archive)+'"',
      original_training_source:'cardio/train.py:uci reads data/processed/uci.pkl; cardio/prepare.py creates that file from Cleveland only. Other centers were retained for an earlier missingness audit.',
      runtime:{node:process.version,platform:process.platform,arch:process.arch},
    },
    model:{dataset:'uci',name:models.datasets.uci.name,version:models.datasets.uci.version,threshold:models.datasets.uci.threshold,features},
    ...evaluation,
    limitations:[
      'Exploratory retrospective transfer audit of historical public datasets, not independent clinical validation, deployment approval, or evidence for Kazakhstan.',
      'Other centers were already inspected for missingness before this analysis; this is not a preregistered external evaluation.',
      'Severe feature missingness, recorded zero cholesterol and differences in case mix may invalidate interpretation of individual probabilities.',
      'No center-specific fitting, imputation, calibration, threshold adjustment or model selection was performed.',
      'The source has no stable cross-center patient identifiers. Exact duplicate checks cannot establish independent patients; duplicate records are retained and counted.',
      'The completeness subset can change case mix and is descriptive only. Apparent performance differences are not evidence of model improvement.',
      'Cleveland nested-CV and BRFSS results remain separate experiments and must not be pooled with these center estimates.',
    ],
    sources:[{title:'UCI Heart Disease dataset',url:'https://archive.ics.uci.edu/dataset/45/heart+disease'}],
  };
  if (digest(readFileSync(resolve(root,'data/models.json')))!==frozenModelHash) throw new Error('Model changed during evaluation');
  writeFileSync(output,JSON.stringify(report,null,2)+'\n');
  return report;
}

if (process.argv[1] && import.meta.url===pathToFileURL(resolve(process.argv[1])).href) {
  const args=process.argv.slice(2), options={};
  for (let i=0;i<args.length;i+=2) {
    if (!['--archive','--python','--output'].includes(args[i]) || !args[i+1]) throw new Error('Usage: node scripts/evaluate-transfer.mjs [--archive ZIP] [--python EXE] [--output JSON]');
    options[args[i].slice(2)]=args[i+1];
  }
  const report=runTransferEvaluation(options);
  console.log(JSON.stringify({stage:report.stage,model_version:report.model.version,cohorts:report.cohorts.map(({center,n,metrics})=>({center,n,roc_auc:metrics.roc_auc,average_precision:metrics.average_precision,brier:metrics.brier}))},null,2));
}
