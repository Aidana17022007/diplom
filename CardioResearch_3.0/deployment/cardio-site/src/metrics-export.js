/** Aggregate-only export: derived outer-CV metrics are averaged within folds. */
export const BASE_METRICS=['roc_auc','average_precision','accuracy','precision','recall','specificity','f1','brier'];
export const DERIVED_METRICS=['balanced_accuracy','mcc','npv','fpr','fnr'];
export const METRICS=[...BASE_METRICS,...DERIVED_METRICS];
export const FIELDS=['dataset','experiment','model','evaluation','training_n','test_n','threshold','threshold_source','weighting','fold_count','base_metrics_method','derived_metrics_method','fold_sd_method',...METRICS,...METRICS.map(key=>key+'_fold_sd'),'procedure_seconds','procedure_definition','predict_seconds'];
const finite=value=>typeof value==='number'&&Number.isFinite(value);
export function metricsFromConfusion(matrix){
 const unavailable=()=>Object.fromEntries(DERIVED_METRICS.map(key=>[key,null]));
 if(!Array.isArray(matrix)||matrix.length!==2||!matrix.every(row=>Array.isArray(row)&&row.length===2))return unavailable();
 const counts=matrix.flat();if(!counts.every(value=>finite(value)&&value>=0))return unavailable();
 const [tn,fp,fn,tp]=counts,n=tn+fp+fn+tp;if(!finite(n)||n<=0)return unavailable();
 const ratio=(a,b)=>b>0?a/b:null,recall=ratio(tp,tp+fn),specificity=ratio(tn,tn+fp);
 const [a,b,c,d]=counts.map(value=>value/n),denominator=Math.sqrt((d+b)*(d+c)*(a+b)*(a+c));
 return {balanced_accuracy:recall===null||specificity===null?null:(recall+specificity)/2,mcc:denominator>0?Math.max(-1,Math.min(1,(a*d-b*c)/denominator)):null,npv:ratio(tn,tn+fn),fpr:ratio(fp,tn+fp),fnr:ratio(fn,tp+fn)};
}
export function exportRows(report,dataset,experiment){
 if(!['brfss','uci'].includes(dataset)||!['benchmark','full'].includes(experiment))throw new Error('Unsupported dataset or experiment');
 return (report[experiment]||[]).map(row=>{
  const isCv=dataset==='uci',folds=Array.isArray(row.folds)?row.folds:[],saved=row.metrics||{};
  const scores=Object.fromEntries(BASE_METRICS.map(key=>[key,finite(saved[key])?saved[key]:null])),std=Object.fromEntries(METRICS.map(key=>[key,null]));let method='unavailable';
  if(isCv){
   for(const key of BASE_METRICS)std[key]=finite(row.std?.[key])&&row.std[key]>=0?row.std[key]:null;
   const derived=folds.map(fold=>metricsFromConfusion(fold?.confusion));if(folds.length)method='mean_of_fold_metrics';
   for(const key of DERIVED_METRICS){const values=derived.map(fold=>fold[key]);if(values.length&&values.every(finite)){const mean=values.reduce((sum,value)=>sum+value,0)/values.length;scores[key]=mean;std[key]=values.length>1?Math.sqrt(values.reduce((sum,value)=>sum+(value-mean)**2,0)/(values.length-1)):null}else scores[key]=null;}
  }else{const derived=metricsFromConfusion(saved.confusion);Object.assign(scores,derived);if(Object.values(derived).some(finite))method='confusion_counts';}
  const evaluation=isCv?(folds.length?`Mean of ${folds.length} outer CV folds; fold SD is not a confidence interval`:'Outer CV; fold details unavailable'):experiment==='full'?'Locked independent test':'Fixed common benchmark test subset';
  const procedure=isCv?'Total outer CV procedure including search, prediction and scoring':experiment==='full'?'Full fit plus calibration and validation procedure':'Base CV plus randomized search and refit';
  const threshold=finite(row.threshold)?row.threshold:null,duration=row.search_seconds??row.fit_seconds;
  return {dataset,experiment,model:row.name??null,evaluation,training_n:row.training_n??null,test_n:row.test_n??null,threshold,threshold_source:threshold===null?'not_recorded_for_row':'saved_row',weighting:'unweighted',fold_count:isCv&&folds.length?folds.length:null,base_metrics_method:isCv?'saved_mean_of_outer_fold_metrics':'saved_single_evaluation',derived_metrics_method:method,fold_sd_method:isCv&&folds.length>1?'sample_ddof_1; descriptive, not confidence interval':null,procedure_seconds:finite(duration)?duration:null,procedure_definition:procedure,predict_seconds:finite(row.predict_seconds)?row.predict_seconds:null,...scores,...Object.fromEntries(METRICS.map(key=>[key+'_fold_sd',std[key]]))};
 });
}
function cell(value){
 if(value==null||typeof value==='number'&&!finite(value))return '';
 let text=String(value);if(typeof value==='string'&&/^(?:[\t\r\n]|\s*[=+\-@])/.test(value))text="'"+text;
 return /[",\r\n]/.test(text)?'"'+text.replaceAll('"','""')+'"':text;
}
export function metricsCSV(report,dataset,experiment){
 const rows=exportRows(report,dataset,experiment);
 return '\uFEFF'+[FIELDS,...rows.map(row=>FIELDS.map(key=>row[key]))].map(row=>row.map(cell).join(',')).join('\r\n')+'\r\n';
}
